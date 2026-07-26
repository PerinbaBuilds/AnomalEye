"""Agent orchestrator — executes a :class:`QueryPlan` against the data.

The orchestrator is the conductor: it takes the plan produced by
:mod:`anomaleye.agent.planner` and invokes *only* the tools the plan lists, in
order, threading the output of one into the next. It never runs a fixed
pipeline — the plan decides.

The return value is a single structured dict designed for a reviewer to
inspect: it echoes the parsed query, the filters/entities detected, the tools
actually invoked, the flagged entities with risk levels, and a plain-English
explanation for each flag.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

import pandas as pd

from anomaleye.agent import llm_planner
from anomaleye.agent.planner import QueryPlan, plan_query
from anomaleye.data.loader import Dataset, load_dataset
from anomaleye.tools import anomaly, eda, explain, features, risk


class Agent:
    """Query-driven AML analysis agent.

    Planning is done by the LLM (real tool-calling) when an API key is
    configured, and by the deterministic rule-based planner otherwise — or
    whenever the LLM call fails. Either way, all *detection* is deterministic.
    """

    def __init__(
        self,
        dataset: Optional[Dataset] = None,
        top_n: int = 10,
        use_llm: Optional[bool] = None,
    ):
        self.dataset = dataset or load_dataset()
        self.top_n = top_n
        # Relative dates ("last 30 days") are anchored to the newest
        # transaction in the data, so demo queries stay meaningful.
        ts = pd.to_datetime(self.dataset.transactions["timestamp"])
        self._data_today = ts.max().to_pydatetime()
        self._data_start = ts.min().date().isoformat()
        self._data_end = ts.max().date().isoformat()
        # Auto-enable the LLM planner if a key is present, unless overridden.
        self.use_llm = (
            llm_planner.llm_enabled() if use_llm is None else use_llm
        )

    # -- public API -------------------------------------------------------
    def run(self, query: str) -> dict[str, Any]:
        """Plan and execute ``query``; return a structured result."""
        plan = self._plan(query)
        return self._execute(plan)

    def plan_only(self, query: str) -> QueryPlan:
        """Expose the plan without executing (useful for the UI / tests)."""
        return self._plan(query)

    def _plan(self, query: str) -> QueryPlan:
        """LLM planner when enabled, with automatic rule-based fallback."""
        if self.use_llm:
            try:
                return llm_planner.plan_with_llm(
                    query, self._data_today, self._data_start, self._data_end
                )
            except llm_planner.LLMUnavailable:
                # Fall through to the deterministic planner.
                pass
        return plan_query(query, today=self._data_today)

    # -- execution --------------------------------------------------------
    def _execute(self, plan: QueryPlan) -> dict[str, Any]:
        ctx: dict[str, Any] = {"scope": self.dataset.transactions}
        invoked: list[str] = []

        for tool in plan.tools:
            handler = getattr(self, f"_tool_{tool}", None)
            if handler is None:
                continue
            handler(plan, ctx)
            invoked.append(tool)

        return self._assemble(plan, ctx, invoked)

    # -- individual tools -------------------------------------------------
    def _tool_filter(self, plan: QueryPlan, ctx: dict) -> None:
        df = self.dataset.transactions.copy()
        f = plan.filters
        ts = pd.to_datetime(df["timestamp"])

        if plan.customer_id is not None:
            df = df[df["customer_id"] == plan.customer_id]
        if f.date_from:
            df = df[ts >= pd.to_datetime(f.date_from)]
            ts = pd.to_datetime(df["timestamp"])
        if f.date_to:
            df = df[pd.to_datetime(df["timestamp"]) <= pd.to_datetime(f.date_to)]
        if f.country and "counterparty_country" in df:
            df = df[df["counterparty_country"].str.upper() == f.country]
        if f.txn_type and "type" in df:
            df = df[df["type"] == f.txn_type]
        # amount filters are applied inside the threshold tool so detectors see
        # the full behavioural context; here they only apply when explicitly a
        # scoping request without a threshold intent.
        if plan.intent != "threshold_query":
            if f.amount_min is not None:
                df = df[df["amount"] >= f.amount_min]
            if f.amount_max is not None:
                df = df[df["amount"] <= f.amount_max]

        ctx["scope"] = df.reset_index(drop=True)

    def _tool_eda(self, plan: QueryPlan, ctx: dict) -> None:
        ctx["eda"] = {
            "profile": eda.profile(ctx["scope"]),
            "structuring_scan": eda.structuring_scan(ctx["scope"]),
        }

    def _tool_features(self, plan: QueryPlan, ctx: dict) -> None:
        ctx["customer_features"] = features.customer_features(ctx["scope"])

    def _tool_detect_typologies(self, plan: QueryPlan, ctx: dict) -> None:
        scope = ctx["scope"]
        findings = ctx.setdefault("findings", [])
        # Choose detectors: those named in the query, else the full rule suite.
        wanted = plan.typologies or list(anomaly.TYPOLOGY_DETECTORS.keys())

        for typ in wanted:
            det = anomaly.TYPOLOGY_DETECTORS.get(typ)
            if det is not None:
                findings.extend(det(scope))

        # Velocity needs the customer feature frame.
        if "velocity_spike" in wanted or not plan.typologies:
            feats = ctx.get("customer_features")
            if feats is None:
                feats = features.customer_features(scope)
                ctx["customer_features"] = feats
            findings.extend(anomaly.detect_velocity(feats))

    def _tool_ml_anomaly(self, plan: QueryPlan, ctx: dict) -> None:
        feats = ctx.get("customer_features")
        if feats is None:
            feats = features.customer_features(ctx["scope"])
            ctx["customer_features"] = feats
        scored, ml_findings = anomaly.ml_anomaly(feats)
        ctx["customer_features"] = scored
        ctx.setdefault("findings", []).extend(ml_findings)

    def _tool_aggregate_threshold(self, plan: QueryPlan, ctx: dict) -> None:
        """Pure aggregation rule for threshold questions."""
        df = ctx["scope"].copy()
        f = plan.filters
        if f.amount_max is not None:
            df = df[df["amount"] <= f.amount_max]
        if f.amount_min is not None:
            df = df[df["amount"] >= f.amount_min]

        min_count = f.min_txn_count or 1
        grp = df.groupby("customer_id")
        counts = grp["amount"].agg(["count", "sum"])
        matched = counts[counts["count"] >= min_count]

        findings = ctx.setdefault("findings", [])
        for cid, row in matched.iterrows():
            sub = df[df["customer_id"] == cid]
            # Many sub-CTR transactions is structuring-like; otherwise it's a
            # high-velocity aggregation.
            near_ctr = (f.amount_max is not None and f.amount_max <= 10_000)
            findings.append(
                {
                    "customer_id": int(cid),
                    "typology": "threshold_rule",
                    "weight_key": "structuring" if near_ctr else "velocity",
                    "severity": min(1.0, int(row["count"]) / (min_count * 2)),
                    "evidence": {
                        "n_matching_transactions": int(row["count"]),
                        "amount_ceiling": f.amount_max,
                        "amount_floor": f.amount_min,
                        "total_amount": round(float(row["sum"]), 2),
                        "example_amounts": [
                            round(a, 2)
                            for a in sub["amount"].head(5).tolist()
                        ],
                        "resembles_structuring": bool(near_ctr),
                    },
                    "transaction_ids": sub["transaction_id"].head(20).tolist(),
                }
            )
        ctx["threshold_matched"] = matched

    def _tool_classify(self, plan: QueryPlan, ctx: dict) -> None:
        findings = ctx.get("findings", [])
        assessments = risk.classify_all(findings)

        if plan.intent == "high_risk_customers":
            assessments = [a for a in assessments if a.risk_level == "high"]
        if plan.customer_id is not None:
            assessments = [
                a for a in assessments if a.customer_id == plan.customer_id
            ] or [
                # entity had no findings -> explicit low-risk assessment
                risk.classify_entity(plan.customer_id, [])
            ]
        ctx["assessments"] = assessments

    def _tool_explain(self, plan: QueryPlan, ctx: dict) -> None:
        assessments = ctx.get("assessments", [])
        intent_phrase = self._intent_phrase(plan)
        ctx["explanations"] = [
            explain.explain_assessment(a, query_intent=intent_phrase)
            for a in assessments[: self.top_n]
        ]

    # -- assembly ---------------------------------------------------------
    def _assemble(
        self, plan: QueryPlan, ctx: dict, invoked: list[str]
    ) -> dict[str, Any]:
        assessments = ctx.get("assessments", [])
        flagged = [
            {
                "customer_id": a.customer_id,
                "risk_score": a.risk_score,
                "risk_level": a.risk_level,
                "escalation": a.escalation,
                "typologies": a.typologies,
                "score_breakdown": a.score_breakdown,
            }
            for a in assessments[: self.top_n]
        ]

        result: dict[str, Any] = {
            "execution_summary": {
                "user_query": plan.query,
                "detected_intent": plan.intent,
                "detected_filters": plan.filters.to_dict(),
                "detected_customer_id": plan.customer_id,
                "detected_typologies": plan.typologies,
                "tools_invoked": invoked,
                "planning_rationale": plan.rationale,
                "transactions_in_scope": int(len(ctx.get("scope", []))),
                "planner": plan.planner,
                "llm_model": (
                    llm_planner.model_name() if plan.planner == "llm" else None
                ),
                "run_at": datetime.now(timezone.utc).isoformat(),
            },
            "flagged_entities": flagged,
            "explanations": ctx.get("explanations", []),
            "counts": {
                "total_flagged": len(assessments),
                "high": sum(1 for a in assessments if a.risk_level == "high"),
                "medium": sum(
                    1 for a in assessments if a.risk_level == "medium"
                ),
                "low": sum(1 for a in assessments if a.risk_level == "low"),
            },
        }
        if "eda" in ctx:
            result["eda"] = ctx["eda"]

        # Optional LLM narrative (best-effort; never blocks the result).
        result["narrative"] = None
        if plan.planner == "llm":
            result["narrative"] = llm_planner.narrate(
                plan.query,
                {
                    "intent": plan.intent,
                    "counts": result["counts"],
                    "top_flagged": flagged[:5],
                },
            )
        return result

    @staticmethod
    def _intent_phrase(plan: QueryPlan) -> str:
        if plan.intent == "single_entity":
            return f"assess customer {plan.customer_id}"
        if plan.intent == "find_pattern":
            return f"find {', '.join(plan.typologies)} patterns"
        if plan.intent == "threshold_query":
            return "identify customers matching your transaction threshold"
        if plan.intent == "high_risk_customers":
            return "flag high-risk customers"
        return "analyse the dataset for suspicious activity"
