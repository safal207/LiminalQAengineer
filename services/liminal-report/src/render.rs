//! HTML report rendering

use anyhow::Result;
use handlebars::Handlebars;
use liminalqa_core::report::ReflectionReport;

const TEMPLATE: &str = include_str!("../templates/reflection.html");

pub fn render_html(report: &ReflectionReport) -> Result<String> {
    let mut handlebars = Handlebars::new();
    handlebars.register_template_string("reflection", TEMPLATE)?;

    // Prepare data for template
    let data = serde_json::json!({
        "run_id": report.run_id,
        "plan_name": report.plan_name,
        "started_at": report.started_at.format("%Y-%m-%d %H:%M:%S UTC"),
        "ended_at": report.ended_at.map(|dt| dt.format("%Y-%m-%d %H:%M:%S UTC").to_string()),
        "duration": report.ended_at.map(|end| {
            let duration = (end - report.started_at).num_seconds();
            format_duration(duration)
        }),
        "summary": {
            "total": report.summary.total,
            "passed": report.summary.passed,
            "failed": report.summary.failed,
            "flake": report.summary.flake,
            "timeout": report.summary.timeout,
            "skip": report.summary.skip,
            "pass_rate": if report.summary.total > 0 {
                (report.summary.passed as f64 / report.summary.total as f64 * 100.0).round() as i64
            } else {
                0
            },
        },
        "timeline": report.timeline.iter().map(|b| {
            serde_json::json!({
                "bucket": b.bucket.format("%H:%M").to_string(),
                "status": b.status,
                "count": b.count,
                "status_class": status_class(&b.status),
            })
        }).collect::<Vec<_>>(),
        "slow_tests": report.top_slow_tests.iter().map(|t| {
            serde_json::json!({
                "name": t.name,
                "suite": t.suite,
                "duration_ms": t.duration_ms,
                "duration_sec": format!("{:.2}s", t.duration_ms as f64 / 1000.0),
                "status": t.status,
                "status_class": status_class(&t.status),
            })
        }).collect::<Vec<_>>(),
        "causality_trails": report.causality_trails.iter().map(|trail| {
            serde_json::json!({
                "test_name": trail.test_name,
                "failed_at": trail.test_failed_at.format("%H:%M:%S").to_string(),
                "signals": trail.signals.iter().map(|sig| {
                    serde_json::json!({
                        "kind": sig.kind,
                        "at": sig.at.format("%H:%M:%S%.3f").to_string(),
                        "time_diff": format_time_diff(sig.time_diff_seconds),
                        "value": sig.value,
                        "meta": sig.meta,
                    })
                }).collect::<Vec<_>>(),
            })
        }).collect::<Vec<_>>(),
    });

    let html = handlebars.render("reflection", &data)?;
    Ok(html)
}

fn status_class(status: &str) -> &str {
    match status {
        "pass" => "pass",
        "fail" => "fail",
        "flake" => "flake",
        "timeout" => "timeout",
        _ => "skip",
    }
}

fn format_duration(seconds: i64) -> String {
    let mins = seconds / 60;
    let secs = seconds % 60;
    if mins > 0 {
        format!("{}m {}s", mins, secs)
    } else {
        format!("{}s", secs)
    }
}

fn format_time_diff(seconds: i32) -> String {
    if seconds < 0 {
        format!("{}s before", -seconds)
    } else if seconds > 0 {
        format!("{}s after", seconds)
    } else {
        "at same time".to_string()
    }
}
