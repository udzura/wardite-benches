use std::error::Error;
use std::io::{self, BufReader};
use xml::reader::{EventReader, XmlEvent};

fn main() -> Result<(), Box<dyn Error>> {
    let input = BufReader::new(io::stdin().lock());
    let mut path = Vec::new();
    let mut items = 0u64;
    let mut title_chars = 0u64;
    let mut in_title = false;

    for event in EventReader::new(input) {
        match event? {
            XmlEvent::StartElement { name, .. } => {
                // Namespaced RSS extensions cannot match the core element names.
                path.push(if name.namespace.is_none() {
                    name.local_name
                } else {
                    String::new()
                });
                if path == ["rss", "channel", "item"] {
                    items += 1;
                } else if path == ["rss", "channel", "item", "title"] {
                    in_title = true;
                }
            }
            XmlEvent::EndElement { .. } => {
                if path.len() == 4 {
                    in_title = false;
                }
                path.pop();
            }
            XmlEvent::Characters(text) | XmlEvent::CData(text) | XmlEvent::Whitespace(text)
                if in_title =>
            {
                title_chars += text.chars().count() as u64;
            }
            _ => {}
        }
    }
    println!("{items} {title_chars}");
    Ok(())
}
