"""Risk classification tool — turns detector findings into risk decisions.

Aggregates all findings for an entity, blends them into a single 0-100 risk
score using the auditable weights in :mod:`anomaleye.config`, assigns a
low/medium/high band, and recommends an escalation action
(``monitor`` / ``review`` / ``report``).

The scoring is deliberately transparent: score = normalised weighted sum of the
strongest finding per signal type, so an analyst can always reconstruct it.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from anomaleye.config import SETTINGS

W = SETTINGS.weights
T = SETTINGS.thresholds


@dataclass
class RiskAssessment:
    customer_id: int
    risk_score: float
    risk_level: str          # low | medium | high
    escalation: str          # monitor | review | report
    typologies: list[str]
    findings: list[dict[str, Any]] = field(default_factory=list)
    score_breakdown: dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _escalation_for(level: str, typologies: list[str]) -> str:
    """Map a risk level to a regulator-friendly next action.

    High risk, or any confirmed structuring/smurfing/layering, warrants a
    filing recommendation; medium warrants analyst review; low is routine
    monitoring.
    """
    reportable = {"structuring", "smurfing", "layering"}
    if level == "high" or (reportable & set(typologies)):
        return "report" if level == "high" else "review"
    if level == "medium":
        return "review"
    return "monitor"


def classify_entity(
    customer_id: int, findings: list[dict[str, Any]]
) -> RiskAssessment:
    """Blend an entity's findings into a single risk assessment."""
    # Keep the strongest instance of each weighted signal.
    strongest: dict[str, dict[str, Any]] = {}
    for f in findings:
        key = f["weight_key"]
        if key not in strongest or f["severity"] > strongest[key]["severity"]:
            strongest[key] = f

    breakdown: dict[str, float] = {}
    weighted = 0.0
    for key, f in strongest.items():
        w = getattr(W, key, 0.0)
        contribution = w * float(f["severity"])
        breakdown[key] = round(contribution, 2)
        weighted += contribution

    # The weighted contributions are calibrated so that a couple of strong
    # "hard" typologies push an entity into the high band; the score is capped
    # at 100. (Dividing by the sum of *all* possible weights would make the
    # high band practically unreachable, since no entity trips every signal.)
    score = round(min(100.0, weighted), 1)
    # A single high-confidence hard typology should not be diluted below the
    # medium line just because other signals are silent.
    hard = {"structuring", "smurfing", "layering", "rapid_cashout"}
    if any(f["typology"] in hard and f["severity"] >= 0.5 for f in findings):
        score = max(score, T.risk_medium + 5)

    if score >= T.risk_high:
        level = "high"
    elif score >= T.risk_medium:
        level = "medium"
    else:
        level = "low"

    typologies = sorted({f["typology"] for f in findings})
    return RiskAssessment(
        customer_id=int(customer_id),
        risk_score=score,
        risk_level=level,
        escalation=_escalation_for(level, typologies),
        typologies=typologies,
        findings=findings,
        score_breakdown=breakdown,
    )


def classify_all(
    findings: list[dict[str, Any]]
) -> list[RiskAssessment]:
    """Group findings by customer and classify each entity."""
    by_customer: dict[int, list[dict[str, Any]]] = {}
    for f in findings:
        by_customer.setdefault(int(f["customer_id"]), []).append(f)

    assessments = [
        classify_entity(cid, fs) for cid, fs in by_customer.items()
    ]
    assessments.sort(key=lambda a: a.risk_score, reverse=True)
    return assessments
