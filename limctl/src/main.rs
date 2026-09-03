//! limctl — LiminalQA CLI tool
//!
//! Usage:
//!   limctl run <plan.yaml>       — Execute test plan
//!   limctl collect <run-id>      — Collect artifacts from run
//!   limctl report <run-id>       — Generate reflection report
//!   limctl query <query.json>    — Query LIMINAL-DB
//!   limctl list runs             — List all runs
//!   limctl list tests <run-id>   — List tests for a run
//!   limctl import-cgqa           — Validate bounded CGQA evidence offline
//!   limctl export-cgqa-candidates — Derive non-authoritative CGQA seeds offline

use anyhow::{Context, Result};
use clap::{Parser, Subcommand};
use liminalqa_db::LiminalDB;
use std::path::PathBuf;
use tracing::Level;
use tracing_subscriber::FmtSubscriber;

mod commands;

use commands::*;

#[derive(Parser)]
#[command(name = "limctl")]
#[command(about = "LiminalQA control CLI", long_about = None)]
#[command(version)]
struct Cli {
    /// Path to LIMINAL-DB
    #[arg(
        short,
        long,
        env = "LIMINAL_DB_PATH",
        default_value = "./data/liminaldb"
    )]
    db_path: PathBuf,

    /// Verbosity level
    #[arg(short, long, action = clap::ArgAction::Count)]
    verbose: u8,

    #[command(subcommand)]
    command: Commands,
}

#[derive(Subcommand)]
enum Commands {
    /// Execute a test plan
    Run {
        /// Path to test plan YAML
        plan: PathBuf,
    },

    /// Collect artifacts from a run
    Collect {
        /// Run ID
        run_id: String,
    },

    /// Generate reflection report
    Report {
        /// Run ID
        run_id: String,

        /// Output format
        #[arg(short, long, default_value = "html")]
        format: ReportFormat,

        /// Output path
        #[arg(short, long)]
        output: Option<PathBuf>,
    },

    /// Query LIMINAL-DB
    Query {
        /// Query JSON file
        query: PathBuf,
    },

    /// List entities
    List {
        #[command(subcommand)]
        entity: ListEntity,
    },

    /// Initialize a new LiminalQA project
    Init {
        /// Project directory
        #[arg(default_value = ".")]
        directory: PathBuf,
    },

    /// Validate bounded ContractGraph-QA evidence without opening LIMINAL-DB
    ImportCgqa {
        /// ContractGraph-QA LiminalQA Evidence v0.1 JSON
        #[arg(long)]
        input: PathBuf,

        /// Destination import receipt JSON
        #[arg(long)]
        output: PathBuf,

        /// Replace an existing regular output file
        #[arg(long)]
        force: bool,
    },

    /// Derive non-authoritative candidate seeds from bounded CGQA evidence
    ExportCgqaCandidates {
        /// ContractGraph-QA LiminalQA Evidence v0.1 JSON
        #[arg(long)]
        input: PathBuf,

        /// Destination candidate export JSON
        #[arg(long)]
        output: PathBuf,

        /// Derivation time as RFC 3339 with explicit offset
        #[arg(long)]
        derived_at: String,

        /// Identifier for this derivation operation
        #[arg(long)]
        operation_id: String,

        /// Identifier for this derivation attempt
        #[arg(long)]
        attempt_id: String,

        /// Replace an existing regular output file
        #[arg(long)]
        force: bool,
    },
}

#[derive(Subcommand)]
enum ListEntity {
    /// List all runs
    Runs,

    /// List tests for a run
    Tests {
        /// Run ID
        run_id: String,
    },

    /// List systems
    Systems,
}

#[derive(Debug, Clone, clap::ValueEnum)]
enum ReportFormat {
    Html,
    Json,
    Markdown,
}

#[tokio::main]
async fn main() -> Result<()> {
    let cli = Cli::parse();

    // Initialize tracing
    let level = match cli.verbose {
        0 => Level::WARN,
        1 => Level::INFO,
        2 => Level::DEBUG,
        _ => Level::TRACE,
    };

    let subscriber = FmtSubscriber::builder()
        .with_max_level(level)
        .with_target(false)
        .compact()
        .finish();
    tracing::subscriber::set_global_default(subscriber)?;

    // File-only interop must not create or open LIMINAL-DB as an incidental side effect.
    match &cli.command {
        Commands::ImportCgqa {
            input,
            output,
            force,
        } => {
            return cgqa_interop_command::execute_import(input, output, *force);
        }
        Commands::ExportCgqaCandidates {
            input,
            output,
            derived_at,
            operation_id,
            attempt_id,
            force,
        } => {
            return cgqa_interop_command::execute_candidate_export(
                input,
                output,
                derived_at,
                operation_id,
                attempt_id,
                *force,
            );
        }
        _ => {}
    }

    // Open database
    let db = LiminalDB::open(&cli.db_path)
        .context(format!("Failed to open database at {:?}", cli.db_path))?;

    // Execute command
    match cli.command {
        Commands::Run { plan } => {
            run_command::execute(&db, &plan).await?;
        }
        Commands::Collect { run_id } => {
            collect_command::execute(&db, &run_id).await?;
        }
        Commands::Report {
            run_id,
            format,
            output,
        } => {
            report_command::execute(&db, &run_id, format, output).await?;
        }
        Commands::Query { query } => {
            query_command::execute(&db, &query).await?;
        }
        Commands::List { entity } => match entity {
            ListEntity::Runs => {
                list_runs_command::execute(&db).await?;
            }
            ListEntity::Tests { run_id } => {
                list_tests_command::execute(&db, &run_id).await?;
            }
            ListEntity::Systems => {
                list_systems_command::execute(&db).await?;
            }
        },
        Commands::Init { directory } => {
            init_command::execute(&directory).await?;
        }
        Commands::ImportCgqa { .. } | Commands::ExportCgqaCandidates { .. } => {
            unreachable!("file-only interop commands returned before opening LIMINAL-DB")
        }
    }

    Ok(())
}
