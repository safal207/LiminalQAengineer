//! Init command

use anyhow::Result;
use std::path::PathBuf;

pub async fn execute(directory: &PathBuf) -> Result<()> {
    println!("Initializing LiminalQA project in {:?}", directory);
    // Stub
    Ok(())
}
