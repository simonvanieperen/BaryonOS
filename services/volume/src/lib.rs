//! Allocator-free M6e copy-on-write document volume (S04/S05), extended in
//! v2 with collections, metadata, restorable history and transactions (S06).
//!
//! Two alternating table copies describe every live object; content lives in
//! fixed 4 KiB chunks. A mutation writes new content only into chunks that the
//! durable table does not reference, flushes, then writes the next table copy
//! and flushes again. Space of replaced or deleted objects is reused by later
//! commits without a separate compaction pass and without a record limit.
//!
//! FNV-64 detects accidental corruption and torn writes only; it is not
//! authentication, encryption or rollback protection (B02 remains open).
#![no_std]
#![forbid(unsafe_code)]

pub mod archive;
pub mod client;
pub mod service;
pub mod table;
pub mod upload;
pub mod ustar;
pub mod wire;

pub use catalog_core::wire::{checksum_update, valid_name, FNV_OFFSET};

pub const SECTOR: usize = 512;
/// Header, collections, then two sectors per object (head+current, history).
pub const TABLE_SECTORS: u64 = 2 + 2 * OBJECTS as u64;
pub const DATA_START: u64 = 2 * TABLE_SECTORS;
pub const CHUNK_SECTORS: u64 = 8;
pub const CHUNK: usize = 4096;
pub const CHUNKS: usize = 64;
pub const VOLUME_SECTORS: u64 = DATA_START + CHUNKS as u64 * CHUNK_SECTORS;
pub const DOMAINS: usize = 2;
pub const PER_DOMAIN: usize = 8;
pub const OBJECTS: usize = DOMAINS * PER_DOMAIN;
pub const MAX_CHUNKS: usize = 16;
pub const MAX_LENGTH: usize = MAX_CHUNKS * CHUNK;
/// Committed plus staged chunks per domain. Quotas deliberately overcommit
/// the 64-chunk volume (2 x 40), so both Quota and Full are reachable.
pub const QUOTA: usize = 40;
pub const NAME: usize = 32;
pub const NO_CHUNK: u16 = 0xffff;
/// Earlier versions retained per object (newest first).
pub const HISTORY: usize = 2;
/// Named collections per domain (index 1..=COLLECTIONS; 0 = none).
pub const COLLECTIONS: usize = 4;
/// Sub-operations in one atomic TRANSACT.
pub const TRANSACT_MAX: usize = 4;

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
#[repr(i32)]
pub enum Status {
    Ok = 0,
    Invalid = -1,
    NoSys = -2,
    Range = -3,
    Access = -5,
    Stale = -10,
    Io = -12,
    Timeout = -13,
    NoDevice = -14,
    Protocol = -15,
    Unknown = -16,
    Full = -17,
    Corrupt = -18,
    NotFound = -19,
    Quota = -20,
    Busy = -21,
}

impl Status {
    pub fn from_code(code: i64) -> Self {
        match code {
            0 => Self::Ok,
            -1 => Self::Invalid,
            -2 => Self::NoSys,
            -3 => Self::Range,
            -5 => Self::Access,
            -10 => Self::Stale,
            -12 => Self::Io,
            -13 => Self::Timeout,
            -14 => Self::NoDevice,
            -16 => Self::Unknown,
            -17 => Self::Full,
            -18 => Self::Corrupt,
            -19 => Self::NotFound,
            -20 => Self::Quota,
            -21 => Self::Busy,
            _ => Self::Protocol,
        }
    }
}

/// Synchronous block access through the service's own scoped capability.
/// `sector` is relative to the granted scope. Success of `write` means only
/// that the device completed it; durability requires a later `flush`.
pub trait Disk {
    fn read(&mut self, sector: u64, buffer: &mut [u8; SECTOR]) -> Result<(), Status>;
    fn write(&mut self, sector: u64, buffer: &[u8; SECTOR]) -> Result<(), Status>;
    fn flush(&mut self) -> Result<(), Status>;
}

pub const fn domain_of(object: usize) -> usize {
    object / PER_DOMAIN
}

pub const fn chunks_for(length: usize) -> usize {
    length.div_ceil(CHUNK)
}

pub fn get16(bytes: &[u8], at: usize) -> u16 {
    u16::from_le_bytes([bytes[at], bytes[at + 1]])
}
pub fn get32(bytes: &[u8], at: usize) -> u32 {
    u32::from_le_bytes([bytes[at], bytes[at + 1], bytes[at + 2], bytes[at + 3]])
}
pub fn get64(bytes: &[u8], at: usize) -> u64 {
    let mut word = [0; 8];
    word.copy_from_slice(&bytes[at..at + 8]);
    u64::from_le_bytes(word)
}
pub fn put16(bytes: &mut [u8], at: usize, value: u16) {
    bytes[at..at + 2].copy_from_slice(&value.to_le_bytes());
}
pub fn put32(bytes: &mut [u8], at: usize, value: u32) {
    bytes[at..at + 4].copy_from_slice(&value.to_le_bytes());
}
pub fn put64(bytes: &mut [u8], at: usize, value: u64) {
    bytes[at..at + 8].copy_from_slice(&value.to_le_bytes());
}
