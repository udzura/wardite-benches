use base64::{Engine, engine::general_purpose::STANDARD};
use std::error::Error;
use std::io::{self, Read, Write};

fn main() -> Result<(), Box<dyn Error>> {
    let mut args = std::env::args().skip(1);
    let operation = args.next();
    let transform = match (operation.as_deref(), args.next()) {
        (Some("encode"), None) => |input: &[u8]| Ok(STANDARD.encode(input).into_bytes()),
        (Some("decode"), None) => |input: &[u8]| STANDARD.decode(input),
        _ => return Err("usage: base64_codec encode|decode".into()),
    };

    let mut input = Vec::new();
    io::stdin().lock().read_to_end(&mut input)?;
    let mut output = io::stdout().lock();
    output.write_all(&transform(&input)?)?;
    output.flush()?;
    Ok(())
}
