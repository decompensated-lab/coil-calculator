//! Check binary: answers kernel requests from pytest over stdin/stdout (see `wire`).

mod wire;

use std::io::{self, BufReader, BufWriter};
use wire::Array;

fn dispatch(name: &str, args: Vec<Array>) -> Result<Vec<Array>, String> {
    match name {
        "echo" => Ok(args),
        _ => Err(format!("unknown function {name:?}")),
    }
}

fn main() -> io::Result<()> {
    let mut input = BufReader::new(io::stdin().lock());
    let mut output = BufWriter::new(io::stdout().lock());
    while let Some((name, args)) = wire::read_request(&mut input)? {
        wire::write_response(&mut output, &dispatch(&name, args))?;
    }
    Ok(())
}
