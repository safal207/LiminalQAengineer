//! Report command

use anyhow::{Context, Result};
use liminalqa_core::{
    entities::{EntityType, Run, Test},
    types::EntityId,
};
use liminalqa_db::LiminalDB;
use std::path::PathBuf;
use std::fs;

pub async fn execute(
    db: &LiminalDB,
    run_id: &str,
    format: crate::ReportFormat,
    output: Option<PathBuf>,
) -> Result<()> {
    println!("📊 Generating reflection report for run: {}", run_id);
    println!("   Format: {:?}", format);

    if let Some(ref path) = output {
        println!("   Output: {}", path.display());
    }

    // Convert run_id string to EntityId
    let entity_id = EntityId::from_string(run_id)
        .context("Invalid run ID format")?;

    // Get the run from the database
    let run: Option<Run> = db.get_entity(entity_id)?;
    
    if let Some(run) = run {
        println!("   Plan: {}", run.plan_name);
        println!("   Started: {}", run.started_at.format("%Y-%m-%d %H:%M:%S UTC"));
        
        // Get all tests for this run
        let all_test_ids = db.get_entities_by_type(EntityType::Test)?;
        let run_tests: Vec<Test> = all_test_ids
            .into_iter()
            .filter_map(|id| {
                if let Ok(Some(test)) = db.get_entity::<Test>(id) {
                    if test.run_id == entity_id {
                        Some(test)
                    } else {
                        None
                    }
                } else {
                    None
                }
            })
            .collect();

        println!("   Found {} tests for this run", run_tests.len());

        let report_content = match format {
            crate::ReportFormat::Html => generate_html_report(&run, &run_tests)?,
            crate::ReportFormat::Json => generate_json_report(&run, &run_tests)?,
            crate::ReportFormat::Markdown => generate_markdown_report(&run, &run_tests)?,
        };

        match output {
            Some(output_path) => {
                fs::write(&output_path, report_content)
                    .context(format!("Failed to write report to {}", output_path.display()))?;
                println!("✅ Report saved to: {}", output_path.display());
            },
            None => {
                println!("{}", report_content);
            }
        }

        Ok(())
    } else {
        println!("❌ Run not found: {}", run_id);
        anyhow::bail!("Run not found: {}", run_id);
    }
}

fn generate_html_report(run: &Run, tests: &[Test]) -> Result<String> {
    let passed_count = tests.iter().filter(|t| t.status.is_pass()).count();
    let failed_count = tests.len() - passed_count;
    
    let mut html = String::new();
    html.push_str("<!DOCTYPE html>\n");
    html.push_str("<html>\n<head>\n<title>LiminalQA Report</title>\n");
    html.push_str("<style>\n");
    html.push_str("body { font-family: Arial, sans-serif; margin: 20px; }\n");
    html.push_str(".summary { background-color: #f5f5f5; padding: 15px; border-radius: 5px; margin-bottom: 20px; }\n");
    html.push_str(".passed { color: green; }\n");
    html.push_str(".failed { color: red; }\n");
    html.push_str("table { border-collapse: collapse; width: 100%; }\n");
    html.push_str("th, td { border: 1px solid #ddd; padding: 8px; text-align: left; }\n");
    html.push_str("th { background-color: #f2f2f2; }\n");
    html.push_str("</style>\n</head>\n<body>\n");
    
    html.push_str("<h1>LiminalQA Test Report</h1>\n");
    
    html.push_str("<div class=\"summary\">\n");
    html.push_str(&format!("<h2>Run Summary</h2>\n"));
    html.push_str(&format!("<p><strong>Plan:</strong> {}</p>\n", run.plan_name));
    html.push_str(&format!("<p><strong>Start Time:</strong> {}</p>\n", run.started_at));
    if let Some(end_time) = run.ended_at {
        html.push_str(&format!("<p><strong>End Time:</strong> {}</p>\n", end_time));
    }
    html.push_str(&format!("<p><strong>Status:</strong> {}</p>\n", if run.ended_at.is_some() { "Completed" } else { "Running" }));
    html.push_str(&format!(
        "<p><strong>Results:</strong> <span class=\"passed\">{} passed</span>, <span class=\"failed\">{} failed</span></p>\n",
        passed_count, failed_count
    ));
    html.push_str("</div>\n");
    
    html.push_str("<h2>Test Results</h2>\n");
    html.push_str("<table>\n");
    html.push_str("<thead>\n<tr><th>Name</th><th>Suite</th><th>Status</th><th>Duration (ms)</th><th>Started</th></tr>\n</thead>\n");
    html.push_str("<tbody>\n");
    
    for test in tests {
        let status_class = if test.status.is_pass() { "passed" } else { "failed" };
        html.push_str(&format!(
            "<tr><td>{}</td><td>{}</td><td class=\"{}\">{}</td><td>{}</td><td>{}</td></tr>\n",
            test.name,
            test.suite,
            status_class,
            format!("{:?}", test.status).to_lowercase(),
            test.duration_ms,
            test.started_at.format("%H:%M:%S%.3f")
        ));
    }
    
    html.push_str("</tbody>\n</table>\n");
    html.push_str("\n</body>\n</html>");
    
    Ok(html)
}

fn generate_json_report(run: &Run, tests: &[Test]) -> Result<String> {
    use serde_json::json;
    
    let report = json!({
        "run": {
            "id": run.id.to_string(),
            "plan_name": run.plan_name,
            "started_at": run.started_at,
            "ended_at": run.ended_at,
            "completed": run.ended_at.is_some(),
        },
        "summary": {
            "total": tests.len(),
            "passed": tests.iter().filter(|t| t.status.is_pass()).count(),
            "failed": tests.len() - tests.iter().filter(|t| t.status.is_pass()).count(),
        },
        "tests": tests.iter().map(|test| json!({
            "name": test.name,
            "suite": test.suite,
            "status": format!("{:?}", test.status).to_lowercase(),
            "duration_ms": test.duration_ms,
            "started_at": test.started_at,
            "completed_at": test.completed_at,
            "guidance": test.guidance,
        })).collect::<Vec<_>>()
    });
    
    Ok(serde_json::to_string_pretty(&report)?)
}

fn generate_markdown_report(run: &Run, tests: &[Test]) -> Result<String> {
    let passed_count = tests.iter().filter(|t| t.status.is_pass()).count();
    let failed_count = tests.len() - passed_count;
    
    let mut md = String::new();
    md.push_str("# LiminalQA Test Report\n\n");
    
    md.push_str("## Run Summary\n\n");
    md.push_str(&format!("**Plan:** {}\n\n", run.plan_name));
    md.push_str(&format!("**Start Time:** {}\n\n", run.started_at));
    if let Some(end_time) = run.ended_at {
        md.push_str(&format!("**End Time:** {}\n\n", end_time));
    }
    md.push_str(&format!("**Status:** {}\n\n", if run.ended_at.is_some() { "Completed" } else { "Running" }));
    md.push_str(&format!(
        "**Results:** {} passed, {} failed\n\n",
        passed_count, failed_count
    ));
    
    md.push_str("## Test Results\n\n");
    md.push_str("| Name | Suite | Status | Duration (ms) | Started |\n");
    md.push_str("|------|-------|--------|---------------|---------|\n");
    
    for test in tests {
        let status = if test.status.is_pass() { 
            format!("✅ {:?}", test.status).to_lowercase() 
        } else { 
            format!("❌ {:?}", test.status).to_lowercase() 
        };
        md.push_str(&format!(
            "| {} | {} | {} | {} | {} |\n",
            test.name,
            test.suite,
            status,
            test.duration_ms,
            test.started_at.format("%H:%M:%S%.3f")
        ));
    }
    
    Ok(md)
}