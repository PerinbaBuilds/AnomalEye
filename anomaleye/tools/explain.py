"""Explanation tool — plain-English reasons for every flag.

Turns a structured :class:`~anomaleye.tools.risk.RiskAssessment` into concise,
human-readable narrative tied to the detected typology and the original query
intent. Deterministic templates keep explanations auditable and reproducible
(no external LLM required), while remaining specific by quoting the actual
evidence numbers.
"""

from __future__ import annotations

from typing import Any

from anomaleye.config import SETTINGS

T = SETTINGS.thresholds

_ESCALATION_RATIONALE = {
    "report": (
        "Recommend filing a Suspicious Activity Report (SAR): the pattern and "
        "risk score meet the reporting threshold."
    ),
    "review": (
        "Route to a compliance analyst for manual review before any filing "
        "decision."
    ),
    "monitor": (
        "Keep under routine monitoring; no immediate action required."
    ),
}


def _explain_finding(f: dict[str, Any]) -> str:
    e = f["evidence"]
    typ = f["typology"]
    if typ == "structuring":
        return (
            f"Made {e['n_just_under_ctr']} cash transactions between "
            f"${T.structuring_band_low:,.0f} and ${T.ctr_threshold:,.0f} "
            f"within {e['window_days']} days "
            f"(total ${e['total_just_under']:,.2f}) — consistent with "
            f"structuring to stay under the ${T.ctr_threshold:,.0f} CTR "
            f"reporting line."
        )
    if typ == "smurfing":
        return (
            f"Received funds from {e['n_counterparties']} distinct "
            f"counterparties aggregating ${e['aggregate_amount']:,.2f} within "
            f"{e['window_days']} days — a classic smurfing / funnel-account "
            f"footprint where many small inbound transfers combine above the "
            f"reporting line."
        )
    if typ == "rapid_cashout":
        return (
            f"A credit of ${e['credit_amount']:,.2f} was "
            f"{int(e['drain_ratio'] * 100)}% drained "
            f"(${e['drained_amount']:,.2f}) within "
            f"{e['window_hours']} hours — placement followed by rapid removal "
            f"of funds."
        )
    if typ == "layering":
        path = " -> ".join(str(p) for p in e["path"])
        return (
            f"Value moved through {e['n_hops']} accounts in a chain "
            f"({path}) within {e['window_hours']} hours with near-constant "
            f"amounts — indicative of layering to obscure the funds' origin."
        )
    if typ == "velocity_spike":
        return (
            f"Transaction velocity spiked to {e['max_transactions_24h']} in a "
            f"24-hour window (z-score {e['zscore']} vs a population mean of "
            f"{e['population_mean']}) — a burst well outside normal behaviour."
        )
    if typ == "high_risk_geography":
        return (
            f"{e['n_high_risk_txns']} transactions "
            f"(${e['amount']:,.2f}) involved FATF high-risk jurisdictions "
            f"({', '.join(e['countries'])})."
        )
    if typ == "threshold_rule":
        ceil = e.get("amount_ceiling")
        floor = e.get("amount_floor")
        bound = ""
        if ceil is not None:
            bound += f" under ${ceil:,.0f}"
        if floor is not None:
            bound += f" over ${floor:,.0f}"
        note = (
            " These sit just below the CTR reporting line, consistent with "
            "structuring." if e.get("resembles_structuring") else ""
        )
        return (
            f"Made {e['n_matching_transactions']} transactions{bound} "
            f"(total ${e['total_amount']:,.2f}), matching your query "
            f"criteria.{note}"
        )
    if typ == "ml_anomaly":
        feats = ", ".join(e.get("outlier_features", {}).keys()) or "several"
        return (
            f"Unsupervised model flagged this customer as an outlier "
            f"(anomaly score {e['ml_anomaly_score']}); the fingerprint departs "
            f"from peers on: {feats}."
        )
    return f"Flagged for {typ}."


def explain_assessment(
    assessment, query_intent: str | None = None
) -> dict[str, Any]:
    """Return a structured explanation for a :class:`RiskAssessment`."""
    reasons = [_explain_finding(f) for f in assessment.findings]

    lead = (
        f"Customer {assessment.customer_id} is assessed as "
        f"{assessment.risk_level.upper()} risk "
        f"(score {assessment.risk_score}/100)"
    )
    if assessment.typologies:
        lead += f", driven by: {', '.join(assessment.typologies)}."
    else:
        lead += "."

    explanation = {
        "customer_id": assessment.customer_id,
        "risk_level": assessment.risk_level,
        "risk_score": assessment.risk_score,
        "summary": lead,
        "reasons": reasons,
        "escalation": assessment.escalation,
        "escalation_rationale": _ESCALATION_RATIONALE[assessment.escalation],
        "score_breakdown": assessment.score_breakdown,
    }
    if query_intent:
        explanation["tied_to_query"] = (
            f"In response to your request to {query_intent}, this entity "
            f"surfaced because of the patterns above."
        )
    return explanation
