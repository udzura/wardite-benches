#![no_std]

use core::panic::PanicInfo;

#[path = "support/splitmix64.rs"]
mod rng;

fn unit_coordinate(state: &mut u64) -> f64 {
    // Use the top 53 bits to form an exactly representable fraction in [0, 1).
    const SCALE: f64 = 1.0 / (1u64 << 53) as f64;
    (rng::next(state) >> 11) as f64 * SCALE
}

#[unsafe(no_mangle)]
pub extern "C" fn monte_carlo_pi(samples: u32, mut state: u64) -> f64 {
    if samples == 0 {
        return f64::NAN;
    }

    let mut inside = 0;
    for _ in 0..samples {
        let x = unit_coordinate(&mut state);
        let y = unit_coordinate(&mut state);
        inside += u32::from(x * x + y * y <= 1.0);
    }

    4.0 * f64::from(inside) / f64::from(samples)
}

#[panic_handler]
fn panic(_: &PanicInfo<'_>) -> ! {
    core::arch::wasm32::unreachable()
}
