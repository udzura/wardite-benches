// Streaming CRC-8 (polynomial 0x07, initial value 0, no reflection or final XOR).
#![no_std]

use core::arch::wasm32;
use core::panic::PanicInfo;

static TABLE: [u8; 256] = {
    let mut table = [0; 256];
    let mut i = 0;
    while i < table.len() {
        let mut crc = i as u8;
        let mut bit = 0;
        while bit < 8 {
            crc = (crc << 1) ^ if crc & 0x80 != 0 { 0x07 } else { 0 };
            bit += 1;
        }
        table[i] = crc;
        i += 1;
    }
    table
};

// Reuse a deterministic 4 KiB input chunk so file I/O stays outside the example.
static CHUNK: [u8; 4096] = {
    let mut bytes = [0; 4096];
    let mut i = 0;
    while i < bytes.len() {
        bytes[i] = (73 * i + (i >> 8)) as u8;
        i += 1;
    }
    bytes
};

#[unsafe(no_mangle)]
pub extern "C" fn crc8_stream(chunks: u32, grow: u32) -> u32 {
    if grow != 0 && wasm32::memory_grow::<0>(1) == usize::MAX {
        wasm32::unreachable();
    }
    let mut crc = 0;
    for _ in 0..chunks {
        for &byte in &CHUNK {
            crc = TABLE[(crc ^ byte) as usize];
        }
    }
    crc.into()
}

#[panic_handler]
fn panic(_: &PanicInfo<'_>) -> ! {
    wasm32::unreachable()
}
