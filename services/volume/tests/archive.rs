//! Host-only S09 archive tests: export, verify and restore through the real
//! volume protocol, including corruption, truncation, full destinations,
//! conflicts, concurrent change and source loss.
mod common;

use common::{fill, pattern, recover, Local, SimDisk};
use volume_core::{
    archive::{self, DiskSink, DiskSource, Report, Sink, Source, HEADER, OBJECT_RECORD, TRAILER},
    checksum_update,
    client::{Client, Stat, Transport},
    service::Service,
    table::Table,
    ustar, wire, Disk, Status, CHUNK, FNV_OFFSET, MAX_LENGTH, SECTOR,
};

const EPOCH: u64 = 4;

struct Bytes(Vec<u8>);
impl Sink for Bytes {
    fn put(&mut self, bytes: &[u8]) -> Result<(), Status> {
        self.0.extend_from_slice(bytes);
        Ok(())
    }
}

/// A destination that accepts at most `room` bytes, like a full disk.
struct Limited {
    room: usize,
    used: usize,
}
impl Sink for Limited {
    fn put(&mut self, bytes: &[u8]) -> Result<(), Status> {
        if self.used + bytes.len() > self.room {
            return Err(Status::Full);
        }
        self.used += bytes.len();
        Ok(())
    }
}

/// Serves the archive in uneven pieces to exercise reassembly.
struct Reader<'a> {
    bytes: &'a [u8],
    at: usize,
}
impl Source for Reader<'_> {
    fn get(&mut self, buffer: &mut [u8]) -> Result<usize, Status> {
        let amount = buffer.len().min(self.bytes.len() - self.at).min(77);
        buffer[..amount].copy_from_slice(&self.bytes[self.at..self.at + amount]);
        self.at += amount;
        Ok(amount)
    }
}
fn reader(bytes: &[u8]) -> Reader<'_> {
    Reader { bytes, at: 0 }
}

fn client<'a>(service: &'a mut Service, disk: &'a mut SimDisk, domain: usize) -> Client<Local<'a>> {
    Client::new(
        Local {
            service,
            disk,
            domain,
        },
        EPOCH,
        100 + 1000 * domain as u64,
    )
}

fn content<T: Transport>(c: &mut Client<T>, object: u64) -> (Stat, Vec<u8>) {
    let stat = c.stat(object).unwrap();
    let mut bytes = vec![0; stat.length];
    c.read(object, stat.revision, stat.length, |offset, chunk| {
        bytes[offset..offset + chunk.len()].copy_from_slice(chunk)
    })
    .unwrap();
    (stat, bytes)
}

fn expected(object: u64, revision: u64, length: usize) -> Vec<u8> {
    (0..length)
        .map(|offset| pattern(object, revision, offset))
        .collect()
}

fn scratch() -> Box<[u8; MAX_LENGTH]> {
    Box::new([0; MAX_LENGTH])
}

/// Domain 0: "Notes" (collection 1 "Werk", tags/kind), "Plan" (two
/// revisions, multi-chunk), "Empty" (zero length) at slot 5.
fn populate<T: Transport>(c: &mut Client<T>, big: usize) {
    c.collection(0, 1, 0, b"Werk").unwrap();
    let r = c.write(0, 0, b"Notes", 300, fill(0, 1)).unwrap().0;
    c.meta(0, r, 0x55, 7, 1).unwrap();
    c.write(1, 0, b"Plan", 40, fill(1, 1)).unwrap();
    c.write(1, 1, b"Plan", big, fill(1, 2)).unwrap();
    c.write(5, 0, b"Empty", 0, fill(5, 1)).unwrap();
}

fn exported(big: usize) -> Vec<u8> {
    let mut disk = SimDisk::new();
    let mut service = Service::new(EPOCH, Table::EMPTY, false);
    let mut source = client(&mut service, &mut disk, 0);
    populate(&mut source, big);
    let mut out = Bytes(Vec::new());
    let summary = archive::export(&mut source, 0, &mut out).unwrap();
    assert_eq!(
        (summary.objects, summary.collections, summary.content_bytes),
        (3, 1, 300 + big as u64)
    );
    out.0
}

#[test]
fn restore_after_source_loss_and_cold_recovery() {
    let big = 2 * CHUNK + 173;
    let bytes = exported(big); // source service and disk are gone here
    let summary = archive::verify(&mut reader(&bytes), &mut scratch()).unwrap();
    assert_eq!(summary.objects, 3);

    let durable = {
        let mut disk = SimDisk::new();
        let mut service = Service::new(EPOCH, Table::EMPTY, false);
        let mut destination = client(&mut service, &mut disk, 1);
        let report =
            archive::restore(&mut reader(&bytes), &mut scratch(), &mut destination, 1).unwrap();
        assert_eq!(
            report,
            Report {
                restored: 0b10_0011,
                conflicts: 0,
                uncollected: 0,
                bare: 0
            }
        );
        assert!(disk.pending.is_empty());
        disk.durable.clone()
    };
    let table = recover(durable.clone()).unwrap();
    let mut disk = SimDisk::from_image(durable);
    let mut service = Service::new(EPOCH + 1, table, true);
    let mut destination = Client::new(
        Local {
            service: &mut service,
            disk: &mut disk,
            domain: 1,
        },
        EPOCH + 1,
        1,
    );
    let (notes, data) = content(&mut destination, 8);
    assert_eq!(&notes.name[..notes.name_length], b"Notes");
    assert_eq!((notes.tags, notes.kind, notes.collection), (0x55, 7, 1));
    assert_eq!(data, expected(0, 1, 300));
    assert_eq!(destination.collection_stat(1, 1).unwrap().name(), b"Werk");
    let (plan, data) = content(&mut destination, 9);
    assert_eq!(&plan.name[..plan.name_length], b"Plan");
    assert_eq!(data, expected(1, 2, big));
    assert_eq!(plan.history_count, 0, "history is not part of an archive");
    let (empty, data) = content(&mut destination, 13);
    assert_eq!(
        (&empty.name[..empty.name_length], data.len()),
        (&b"Empty"[..], 0)
    );
    assert_eq!(destination.stat(10).unwrap_err().0, Status::NotFound);
}

#[test]
fn every_truncation_flip_and_trailing_byte_is_rejected() {
    let bytes = exported(500);
    let mut scratch = scratch();
    assert!(archive::verify(&mut reader(&bytes), &mut scratch).is_ok());
    for length in 0..bytes.len() {
        assert_eq!(
            archive::verify(&mut reader(&bytes[..length]), &mut scratch),
            Err(Status::Corrupt),
            "prefix {length}"
        );
    }
    for at in 0..bytes.len() {
        for bit in [0x01, 0x80] {
            let mut damaged = bytes.clone();
            damaged[at] ^= bit;
            assert_eq!(
                archive::verify(&mut reader(&damaged), &mut scratch),
                Err(Status::Corrupt),
                "byte {at} bit {bit:#x}"
            );
        }
    }
    let mut longer = bytes.clone();
    longer.push(0);
    assert_eq!(
        archive::verify(&mut reader(&longer), &mut scratch),
        Err(Status::Corrupt)
    );
}

#[test]
fn overlong_source_count_is_a_protocol_error() {
    struct Liar;
    impl Source for Liar {
        fn get(&mut self, buffer: &mut [u8]) -> Result<usize, Status> {
            Ok(buffer.len() + 1)
        }
    }
    assert_eq!(
        archive::verify(&mut Liar, &mut scratch()),
        Err(Status::Protocol)
    );
}

#[test]
fn overlong_count_at_end_of_stream_is_a_protocol_error() {
    /// Serves a valid archive, then claims 2 bytes for the 1-byte EOF probe.
    struct LiarAtEnd<'a>(Reader<'a>);
    impl Source for LiarAtEnd<'_> {
        fn get(&mut self, buffer: &mut [u8]) -> Result<usize, Status> {
            if self.0.at == self.0.bytes.len() {
                return Ok(buffer.len() + 1);
            }
            self.0.get(buffer)
        }
    }
    let bytes = exported(500);
    assert_eq!(
        archive::verify(&mut LiarAtEnd(reader(&bytes)), &mut scratch()),
        Err(Status::Protocol)
    );
}

#[test]
fn full_or_failing_destination_never_reports_success() {
    let mut disk = SimDisk::new();
    let mut service = Service::new(EPOCH, Table::EMPTY, false);
    let mut source = client(&mut service, &mut disk, 0);
    populate(&mut source, CHUNK + 9);
    let mut out = Bytes(Vec::new());
    archive::export(&mut source, 0, &mut out).unwrap();
    let total = out.0.len();
    for room in (0..total).step_by(37).chain([total - 1]) {
        let mut sink = Limited { room, used: 0 };
        assert_eq!(
            archive::export(&mut source, 0, &mut sink),
            Err(Status::Full),
            "room {room}"
        );
    }
    let mut exact = Limited {
        room: total,
        used: 0,
    };
    assert!(archive::export(&mut source, 0, &mut exact).is_ok());
}

/// Writes `object` just before the first content read of the export: an
/// already listed object (1) or a new one (3) that only the final re-listing
/// can notice.
struct Meddle<'a> {
    client: Client<Local<'a>>,
    object: u64,
    done: bool,
}
impl Transport for Meddle<'_> {
    fn call(&mut self, request: &[u8; wire::SIZE]) -> Result<[u8; wire::SIZE], Status> {
        if !self.done && wire::header(request).operation == wire::READ {
            self.done = true;
            let revision = match self.client.stat(self.object) {
                Ok(stat) => stat.revision,
                Err((_, tombstone)) => tombstone,
            };
            self.client
                .write(self.object, revision, b"Late", 10, fill(1, 9))
                .unwrap();
        }
        self.client.transport.call(request)
    }
}

/// Flips the first content byte of the first non-empty READ reply.
struct Flip<'a> {
    inner: Local<'a>,
    done: bool,
}
impl Transport for Flip<'_> {
    fn call(&mut self, request: &[u8; wire::SIZE]) -> Result<[u8; wire::SIZE], Status> {
        let mut body = self.inner.call(request)?;
        if !self.done
            && wire::header(&body).operation == wire::READ
            && wire::header(&body).length > 0
        {
            self.done = true;
            body[64] ^= 1;
        }
        Ok(body)
    }
}

#[test]
fn export_rejects_content_that_contradicts_the_service_sum() {
    let mut disk = SimDisk::new();
    let mut service = Service::new(EPOCH, Table::EMPTY, false);
    populate(&mut client(&mut service, &mut disk, 0), 64);
    let mut flipped = Client::new(
        Flip {
            inner: Local {
                service: &mut service,
                disk: &mut disk,
                domain: 0,
            },
            done: false,
        },
        EPOCH,
        7000,
    );
    assert_eq!(
        archive::export(&mut flipped, 0, &mut Bytes(Vec::new())),
        Err(Status::Corrupt)
    );
}

#[test]
fn concurrent_change_makes_export_stale() {
    for object in [1, 3] {
        let mut disk = SimDisk::new();
        let mut service = Service::new(EPOCH, Table::EMPTY, false);
        let mut inner = client(&mut service, &mut disk, 0);
        populate(&mut inner, 64);
        let mut meddled = Client::new(
            Meddle {
                client: inner,
                object,
                done: false,
            },
            EPOCH,
            9000,
        );
        let mut out = Bytes(Vec::new());
        assert_eq!(
            archive::export(&mut meddled, 0, &mut out),
            Err(Status::Stale),
            "object {object}"
        );
        assert!(archive::verify(&mut reader(&out.0), &mut scratch()).is_err());
    }
}

#[test]
fn restore_never_overwrites_objects_names_or_collections() {
    let bytes = exported(64);
    let mut disk = SimDisk::new();
    let mut service = Service::new(EPOCH, Table::EMPTY, false);
    let mut destination = client(&mut service, &mut disk, 1);
    destination.collection(1, 1, 0, "Privé".as_bytes()).unwrap();
    destination.write(8, 0, b"Keep", 71, fill(8, 1)).unwrap(); // slot 0 occupied
    destination.write(11, 0, b"Plan", 33, fill(11, 1)).unwrap(); // name of slot 1
    let report =
        archive::restore(&mut reader(&bytes), &mut scratch(), &mut destination, 1).unwrap();
    assert_eq!(
        report,
        Report {
            restored: 0b10_0000,
            conflicts: 0b11,
            uncollected: 0,
            bare: 0
        }
    );
    let (keep, data) = content(&mut destination, 8);
    assert_eq!(
        (&keep.name[..keep.name_length], keep.revision),
        (&b"Keep"[..], 1)
    );
    assert_eq!(data, expected(8, 1, 71));
    assert_eq!(destination.stat(9).unwrap_err().0, Status::NotFound);
    assert_eq!(content(&mut destination, 11).1, expected(11, 1, 33));
    assert_eq!(
        destination.collection_stat(1, 1).unwrap().name(),
        "Privé".as_bytes()
    );

    // Into an empty domain whose collection 1 has another name: restored,
    // but outside the foreign collection, which keeps its name.
    let mut disk = SimDisk::new();
    let mut service = Service::new(EPOCH, Table::EMPTY, false);
    let mut destination = client(&mut service, &mut disk, 1);
    destination.collection(1, 1, 0, "Privé".as_bytes()).unwrap();
    let report =
        archive::restore(&mut reader(&bytes), &mut scratch(), &mut destination, 1).unwrap();
    assert_eq!((report.restored, report.uncollected), (0b10_0011, 0b1));
    assert_eq!(destination.stat(8).unwrap().collection, 0);
    assert_eq!(
        destination.collection_stat(1, 1).unwrap().name(),
        "Privé".as_bytes()
    );
}

#[test]
fn restore_creates_no_collection_for_a_conflicting_object() {
    // "Notes" (slot 0) is the only object in collection 1; when it conflicts
    // by slot or by name, restore must not create that collection.
    let bytes = exported(64);
    for (object, name) in [(8, &b"Keep"[..]), (12, &b"Notes"[..])] {
        let mut disk = SimDisk::new();
        let mut service = Service::new(EPOCH, Table::EMPTY, false);
        let mut destination = client(&mut service, &mut disk, 1);
        destination
            .write(object, 0, name, 21, fill(object, 1))
            .unwrap();
        let report =
            archive::restore(&mut reader(&bytes), &mut scratch(), &mut destination, 1).unwrap();
        assert_eq!(
            report,
            Report {
                restored: 0b10_0010,
                conflicts: 0b1,
                uncollected: 0,
                bare: 0
            }
        );
        let info = destination.collection_stat(1, 1).unwrap();
        assert_eq!((info.present, info.revision), (false, 0));
        assert_eq!(content(&mut destination, object).1, expected(object, 1, 21));
    }
}

#[test]
fn uncollected_object_without_metadata_stays_at_revision_one() {
    // A collected source object without tags or kind, restored where its
    // collection index holds another name: content only, no META.
    let mut disk = SimDisk::new();
    let mut service = Service::new(EPOCH, Table::EMPTY, false);
    let mut source = client(&mut service, &mut disk, 0);
    source.collection(0, 1, 0, b"Werk").unwrap();
    let revision = source.write(0, 0, b"Bare", 40, fill(0, 1)).unwrap().0;
    source.meta(0, revision, 0, 0, 1).unwrap();
    let mut out = Bytes(Vec::new());
    archive::export(&mut source, 0, &mut out).unwrap();

    let mut disk = SimDisk::new();
    let mut service = Service::new(EPOCH, Table::EMPTY, false);
    let mut destination = client(&mut service, &mut disk, 1);
    destination.collection(1, 1, 0, "Privé".as_bytes()).unwrap();
    let report =
        archive::restore(&mut reader(&out.0), &mut scratch(), &mut destination, 1).unwrap();
    assert_eq!(
        (report.restored, report.uncollected, report.bare),
        (0b1, 0b1, 0)
    );
    let (stat, data) = content(&mut destination, 8);
    assert_eq!(
        (stat.revision, stat.collection, stat.tags, stat.kind),
        (1, 0, 0, 0)
    );
    assert_eq!(data, expected(0, 1, 40));
}

#[test]
fn unverified_truncated_restore_commits_only_checked_objects() {
    let big = 2 * CHUNK;
    let bytes = exported(big);
    // Cut inside the content of "Plan" (the "Empty" record follows it).
    let cut = bytes.len() - 16 - 96 - big / 2;
    assert_eq!(
        archive::verify(&mut reader(&bytes[..cut]), &mut scratch()),
        Err(Status::Corrupt)
    );
    let mut disk = SimDisk::new();
    let mut service = Service::new(EPOCH, Table::EMPTY, false);
    let mut destination = client(&mut service, &mut disk, 1);
    let (status, report) = archive::restore(
        &mut reader(&bytes[..cut]),
        &mut scratch(),
        &mut destination,
        1,
    )
    .unwrap_err();
    assert_eq!((status, report.restored), (Status::Corrupt, 0b1));
    assert_eq!(content(&mut destination, 8).1, expected(0, 1, 300));
    assert_eq!(destination.stat(9).unwrap_err().0, Status::NotFound);
}

#[test]
fn destination_quota_stops_restore_without_touching_existing_data() {
    let bytes = exported(MAX_LENGTH);
    let mut disk = SimDisk::new();
    let mut service = Service::new(EPOCH, Table::EMPTY, false);
    let mut destination = client(&mut service, &mut disk, 1);
    destination
        .write(14, 0, b"Big", MAX_LENGTH, fill(14, 1))
        .unwrap();
    destination
        .write(15, 0, b"Bigger", MAX_LENGTH, fill(15, 1))
        .unwrap();
    let (status, report) =
        archive::restore(&mut reader(&bytes), &mut scratch(), &mut destination, 1).unwrap_err();
    assert_eq!((status, report.restored), (Status::Quota, 0b1));
    assert_eq!(destination.stat(9).unwrap_err().0, Status::NotFound);
    assert_eq!(content(&mut destination, 14).1, expected(14, 1, MAX_LENGTH));
    assert_eq!(content(&mut destination, 15).1, expected(15, 1, MAX_LENGTH));
}

#[test]
fn invalid_domain_is_rejected() {
    let bytes = exported(1);
    let mut disk = SimDisk::new();
    let mut service = Service::new(EPOCH, Table::EMPTY, false);
    let mut c = client(&mut service, &mut disk, 1);
    assert_eq!(
        archive::export(&mut c, 2, &mut Bytes(Vec::new())),
        Err(Status::Invalid)
    );
    assert_eq!(
        archive::restore(&mut reader(&bytes), &mut scratch(), &mut c, 2),
        Err((Status::Invalid, Report::default()))
    );
}

/// Re-seal a fixed record at `at` and the trailer after a deliberate edit,
/// so only the canonical-format checks can reject the result.
fn resealed(mut bytes: Vec<u8>, at: usize, size: usize, edit: impl Fn(&mut [u8])) -> Vec<u8> {
    edit(&mut bytes[at..at + size]);
    let sum = checksum_update(FNV_OFFSET, &bytes[at..at + size - 8]);
    bytes[at + size - 8..at + size].copy_from_slice(&sum.to_le_bytes());
    let end = bytes.len() - TRAILER;
    let total = checksum_update(FNV_OFFSET, &bytes[..end]);
    bytes[end + 8..].copy_from_slice(&total.to_le_bytes());
    bytes
}

#[test]
fn resealed_non_canonical_records_are_rejected() {
    let bytes = exported(500);
    let mut scratch = scratch();
    // Sanity: resealing without an edit keeps the archive valid.
    assert!(archive::verify(
        &mut reader(&resealed(bytes.clone(), 0, HEADER, |_| ())),
        &mut scratch
    )
    .is_ok());
    let collection = HEADER;
    let notes = HEADER + 48; // first object record
    let plan = notes + OBJECT_RECORD + 300;
    type Edit = fn(&mut [u8]);
    let cases: [(&str, usize, usize, Edit); 20] = [
        ("header version", 0, HEADER, |h| h[8] = 2),
        ("header reserved", 0, HEADER, |h| h[10] = 1),
        ("header count > 8", 0, HEADER, |h| h[12] = 9),
        ("header count low", 0, HEADER, |h| h[12] = 2),
        ("header collections > 4", 0, HEADER, |h| h[13] = 5),
        ("header content bytes", 0, HEADER, |h| h[24] ^= 1),
        ("header tail reserved", 0, HEADER, |h| h[40] = 1),
        ("collection index 0", collection, 48, |c| c[0] = 0),
        ("collection index 5", collection, 48, |c| c[0] = 5),
        ("collection name too long", collection, 48, |c| c[1] = 33),
        ("collection padding", collection, 48, |c| c[30] = b'x'),
        ("object name too long", notes, OBJECT_RECORD, |o| o[1] = 33),
        ("object name padding", notes, OBJECT_RECORD, |o| {
            o[60] = b'x'
        }),
        ("object empty name", notes, OBJECT_RECORD, |o| o[1] = 0),
        ("object unknown collection", notes, OBJECT_RECORD, |o| {
            o[2] = 2
        }),
        ("object reserved", notes, OBJECT_RECORD, |o| o[3] = 1),
        ("object revision 0", notes, OBJECT_RECORD, |o| {
            o[16..24].fill(0)
        }),
        ("object slot not increasing", plan, OBJECT_RECORD, |o| {
            o[0] = 0
        }),
        ("object slot past domain", plan, OBJECT_RECORD, |o| o[0] = 8),
        ("object too long", plan, OBJECT_RECORD, |o| {
            o[12..16].copy_from_slice(&(MAX_LENGTH as u32 + 1).to_le_bytes())
        }),
    ];
    for (label, at, size, edit) in cases {
        assert_eq!(
            archive::verify(
                &mut reader(&resealed(bytes.clone(), at, size, edit)),
                &mut scratch
            ),
            Err(Status::Corrupt),
            "{label}"
        );
    }
}

#[test]
fn duplicate_source_names_round_trip() {
    let mut disk = SimDisk::new();
    let mut service = Service::new(EPOCH, Table::EMPTY, false);
    let mut source = client(&mut service, &mut disk, 0);
    source.write(0, 0, b"Same", 5, fill(0, 1)).unwrap();
    source.write(2, 0, b"Same", 6, fill(2, 1)).unwrap();
    let mut out = Bytes(Vec::new());
    archive::export(&mut source, 0, &mut out).unwrap();
    assert!(archive::verify(&mut reader(&out.0), &mut scratch()).is_ok());
    let mut disk = SimDisk::new();
    let mut service = Service::new(EPOCH, Table::EMPTY, false);
    let mut destination = client(&mut service, &mut disk, 1);
    let report =
        archive::restore(&mut reader(&out.0), &mut scratch(), &mut destination, 1).unwrap();
    assert_eq!(report.restored, 0b101);
    assert_eq!(content(&mut destination, 10).1, expected(2, 1, 6));
}

#[test]
fn deleted_destination_slot_is_restored_over_its_tombstone() {
    let bytes = exported(64);
    let mut disk = SimDisk::new();
    let mut service = Service::new(EPOCH, Table::EMPTY, false);
    let mut destination = client(&mut service, &mut disk, 1);
    let r = destination.write(9, 0, b"Gone", 20, fill(9, 1)).unwrap().0;
    let tombstone = destination.delete(9, r).unwrap();
    let report =
        archive::restore(&mut reader(&bytes), &mut scratch(), &mut destination, 1).unwrap();
    assert_eq!(report.restored, 0b10_0011);
    let (plan, data) = content(&mut destination, 9);
    assert_eq!(
        (&plan.name[..plan.name_length], plan.revision),
        (&b"Plan"[..], tombstone + 1)
    );
    assert_eq!(data, expected(1, 2, 64));
}

/// Answers COMMIT (optionally after forwarding it) or META with a failure.
/// With `skew_stat`, the first STAT reply after that fault reports another
/// content sum (revision, name and length unchanged).
struct Faulty<'a> {
    inner: Local<'a>,
    operation: u16,
    forward: bool,
    status: Status,
    done: bool,
    skew_stat: bool,
}
impl Transport for Faulty<'_> {
    fn call(&mut self, request: &[u8; wire::SIZE]) -> Result<[u8; wire::SIZE], Status> {
        let header = wire::header(request);
        if self.done && self.skew_stat && header.operation == wire::STAT {
            self.skew_stat = false;
            let mut reply = self.inner.call(request)?;
            reply[64 + 32] ^= 1; // content sum in the STAT data
            return Ok(reply);
        }
        if self.done || header.operation != self.operation {
            return self.inner.call(request);
        }
        self.done = true;
        if self.forward {
            self.inner.call(request)?;
        }
        let mut reply = header;
        reply.status = self.status as i32;
        (
            reply.revision,
            reply.length,
            reply.name_length,
            reply.count,
            reply.aux,
        ) = (0, 0, 0, 0, 0);
        Ok(wire::encode(&reply, &[]))
    }
}

type Outcome = Result<Report, (Status, Report)>;

fn faulty_restore(
    operation: u16,
    forward: bool,
    status: Status,
    skew_stat: bool,
) -> (Outcome, Service, SimDisk) {
    let bytes = exported(64);
    let mut disk = SimDisk::new();
    let mut service = Service::new(EPOCH, Table::EMPTY, false);
    let result = {
        let mut destination = Client::new(
            Faulty {
                inner: Local {
                    service: &mut service,
                    disk: &mut disk,
                    domain: 1,
                },
                operation,
                forward,
                status,
                done: false,
                skew_stat,
            },
            EPOCH,
            3000,
        );
        archive::restore(&mut reader(&bytes), &mut scratch(), &mut destination, 1)
    };
    (result, service, disk)
}

#[test]
fn unknown_commit_is_resolved_by_stat() {
    // The commit landed: the object counts as restored and gets its metadata.
    let (result, mut service, mut disk) =
        faulty_restore(wire::COMMIT, true, Status::Unknown, false);
    assert_eq!(result.unwrap().restored, 0b10_0011);
    let stat = client(&mut service, &mut disk, 1).stat(8).unwrap();
    assert_eq!((stat.tags, stat.collection), (0x55, 1));
    // The commit never arrived: the restore stops and does not claim it.
    let (result, mut service, mut disk) =
        faulty_restore(wire::COMMIT, false, Status::Unknown, false);
    let (status, report) = result.unwrap_err();
    assert_eq!((status, report.restored), (Status::Unknown, 0));
    assert_eq!(
        client(&mut service, &mut disk, 1).stat(8).unwrap_err().0,
        Status::NotFound
    );
}

#[test]
fn unknown_commit_with_another_content_sum_is_not_claimed() {
    // The commit landed, but STAT reports another content sum: not ours.
    let (result, mut service, mut disk) = faulty_restore(wire::COMMIT, true, Status::Unknown, true);
    let (status, report) = result.unwrap_err();
    assert_eq!(
        (status, report.restored, report.bare),
        (Status::Unknown, 0, 0)
    );
    // No META reached the service: the landed object kept bare metadata.
    let stat = client(&mut service, &mut disk, 1).stat(8).unwrap();
    assert_eq!((stat.tags, stat.kind, stat.collection), (0, 0, 0));
}

#[test]
fn failed_metadata_is_reported_as_bare() {
    let (result, mut service, mut disk) = faulty_restore(wire::META, false, Status::Io, false);
    let (status, report) = result.unwrap_err();
    assert_eq!(
        (status, report.restored, report.bare),
        (Status::Io, 0b1, 0b1)
    );
    let stat = client(&mut service, &mut disk, 1).stat(8).unwrap();
    assert_eq!((stat.tags, stat.collection), (0, 0));
}

/// A dedicated raw sector range (the native portal target), pre-filled with
/// a canary so untouched sectors stay recognizable.
struct Range {
    sectors: Vec<[u8; SECTOR]>,
    fail_write_at: Option<u64>,
    flushes: usize,
}
impl Range {
    fn new(sectors: usize) -> Self {
        Self {
            sectors: vec![[0xA5; SECTOR]; sectors],
            fail_write_at: None,
            flushes: 0,
        }
    }
    fn bytes(&self) -> Vec<u8> {
        self.sectors.iter().flatten().copied().collect()
    }
}
impl Disk for Range {
    fn read(&mut self, sector: u64, buffer: &mut [u8; SECTOR]) -> Result<(), Status> {
        *buffer = self.sectors[sector as usize]; // panics outside the range
        Ok(())
    }
    fn write(&mut self, sector: u64, buffer: &[u8; SECTOR]) -> Result<(), Status> {
        if self.fail_write_at == Some(sector) {
            return Err(Status::Io);
        }
        self.sectors[sector as usize] = *buffer;
        Ok(())
    }
    fn flush(&mut self) -> Result<(), Status> {
        self.flushes += 1;
        Ok(())
    }
}

fn sectors_for(length: usize) -> usize {
    length.div_ceil(SECTOR)
}

fn export_to_range(big: usize, range: &mut Range) -> Result<u64, Status> {
    let capacity = range.sectors.len() as u64;
    export_scoped(big, range, capacity)
}

/// Export into the first `capacity` sectors of `range` (a cut target scope).
fn export_scoped(big: usize, range: &mut Range, capacity: u64) -> Result<u64, Status> {
    let mut disk = SimDisk::new();
    let mut service = Service::new(EPOCH, Table::EMPTY, false);
    let mut source = client(&mut service, &mut disk, 0);
    populate(&mut source, big);
    let mut sink = DiskSink::new(range, capacity);
    archive::export(&mut source, 0, &mut sink)?;
    sink.finish()
}

#[test]
fn disk_range_round_trip_keeps_bytes_and_untouched_sectors() {
    let big = 2 * CHUNK + 173;
    let bytes = exported(big);
    let used = sectors_for(bytes.len());
    let mut range = Range::new(used + 3);
    assert_eq!(export_to_range(big, &mut range), Ok(bytes.len() as u64));
    assert_eq!(range.flushes, 1);
    let stored = range.bytes();
    assert_eq!(&stored[..bytes.len()], &bytes[..]);
    assert!(stored[bytes.len()..used * SECTOR].iter().all(|b| *b == 0));
    assert!(stored[used * SECTOR..].iter().all(|b| *b == 0xA5));

    let capacity = range.sectors.len() as u64;
    let summary =
        archive::verify(&mut DiskSource::new(&mut range, capacity), &mut scratch()).unwrap();
    assert_eq!(
        (summary.objects, summary.content_bytes),
        (3, 300 + big as u64)
    );
    // Restore from the range alone into a fresh destination volume.
    let mut disk = SimDisk::new();
    let mut service = Service::new(EPOCH, Table::EMPTY, false);
    let mut destination = client(&mut service, &mut disk, 1);
    let report = archive::restore(
        &mut DiskSource::new(&mut range, capacity),
        &mut scratch(),
        &mut destination,
        1,
    )
    .unwrap();
    assert_eq!(report.restored, 0b10_0011);
    assert_eq!(content(&mut destination, 9).1, expected(1, 2, big));
}

#[test]
fn disk_sink_reports_full_at_the_exact_boundary_and_device_errors() {
    let big = CHUNK + 1;
    let length = exported(big).len();
    let needed = sectors_for(length);
    assert_eq!(
        export_to_range(big, &mut Range::new(needed)),
        Ok(length as u64)
    );
    let mut short = Range::new(needed - 1);
    assert_eq!(export_to_range(big, &mut short), Err(Status::Full));
    assert_eq!(short.flushes, 0, "a failed export must not flush");
    for at in [0, needed as u64 - 1] {
        let mut failing = Range::new(needed);
        failing.fail_write_at = Some(at);
        assert_eq!(export_to_range(big, &mut failing), Err(Status::Io));
        assert_eq!(failing.flushes, 0);
    }
}

#[test]
fn full_target_leaves_no_archive_and_a_later_export_over_it_verifies() {
    let big = CHUNK + 1;
    let bytes = exported(big);
    let needed = sectors_for(bytes.len());
    // One sector short (only the buffered tail is missing: `finish` reports
    // Full) and half the archive (the stream itself reports Full).
    for short in [needed as u64 - 1, needed as u64 / 2] {
        let mut range = Range::new(needed);
        assert_eq!(export_scoped(big, &mut range, short), Err(Status::Full));
        assert_eq!(range.flushes, 0);
        assert!(range.sectors[short as usize..]
            .iter()
            .all(|sector| *sector == [0xA5; SECTOR]));
        // Neither the cut scope nor a scope that fits accepts the leftover.
        for capacity in [short, needed as u64] {
            assert_eq!(
                archive::verify(&mut DiskSource::new(&mut range, capacity), &mut scratch()),
                Err(Status::Corrupt),
                "short {short}, capacity {capacity}"
            );
        }
        // A retry into a target that fits overwrites the leftover and verifies.
        assert_eq!(export_to_range(big, &mut range), Ok(bytes.len() as u64));
        assert_eq!(&range.bytes()[..bytes.len()], &bytes[..]);
        assert!(archive::verify(
            &mut DiskSource::new(&mut range, needed as u64),
            &mut scratch()
        )
        .is_ok());
    }
}

#[test]
fn disk_source_refuses_empty_oversized_and_damaged_ranges() {
    let big = CHUNK;
    let length = exported(big).len();
    let needed = sectors_for(length);
    let verify = |range: &mut Range, capacity: u64| {
        archive::verify(&mut DiskSource::new(range, capacity), &mut scratch())
    };
    // No archive at all, a zero-length range, and a range one sector short.
    let mut zeroed = Range::new(needed);
    zeroed.sectors.iter_mut().for_each(|s| *s = [0; SECTOR]);
    assert_eq!(verify(&mut zeroed, needed as u64), Err(Status::Corrupt));
    let mut range = Range::new(needed);
    export_to_range(big, &mut range).unwrap();
    assert_eq!(verify(&mut range, 0), Err(Status::Corrupt));
    assert_eq!(verify(&mut range, needed as u64 - 1), Err(Status::Corrupt));
    assert!(verify(&mut range, needed as u64).is_ok());
    // Counts claiming more content than the range holds are refused before
    // any read beyond the range (Range panics on such a read).
    let mut forged = Range::new(needed);
    export_to_range(big, &mut forged).unwrap();
    forged.sectors[0][24..32].copy_from_slice(&u64::MAX.to_le_bytes());
    assert_eq!(verify(&mut forged, needed as u64), Err(Status::Corrupt));
    forged.sectors[0][24..32].copy_from_slice(&(needed as u64 * 512).to_le_bytes());
    assert_eq!(verify(&mut forged, needed as u64), Err(Status::Corrupt));
    // One flipped bit anywhere in the archive bytes.
    for at in [0, HEADER + 5, length / 2, length - 1] {
        let mut flipped = Range::new(needed);
        export_to_range(big, &mut flipped).unwrap();
        flipped.sectors[at / SECTOR][at % SECTOR] ^= 0x01;
        assert_eq!(
            verify(&mut flipped, needed as u64),
            Err(Status::Corrupt),
            "at {at}"
        );
    }
    // Padding after the trailer is outside the archive and is ignored.
    let mut padded = Range::new(needed);
    export_to_range(big, &mut padded).unwrap();
    if !length.is_multiple_of(SECTOR) {
        padded.sectors[needed - 1][SECTOR - 1] = 0xFF;
    }
    assert!(verify(&mut padded, needed as u64).is_ok());
}

/// Python's stdlib `tarfile` is the independent reader of the ustar export.
const TARFILE: &str = r#"
import sys, io, tarfile
t = tarfile.open(fileobj=io.BytesIO(sys.stdin.buffer.read()), mode="r:", encoding="utf-8", errors="strict")
for m in t.getmembers():
    d = t.extractfile(m).read() if m.isfile() else b""
    line = "\t".join(map(str, (m.name, m.pax_headers.get("path", "-"), m.type.decode(), m.size, oct(m.mode), m.mtime, m.uid, m.gid, d.hex())))
    sys.stdout.buffer.write(line.encode("utf-8") + b"\n")
"#;

fn tarfile(tar: &[u8]) -> Vec<String> {
    use std::io::Write;
    use std::process::{Command, Stdio};
    let mut child = Command::new("python3")
        .args(["-I", "-c", TARFILE])
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()
        .expect("python3 is the independent ustar reader; not run is not a pass");
    child.stdin.take().unwrap().write_all(tar).unwrap();
    let out = child.wait_with_output().unwrap();
    assert!(
        out.status.success(),
        "{}",
        String::from_utf8_lossy(&out.stderr)
    );
    String::from_utf8(out.stdout)
        .unwrap()
        .lines()
        .map(str::to_owned)
        .collect()
}

/// The system tar (GNU tar 1.35 where this was written) extracts the export
/// into a fresh directory, as a user would.
fn tar_extract(tar: &[u8]) -> std::path::PathBuf {
    use std::io::Write;
    use std::process::{Command, Stdio};
    let dir = std::env::temp_dir().join(format!("volume-ustar-{}", std::process::id()));
    let _ = std::fs::remove_dir_all(&dir);
    std::fs::create_dir_all(&dir).unwrap();
    let mut child = Command::new("tar")
        .args(["--extract", "--file=-", "--directory"])
        .arg(&dir)
        .stdin(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()
        .expect("tar is the second ustar reader; not run is not a pass");
    child.stdin.take().unwrap().write_all(tar).unwrap();
    let out = child.wait_with_output().unwrap();
    assert!(
        out.status.success(),
        "{}",
        String::from_utf8_lossy(&out.stderr)
    );
    dir
}

fn ustar(bytes: &[u8]) -> (Result<archive::Summary, Status>, Vec<u8>) {
    let mut out = Bytes(Vec::new());
    let result = ustar::from_archive(&mut reader(bytes), &mut scratch(), &mut out);
    (result, out.0)
}

#[test]
fn ustar_export_opens_with_a_standard_reader() {
    let mut disk = SimDisk::new();
    let mut service = Service::new(EPOCH, Table::EMPTY, false);
    let mut source = client(&mut service, &mut disk, 0);
    populate(&mut source, 5000);
    source
        .write(2, 0, "Notitie ✓".as_bytes(), 50, fill(2, 1))
        .unwrap();
    let mut bytes = Bytes(Vec::new());
    archive::export(&mut source, 0, &mut bytes).unwrap();
    assert!(archive::verify(&mut reader(&bytes.0), &mut scratch()).is_ok());
    let (result, tar) = ustar(&bytes.0);
    assert_eq!(result.map(|s| s.objects), Ok(4));
    assert_eq!(tar.len() % ustar::BLOCK, 0);
    assert!(tar[tar.len() - 2 * ustar::BLOCK..].iter().all(|&b| b == 0));
    let hex = |data: &[u8]| data.iter().map(|b| format!("{b:02x}")).collect::<String>();
    let file = |name: &str, pax: &str, data: Vec<u8>| {
        format!(
            "{name}\t{pax}\t0\t{}\t0o644\t0\t0\t0\t{}",
            data.len(),
            hex(&data)
        )
    };
    // The non-ASCII name reaches the reader through its pax path record.
    assert_eq!(
        tarfile(&tar),
        [
            file("Werk/Notes", "-", expected(0, 1, 300)),
            file("Plan", "-", expected(1, 2, 5000)),
            file("Notitie ✓", "Notitie ✓", expected(2, 1, 50)),
            file("Empty", "-", Vec::new()),
        ]
    );
    let dir = tar_extract(&tar);
    for (path, data) in [
        ("Werk/Notes", expected(0, 1, 300)),
        ("Plan", expected(1, 2, 5000)),
        ("Notitie ✓", expected(2, 1, 50)),
        ("Empty", Vec::new()),
    ] {
        assert_eq!(std::fs::read(dir.join(path)).unwrap(), data, "{path}");
    }
    assert_eq!(std::fs::read_dir(&dir).unwrap().count(), 4);
    std::fs::remove_dir_all(&dir).unwrap();
    assert_eq!(ustar(&bytes.0).1, tar, "equal archives give equal bytes");
}

#[test]
fn ustar_export_ends_only_after_the_whole_archive_checked_out() {
    let bytes = exported(500);
    let (result, good) = ustar(&bytes);
    assert!(result.is_ok());
    let mut bad = bytes.clone();
    *bad.last_mut().unwrap() ^= 1;
    let (result, partial) = ustar(&bad);
    assert_eq!(result, Err(Status::Corrupt));
    // Every file was written, but not the end-of-archive blocks.
    assert_eq!(partial, good[..good.len() - 2 * ustar::BLOCK]);
    // A reader accepts that silently, so callers verify first and discard the
    // output on error.
    assert_eq!(tarfile(&partial).len(), 3);
}

#[test]
fn ustar_export_refuses_colliding_paths_and_drive_names() {
    let bytes = exported(500);
    let plan = HEADER + 48 + OBJECT_RECORD + 300;
    let rename = |name: &'static [u8], collection: u8| {
        resealed(bytes.clone(), plan, OBJECT_RECORD, move |r| {
            r[1] = name.len() as u8;
            r[2] = collection;
            r[48..80].fill(0);
            r[48..48 + name.len()].copy_from_slice(name);
        })
    };
    assert!(
        ustar(&rename(b"Plan", 0)).0.is_ok(),
        "an unchanged rename stays exportable"
    );
    assert!(
        ustar(&rename(b"Plan:2", 0)).0.is_ok(),
        "a later colon is kept"
    );
    let drive = resealed(bytes.clone(), HEADER, 48, |r| {
        r[1] = 2;
        r[8..40].fill(0);
        r[8..10].copy_from_slice(b"C:");
    });
    // A file and a directory at "Werk"; two files at "Werk/Notes"; paths that
    // Windows reads as a drive: "C:x", "C:/Notes", and drives that are not a
    // letter or not one UTF-8 byte ("1:x", "é:x"), plus a non-BMP character
    // that Python's ntpath reads as a drive.
    for archive in [
        rename(b"Werk", 0),
        rename(b"Notes", 1),
        rename(b"C:x", 0),
        rename(b"1:x", 0),
        rename("é:x".as_bytes(), 0),
        rename("\u{1F600}:x".as_bytes(), 0),
        drive,
    ] {
        assert!(archive::verify(&mut reader(&archive), &mut scratch()).is_ok());
        assert_eq!(ustar(&archive).0, Err(Status::Invalid));
    }
}
