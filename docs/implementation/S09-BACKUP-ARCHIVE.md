# S09 — Recovery copy and export archive (format v1)

**Status:** host-implemented in `services/volume/src/archive.rs`, tested in
`services/volume/tests/archive.rs`; a native fixture portal passes the local
QEMU gate (see "Native slice"). No user-chosen target, no user task, no
physical disk. S09 remains open.

## Goal and invariant

A user can make an **independent copy** of one document domain that
is verifiable and restorable without the source volume, source service or source disk.

- **Export** is a consistent snapshot: no archive is finalized if the domain
  changes during the export (`Stale`), if the target becomes full or gives an I/O error
  (error from the sink), or if read content deviates from the service's own
  content checksum (`Corrupt`). After an error the output is invalid, and
  `verify` refuses it.
- **Verify** has no side effects and accepts only a complete, canonical archive.
- **Restore** never overwrites anything. An occupied target slot or an already used name
  is reported as a conflict and stays untouched. A target collection with
  a different name is never renamed; the object then ends up outside a collection
  (`uncollected`). Each object is committed only after its record and content
  have been checked. Because the trailer only comes after the last object, a
  portal must **first run `verify` on the same bytes**. Without verify,
  on truncation only the earlier, fully checked objects may have been
  restored; the `Report` names those exactly.
- A write with outcome `Unknown` counts as restored only if `stat` shows exactly
  the expected revision, name, length and content checksum; otherwise restore stops with
  `Unknown`. If setting tags, kind or collection fails after a successful write,
  the object is in `restored` and in `bare`, and restore stops with that error.
- Restore assumes there is one writer on the target domain during the restore. A concurrent
  slot change aborts with `Stale`; a concurrently created identical name
  is not detected (the volume does not enforce unique names).
- A deleted target slot (tombstone) is filled. The kept history of that
  slot remains and can later be retrieved via local history; no
  data is lost, but local undo of that slot then shows older, different content.

## Bytes (little-endian)

| Part | Size | Content |
|---|---|---|
| Header | 64 | `NOSBAK\0\x01`, version u16=1, 2×0, number of objects u8 (≤8), number of collections u8 (≤4), 2×0, source generation u64, total content u64, 24×0, FNV-64 over bytes 0..56 |
| Collection record | 48 | index u8 (1..4, strictly ascending), name length u8, 6×0, name[32] (padding 0), FNV-64 over 0..40 |
| Object record | 96 | slot u8 (0..7, strictly ascending), name length u8, collection u8 (0 or present), 0, kind u16, 2×0, tags u32, length u32 (≤64 KiB), source revision u64 (≠0), created u64, modified u64, content FNV-64, name[32] (padding 0), 8×0, FNV-64 over 0..88 |
| Content | length | raw document bytes directly after its own record |
| Trailer | 16 | `NOSBAKZ\0`, FNV-64 over all preceding bytes |

After the trailer the stream must end. Names follow `valid_name` (UTF-8,
1–32 bytes, no `.`/`..`). Duplicate names are allowed, just as in the volume
itself. A source that reports more
bytes than were requested yields `Protocol`; any other deviation yields `Corrupt`.

## What is deliberately not in v1

- **No authenticity or encryption.** FNV-64 only catches accidental
  corruption, truncation and torn transfers, not deliberate tampering. The archive
  is plaintext personal data. It may only go to a target chosen by the user
  that is their own (LOCAL-PRIVACY-CONTRACT: own offline recovery copy). For a NAS or a
  provider client-side encryption is needed (B02, P01, ENCRYPTED-OBJECT-STORAGE);
  that is still open here.
- **Current versions only.** Local history is not a backup and is not
  included. `created`/`modified` are kept and are exportable,
  but on restore the service assigns new times.
- **One domain per archive**, within the current volume limits (8 objects,
  64 KiB per object, 4 collections).

## Evidence and open points

Host evidence (gnu host target, Rust 1.90.0, access via the real volume client and service):
round trip after loss of the source and cold restart of the target; every prefix, every
bit flip (bits 0x01 and 0x80 on every byte) and an extra byte are refused;
a too-high source count gives `Protocol`, also at the EOF check after the trailer;
a full target at 132 failing boundaries (every 37th byte and the last byte) and success
at exactly the archive size; concurrent change of a listed object and
of a new object; content that contradicts the service checksum; conflicts without
overwriting; quota during restore; invalid domain. Of 13 mutation trials,
11 make a test fail (name conflict, EOF, both `Protocol` checks, generation,
content checksum on export and on `Unknown`, collection mapping, `bare`, revision 0,
name padding); see the evidence file. Resealed, non-canonical records
(20 cases) are refused; `Unknown` (landed/not landed, and landed with a
different content checksum), failed META, a tombstone slot and duplicate source names are
tested. Not covered by a test: omitting the revision comparison on
`Unknown` (a revision that is one too far is caught) and the length check
list/stat on export (only relevant if another writer or the service itself
deviates).

Open for S09/FR-O06: native backup portal with a target volume and capability
chosen by the user, native QEMU trial with a second virtual disk,
user export to common formats (e.g. plain text/image per
document), encrypted variant for NAS/provider, and a user task.

## Native slice — local QEMU gate passes (13 November 2026, branch `feat/s09-native-archive`)

**Status:** implemented and locally gate-tested; S09 stays **open** (see
"Still open"). Evidence: [verification/s09-archive/NATIVE-20261113.md](../verification/s09-archive/NATIVE-20261113.md).

**Range adapters (host-tested).** `archive::DiskSink` and `archive::DiskSource`
store an archive from sector 0 of a dedicated raw block range. No extra
framing: the length follows from the header counts (bounded by the range,
otherwise `Corrupt`) and `verify` remains the only acceptance gate. The native
block adapter is shared by service and portal in `volume-docs/src/disk.rs`.

**Kernel fixture profile** (`kernel/src/m2/m3/volume.rs`, features
`test-volume-archive-export|restore|corrupt|conflict|full`, cases 7–11):
- Slot 1 is the backup portal. It alone receives a block capability on device
  0, sectors 1000..2040 of the disposable test image, disjoint from the volume
  scope 4..584 (compile-time assertion). The range ends below the 2048-sector
  image, so the portal's past-the-end probe is refused by the capability
  scope rather than by the device size; the largest v1 archive (525 328 bytes,
  1027 sectors) fits. Export grants READ|WRITE|FLUSH; restore, corrupt and
  conflict grant READ only (`ARCHIVE_READONLY_RIGHTS`). The full-target case
  grants READ|WRITE|FLUSH on only the first 100 sectors of the range. The handle is startup word 504.
  No handle enumeration exists, so the manifest counts instead: it fails with
  `ARCHIVE_ESCAPE` unless the grant adds exactly one block object, node and
  handle, that handle is held by slot 1, the service and slot 2 hold exactly
  as many handles as before, and the service's own block handle resolves to a
  different object key. Service and slot 2 keep their earlier authority.
- During export (cases 7 and 11) the device stays writable but the volume service receives
  READ only (`service_read_only`), so every write and flush goes to the archive.
- Archive I/O is counted per capability object at publication and kept out of
  the volume table/data write classification. `finish` fails with
  `ARCHIVE_IO` unless every export write and flush went through the archive
  object and the portal read the archive back through it, and restore,
  corrupt and conflict only read it. In the full-target case it requires as many
  archive writes as the cut scope has sectors (100), no flush and at least one
  archive read. The portal's `verify` reads only the header sector and refuses
  it at the length bound, so the contents of the 100 sectors are checked by
  the host oracle alone. Evidence lines
  `VOLUME:ARCHIVE:READS|WRITES|FLUSHES`; markers
  `VOLUME:CASE:ARCHIVE_EXPORT|ARCHIVE_RESTORE|ARCHIVE_CORRUPT|ARCHIVE_CONFLICT|ARCHIVE_FULL:PASS`.
- Calls on the portal's own archive object (pending collects, the scope
  probe) are not counted as app device denials; every app's own-handle and
  forged-handle probes still are, and each app must show at least one.

**Portal app.** `volume-app` built with feature `archive-portal` (separate
target directory `volume-docs-portal`; the normal build would exceed the
64 KiB startup text boundary with both paths). The archive cases use the
normal `volume-service` build unchanged. The 64 KiB archive scratch is the
private RW/NX heap the kernel premaps at `0x6000_0000`. Restore, corrupt and
conflict share one flow: `verify` the whole archive, then `restore`. Corrupt must stop
at `verify` with `Corrupt`, and the volume must stay empty.

**Serialization.** The broker serves one block request at a time and answers
others with Busy. The portal therefore reaches a READY service before its
first archive read, and slot 2 waits for kernel gate 2 (portal phase 2) before
using the service. The first gate run that reached the corrupt stage
without this ordering (run 2) failed it with a Busy status instead of
`Corrupt` (step 740).

**Runner stages** (`tools/run_volume.py`, plan of `tools/test_volume.py`, now
14 QEMU runs): `archive-export` on the image left by `recover` (volume mounted
read-only, every byte outside the archive range unchanged, zero padding, no
write past the archive, writes = ⌈length/512⌉); `archive-restore` and
`archive-corrupt` on a fresh image that holds only the copied archive range
(source loss); corrupt flips one byte at `length // 2`. The independent reader
`tools/volume_archive.py` parses every guest-written archive and must refuse
the damaged one. Restored objects are compared byte for byte with the archive
through `volume_disk.analyse(..., opaque=...)` (revision 1, or 2 after
metadata), and the guest digests must equal the oracle digests. Export also
compares each object's created and modified times with the volume; restore
expects only the collections a restored object refers to, because restore
creates no unreferenced collection. The archive
header carries LIST's domain generation (sum of the domain's object and
collection revisions), not the global volume generation.

`archive-conflict` restores the same archive into a fresh image whose domain
already holds two written objects and two collections: one object occupies an
archived slot, the other carries the name of another archived object;
collection 1 has the archived name, collection 2 another name. The expected end
state comes from `volume_archive.expected_restore`, which follows the restore
rule above and shares no code with `volume-core`. The stage requires at least
one slot conflict, name conflict, uncollected object and reused collection.
Both conflicting archived objects stay unrestored, the pre-existing objects
stay at revision 1, collection 2 is not renamed, and the archived object that
referred to it is restored outside a collection. The conflict and plain restore
oracles each refuse the other stage's after-image. Two more rules are host tests
in `services/volume/tests/archive.rs`. No collection is created for a
conflicting object: with only two collected objects in the archive, this
cannot hold together with the four rules above. An uncollected object without
other metadata stays at revision 1: this fixture does not exercise it,
because its uncollected object has a kind.

`archive-full` exports the recovered fixture into a target too small for it.
Its image is the export stage's input again: the export stage's output with
the archive range set back to its canaries, byte-identical to that input.
The portal's scope covers 100 sectors; the archive needs 180. The spec
requires that a full target leaves no finalized archive and that `verify`
refuses it. The portal must receive `Full` from `export` and does not finish
the sink, so nothing is padded or flushed; the kernel refuses a write at
sector 100; `verify` refuses the range with `Corrupt`; the volume still lists
its objects and refuses a document write. The runner requires that the 100
sectors equal the prefix of the export stage's archive, that no other sector
changed, that the independent reader refuses both the cut range and the full
archive range, and that the volume oracle still sees the recovered fixture.
A `volume-core` host test adds the two ways a target can be too small (only
the buffered last sector missing, where `finish` reports `Full`, and a
stream that runs out mid-way) and shows that a later export over the
leftover verifies. Limit: the stage starts from a range without an earlier
archive. It does not show that a failed export invalidates an older archive
already in the range; an older archive whose leading sectors equal the new
stream would still verify as that older archive.

## User export to ustar (proposed format, host-tested, 13 November 2026)

**Status:** proposed for confirmation by the project owner (D6 in
[S09-BACKUP-DESTINATION-PROPOSAL.md](S09-BACKUP-DESTINATION-PROPOSAL.md));
host-tested only. It changes no capability. It has no native stage, because
writing it out needs a destination (D1).

`ustar::from_archive` converts a format-v1 archive into a POSIX.1-1988 ustar
stream, with POSIX.1-2001 pax `path` records for names that are not ASCII.
It is meant for common tar readers outside Baryon OS; the readers tested are
Python's `tarfile` module and GNU tar 1.35.
- **Layout.** Per object, in slot order, one regular file holding its bytes
  as stored: `<collection>/<name>` for a collected object, `<name>` otherwise.
  There are no directory entries, so an empty collection is not exported.
  A path is at most 65 bytes and fits the 100-byte ustar name field; a
  compile-time assertion pins this.
- **Fixed fields.** Mode 0644, uid and gid 0, empty owner names and mtime 0.
  Object times are a per-domain logical clock, not wall-clock time. Equal
  archives give equal bytes.
- **Lossy by design.** Kind, tags, revisions, times, slots and collection
  indices are dropped. The export is for other systems, not a recovery copy,
  and nothing restores from it. Content is not converted: the volume has no
  registry of kinds, so a document is exported as the bytes it holds.
- **Refusals.** These give `Invalid`, and nothing is renamed:
  - two objects with one path;
  - an uncollected object whose name equals a declared collection's name (a
    file and a directory at one path). This conservative rule also refuses
    the export when that collection is empty, although an empty collection
    gets no directory;
  - a path whose first character, of any kind, is followed by `:`. The Windows
    path parser takes any single UTF-16 code unit followed by `:` as a drive,
    not only A–Z. Such a drive exists only once it is created, for example
    with `subst` (`+:`, `€:`); File Explorer and PowerShell do not accept it
    ([R. Liptak, "Windows drive letters are not limited to A-Z"](https://www.ryanliptak.com/blog/windows-drive-letters-are-not-limited-to-a-z/)).
    Where it exists, such a path can leave the extraction directory. Python's
    `ntpath` takes any one character there as a drive, also one outside the
    Basic Multilingual Plane, which Win32 does not; the rule refuses both.
    Extraction on Windows was not tested. A later `:` is kept.
- **Order of checks.** Each file is written while `archive::walk` checks its
  object. The two end-of-archive blocks are written only after the trailer and
  the end of the stream have been checked. Python's `tarfile` reads a stream
  without those blocks without an error (tested), so the caller verifies the
  same bytes first and discards the output on any error, as for restore.
- **Names.** Object and collection names are UTF-8. They hold no control
  characters (Unicode category Cc), no `/` or `\`, and none of the
  bidirectional embedding, override and isolate controls U+202A–U+202E and
  U+2066–U+2069; they are never `.` or `..`. A path therefore stays inside
  the extraction directory on POSIX systems, and the drive rule above covers
  the Windows drive form, including drives that are not a letter.
  Bidirectional marks such as U+200E, U+200F and U+061C are allowed.
- **Not handled (extraction elsewhere).** The following names export
  unchanged, but extract differently. Whether the export should refuse them
  is part of D6.
  - On Windows, a later `:` names an alternate data stream.
  - On Windows, the reserved device names (for example `NUL`) and names with
    trailing dots or spaces are altered or lost.
  - On Windows, other characters that it forbids, such as `?`, are not
    accepted.
  - Names that differ only in case, or only in Unicode normalisation (NFC
    against NFD), collide on case-insensitive or normalisation-insensitive file
    systems such as default macOS and Windows volumes. One file then
    overwrites the other.

**Evidence (host).** Three `volume-core` tests in
`services/volume/tests/archive.rs`. The reader test needs `python3` and `tar`,
and the end-block test needs `python3`; each fails when its tool is missing. The
refusal test starts no external tool:
- Python's standard `tarfile` module is the independent reader. It reads an
  export that contains a collection, a multi-chunk object, an empty object and
  the name `Notitie ✓`. Names, the pax `path` record, type, size, mode, mtime,
  uid, gid and content all match. The system tar (GNU tar 1.35 locally)
  extracts the same stream into a fresh directory with byte-identical files,
  and a second conversion gives equal bytes.
- An archive with a flipped trailer byte gives `Corrupt`. The output then
  lacks exactly the two end-of-archive blocks, and `tarfile` still reads its
  three files without an error.
- Resealed archives that `verify` accepts give `Invalid` when their paths
  collide or take the drive form: uncollected `C:x`, `1:x`, `é:x` and
  `😀:x`, and a collection named `C:`. A name with a later colon,
  `Plan:2`, is still exported.

Nine mutants of the converter were each killed: no pax record, no
file/directory check, no duplicate check, no drive check, a drive check for
ASCII letters only, a checksum off by one, mode 0600, end blocks before the
trailer check, and no content padding.
Not checked: bsdtar and Windows `tar` as readers, extraction on Windows or
macOS, and a native stage.

**Still open for S09:** a user-chosen target behind its own capability (not a
fixture range on the same disk); confirmation of the proposed ustar export
(D6) and a native stage that writes it out; the encrypted NAS/provider variant; a user-facing task;
a second simultaneously attached disk (archive and volume
share one virtual device here). Plaintext archives are used only on
harness-assigned local test images. The destination and its capability
are put to the project owner as a decision proposal, not a contract:
[S09-BACKUP-DESTINATION-PROPOSAL.md](S09-BACKUP-DESTINATION-PROPOSAL.md).
