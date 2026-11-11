#![no_std]

use core::panic::PanicInfo;

#[unsafe(no_mangle)]
pub extern "C" fn xorshift(mut rounds: u32, mut state: u32) -> u32 {
    while rounds != 0 {
        state ^= state << 13;
        state ^= state >> 17;
        state ^= state << 5;
        rounds -= 1;
    }
    state
}

#[panic_handler]
fn panic(_: &PanicInfo<'_>) -> ! {
    core::arch::wasm32::unreachable()
}
