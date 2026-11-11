#![no_std]

use core::panic::PanicInfo;

macro_rules! mandelbrot {
    ($name:ident, $float:ty) => {
        #[unsafe(no_mangle)]
        pub extern "C" fn $name(width: u32, height: u32, max_iterations: u32) -> u32 {
            if width == 0 || height == 0 || max_iterations == 0 {
                return 0;
            }

            let dx = 3.0 / width as $float;
            let dy = 2.5 / height as $float;
            let mut total = 0u32;

            for y in 0..height {
                let c_im = -1.25 + y as $float * dy;
                for x in 0..width {
                    let c_re = -2.0 + x as $float * dx;
                    let mut re: $float = 0.0;
                    let mut im: $float = 0.0;
                    let mut iterations = 0;

                    while iterations < max_iterations {
                        let re_sq = re * re;
                        let im_sq = im * im;
                        if re_sq + im_sq > 4.0 {
                            break;
                        }
                        im = 2.0 * re * im + c_im;
                        re = re_sq - im_sq + c_re;
                        iterations += 1;
                    }

                    total = total.wrapping_add(iterations);
                }
            }
            total
        }
    };
}

mandelbrot!(mandelbrot_f32, f32);
mandelbrot!(mandelbrot_f64, f64);

#[panic_handler]
fn panic(_: &PanicInfo<'_>) -> ! {
    core::arch::wasm32::unreachable()
}
