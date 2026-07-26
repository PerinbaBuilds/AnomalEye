"""Evaluation harness — how well does the detection recover injected labels?

Because the synthetic generator tags every laundering transaction with its
typology, we can measure the agent's detection quality honestly. This module
runs the full detection suite and reports customer-level precision / recall /
F1 against the ground truth, plus a per-typology recovery breakdown.
"""

from __future__ import annotations

from typing import Any

import pandas as pd

from anomaleye.data.loader import load_dataset
from anomaleye.tools import anomaly, features, risk


def _truth_customers(dataset) -> dict[str, set[int]]:
    """Map typology -> set of customer_ids that actually exhibit it."""
    gt = dataset.ground_truth
    if gt is None:
        return {}
    laundering = gt[gt["is_laundering"] == 1]
    txn_to_cust = dict(
        zip(dataset.transactions["transaction_id"],
            dataset.transactions["customer_id"])
    )
    out: dict[str, set[int]] = {}
    for _, row in laundering.iterrows():
        cid = txn_to_cust.get(row["transaction_id"])
        if cid is None:
            continue
        out.setdefault(row["typology"], set()).add(int(cid))
    out["any"] = set().union(*out.values()) if out else set()
    return out


def evaluate(dataset=None, min_level: str = "medium") -> dict[str, Any]:
    """Run detection and score it against the ground truth."""
    dataset = dataset or load_dataset()
    truth = _truth_customers(dataset)
    if not truth:
        return {"error": "dataset has no ground truth to evaluate against"}

    cf = features.customer_features(dataset.transactions)
    findings: list[dict] = []
    for det in anomaly.TYPOLOGY_DETECTORS.values():
        findings.extend(det(dataset.transactions))
    findings.extend(anomaly.detect_velocity(cf))
    _, ml_findings = anomaly.ml_anomaly(cf)
    findings.extend(ml_findings)

    assessments = risk.classify_all(findings)
    levels = {"low": 0, "medium": 1, "high": 2}
    threshold = levels[min_level]
    flagged = {
        a.customer_id
        for a in assessments
        if levels[a.risk_level] >= threshold
    }

    truth_any = truth["any"]
    tp = len(flagged & truth_any)
    fp = len(flagged - truth_any)
    fn = len(truth_any - flagged)
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = (
        2 * precision * recall / (precision + recall)
        if (precision + recall)
        else 0.0
    )

    # Per-typology recovery: did the matching detector flag those customers?
    per_typology = {}
    for typ, custs in truth.items():
        if typ == "any":
            continue
        detected = {
            f["customer_id"] for f in findings if f["typology"] == typ
        }
        # rapid_cashout / structuring map 1:1; smurfing collectors etc.
        recovered = len(detected & custs)
        per_typology[typ] = {
            "injected_customers": len(custs),
            "recovered": recovered,
            "recall": round(recovered / len(custs), 3) if custs else None,
        }

    return {
        "min_risk_level": min_level,
        "customer_level": {
            "true_positives": tp,
            "false_positives": fp,
            "false_negatives": fn,
            "precision": round(precision, 3),
            "recall": round(recall, 3),
            "f1": round(f1, 3),
        },
        "per_typology": per_typology,
        "n_flagged": len(flagged),
        "n_true_laundering_customers": len(truth_any),
    }


def main() -> None:  # pragma: no cover - thin CLI
    import json

    print(json.dumps(evaluate(), indent=2))


if __name__ == "__main__":
    main()
