"""End-to-end tests for the agent orchestrator and evaluation quality."""

from __future__ import annotations

from anomaleye.evaluate import evaluate


def test_full_analysis_returns_structured_result(agent):
    r = agent.run("Analyse this dataset for suspicious activity")
    es = r["execution_summary"]
    assert es["detected_intent"] == "full_analysis"
    assert "ml_anomaly" in es["tools_invoked"]
    assert set(r["counts"]) == {"total_flagged", "high", "medium", "low"}
    assert "eda" in r
    # Every flagged entity must carry an explanation + escalation.
    for ex in r["explanations"]:
        assert ex["reasons"]
        assert ex["escalation"] in {"monitor", "review", "report"}


def test_single_entity_scopes_to_one_customer(agent, dataset):
    cid = int(dataset.transactions["customer_id"].iloc[0])
    r = agent.run(f"Is customer ID {cid} suspicious?")
    assert r["execution_summary"]["detected_customer_id"] == cid
    # scope must be just that customer's transactions
    n = int((dataset.transactions["customer_id"] == cid).sum())
    assert r["execution_summary"]["transactions_in_scope"] == n
    assert all(
        e["customer_id"] == cid for e in r["flagged_entities"]
    )


def test_pattern_query_only_runs_relevant_detector(agent):
    r = agent.run("Find structuring patterns in the last 30 days")
    tools = r["execution_summary"]["tools_invoked"]
    assert "aggregate_threshold" not in tools
    assert "ml_anomaly" not in tools
    for ex in r["explanations"]:
        assert "structuring" in ex["summary"] or any(
            "structuring" in reason.lower() for reason in ex["reasons"]
        )


def test_threshold_query_runs_pure_aggregation(agent):
    r = agent.run("Which customers made 10+ transactions under $10,000?")
    tools = r["execution_summary"]["tools_invoked"]
    assert "aggregate_threshold" in tools
    assert "ml_anomaly" not in tools


def test_high_risk_filter_returns_only_high(agent):
    r = agent.run("Flag high-risk customers")
    assert all(e["risk_level"] == "high" for e in r["flagged_entities"])


def test_detection_quality_meets_baseline(dataset):
    """The hybrid detector should recover most injected laundering."""
    report = evaluate(dataset, min_level="medium")
    cl = report["customer_level"]
    assert cl["recall"] >= 0.7, report
    assert cl["precision"] >= 0.5, report
    # Hard typologies must be recovered well.
    assert report["per_typology"]["structuring"]["recall"] >= 0.8
    assert report["per_typology"]["rapid_cashout"]["recall"] >= 0.8
