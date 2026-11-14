//! S09 user export (proposed format, host-tested): turn a format-v1 archive
//! into a POSIX ustar stream for common tar readers outside Baryon OS. Spec:
//! `docs/implementation/S09-BACKUP-ARCHIVE.md`, "User export to ustar".
//!
//! Per object, in slot order, one regular file `<collection>/<name>` or
//! `<name>` holding its bytes as stored. A path that is not ASCII is preceded
//! by a pax `path` record (UTF-8). No directory entries: empty collections
//! are not exported. Lossy by design: kind, tags, revisions, times and slots
//! are dropped, so this is an export for other systems, not a recovery copy,
//! and nothing restores from it. Mode 0644, uid/gid 0 and mtime 0 (object
//! times are a per-domain logical clock), so equal archives give equal bytes.
use crate::archive::{walk, Collections, Entry, Sink, Source, Summary};
use crate::{Status, COLLECTIONS, MAX_LENGTH, NAME, PER_DOMAIN};

pub const BLOCK: usize = 512;
const PATH: usize = 2 * NAME + 1;
// shortcut: every path fits the 100-byte ustar name field, so there is no prefix or long-name handling; upgrade when NAME grows.
const _: () = assert!(PATH <= 100);
// A pax record "NN path=<path>\n" is `path + 9` bytes, which keeps NN two digits.
const _: () = assert!(PATH + 9 <= 99);
const ZERO: [u8; BLOCK] = [0; BLOCK];

/// Convert an archive. The caller must `archive::verify` the same bytes
/// first: files are written while the walk checks each object and the
/// trailer is checked last. The two end-of-archive blocks are written only
/// after the whole archive checked out; on any error the bytes already
/// written are not an export and must be discarded. Two objects with one
/// path, an uncollected object named like a declared collection (a file and
/// a directory at one path; also refused when that collection is empty), or a
/// path whose first character, of any kind, is followed by `:` (Windows reads
/// it as a drive, outside the extraction directory) give `Invalid`; nothing is
/// renamed.
pub fn from_archive<S: Source, K: Sink>(
    source: &mut S,
    scratch: &mut [u8; MAX_LENGTH],
    sink: &mut K,
) -> Result<Summary, Status> {
    let mut seen = [([0; PATH], 0); PER_DOMAIN];
    let mut count = 0;
    let summary = walk(source, scratch, |entry, collections, content| {
        let (buffer, length) = path(entry, collections)?;
        let path = &buffer[..length];
        if seen[..count].iter().any(|(p, l)| &p[..*l] == path) {
            return Err(Status::Invalid);
        }
        seen[count] = (buffer, length);
        count += 1;
        if !path.is_ascii() {
            let size = length + 9;
            let mut record = [0; PATH + 9];
            record[0] = b'0' + (size / 10) as u8;
            record[1] = b'0' + (size % 10) as u8;
            record[2..8].copy_from_slice(b" path=");
            record[8..8 + length].copy_from_slice(path);
            record[8 + length] = b'\n';
            header(sink, b"PaxHeader", b'x', size)?;
            sink.put(&record[..size])?;
            sink.put(&ZERO[..BLOCK - size])?;
        }
        header(sink, path, b'0', content.len())?;
        sink.put(content)?;
        sink.put(&ZERO[..(BLOCK - content.len() % BLOCK) % BLOCK])
    })?;
    sink.put(&ZERO)?;
    sink.put(&ZERO)?;
    Ok(summary)
}

fn path(entry: &Entry, collections: &Collections) -> Result<([u8; PATH], usize), Status> {
    let name = entry.name();
    let mut out = [0; PATH];
    let mut length = 0;
    if entry.collection == 0 {
        if (1..=COLLECTIONS).any(|i| collections.present[i - 1] && collections.name(i) == name) {
            return Err(Status::Invalid);
        }
    } else {
        let directory = collections.name(usize::from(entry.collection));
        out[..directory.len()].copy_from_slice(directory);
        out[directory.len()] = b'/';
        length = directory.len() + 1;
    }
    out[length..length + name.len()].copy_from_slice(name);
    length += name.len();
    // Windows takes any UTF-16 unit before ':' as a drive (not only A-Z), ntpath any char.
    let mut chars = core::str::from_utf8(&out[..length])
        .map_err(|_| Status::Invalid)?
        .chars();
    chars.next();
    if chars.next() == Some(':') {
        return Err(Status::Invalid);
    }
    Ok((out, length))
}

fn header<K: Sink>(sink: &mut K, name: &[u8], kind: u8, size: usize) -> Result<(), Status> {
    let mut block = [0; BLOCK];
    block[..name.len()].copy_from_slice(name);
    octal(&mut block[100..108], 0o644);
    octal(&mut block[108..116], 0);
    octal(&mut block[116..124], 0);
    octal(&mut block[124..136], size as u32);
    octal(&mut block[136..148], 0);
    block[148..156].fill(b' ');
    block[156] = kind;
    block[257..263].copy_from_slice(b"ustar\0");
    block[263..265].copy_from_slice(b"00");
    let sum = block.iter().map(|&byte| u32::from(byte)).sum();
    octal(&mut block[148..155], sum);
    sink.put(&block)
}

/// Zero-padded octal digits followed by NUL. Callers keep values in range:
/// sizes are at most MAX_LENGTH and a header sum is at most 512 * 255.
fn octal(field: &mut [u8], mut value: u32) {
    let digits = field.len() - 1;
    for digit in field[..digits].iter_mut().rev() {
        *digit = b'0' + (value & 7) as u8;
        value >>= 3;
    }
    field[digits] = 0;
}
