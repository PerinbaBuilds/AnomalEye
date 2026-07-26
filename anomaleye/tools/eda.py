"""EDA tool — exploratory data analysis and profiling.

Produces a compact, machine-readable profile of whatever slice of the data the
agent hands it. The agent only calls this when the user asks for broad
exploration; targeted / single-entity queries skip it.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd


def _amount_stats(s: pd.Series) -> dict[str, float]:
    s = s.dropna()
    if s.empty:
        return {}
    return {
        "count": int(s.size),
        "total": round(float(s.sum()), 2),
        "mean": round(float(s.mean()), 2),
        "median": round(float(s.median()), 2),
        "std": round(float(s.std(ddof=0)), 2),
        "min": round(float(s.min()), 2),
        "max": round(float(s.max()), 2),
        "p95": round(float(s.quantile(0.95)), 2),
        "p99": round(float(s.quantile(0.99)), 2),
    }


def profile(transactions: pd.DataFrame, top_n: int = 5) -> dict[str, Any]:
    """Return a structured profile of a transactions frame."""
    df = transactions
    if df.empty:
        return {"n_transactions": 0, "note": "no transactions in scope"}

    span = None
    if "timestamp" in df:
        ts = pd.to_datetime(df["timestamp"])
        span = {
            "start": ts.min().isoformat(),
            "end": ts.max().isoformat(),
            "days": int((ts.max() - ts.min()).days) + 1,
        }

    out: dict[str, Any] = {
        "n_transactions": int(len(df)),
        "n_customers": int(df["customer_id"].nunique())
        if "customer_id" in df
        else None,
        "date_span": span,
        "amount": _amount_stats(df["amount"]) if "amount" in df else {},
    }

    if "type" in df:
        out["by_type"] = (
            df["type"].value_counts().head(top_n).astype(int).to_dict()
        )
    if "channel" in df:
        out["by_channel"] = (
            df["channel"].value_counts().head(top_n).astype(int).to_dict()
        )
    if "customer_id" in df and "amount" in df:
        top = (
            df.groupby("customer_id")["amount"]
            .agg(["count", "sum"])
            .sort_values("sum", ascending=False)
            .head(top_n)
        )
        out["top_customers_by_volume"] = [
            {
                "customer_id": int(cid),
                "n_transactions": int(r["count"]),
                "total_amount": round(float(r["sum"]), 2),
            }
            for cid, r in top.iterrows()
        ]

    # A CTR-band concentration is itself an EDA red flag worth surfacing.
    if "amount" in df:
        band = df[(df["amount"] >= 9_000) & (df["amount"] < 10_000)]
        out["ctr_band_share"] = round(len(band) / len(df), 4)

    return out


def structuring_scan(
    transactions: pd.DataFrame, low: float = 9_000, high: float = 10_000
) -> dict[str, Any]:
    """Quick EDA helper: where does cash cluster just below the CTR line?"""
    df = transactions
    band = df[(df["amount"] >= low) & (df["amount"] < high)]
    hist, edges = np.histogram(
        df["amount"].clip(upper=15_000), bins=15, range=(0, 15_000)
    )
    return {
        "band": [low, high],
        "n_in_band": int(len(band)),
        "share_in_band": round(len(band) / max(len(df), 1), 4),
        "histogram": {
            "bin_edges": [round(float(e), 0) for e in edges],
            "counts": [int(c) for c in hist],
        },
    }
