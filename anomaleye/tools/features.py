"""Feature engineering tool — creates model- and rule-ready AML features.

Two granularities are produced:

* **transaction-level** features attach behavioural context to each row
  (rolling sums, velocity, amount deviation, proximity to the CTR line).
* **customer-level** aggregates roll those up into a per-customer behavioural
  fingerprint used by both the rule detectors and the ML model.

The agent asks for only the features a given query needs — e.g. a structuring
query needs the CTR-proximity and rolling-count features but not the layering
graph features.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from anomaleye.config import SETTINGS

T = SETTINGS.thresholds


def add_transaction_features(txns: pd.DataFrame) -> pd.DataFrame:
    """Return a copy of ``txns`` with per-transaction AML features added."""
    df = txns.sort_values(["customer_id", "timestamp"]).copy()
    df["timestamp"] = pd.to_datetime(df["timestamp"])

    grp = df.groupby("customer_id", sort=False)

    # Proximity to the CTR reporting line (1.0 == right at the line).
    df["ctr_proximity"] = (df["amount"] / T.ctr_threshold).clip(upper=1.5)
    df["just_under_ctr"] = (
        (df["amount"] >= T.structuring_band_low)
        & (df["amount"] < T.ctr_threshold)
    ).astype(int)

    # Amount deviation vs the customer's own history (robust z via MAD).
    med = grp["amount"].transform("median")
    mad = grp["amount"].transform(lambda s: (s - s.median()).abs().median())
    df["amount_dev_z"] = ((df["amount"] - med) / (mad.replace(0, np.nan) * 1.4826))
    df["amount_dev_z"] = df["amount_dev_z"].fillna(0.0).abs()

    # Time since the customer's previous transaction (velocity signal).
    df["secs_since_prev"] = (
        grp["timestamp"].diff().dt.total_seconds().fillna(np.inf)
    )
    df["is_rapid_followup"] = (df["secs_since_prev"] < 3600).astype(int)

    # Rolling 24h / 7d transaction counts per customer (time-windowed).
    df = df.set_index("timestamp")
    df["cnt_24h"] = (
        df.groupby("customer_id")["amount"]
        .rolling("24h").count().reset_index(level=0, drop=True)
    )
    df["sum_7d"] = (
        df.groupby("customer_id")["amount"]
        .rolling("7D").sum().reset_index(level=0, drop=True)
    )
    df = df.reset_index()

    return df


def customer_features(txns: pd.DataFrame) -> pd.DataFrame:
    """Aggregate transaction features into a per-customer fingerprint."""
    df = add_transaction_features(txns)
    g = df.groupby("customer_id")

    feats = pd.DataFrame(
        {
            "n_transactions": g.size(),
            "total_amount": g["amount"].sum(),
            "mean_amount": g["amount"].mean(),
            "std_amount": g["amount"].std(ddof=0).fillna(0.0),
            "max_amount": g["amount"].max(),
            "n_just_under_ctr": g["just_under_ctr"].sum(),
            "share_just_under_ctr": g["just_under_ctr"].mean(),
            "max_amount_dev_z": g["amount_dev_z"].max(),
            "n_rapid_followups": g["is_rapid_followup"].sum(),
            "max_cnt_24h": g["cnt_24h"].max(),
            "max_sum_7d": g["sum_7d"].max(),
            "n_counterparties": g["counterparty_id"].nunique()
            if "counterparty_id" in df
            else 0,
        }
    )

    # Inbound counterparty concentration (smurfing collectors receive from
    # many distinct parties).
    if "counterparty_id" in df and "type" in df:
        inbound = df[df["type"].isin(["transfer", "deposit"])]
        feats["n_inbound_counterparties"] = (
            inbound.groupby("customer_id")["counterparty_id"].nunique()
        )
        feats["n_inbound_counterparties"] = (
            feats["n_inbound_counterparties"].fillna(0).astype(int)
        )
    else:
        feats["n_inbound_counterparties"] = 0

    return feats.reset_index()


# The numeric columns the ML anomaly model consumes.
ML_FEATURE_COLS = [
    "n_transactions",
    "total_amount",
    "mean_amount",
    "std_amount",
    "max_amount",
    "n_just_under_ctr",
    "share_just_under_ctr",
    "max_amount_dev_z",
    "n_rapid_followups",
    "max_cnt_24h",
    "max_sum_7d",
    "n_counterparties",
    "n_inbound_counterparties",
]
