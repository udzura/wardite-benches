use png::{ColorType, Decoder, Transformations};
use std::error::Error;
use std::io::{self, Cursor, Read, Write};

fn main() -> Result<(), Box<dyn Error>> {
    let mut input = Vec::new();
    io::stdin().lock().read_to_end(&mut input)?;

    let mut decoder = Decoder::new(Cursor::new(input));
    decoder.set_transformations(Transformations::EXPAND | Transformations::STRIP_16);
    let mut reader = decoder.read_info()?;
    let mut pixels = vec![0; reader.output_buffer_size().ok_or("PNG is too large")?];
    let frame = reader.next_frame(&mut pixels)?;
    pixels.truncate(frame.buffer_size());

    let gray = match frame.color_type {
        ColorType::Grayscale => pixels,
        ColorType::GrayscaleAlpha => pixels.chunks_exact(2).map(|pixel| pixel[0]).collect(),
        ColorType::Rgb | ColorType::Rgba => pixels
            .chunks_exact(frame.color_type.samples())
            .map(|pixel| luma(pixel[0], pixel[1], pixel[2]))
            .collect(),
        ColorType::Indexed => return Err("expected expanded PNG pixels".into()),
    };

    let mut output = io::stdout().lock();
    write!(output, "P5\n{} {}\n255\n", frame.width, frame.height)?;
    output.write_all(&gray)?;
    output.flush()?;
    Ok(())
}

fn luma(red: u8, green: u8, blue: u8) -> u8 {
    ((299 * u32::from(red) + 587 * u32::from(green) + 114 * u32::from(blue) + 500) / 1000) as u8
}
