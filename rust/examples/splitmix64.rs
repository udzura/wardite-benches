#![no_std]

use core::panic::PanicInfo;

#[unsafe(no_mangle)]
pub extern "C" fn splitmix64(rounds: u32, mut state: u64) -> u64 {
    let mut checksum = 0;
    for _ in 0..rounds {
        state = state.wrapping_add(0x9e37_79b9_7f4a_7c15);
        let mixed = (state ^ (state >> 30)).wrapping_mul(0xbf58_476d_1ce4_e5b9);
        let mixed = (mixed ^ (mixed >> 27)).wrapping_mul(0x94d0_49bb_1331_11eb);
        checksum ^= mixed ^ (mixed >> 31);
    }
    checksum
}

#[panic_handler]
fn panic(_: &PanicInfo<'_>) -> ! {
    core::arch::wasm32::unreachable()
}
