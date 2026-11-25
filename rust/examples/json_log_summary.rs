use serde::Deserialize;
use std::error::Error;
use std::io::{self, Read};

#[derive(Deserialize)]
struct Entry {
    status: u16,
    bytes: u64,
    path: String,
}

fn main() -> Result<(), Box<dyn Error>> {
    let mut input = Vec::new();
    io::stdin().lock().read_to_end(&mut input)?;
    let entries: Vec<Entry> = serde_json::from_slice(&input)?;

    let mut errors = 0usize;
    let mut error_bytes = 0u64;
    let mut longest_path = 0;
    for entry in entries {
        if (500..600).contains(&entry.status) {
            errors += 1;
            error_bytes += entry.bytes;
        }
        longest_path = longest_path.max(entry.path.len());
    }
    println!("{errors} {error_bytes} {longest_path}");
    Ok(())
}
