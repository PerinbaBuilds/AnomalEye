"""Anomaly detection tool — hybrid rule + statistical + ML detection.

The tool exposes individual *typology detectors* (structuring, smurfing, rapid
cash-out, layering, velocity) plus an unsupervised ML model (Isolation Forest)
over the customer fingerprint. Each detector returns structured **findings**
carrying the evidence that triggered them, so the explanation layer can turn
them into plain English and an analyst can audit the decision.

A ``Finding`` is a plain dict:

    {
      "customer_id": int,
      "typology": str,             # e.g. "structuring"
      "weight_key": str,           # key into config.Weights
      "severity": float,           # 0..1, how strong this instance is
      "evidence": dict,            # numbers that justify the flag
      "transaction_ids": list[int] # supporting transactions
    }
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from anomaleye.config import HIGH_RISK_COUNTRIES, SETTINGS
from anomaleye.tools.features import ML_FEATURE_COLS

T = SETTINGS.thresholds

Finding = dict[str, Any]


# --------------------------------------------------------------------------
# Rule-based typology detectors
# --------------------------------------------------------------------------
def detect_structuring(txns: pd.DataFrame) -> list[Finding]:
    """Repeated cash/deposits just under the CTR line within the window."""
    df = txns.copy()
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    band = df[
        (df["amount"] >= T.structuring_band_low)
        & (df["amount"] < T.ctr_threshold)
    ]
    findings: list[Finding] = []
    for cid, g in band.groupby("customer_id"):
        g = g.sort_values("timestamp")
        # Sliding window: any window of length structuring_window_days with
        # enough just-under transactions counts.
        best = _max_in_window(g["timestamp"], T.structuring_window_days)
        if best >= T.structuring_min_count:
            total = float(g["amount"].sum())
            findings.append(
                {
                    "customer_id": int(cid),
                    "typology": "structuring",
                    "weight_key": "structuring",
                    "severity": min(1.0, best / (T.structuring_min_count * 2)),
                    "evidence": {
                        "n_just_under_ctr": int(best),
                        "window_days": T.structuring_window_days,
                        "total_just_under": round(total, 2),
                        "example_amounts": [
                            round(a, 2) for a in g["amount"].head(5).tolist()
                        ],
                    },
                    "transaction_ids": g["transaction_id"].head(20).tolist(),
                }
            )
    return findings


def detect_smurfing(txns: pd.DataFrame) -> list[Finding]:
    """Many distinct counterparties feeding one account above the CTR line."""
    df = txns.copy()
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    # Only *small* inbound transfers count — smurfing breaks a large sum into
    # many pieces, so large legitimate inbound transfers are excluded.
    inbound = df[
        (df["type"].isin(["transfer", "deposit"]))
        & (df["amount"] < T.smurfing_max_txn_amount)
    ]
    findings: list[Finding] = []
    if "counterparty_id" not in inbound:
        return findings
    for cid, g in inbound.groupby("customer_id"):
        g = g.sort_values("timestamp")
        # Rolling window on distinct counterparties + aggregate.
        window = pd.Timedelta(days=T.smurfing_window_days)
        ts = g["timestamp"].to_numpy()
        best = _best_smurf_window(g, window)
        if (
            best["n_counterparties"] >= T.smurfing_min_counterparties
            and best["total"]
            >= T.ctr_threshold * T.smurfing_aggregate_multiplier
        ):
            findings.append(
                {
                    "customer_id": int(cid),
                    "typology": "smurfing",
                    "weight_key": "smurfing",
                    "severity": min(
                        1.0,
                        best["n_counterparties"]
                        / (T.smurfing_min_counterparties * 2),
                    ),
                    "evidence": {
                        "n_counterparties": int(best["n_counterparties"]),
                        "aggregate_amount": round(float(best["total"]), 2),
                        "window_days": T.smurfing_window_days,
                    },
                    "transaction_ids": best["txn_ids"],
                }
            )
    return findings


def detect_rapid_cashout(txns: pd.DataFrame) -> list[Finding]:
    """A large credit drained by withdrawals within the window."""
    df = txns.copy()
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    findings: list[Finding] = []
    credit_types = {"deposit", "transfer", "payment"}
    debit_types = {"withdrawal", "cash", "transfer", "payment"}
    window = pd.Timedelta(hours=T.rapid_cashout_window_hours)

    for cid, g in df.groupby("customer_id"):
        g = g.sort_values("timestamp")
        credits = g[(g["type"].isin(credit_types)) & (g["amount"] >= 20_000)]
        for _, credit in credits.iterrows():
            t0 = credit["timestamp"]
            after = g[
                (g["timestamp"] > t0)
                & (g["timestamp"] <= t0 + window)
                & (g["type"].isin(debit_types))
            ]
            drained = float(after["amount"].sum())
            ratio = drained / credit["amount"] if credit["amount"] else 0.0
            if ratio >= T.rapid_cashout_drain_ratio:
                findings.append(
                    {
                        "customer_id": int(cid),
                        "typology": "rapid_cashout",
                        "weight_key": "rapid_cashout",
                        "severity": min(1.0, ratio),
                        "evidence": {
                            "credit_amount": round(float(credit["amount"]), 2),
                            "drained_amount": round(drained, 2),
                            "drain_ratio": round(ratio, 3),
                            "window_hours": T.rapid_cashout_window_hours,
                        },
                        "transaction_ids": [int(credit["transaction_id"])]
                        + after["transaction_id"].tolist(),
                    }
                )
                break  # one finding per customer is enough
    return findings


def detect_layering(txns: pd.DataFrame) -> list[Finding]:
    """Similar value bounced through a chain of accounts in quick hops."""
    df = txns.copy()
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    transfers = df[df["type"] == "transfer"].copy()
    findings: list[Finding] = []
    if "counterparty_id" not in transfers:
        return findings

    transfers = transfers.sort_values("timestamp")
    window = pd.Timedelta(hours=T.layering_window_hours)

    # Build hops keyed by (customer -> counterparty). A layering chain is a set
    # of transfers where each destination becomes the next source with a
    # similar amount inside the time window.
    hops = transfers[
        ["transaction_id", "customer_id", "counterparty_id", "amount",
         "timestamp"]
    ].to_dict("records")
    by_src: dict[int, list[dict]] = {}
    for h in hops:
        by_src.setdefault(int(h["customer_id"]), []).append(h)

    seen = set()
    for h in hops:
        if h["transaction_id"] in seen:
            continue
        chain = [h]
        cur = h
        while True:
            nxt_src = int(cur["counterparty_id"])
            candidates = [
                c
                for c in by_src.get(nxt_src, [])
                if c["timestamp"] > cur["timestamp"]
                and c["timestamp"] <= cur["timestamp"] + window
                and abs(c["amount"] - cur["amount"]) / cur["amount"]
                <= T.layering_amount_tolerance
                and c["transaction_id"] not in seen
            ]
            if not candidates:
                break
            cur = min(candidates, key=lambda c: c["timestamp"])
            chain.append(cur)
        if len(chain) >= T.layering_min_hops:
            for c in chain:
                seen.add(c["transaction_id"])
            path = [int(chain[0]["customer_id"])] + [
                int(c["counterparty_id"]) for c in chain
            ]
            evidence = {
                "n_hops": len(chain),
                "window_hours": T.layering_window_hours,
                "amounts": [round(c["amount"], 2) for c in chain],
                "path": path,
            }
            txn_ids = [int(c["transaction_id"]) for c in chain]
            severity = min(1.0, len(chain) / (T.layering_min_hops * 2))
            # Every account the value passes through is a mule in the scheme,
            # so each participant is flagged (with the shared chain evidence).
            participants = {int(c["customer_id"]) for c in chain}
            participants.add(int(chain[-1]["counterparty_id"]))
            for cid in participants:
                role = "originator" if cid == path[0] else (
                    "terminus" if cid == path[-1] else "intermediary"
                )
                findings.append(
                    {
                        "customer_id": cid,
                        "typology": "layering",
                        "weight_key": "layering",
                        "severity": severity,
                        "evidence": {**evidence, "role": role},
                        "transaction_ids": txn_ids,
                    }
                )
    return findings


def detect_velocity(customer_feats: pd.DataFrame) -> list[Finding]:
    """Customers whose 24h burst count is a statistical outlier."""
    f = customer_feats
    if f.empty or "max_cnt_24h" not in f:
        return []
    vals = f["max_cnt_24h"].astype(float)
    mu, sd = vals.mean(), vals.std(ddof=0)
    if sd == 0:
        return []
    z = (vals - mu) / sd
    findings: list[Finding] = []
    for i, zi in z.items():
        if zi >= T.velocity_zscore:
            row = f.loc[i]
            findings.append(
                {
                    "customer_id": int(row["customer_id"]),
                    "typology": "velocity_spike",
                    "weight_key": "velocity",
                    "severity": min(1.0, float(zi) / (T.velocity_zscore * 2)),
                    "evidence": {
                        "max_transactions_24h": int(row["max_cnt_24h"]),
                        "zscore": round(float(zi), 2),
                        "population_mean": round(float(mu), 2),
                    },
                    "transaction_ids": [],
                }
            )
    return findings


def detect_high_risk_geography(txns: pd.DataFrame) -> list[Finding]:
    """Exposure to FATF-flagged jurisdictions (mild amplifier only)."""
    if "counterparty_country" not in txns:
        return []
    df = txns.copy()
    hr = df[df["counterparty_country"].str.upper().isin(HIGH_RISK_COUNTRIES)]
    findings: list[Finding] = []
    for cid, g in hr.groupby("customer_id"):
        findings.append(
            {
                "customer_id": int(cid),
                "typology": "high_risk_geography",
                "weight_key": "high_risk_geography",
                "severity": min(1.0, len(g) / 5),
                "evidence": {
                    "n_high_risk_txns": int(len(g)),
                    "countries": sorted(
                        g["counterparty_country"].str.upper().unique().tolist()
                    ),
                    "amount": round(float(g["amount"].sum()), 2),
                },
                "transaction_ids": g["transaction_id"].head(10).tolist(),
            }
        )
    return findings


# --------------------------------------------------------------------------
# ML detector (unsupervised)
# --------------------------------------------------------------------------
def ml_anomaly(customer_feats: pd.DataFrame, contamination: float = 0.05):
    """Isolation Forest over the customer fingerprint.

    Returns ``(scored_df, findings)`` where ``scored_df`` has an
    ``ml_anomaly_score`` in ``[0, 1]`` (higher == more anomalous) for every
    customer, and ``findings`` covers the flagged outliers.
    """
    from sklearn.ensemble import IsolationForest
    from sklearn.preprocessing import StandardScaler

    f = customer_feats.copy()
    cols = [c for c in ML_FEATURE_COLS if c in f.columns]
    X = f[cols].replace([np.inf, -np.inf], np.nan).fillna(0.0).to_numpy()
    if len(f) < 5:
        f["ml_anomaly_score"] = 0.0
        return f, []

    Xs = StandardScaler().fit_transform(X)
    model = IsolationForest(
        n_estimators=200,
        contamination=contamination,
        random_state=SETTINGS.random_seed,
    )
    model.fit(Xs)
    raw = -model.score_samples(Xs)  # higher == more anomalous
    # Normalise to 0..1 across the population.
    lo, hi = raw.min(), raw.max()
    norm = (raw - lo) / (hi - lo) if hi > lo else np.zeros_like(raw)
    f["ml_anomaly_score"] = norm
    flags = model.predict(Xs) == -1

    findings: list[Finding] = []
    top_cols = cols
    for i, is_out in enumerate(flags):
        if not is_out:
            continue
        row = f.iloc[i]
        # Surface the features that most exceed the population mean.
        contrib = {
            c: round(float(row[c]), 2)
            for c in top_cols
            if row[c] > f[c].mean() + f[c].std(ddof=0)
        }
        findings.append(
            {
                "customer_id": int(row["customer_id"]),
                "typology": "ml_anomaly",
                "weight_key": "ml_anomaly",
                "severity": float(row["ml_anomaly_score"]),
                "evidence": {
                    "ml_anomaly_score": round(float(row["ml_anomaly_score"]), 3),
                    "outlier_features": dict(sorted(
                        contrib.items(), key=lambda kv: -kv[1])[:5]),
                },
                "transaction_ids": [],
            }
        )
    return f, findings


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------
def _max_in_window(timestamps: pd.Series, window_days: int) -> int:
    """Max number of events falling inside any window of ``window_days``."""
    ts = np.sort(timestamps.to_numpy().astype("datetime64[s]"))
    if len(ts) == 0:
        return 0
    window = np.timedelta64(window_days, "D")
    best = 1
    j = 0
    for i in range(len(ts)):
        while ts[i] - ts[j] > window:
            j += 1
        best = max(best, i - j + 1)
    return best


def _best_smurf_window(g: pd.DataFrame, window: pd.Timedelta) -> dict:
    """Find the window with the most distinct inbound counterparties."""
    g = g.sort_values("timestamp").reset_index(drop=True)
    ts = g["timestamp"].to_numpy()
    best = {"n_counterparties": 0, "total": 0.0, "txn_ids": []}
    j = 0
    for i in range(len(g)):
        while ts[i] - ts[j] > window.to_timedelta64():
            j += 1
        window_slice = g.iloc[j : i + 1]
        n_cp = window_slice["counterparty_id"].nunique()
        if n_cp > best["n_counterparties"]:
            best = {
                "n_counterparties": int(n_cp),
                "total": float(window_slice["amount"].sum()),
                "txn_ids": window_slice["transaction_id"].head(25).tolist(),
            }
    return best


# Registry so the orchestrator can select detectors by typology name.
TYPOLOGY_DETECTORS = {
    "structuring": detect_structuring,
    "smurfing": detect_smurfing,
    "rapid_cashout": detect_rapid_cashout,
    "layering": detect_layering,
    "high_risk_geography": detect_high_risk_geography,
}
