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
            det_by_typ: dict[str, list] = {}
            for typ, det in anomaly.TYPOLOGY_DETECTORS.items():
                det_by_typ[typ] = det(txns)
                findings.extend(det_by_typ[typ])
            velocity = anomaly.detect_velocity(cf)
            findings.extend(velocity)
            scored, ml_findings = anomaly.ml_anomaly(cf)
            findings.extend(ml_findings)

            self._customer_features = scored
            self._findings = findings
            self._assessments = risk.classify_all(findings)
            self._assess_by_id = {a.customer_id: a for a in self._assessments}
            self._flagged_ids = {a.customer_id for a in self._assessments}

            # Warm the agent's full-scope cache so the first broad NL query is
            # instant (it reuses this analysis instead of recomputing).
            self.agent._cache.update(
                {
                    "features": cf,
                    "ml": (scored, ml_findings),
                    "velocity": velocity,
                    **{f"det_{typ}": v for typ, v in det_by_typ.items()},
                }
            )
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

    def customer_breakdown(self) -> dict[str, Any]:
        """Customer- and transaction-level segmentation for the dashboard."""
        txns = self.dataset.transactions
        cust = self.dataset.customers
        T = SETTINGS.thresholds

        # Transaction bands around the CTR reporting line.
        amt = txns["amount"]
        tx_bands = {
            "above_ctr": int((amt >= T.ctr_threshold).sum()),
            "ctr_band": int(
                ((amt >= T.structuring_band_low) & (amt < T.ctr_threshold)).sum()
            ),
            "below_band": int((amt < T.structuring_band_low).sum()),
        }

        # Customer-level flags.
        per_cust = txns.groupby("customer_id")["amount"]
        cust_over_10k = per_cust.max()
        n_over_10k = int((cust_over_10k >= T.ctr_threshold).sum())
        in_band = txns[
            (amt >= T.structuring_band_low) & (amt < T.ctr_threshold)
        ]["customer_id"].nunique()

        hr_geo_customers = 0
        if "counterparty_country" in txns:
            from anomaleye.config import HIGH_RISK_COUNTRIES

            hr = txns[
                txns["counterparty_country"].str.upper().isin(HIGH_RISK_COUNTRIES)
            ]
            hr_geo_customers = int(hr["customer_id"].nunique())

        by_segment = (
            cust["segment"].value_counts().to_dict()
            if "segment" in cust
            else {}
        )
        by_kyc = (
            cust["kyc_risk_rating"].value_counts().to_dict()
            if "kyc_risk_rating" in cust
            else {}
        )
        flagged_ids = self._flagged_ids
        by_segment_flagged = {}
        if "segment" in cust:
            seg_of = dict(zip(cust["customer_id"], cust["segment"]))
            for cid in flagged_ids:
                s = seg_of.get(cid, "unknown")
                by_segment_flagged[s] = by_segment_flagged.get(s, 0) + 1

        total = int(cust["customer_id"].nunique())
        return {
            "total_customers": total,
            "flagged_customers": len(flagged_ids),
            "customers_over_ctr": n_over_10k,
            "customers_in_ctr_band": int(in_band),
            "high_risk_geo_customers": hr_geo_customers,
            "avg_txns_per_customer": round(len(txns) / max(total, 1), 1),
            "transaction_bands": tx_bands,
            "by_segment": {str(k): int(v) for k, v in by_segment.items()},
            "by_kyc": {str(k): int(v) for k, v in by_kyc.items()},
            "flagged_by_segment": {
                str(k): int(v) for k, v in by_segment_flagged.items()
            },
            "ctr_threshold": T.ctr_threshold,
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
    def sample_transaction_stream(self, n: int = 250) -> list[dict[str, Any]]:
        """A pre-scored, shuffled stream for the live-monitor simulation.

        Suspicious transactions are only ~0.5% of the data, so a naive random
        sample would show almost nothing but LOW. Instead we deliberately mix a
        healthy share of the actually-flagged transactions (carrying their
        entity's risk band) with normal traffic, so the blotter reads like a
        real triage feed with a believable high/medium/low spread.
        """
        import numpy as np

        txns = self.dataset.transactions
        # Map each flagged transaction to its entity's risk band.
        susp_level: dict[int, str] = {}
        for a in self._assessments:
            if a.risk_level == "low":
                continue
            for f in a.findings:
                for tid in f.get("transaction_ids", []):
                    prev = susp_level.get(int(tid))
                    if prev != "high":  # keep the strongest band
                        susp_level[int(tid)] = a.risk_level
        susp_ids = list(susp_level.keys())

        rng = np.random.default_rng(SETTINGS.random_seed)
        # ~40% of the feed is suspicious for a meaningful demo.
        n_susp = min(len(susp_ids), int(n * 0.4))
        n_normal = n - n_susp
        chosen_susp = set(
            rng.choice(susp_ids, n_susp, replace=False).tolist()
        ) if susp_ids else set()

        normal_pool = txns[~txns["transaction_id"].isin(susp_level)]
        normal_sample = normal_pool.sample(
            min(n_normal, len(normal_pool)), random_state=SETTINGS.random_seed
        )
        susp_sample = txns[txns["transaction_id"].isin(chosen_susp)]

        combined = pd.concat([normal_sample, susp_sample]).sample(
            frac=1.0, random_state=SETTINGS.random_seed
        )

        out = []
        for _, r in combined.iterrows():
            tid = int(r["transaction_id"])
            level = susp_level.get(tid, "low")
            out.append(
                {
                    "transaction_id": tid,
                    "customer_id": int(r["customer_id"]),
                    "amount": round(float(r["amount"]), 2),
                    "type": str(r["type"]),
                    "counterparty_country": str(r.get("counterparty_country", "")),
                    "risk_level": level,
                    "suspicious": tid in susp_level,
                }
            )
        return out


_service: AnalysisService | None = None


def get_service() -> AnalysisService:
    global _service
    if _service is None:
        _service = AnalysisService()
    return _service
