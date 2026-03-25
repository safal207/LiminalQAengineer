// ---------------------------------------------------------------------------
// In-process alert notifications
// ---------------------------------------------------------------------------
//
// Reads configuration from environment variables at startup:
//
//   LIMINAL_ALERT_WEBHOOK_URL  — Slack incoming-webhook URL (optional)
//
// When set, `AlertManager::notify` fires a non-blocking POST to that URL
// every time a new regression or flaky test is detected during ingest.
// Failures are logged but never surfaced to callers.
//
// NOTE: The built-in HTTP sender supports plain HTTP only.  For HTTPS
// webhooks (standard Slack) place the server behind a TLS-terminating
// reverse proxy (nginx/caddy) that forwards to a local HTTP listener, or
// add `reqwest` with the `rustls-tls` feature to the workspace.

use std::env;
use tracing::{info, warn};

// ---------------------------------------------------------------------------
// Alert severity
// ---------------------------------------------------------------------------

/// Severity level of an alert notification.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum AlertSeverity {
    Info,
    Warning,
    Critical,
}

impl AlertSeverity {
    fn emoji(self) -> &'static str {
        match self {
            AlertSeverity::Info => ":information_source:",
            AlertSeverity::Warning => ":warning:",
            AlertSeverity::Critical => ":rotating_light:",
        }
    }

    fn label(self) -> &'static str {
        match self {
            AlertSeverity::Info => "INFO",
            AlertSeverity::Warning => "WARNING",
            AlertSeverity::Critical => "CRITICAL",
        }
    }
}

// ---------------------------------------------------------------------------
// AlertManager
// ---------------------------------------------------------------------------

/// Lightweight alert dispatcher backed by Slack incoming-webhooks.
///
/// Instantiate once at server startup with [`AlertManager::from_env`].
/// Call [`AlertManager::notify`] from any async context — it spawns a
/// fire-and-forget task so it never blocks the caller.
#[derive(Clone, Debug)]
pub struct AlertManager {
    webhook_url: Option<String>,
}

impl AlertManager {
    /// Build from environment.  If `LIMINAL_ALERT_WEBHOOK_URL` is not set,
    /// notifications are simply logged and not sent over HTTP.
    pub fn from_env() -> Self {
        let webhook_url = env::var("LIMINAL_ALERT_WEBHOOK_URL").ok();
        if webhook_url.is_some() {
            info!("Alert webhook configured");
        } else {
            info!("LIMINAL_ALERT_WEBHOOK_URL not set — alerts will be logged only");
        }
        Self { webhook_url }
    }

    /// Send an alert asynchronously (fire-and-forget).
    ///
    /// Returns immediately; the HTTP POST happens on a spawned Tokio task.
    pub fn notify(&self, severity: AlertSeverity, summary: &str, detail: &str) {
        let message = format!(
            "{} *[{}]* {}\n{}",
            severity.emoji(),
            severity.label(),
            summary,
            detail
        );

        // Always log the alert locally
        match severity {
            AlertSeverity::Critical => warn!("[ALERT/CRITICAL] {} — {}", summary, detail),
            AlertSeverity::Warning => warn!("[ALERT/WARNING] {} — {}", summary, detail),
            AlertSeverity::Info => info!("[ALERT/INFO] {} — {}", summary, detail),
        }

        if let Some(url) = self.webhook_url.clone() {
            tokio::spawn(async move {
                if let Err(e) = post_webhook(&url, &message).await {
                    warn!("Alert webhook delivery failed: {}", e);
                }
            });
        }
    }
}

// ---------------------------------------------------------------------------
// Minimal HTTP/1.1 POST over plain TCP (no extra dependencies)
// ---------------------------------------------------------------------------

/// Parse `http://host[:port]/path` into `(host, port, path)`.
fn parse_http_url(url: &str) -> Result<(String, u16, String), String> {
    let rest = url
        .strip_prefix("http://")
        .ok_or("only http:// webhooks are supported; use a TLS proxy for https://")?;
    let (authority, path) = match rest.find('/') {
        Some(pos) => (&rest[..pos], &rest[pos..]),
        None => (rest, "/"),
    };
    let (host, port) = match authority.find(':') {
        Some(pos) => {
            let p: u16 = authority[pos + 1..]
                .parse()
                .map_err(|_| "invalid port in webhook URL")?;
            (authority[..pos].to_owned(), p)
        }
        None => (authority.to_owned(), 80u16),
    };
    Ok((host, port, path.to_owned()))
}

async fn post_webhook(url: &str, message: &str) -> Result<(), String> {
    use tokio::io::AsyncWriteExt;

    let (host, port, path) = parse_http_url(url)?;

    // Slack-compatible JSON body: `{"text": "..."}`.
    // Escape only the characters that would break JSON string literals.
    let escaped = message
        .replace('\\', "\\\\")
        .replace('"', "\\\"")
        .replace('\n', "\\n")
        .replace('\r', "\\r");
    let body = format!("{{\"text\":\"{}\"}}", escaped);

    let request = format!(
        "POST {} HTTP/1.1\r\nHost: {}\r\nContent-Type: application/json\r\nContent-Length: {}\r\nConnection: close\r\n\r\n{}",
        path,
        host,
        body.len(),
        body
    );

    let addr = format!("{}:{}", host, port);
    let mut stream = tokio::net::TcpStream::connect(&addr)
        .await
        .map_err(|e| format!("connect to {}: {}", addr, e))?;

    stream
        .write_all(request.as_bytes())
        .await
        .map_err(|e| format!("write: {}", e))?;

    stream.flush().await.map_err(|e| format!("flush: {}", e))?;

    // Read just the status line to check success; ignore the body.
    let mut buf = [0u8; 256];
    use tokio::io::AsyncReadExt;
    let n = stream
        .read(&mut buf)
        .await
        .map_err(|e| format!("read: {}", e))?;
    let response = std::str::from_utf8(&buf[..n]).unwrap_or("");

    // HTTP/1.1 200 OK  or  HTTP/1.1 2xx
    if !response.starts_with("HTTP/1.1 2") && !response.starts_with("HTTP/1.0 2") {
        let status_line = response.lines().next().unwrap_or(response);
        return Err(format!("webhook returned: {}", status_line));
    }
    Ok(())
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn parse_standard_url() {
        let (host, port, path) = parse_http_url("http://hooks.example.com/services/abc").unwrap();
        assert_eq!(host, "hooks.example.com");
        assert_eq!(port, 80);
        assert_eq!(path, "/services/abc");
    }

    #[test]
    fn parse_url_with_port() {
        let (host, port, path) = parse_http_url("http://localhost:9000/hook").unwrap();
        assert_eq!(host, "localhost");
        assert_eq!(port, 9000);
        assert_eq!(path, "/hook");
    }

    #[test]
    fn parse_https_fails_gracefully() {
        assert!(parse_http_url("https://hooks.slack.com/services/xyz").is_err());
    }

    #[test]
    fn alert_manager_no_env_does_not_panic() {
        // Ensure constructing without the env var works fine
        std::env::remove_var("LIMINAL_ALERT_WEBHOOK_URL");
        let mgr = AlertManager::from_env();
        assert!(mgr.webhook_url.is_none());
    }
}
