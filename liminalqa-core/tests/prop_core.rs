//! Property-based tests for liminalqa-core.
//!
//! Run with: cargo test -p liminalqa-core

use chrono::{DateTime, TimeZone, Utc};
use liminalqa_core::{
    facts::{Attribute, Fact, FactBatch},
    temporal::{BiTemporalTime, TimeRange, TimeshiftQuery},
    types::{EntityId, TestStatus},
};
use proptest::prelude::*;

// ---------------------------------------------------------------------------
// Strategies
// ---------------------------------------------------------------------------

/// DateTime<Utc> in a realistic range (2000-01-01 to 2030-01-01).
fn arb_datetime() -> impl Strategy<Value = DateTime<Utc>> {
    const BASE_MS: i64 = 946_684_800_000; // 2000-01-01
    const RANGE_MS: i64 = 946_080_000_000; // ~30 years in ms
    (0i64..RANGE_MS).prop_map(move |offset| Utc.timestamp_millis_opt(BASE_MS + offset).unwrap())
}

fn arb_bitemporal() -> impl Strategy<Value = BiTemporalTime> {
    (arb_datetime(), arb_datetime()).prop_map(|(vt, tx)| BiTemporalTime::with_times(vt, tx))
}

fn arb_entity_id() -> impl Strategy<Value = EntityId> {
    any::<u128>().prop_map(EntityId::from)
}

fn arb_attribute() -> impl Strategy<Value = Attribute> {
    prop_oneof![
        Just(Attribute::TestStatus),
        Just(Attribute::TestDuration),
        Just(Attribute::TestError),
        Just(Attribute::TestGuidance),
        Just(Attribute::ApiLatency),
        Just(Attribute::ApiStatusCode),
        Just(Attribute::RunStatus),
        Just(Attribute::ResonanceScore),
        "[a-z]{3,10}".prop_map(|s| Attribute::Custom(s)),
    ]
}

fn arb_json_value() -> impl Strategy<Value = serde_json::Value> {
    prop_oneof![
        any::<i64>().prop_map(|n| serde_json::json!(n)),
        "[a-zA-Z0-9 ]{0,40}".prop_map(|s: String| serde_json::json!(s)),
        any::<bool>().prop_map(|b| serde_json::json!(b)),
    ]
}

fn arb_fact() -> impl Strategy<Value = Fact> {
    (
        arb_entity_id(),
        arb_attribute(),
        arb_json_value(),
        arb_bitemporal(),
    )
        .prop_map(|(entity_id, attribute, value, time)| {
            Fact::with_time(entity_id, attribute, value, time)
        })
}

fn arb_test_status() -> impl Strategy<Value = TestStatus> {
    prop_oneof![
        Just(TestStatus::Pass),
        Just(TestStatus::Fail),
        Just(TestStatus::XFail),
        Just(TestStatus::Flake),
        Just(TestStatus::Timeout),
        Just(TestStatus::Skip),
    ]
}

// ---------------------------------------------------------------------------
// TimeRange properties
// ---------------------------------------------------------------------------

proptest! {
    /// The start instant is always contained in an open-ended range.
    #[test]
    fn prop_timerange_contains_start(t in arb_datetime()) {
        let range = TimeRange::from(t);
        prop_assert!(range.contains(t));
    }

    /// A point before start is never contained.
    #[test]
    fn prop_timerange_excludes_before_start(
        start in arb_datetime(),
        offset_ms in 1i64..86_400_000i64,
    ) {
        let before_ms = start.timestamp_millis() - offset_ms;
        let before = Utc.timestamp_millis_opt(before_ms).unwrap();
        let range = TimeRange::from(start);
        prop_assert!(!range.contains(before));
    }

    /// Any point in [start, end] is contained.
    #[test]
    fn prop_timerange_contains_interior(
        start in arb_datetime(),
        offset_a in 0i64..500_000i64,
        offset_b in 0i64..500_000i64,
    ) {
        let (lo, hi) = if offset_a <= offset_b {
            (offset_a, offset_b)
        } else {
            (offset_b, offset_a)
        };
        let mid = Utc.timestamp_millis_opt(start.timestamp_millis() + lo).unwrap();
        let end = Utc.timestamp_millis_opt(start.timestamp_millis() + hi).unwrap();
        let range = TimeRange::between(start, end);
        prop_assert!(range.contains(mid));
    }

    /// A point strictly after end is never contained.
    #[test]
    fn prop_timerange_excludes_after_end(
        start in arb_datetime(),
        end_offset in 0i64..500_000i64,
        extra in 1i64..86_400_000i64,
    ) {
        let end = Utc.timestamp_millis_opt(start.timestamp_millis() + end_offset).unwrap();
        let after = Utc.timestamp_millis_opt(end.timestamp_millis() + extra).unwrap();
        let range = TimeRange::between(start, end);
        prop_assert!(!range.contains(after));
    }

    /// Open-ended range contains every point >= start.
    #[test]
    fn prop_open_range_contains_any_future(
        start in arb_datetime(),
        offset_ms in 0i64..500_000_000i64,
    ) {
        let future = Utc.timestamp_millis_opt(start.timestamp_millis() + offset_ms).unwrap();
        let range = TimeRange::from(start);
        prop_assert!(range.contains(future));
    }

    /// contains is equivalent to the manual predicate.
    #[test]
    fn prop_timerange_contains_matches_manual(
        start in arb_datetime(),
        end_offset in 0i64..500_000i64,
        check_offset in -500_000i64..1_000_000i64,
    ) {
        let end = Utc.timestamp_millis_opt(start.timestamp_millis() + end_offset).unwrap();
        let t = Utc.timestamp_millis_opt(start.timestamp_millis() + check_offset).unwrap();
        let range = TimeRange::between(start, end);

        let expected = t >= start && t <= end;
        prop_assert_eq!(range.contains(t), expected);
    }
}

// ---------------------------------------------------------------------------
// BiTemporalTime properties
// ---------------------------------------------------------------------------

proptest! {
    /// BiTemporalTime round-trips through JSON with no precision loss.
    #[test]
    fn prop_bitemporal_json_roundtrip(btt in arb_bitemporal()) {
        let json = serde_json::to_string(&btt).unwrap();
        let decoded: BiTemporalTime = serde_json::from_str(&json).unwrap();
        prop_assert_eq!(btt.valid_time, decoded.valid_time);
        prop_assert_eq!(btt.tx_time, decoded.tx_time);
    }

    /// BiTemporalTime::now() always has valid_time == tx_time (within a tick).
    #[test]
    fn prop_bitemporal_now_axes_equal(_dummy in any::<u8>()) {
        let btt = BiTemporalTime::now();
        // valid_time and tx_time are set from the same Utc::now() call
        // — they may differ by at most 1 µs in practice.
        let diff_ms = (btt.valid_time - btt.tx_time).num_milliseconds().abs();
        prop_assert!(diff_ms <= 1);
    }
}

// ---------------------------------------------------------------------------
// TimeshiftQuery properties
// ---------------------------------------------------------------------------

proptest! {
    /// TimeshiftQuery::at sets both axes to the same instant.
    #[test]
    fn prop_timeshift_at_axes_equal(t in arb_datetime()) {
        let ts = TimeshiftQuery::at(t);
        prop_assert_eq!(ts.valid_time, t);
        prop_assert_eq!(ts.tx_time, t);
    }

    /// TimeshiftQuery round-trips through JSON.
    #[test]
    fn prop_timeshift_json_roundtrip(vt in arb_datetime(), tx in arb_datetime()) {
        let ts = TimeshiftQuery::valid_at_tx(vt, tx);
        let json = serde_json::to_string(&ts).unwrap();
        let decoded: TimeshiftQuery = serde_json::from_str(&json).unwrap();
        prop_assert_eq!(ts.valid_time, decoded.valid_time);
        prop_assert_eq!(ts.tx_time, decoded.tx_time);
    }
}

// ---------------------------------------------------------------------------
// Fact properties
// ---------------------------------------------------------------------------

proptest! {
    /// Fact::new stores the supplied entity_id, attribute, and value unchanged.
    #[test]
    fn prop_fact_new_preserves_fields(
        entity_id in arb_entity_id(),
        attribute in arb_attribute(),
        value in arb_json_value(),
    ) {
        let fact = Fact::new(entity_id, attribute.clone(), value.clone());
        prop_assert_eq!(fact.entity_id, entity_id);
        prop_assert_eq!(&fact.attribute, &attribute);
        prop_assert_eq!(&fact.value, &value);
    }

    /// Fact round-trips through JSON preserving all fields.
    #[test]
    fn prop_fact_json_roundtrip(fact in arb_fact()) {
        let json = serde_json::to_string(&fact).unwrap();
        let decoded: Fact = serde_json::from_str(&json).unwrap();
        prop_assert_eq!(fact.entity_id, decoded.entity_id);
        prop_assert_eq!(&fact.attribute, &decoded.attribute);
        prop_assert_eq!(&fact.value, &decoded.value);
        prop_assert_eq!(fact.time.valid_time, decoded.time.valid_time);
        prop_assert_eq!(fact.time.tx_time, decoded.time.tx_time);
    }

    /// FactBatch preserves the exact number of facts supplied.
    #[test]
    fn prop_factbatch_preserves_count(
        facts in prop::collection::vec(arb_fact(), 0..50),
    ) {
        let n = facts.len();
        let batch = FactBatch::new(facts);
        prop_assert_eq!(batch.facts.len(), n);
    }
}

// ---------------------------------------------------------------------------
// Attribute properties
// ---------------------------------------------------------------------------

proptest! {
    /// Every Attribute variant round-trips through JSON.
    #[test]
    fn prop_attribute_json_roundtrip(attr in arb_attribute()) {
        let json = serde_json::to_string(&attr).unwrap();
        let decoded: Attribute = serde_json::from_str(&json).unwrap();
        prop_assert_eq!(attr, decoded);
    }
}

// ---------------------------------------------------------------------------
// TestStatus properties
// ---------------------------------------------------------------------------

proptest! {
    /// is_pass() returns true only for the Pass variant.
    #[test]
    fn prop_test_status_is_pass_only_for_pass(status in arb_test_status()) {
        let expected = matches!(status, TestStatus::Pass);
        prop_assert_eq!(status.is_pass(), expected);
    }

    /// TestStatus round-trips through JSON.
    #[test]
    fn prop_test_status_json_roundtrip(status in arb_test_status()) {
        let json = serde_json::to_string(&status).unwrap();
        let decoded: TestStatus = serde_json::from_str(&json).unwrap();
        prop_assert_eq!(status, decoded);
    }
}

// ---------------------------------------------------------------------------
// EntityId properties
// ---------------------------------------------------------------------------

proptest! {
    /// EntityId round-trips through its byte representation.
    #[test]
    fn prop_entity_id_bytes_roundtrip(raw in any::<u128>()) {
        let id = EntityId::from(raw);
        let bytes = id.to_bytes();
        let restored = EntityId::from_bytes(bytes);
        prop_assert_eq!(id, restored);
    }
}
