# S09 — Backup destination and its capability: decision proposal

**Status: proposal, awaiting a decision by the project owner (13 November
2026).** This document establishes no security contract and changes no
existing one. Nothing in it is implemented. Until the project owner decides,
the only archive authority that exists is the test-fixture grant described in
[S09-BACKUP-ARCHIVE.md](S09-BACKUP-ARCHIVE.md), section "Native slice". That
grant is a fixture, not this design.

## Why a decision is needed

S09 requires that "a user can create, verify, restore, and export independent
recovery copies". The native slice proves the archive format, the portal flow
and the kernel accounting against a fixed sector range of the same disposable
test image. A product needs a destination that the user chooses, and an
authority that lets one component write there and nothing else. That authority
is a new trust boundary. The project rules require explicit permission for a
new trust boundary, so the options below are put to the project owner
instead of being chosen silently.

## Constraints that every option keeps

These come from existing documents and are not open for this decision:
- **Security Floor (AGENTS.md).** No option weakens process isolation,
  capability enforcement, key isolation or protection of unshared data.
- **Plaintext only on the user's own target.** Archive format v1 is plaintext
  with an accidental-damage checksum only. It may go only to a target that the
  user chose and that is their own; a NAS or provider needs client-side
  encryption (S09-BACKUP-ARCHIVE.md, "What is deliberately not in v1";
  LOCAL-PRIVACY-CONTRACT.md; ENCRYPTED-OBJECT-STORAGE.md).
- **No implicit authority.** Installation grants no file, NAS, device or
  export right; permissions are separate, visible and revocable
  (LOCAL-PRIVACY-CONTRACT.md, section 4).
- **Restore never overwrites** (S09-BACKUP-ARCHIVE.md).
- **`verify` remains the only acceptance check** for an archive.

## Decisions requested

### D1 — What the destination is

- **(a) A raw block range on a user-chosen device**, granted as the existing
  `BlockScope` capability (device, first sector, sector count). This is what
  the fixture does. It needs no new capability type. However, the raw range
  carries no identity and no ownership record. The "never overwrite foreign
  data" constraint would then rest entirely on the component that picks the
  range.
- **(b) A destination service that owns the target device or partition** and
  stores archives as named, append-only entries. The portal would receive a
  write-once stream capability for one new entry, or a read capability for one
  existing entry, never raw sectors. This needs a new service and interface,
  but it keeps foreign data on the target out of reach by construction.
- **(c) An archive object in another volume domain of the same machine.**
  This is not an independent copy if the volume or the device is lost, and v1
  objects are limited to 64 KiB. It is listed for completeness only.

*Proposed rule for every option (new, not an existing constraint):* an
export must not overwrite data on the target that is not a previous archive
of the same user. Under (a) only the component that picks the range can
uphold it; under (b) the destination service does.

*Recommendation:* (b) as the product design. Keep (a) as the test fixture,
and possibly as the first native step towards (b) on a dedicated, whole
second virtual disk that holds nothing else.

### D2 — Who chooses the destination and how the grant is issued

- **(a) A trusted system dialog** ("choose a backup destination") issues a
  capability for exactly the chosen destination and one operation to the
  backup portal. The user sees the destination's name, size and whether it
  is local, NAS or provider.
- **(b) A persistent grant in the portal's manifest**, configured once.
- **(c) Any app may request the grant through a permission prompt.**

*Recommendation:* (a) for every new destination. A remembered destination may
be reused for scheduled backups within the same permission, as the product
ambition allows "normal repetition within existing permissions". The grant
stays revocable. (c) is not recommended, because a third-party app would then
hold a raw export path for personal data.

### D3 — Rights per operation

- Export: READ on the user's own domain through the normal volume client;
  write and flush on one new destination entry; read back of that entry for
  `verify`.
- Restore: read-only on one destination entry; write on the user's domain
  through the normal volume client, under the restore rule.
- The volume service never receives destination rights; the fixture kernel
  counts this (`ARCHIVE_ESCAPE`). The portal never receives the volume's
  block capability; in the fixture this holds because the manifest never
  delegates it, and no kernel check counts it.

*Recommendation:* adopt these per-operation rights as written; they mirror the
fixture (cases 7–11) and add no new kernel mechanism for D1 (a). A product
grant should also check the portal side explicitly, for example that none of
the portal's handles resolves to the volume's block object.

### D4 — Which component holds the authority

- **(a) A system backup portal** shipped and signed with the OS image, the
  only component that receives destination capabilities.
- **(b) A third-party backup app** with a destination permission.

*Recommendation:* (a). A third-party app may later receive an exported copy
through the export portal, which is a different permission than access to the
destination.

### D5 — Encrypted destinations (NAS and provider)

- **(a) Not before the key path.** Use encrypted destinations only after key
  handling (B01, currently parked in this work) and the client-side
  encryption that S09-BACKUP-ARCHIVE.md names (B02, P01,
  ENCRYPTED-OBJECT-STORAGE) exist. Until then, plaintext archives go to local
  user-owned targets only.
- **(b) A separate archive key now**, without that key path.

*Recommendation:* (a). (b) would introduce key handling outside the reviewed
key path, which the project rules do not allow without a recorded threat
model and dependency review.

### D6 — Common export format

- **(a) POSIX ustar with pax `path` records** for names that are not ASCII:
  one file per document under a `<collection>/` path prefix. There are no
  directory entries, so an empty collection is not exported. Host-tested as
  `ustar::from_archive` ([S09-BACKUP-ARCHIVE.md](S09-BACKUP-ARCHIVE.md),
  "User export to ustar").
- **(b) ZIP.** It is just as widely opened, but needs CRC-32, a central
  directory and a flag for UTF-8 names. No code exists.
- **(c) Plain files without a container.** This needs a destination that
  holds a file system, that is D1 (b).

*Recommendation:* (a). It needs only a byte sum per header, with no CRC-32 or
compression code, and its bytes are deterministic. Linux, macOS and current
Windows ship a tar reader; only Python's `tarfile` and GNU tar have been
tested here. It is an export, not a recovery copy: format v1 remains the only
format that restores.

*Also to decide:* whether the export refuses names that extract differently
on Windows or macOS (a later `:`, reserved device names, trailing dots or
spaces, case or normalisation variants). The converter refuses only colliding
paths, an uncollected document named like a declared collection (also when
that collection is empty), and a path whose first character is followed by `:`
(the drive form, such as `C:` or `1:`). The collection rule already makes a
domain with an empty collection "Werk" and an uncollected document "Werk"
impossible to export until one of them is renamed; refusing more names would
do the same for more domains.

## What a decision changes

- If D1 (a) and D3 are accepted: a native step on a second whole virtual disk
  becomes possible with the existing `BlockScope` capability. It needs a
  second virtio-blk device in the volume profile and a trusted grant path
  (D2), which is new kernel and shell work.
- If D1 (b) is accepted: a destination service specification
  (`docs/implementation/`), an ADR, an interface with negative tests, and
  native acceptance come first; the portal changes only its sink and source.
- Either way, S09 also needs a user-facing task, and the export format (D6)
  confirmed and written out natively, before it can be accepted.

## Evidence boundary

This proposal is design text. It has no tests. The fixture evidence for cases
7–11 (local QEMU gate) shows that the portal-only grant, the per-operation
rights and the archive I/O accounting work for a fixed range on one
disposable image. It does not show any of D1 (b), D2, D4 or D5. D6 has host tests only.
