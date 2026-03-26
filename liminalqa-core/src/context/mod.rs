//! Contextual interpretation of signals.
//!
//! A signal's importance changes depending on *when* and *where* it was
//! observed. This module provides a lightweight `SignalContext` that carries
//! three independent axes and translates them into a multiplier applied on
//! top of the base `SignalImportance` score.
//!
//! ## Axes
//!
//! | Axis        | Values                              | Effect |
//! |-------------|-------------------------------------|--------|
//! | Environment | `Prod` > `Staging` > `Dev`          | Prod signals matter more |
//! | Time window | `BusinessHours` > `OffHours` > `Night` | Night failures are less urgent |
//! | Load level  | `High` > `Normal` > `Low`           | High-load failures may be infra noise |
//!
//! ## Usage
//!
//! ```ignore
//! let ctx = SignalContext::new(Environment::Prod, TimeWindow::BusinessHours, LoadLevel::Normal);
//! let adjusted = ctx.apply(base_importance);
//! ```

use chrono::{Datelike, Timelike, Weekday};

// ---------------------------------------------------------------------------
// Environment
// ---------------------------------------------------------------------------

/// The environment in which the signal was captured.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub enum Environment {
    /// Production — highest weight; every failure is customer-impacting.
    Prod,
    /// Staging / pre-prod — medium weight; likely real but not customer-facing.
    Staging,
    /// Development / CI — lowest weight; expected instability.
    Dev,
}

impl Environment {
    /// Base multiplier for the environment axis (0.6–1.2).
    pub fn multiplier(self) -> f64 {
        match self {
            Environment::Prod => 1.20,
            Environment::Staging => 1.00,
            Environment::Dev => 0.60,
        }
    }

    /// Infer environment from a string label (case-insensitive).
    /// Falls back to `Dev` for unknown values.
    pub fn from_label(label: &str) -> Self {
        match label.to_lowercase().as_str() {
            "prod" | "production" => Environment::Prod,
            "staging" | "stage" | "preprod" | "pre-prod" => Environment::Staging,
            _ => Environment::Dev,
        }
    }
}

// ---------------------------------------------------------------------------
// Time window
// ---------------------------------------------------------------------------

/// The time-of-day / day-of-week bucket when the signal was observed.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub enum TimeWindow {
    /// Monday–Friday 08:00–18:00 UTC — on-call engineers are awake.
    BusinessHours,
    /// Monday–Friday 18:00–23:00 or Saturday–Sunday daytime.
    OffHours,
    /// 23:00–08:00 UTC — failures during batch jobs / nightlies.
    Night,
}

impl TimeWindow {
    /// Multiplier for the time axis (0.8–1.1).
    ///
    /// Night failures are scored *slightly* lower because automated nightly
    /// runs have inherently higher noise; business-hours failures are scored
    /// higher because they impact active work.
    pub fn multiplier(self) -> f64 {
        match self {
            TimeWindow::BusinessHours => 1.10,
            TimeWindow::OffHours => 1.00,
            TimeWindow::Night => 0.80,
        }
    }

    /// Classify a UTC datetime into a `TimeWindow`.
    pub fn from_datetime(dt: &chrono::DateTime<chrono::Utc>) -> Self {
        let hour = dt.hour(); // 0–23 UTC
        let weekday = dt.weekday();
        let is_weekend = matches!(weekday, Weekday::Sat | Weekday::Sun);

        if is_weekend {
            if (8..20).contains(&hour) {
                return TimeWindow::OffHours;
            }
            return TimeWindow::Night;
        }

        // Weekday
        if (8..18).contains(&hour) {
            TimeWindow::BusinessHours
        } else if (18..23).contains(&hour) {
            TimeWindow::OffHours
        } else {
            TimeWindow::Night
        }
    }
}

// ---------------------------------------------------------------------------
// Load level
// ---------------------------------------------------------------------------

/// The system load level at the time the signal was observed.
///
/// High-load failures may be infrastructure noise rather than test bugs.
/// The noise filter (Z-score / IQR) removes statistical outliers, but the
/// load level provides a softer adjustment on the remaining signals.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub enum LoadLevel {
    /// CPU/traffic well below normal — failures are likely genuine.
    Low,
    /// Normal operating range.
    Normal,
    /// Elevated CPU / request rate — some failures are load-induced noise.
    High,
}

impl LoadLevel {
    /// Multiplier for the load axis (0.85–1.05).
    pub fn multiplier(self) -> f64 {
        match self {
            LoadLevel::Low => 1.05,
            LoadLevel::Normal => 1.00,
            LoadLevel::High => 0.85,
        }
    }

    /// Infer load level from a CPU utilisation percentage (0–100).
    pub fn from_cpu_pct(cpu_pct: f64) -> Self {
        if cpu_pct < 40.0 {
            LoadLevel::Low
        } else if cpu_pct < 80.0 {
            LoadLevel::Normal
        } else {
            LoadLevel::High
        }
    }

    /// Infer load level from requests-per-second relative to a known baseline.
    /// `ratio = current_rps / baseline_rps`.
    pub fn from_rps_ratio(ratio: f64) -> Self {
        if ratio < 0.5 {
            LoadLevel::Low
        } else if ratio < 1.5 {
            LoadLevel::Normal
        } else {
            LoadLevel::High
        }
    }
}

// ---------------------------------------------------------------------------
// SignalContext — composite
// ---------------------------------------------------------------------------

/// Combined context for a single signal observation.
///
/// The overall context multiplier is the *product* of the three axis
/// multipliers, so they are independent and compose linearly in log-space.
///
/// Range: `0.6 × 0.8 × 0.85 = 0.408` (Dev, Night, High-load)
///    to  `1.2 × 1.1 × 1.05 = 1.386` (Prod, BusinessHours, Low-load)
#[derive(Debug, Clone, Copy, PartialEq)]
pub struct SignalContext {
    pub environment: Environment,
    pub time_window: TimeWindow,
    pub load_level: LoadLevel,
}

impl Default for SignalContext {
    fn default() -> Self {
        Self {
            environment: Environment::Dev,
            time_window: TimeWindow::BusinessHours,
            load_level: LoadLevel::Normal,
        }
    }
}

impl SignalContext {
    pub fn new(environment: Environment, time_window: TimeWindow, load_level: LoadLevel) -> Self {
        Self {
            environment,
            time_window,
            load_level,
        }
    }

    /// Combined multiplier (product of all three axes).
    pub fn multiplier(&self) -> f64 {
        self.environment.multiplier() * self.time_window.multiplier() * self.load_level.multiplier()
    }

    /// Apply context to a raw importance score.
    pub fn apply(&self, base_importance: f64) -> f64 {
        base_importance * self.multiplier()
    }

    /// Build a context from a signal timestamp and optional metadata tags.
    ///
    /// `env_label` — e.g. `"prod"`, `"staging"`, `"dev"`
    /// `cpu_pct`   — 0–100 CPU utilisation at observation time (optional)
    pub fn from_signal_meta(
        timestamp: &chrono::DateTime<chrono::Utc>,
        env_label: Option<&str>,
        cpu_pct: Option<f64>,
    ) -> Self {
        let environment = env_label
            .map(Environment::from_label)
            .unwrap_or(Environment::Dev);
        let time_window = TimeWindow::from_datetime(timestamp);
        let load_level = cpu_pct
            .map(LoadLevel::from_cpu_pct)
            .unwrap_or(LoadLevel::Normal);
        Self::new(environment, time_window, load_level)
    }
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;
    use chrono::TimeZone;

    #[test]
    fn prod_business_hours_low_load_is_highest() {
        let ctx = SignalContext::new(Environment::Prod, TimeWindow::BusinessHours, LoadLevel::Low);
        let m = ctx.multiplier();
        // 1.20 * 1.10 * 1.05
        assert!((m - 1.386).abs() < 1e-9);
    }

    #[test]
    fn dev_night_high_load_is_lowest() {
        let ctx = SignalContext::new(Environment::Dev, TimeWindow::Night, LoadLevel::High);
        let m = ctx.multiplier();
        // 0.60 * 0.80 * 0.85
        assert!((m - 0.408).abs() < 1e-9);
    }

    #[test]
    fn apply_scales_correctly() {
        let ctx = SignalContext::new(Environment::Prod, TimeWindow::BusinessHours, LoadLevel::Low);
        let base = 1.0;
        assert!((ctx.apply(base) - 1.386).abs() < 1e-9);
    }

    #[test]
    fn time_window_business_hours() {
        // Monday 10:00 UTC
        let dt = chrono::Utc.with_ymd_and_hms(2025, 4, 7, 10, 0, 0).unwrap();
        assert_eq!(TimeWindow::from_datetime(&dt), TimeWindow::BusinessHours);
    }

    #[test]
    fn time_window_night() {
        // Wednesday 02:00 UTC
        let dt = chrono::Utc.with_ymd_and_hms(2025, 4, 9, 2, 0, 0).unwrap();
        assert_eq!(TimeWindow::from_datetime(&dt), TimeWindow::Night);
    }

    #[test]
    fn time_window_weekend_off_hours() {
        // Saturday 12:00 UTC
        let dt = chrono::Utc.with_ymd_and_hms(2025, 4, 12, 12, 0, 0).unwrap();
        assert_eq!(TimeWindow::from_datetime(&dt), TimeWindow::OffHours);
    }

    #[test]
    fn environment_from_label() {
        assert_eq!(Environment::from_label("production"), Environment::Prod);
        assert_eq!(Environment::from_label("PROD"), Environment::Prod);
        assert_eq!(Environment::from_label("staging"), Environment::Staging);
        assert_eq!(Environment::from_label("preprod"), Environment::Staging);
        assert_eq!(Environment::from_label("dev"), Environment::Dev);
        assert_eq!(Environment::from_label("unknown"), Environment::Dev);
    }

    #[test]
    fn load_level_from_cpu() {
        assert_eq!(LoadLevel::from_cpu_pct(20.0), LoadLevel::Low);
        assert_eq!(LoadLevel::from_cpu_pct(60.0), LoadLevel::Normal);
        assert_eq!(LoadLevel::from_cpu_pct(90.0), LoadLevel::High);
    }
}
