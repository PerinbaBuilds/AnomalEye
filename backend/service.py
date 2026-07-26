"""Analysis service — a cached, API-friendly wrapper over the engine.

On startup it runs one full hybrid-detection pass over the whole dataset and
caches the result, so the dashboard, alert queue, entity-360 and network views
are all served from the same coherent analysis without recomputing. Free-text
agent queries are delegated to :class:`anomaleye.agent.orchestrator.Agent`,
which re-plans per query.
"""

from __future__ import annotations

import threading
from typing import Any, Optional

import numpy as np
import pandas as pd

from anomaleye.agent.orchestrator import Agent
from anomaleye.config import SETTINGS
from anomaleye.data.loader import Dataset, load_dataset
from anomaleye.evaluate import evaluate
from anomaleye.tools import anomaly, eda, explain, features, network, risk


class AnalysisService:
    """Singleton-style service holding the cached full analysis."""

    def __init__(self, dataset: Optional[Dataset] = None):
        self.dataset = dataset or load_dataset()
        self.agent = Agent(dataset=self.dataset, top_n=50)
        self._lock = threading.Lock()
        self._built = False
        self._findings: list[dict] = []
        self._assessments: list[risk.RiskAssessment] = []
        self._assess_by_id: dict[int, risk.RiskAssessment] = {}
        self._customer_features: pd.DataFrame | None = None
        self._flagged_ids: set[int] = set()
        self.build()

    # -- one-time full analysis ------------------------------------------
    def build(self) -> None:
        with self._lock:
            if self._built:
                return
            txns = self.dataset.transactions
            cf = features.customer_features(txns)
            findings: list[dict] = []
            for det in anomaly.TYPOLOGY_DETECTORS.values():
                findings.extend(det(txns))
            findings.extend(anomaly.detect_velocity(cf))
            scored, ml_findings = anomaly.ml_anomaly(cf)
            findings.extend(ml_findings)

            self._customer_features = scored
            self._findings = findings
            self._assessments = risk.classify_all(findings)
            self._assess_by_id = {a.customer_id: a for a in self._assessments}
            self._flagged_ids = {a.customer_id for a in self._assessments}
            self._built = True

    # -- dashboard -------------------------------------------------------
    def overview(self) -> dict[str, Any]:
        txns = self.dataset.transactions
        prof = eda.profile(txns)
        scan = eda.structuring_scan(txns)
        levels = {"high": 0, "medium": 0, "low": 0}
        for a in self._assessments:
            levels[a.risk_level] += 1

        typ_counts: dict[str, int] = {}
        for f in self._findings:
            typ_counts[f["typology"]] = typ_counts.get(f["typology"], 0) + 1

        escalations = {"report": 0, "review": 0, "monitor": 0}
        for a in self._assessments:
            escalations[a.escalation] += 1

        ts = pd.to_datetime(txns["timestamp"])
        return {
            "dataset": {
                "transactions": int(len(txns)),
                "customers": int(txns["customer_id"].nunique()),
                "date_start": ts.min().isoformat(),
                "date_end": ts.max().isoformat(),
                "total_volume": round(float(txns["amount"].sum()), 2),
            },
            "risk_distribution": levels,
            "escalations": escalations,
            "typology_counts": typ_counts,
            "amount_stats": prof.get("amount", {}),
            "ctr_band_share": prof.get("ctr_band_share"),
            "amount_histogram": scan["histogram"],
            "alerts_total": len(self._assessments),
            "sar_recommended": escalations["report"],
        }

    def alerts_timeline(self, freq: str = "W") -> list[dict[str, Any]]:
        """Alert-weighted transaction volume over time (for a trend chart)."""
        txns = self.dataset.transactions.copy()
        txns["timestamp"] = pd.to_datetime(txns["timestamp"])
        flagged_txn_ids = set()
        for f in self._findings:
            flagged_txn_ids.update(f.get("transaction_ids", []))
        txns["flagged"] = txns["transaction_id"].isin(flagged_txn_ids)
        g = (
            txns.set_index("timestamp")
            .groupby(pd.Grouper(freq=freq))
            .agg(total=("transaction_id", "size"),
                 flagged=("flagged", "sum"))
            .reset_index()
        )
        return [
            {
                "date": r["timestamp"].date().isoformat(),
                "total": int(r["total"]),
                "flagged": int(r["flagged"]),
            }
            for _, r in g.iterrows()
        ]

    # -- alerts / cases --------------------------------------------------
    def alerts(
        self,
        level: Optional[str] = None,
        typology: Optional[str] = None,
        escalation: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> dict[str, Any]:
        items = self._assessments
        if level:
            items = [a for a in items if a.risk_level == level]
        if escalation:
            items = [a for a in items if a.escalation == escalation]
        if typology:
            items = [a for a in items if typology in a.typologies]
        total = len(items)
        page = items[offset : offset + limit]
        return {
            "total": total,
            "limit": limit,
            "offset": offset,
            "items": [self._alert_row(a) for a in page],
        }

    def _alert_row(self, a: risk.RiskAssessment) -> dict[str, Any]:
        return {
            "customer_id": a.customer_id,
            "risk_score": a.risk_score,
            "risk_level": a.risk_level,
            "escalation": a.escalation,
            "typologies": a.typologies,
            "score_breakdown": a.score_breakdown,
            "n_signals": len(a.findings),
        }

    # -- entity 360 ------------------------------------------------------
    def customer(self, customer_id: int) -> dict[str, Any]:
        txns = self.dataset.transactions
        sub = txns[txns["customer_id"] == customer_id].copy()
        if sub.empty:
            return {"error": f"customer {customer_id} not found"}
        sub["timestamp"] = pd.to_datetime(sub["timestamp"])

        profile = self._customer_profile(customer_id)
        assessment = self._assess_by_id.get(customer_id)
        if assessment is None:
            assessment = risk.classify_entity(customer_id, [])
        expl = explain.explain_assessment(
            assessment, query_intent=f"assess customer {customer_id}"
        )

        timeline = [
            {
                "transaction_id": int(r["transaction_id"]),
                "timestamp": r["timestamp"].isoformat(),
                "amount": round(float(r["amount"]), 2),
                "type": str(r["type"]),
                "channel": str(r.get("channel", "")),
                "counterparty_id": int(r["counterparty_id"])
                if "counterparty_id" in r and not pd.isna(r["counterparty_id"])
                else None,
                "counterparty_country": str(r.get("counterparty_country", "")),
                "suspicious": int(r["transaction_id"]) in self._flagged_txn_ids(customer_id),
            }
            for _, r in sub.sort_values("timestamp").iterrows()
        ]

        return {
            "customer_id": customer_id,
            "profile": profile,
            "assessment": {
                "risk_score": assessment.risk_score,
                "risk_level": assessment.risk_level,
                "escalation": assessment.escalation,
                "typologies": assessment.typologies,
                "score_breakdown": assessment.score_breakdown,
                "findings": assessment.findings,
            },
            "explanation": expl,
            "timeline": timeline,
            "network": network.build_customer_network(
                txns, customer_id, self._flagged_ids
            ),
        }

    def _flagged_txn_ids(self, customer_id: int) -> set[int]:
        out: set[int] = set()
        a = self._assess_by_id.get(customer_id)
        if a:
            for f in a.findings:
                out.update(f.get("transaction_ids", []))
        return out

    def _customer_profile(self, customer_id: int) -> dict[str, Any]:
        cust = self.dataset.customers
        row = cust[cust["customer_id"] == customer_id]
        if row.empty:
            return {"customer_id": customer_id}
        r = row.iloc[0].to_dict()
        return {k: (None if pd.isna(v) else v) for k, v in r.items()}

    def network(self, customer_id: int) -> dict[str, Any]:
        return network.build_customer_network(
            self.dataset.transactions, customer_id, self._flagged_ids
        )

    def layering_chains(self) -> list[dict[str, Any]]:
        return network.layering_paths(self._findings)

    # -- agent -----------------------------------------------------------
    def agent_query(self, query: str) -> dict[str, Any]:
        return self.agent.run(query)

    # -- model performance ----------------------------------------------
    def performance(self) -> dict[str, Any]:
        return evaluate(self.dataset, min_level="medium")

    # -- methodology (thresholds) ---------------------------------------
    def methodology(self) -> dict[str, Any]:
        t = SETTINGS.thresholds
        w = SETTINGS.weights
        return {
            "thresholds": {k: getattr(t, k) for k in vars(t)},
            "weights": {k: getattr(w, k) for k in vars(w)},
            "risk_bands": {
                "high": f">= {t.risk_high}",
                "medium": f"{t.risk_medium} - {t.risk_high}",
                "low": f"< {t.risk_medium}",
            },
        }

    # -- live feed helper ------------------------------------------------
    def sample_transaction_stream(self, n: int = 200) -> list[dict[str, Any]]:
        """A shuffled slice of transactions for the live-monitor simulation,
        each pre-scored so the UI can animate real-time triage."""
        txns = self.dataset.transactions
        flagged_txn = set()
        for f in self._findings:
            flagged_txn.update(f.get("transaction_ids", []))
        sample = txns.sample(min(n, len(txns)),
                             random_state=SETTINGS.random_seed).copy()
        sample["timestamp"] = pd.to_datetime(sample["timestamp"])
        out = []
        for _, r in sample.iterrows():
            tid = int(r["transaction_id"])
            cid = int(r["customer_id"])
            a = self._assess_by_id.get(cid)
            level = a.risk_level if (a and tid in self._flagged_txn_ids(cid)) else (
                "medium" if tid in flagged_txn else "low")
            out.append(
                {
                    "transaction_id": tid,
                    "customer_id": cid,
                    "amount": round(float(r["amount"]), 2),
                    "type": str(r["type"]),
                    "counterparty_country": str(r.get("counterparty_country", "")),
                    "risk_level": level,
                    "suspicious": tid in flagged_txn,
                }
            )
        return out


_service: AnalysisService | None = None


def get_service() -> AnalysisService:
    global _service
    if _service is None:
        _service = AnalysisService()
    return _service
