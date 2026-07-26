"""Tests for the individual typology detectors and risk classification."""

from __future__ import annotations

import pandas as pd

from anomaleye.tools import anomaly, features, risk


def _txn(tid, cid, ts, amount, ttype="cash", cp=99999):
    return {
        "transaction_id": tid,
        "customer_id": cid,
        "timestamp": pd.Timestamp(ts),
        "amount": amount,
        "type": ttype,
        "channel": "branch",
        "counterparty_id": cp,
        "counterparty_country": "US",
    }


def test_structuring_detected_on_repeated_sub_ctr_cash():
    rows = [
        _txn(i, 1, f"2024-01-{i+1:02d}", 9_500 + i, "cash") for i in range(5)
    ]
    df = pd.DataFrame(rows)
    findings = anomaly.detect_structuring(df)
    assert len(findings) == 1
    assert findings[0]["typology"] == "structuring"
    assert findings[0]["evidence"]["n_just_under_ctr"] >= 3


def test_structuring_ignores_normal_amounts():
    rows = [_txn(i, 1, f"2024-01-{i+1:02d}", 200 + i) for i in range(5)]
    assert anomaly.detect_structuring(pd.DataFrame(rows)) == []


def test_rapid_cashout_detected():
    rows = [_txn(1, 1, "2024-01-01 09:00", 80_000, "deposit")]
    rows += [
        _txn(i + 2, 1, f"2024-01-01 {12 + i}:00", 20_000, "withdrawal")
        for i in range(4)
    ]
    findings = anomaly.detect_rapid_cashout(pd.DataFrame(rows))
    assert len(findings) == 1
    assert findings[0]["evidence"]["drain_ratio"] >= 0.8


def test_smurfing_detected_with_many_small_counterparties():
    rows = [
        _txn(i, 1, f"2024-01-01 {8 + i}:00", 2_000, "transfer", cp=1000 + i)
        for i in range(8)
    ]
    findings = anomaly.detect_smurfing(pd.DataFrame(rows))
    assert len(findings) == 1
    assert findings[0]["evidence"]["n_counterparties"] >= 6


def test_smurfing_ignores_single_large_transfer():
    rows = [_txn(1, 1, "2024-01-01", 50_000, "transfer", cp=1)]
    assert anomaly.detect_smurfing(pd.DataFrame(rows)) == []


def test_layering_chain_flags_all_participants():
    # 1 -> 2 -> 3 -> 4 within the window, near-constant amounts.
    rows = [
        _txn(1, 1, "2024-01-01 09:00", 30_000, "transfer", cp=2),
        _txn(2, 2, "2024-01-01 12:00", 29_500, "transfer", cp=3),
        _txn(3, 3, "2024-01-01 15:00", 29_000, "transfer", cp=4),
    ]
    findings = anomaly.detect_layering(pd.DataFrame(rows))
    flagged = {f["customer_id"] for f in findings}
    assert {1, 2, 3, 4} <= flagged
    assert all(f["typology"] == "layering" for f in findings)


def test_risk_classification_bands_and_escalation():
    findings = [
        {
            "customer_id": 1,
            "typology": "structuring",
            "weight_key": "structuring",
            "severity": 1.0,
            "evidence": {"n_just_under_ctr": 8, "window_days": 30,
                        "total_just_under": 76000, "example_amounts": []},
            "transaction_ids": [],
        },
        {
            "customer_id": 1,
            "typology": "rapid_cashout",
            "weight_key": "rapid_cashout",
            "severity": 0.95,
            "evidence": {"credit_amount": 100000, "drained_amount": 95000,
                        "drain_ratio": 0.95, "window_hours": 72},
            "transaction_ids": [],
        },
        {
            "customer_id": 1,
            "typology": "ml_anomaly",
            "weight_key": "ml_anomaly",
            "severity": 0.9,
            "evidence": {"ml_anomaly_score": 0.9, "outlier_features": {}},
            "transaction_ids": [],
        },
    ]
    a = risk.classify_entity(1, findings)
    assert a.risk_level == "high"
    assert a.escalation == "report"
    assert a.risk_score >= 70


def test_clean_entity_is_low_risk_monitor():
    a = risk.classify_entity(99, [])
    assert a.risk_level == "low"
    assert a.escalation == "monitor"
    assert a.risk_score == 0.0


def test_customer_features_shape(dataset):
    cf = features.customer_features(dataset.transactions)
    assert len(cf) == dataset.transactions["customer_id"].nunique()
    for col in features.ML_FEATURE_COLS:
        assert col in cf.columns
