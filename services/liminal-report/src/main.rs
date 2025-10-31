//! Liminal Report Generator - Create Reflection reports from LIMINAL-DB

mod query;
mod render;

use anyhow::{Context, Result};
use std::env;
use std::path::PathBuf;
use tracing::info;
use tracing_subscriber::{layer::SubscriberExt, util::SubscriberInitExt, EnvFilter};
use uuid::Uuid;

#[tokio::main]
async fn main() -> Result<()> {
    // Initialize tracing
    tracing_subscriber::registry()
        .with(EnvFilter::from_default_env())
        .with(tracing_subscriber::fmt::layer())
        .init();

    info!("Starting Liminal Report Generator");

    // Get arguments
    let args: Vec<String> = env::args().collect();
    if args.len() < 2 {
        eprintln!("Usage: liminal-report <run-id> [output-path]");
        std::process::exit(1);
    }

    let run_id_str = &args[1];
    let run_id = Uuid::parse_str(run_id_str).context("Invalid run ID")?;

    let output_path = if args.len() >= 3 {
        PathBuf::from(&args[2])
    } else {
        PathBuf::from(format!("/var/liminal/runs/{}/report/index.html", run_id))
    };

    // Connect to database
    let pg_url = env::var("LIMINAL_PG_URL")
        .unwrap_or_else(|_| "postgres://liminal:liminal@localhost:5432/liminal".to_string());

    info!("Connecting to database");
    let pool = sqlx::PgPool::connect(&pg_url).await?;

    // Query data
    info!("Querying data for run {}", run_id);
    let report = query::build_report(&pool, run_id).await?;

    // Render HTML
    info!("Rendering HTML report");
    let html = render::render_html(&report)?;

    // Write to file
    if let Some(parent) = output_path.parent() {
        std::fs::create_dir_all(parent)?;
    }
    std::fs::write(&output_path, html)?;

    info!("Report generated: {}", output_path.display());
    println!("✅ Report generated: {}", output_path.display());

    Ok(())
}
