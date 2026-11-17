#![no_std]

use core::panic::PanicInfo;

#[path = "support/splitmix64.rs"]
mod rng;

#[unsafe(no_mangle)]
pub extern "C" fn splitmix64(rounds: u32, mut state: u64) -> u64 {
    let mut checksum = 0;
    for _ in 0..rounds {
        checksum ^= rng::next(&mut state);
    }
    checksum
}

#[panic_handler]
fn panic(_: &PanicInfo<'_>) -> ! {
    core::arch::wasm32::unreachable()
}
