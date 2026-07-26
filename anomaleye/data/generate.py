"""Synthetic AML dataset generator.

Real transaction data is confidential, so AnomalEye ships a generator that
produces a realistic customer + transaction dataset with a *known* set of
laundering typologies injected into it. Because the ground truth is known, the
detection tools can be validated end to end (see ``tests/``).

Injected typologies
-------------------
* **structuring**  — one customer makes many cash deposits just below the
  USD 10,000 CTR reporting line.
* **smurfing**     — many "mule" counterparties push small transfers into a
  single collector account that aggregate well over the CTR line.
* **rapid cash-out** — a large credit lands and is drained by withdrawals
  within a few days (placement then removal).
* **layering**     — value is bounced through a chain of accounts in quick
  hops to obscure its origin.

Every injected transaction is tagged in the hidden ``is_laundering`` /
``typology`` columns so evaluation is possible; a detector should never *see*
those columns, they exist purely for scoring.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timedelta

import numpy as np
import pandas as pd

from anomaleye.config import DEFAULT_CUSTOMERS, DEFAULT_TRANSACTIONS, SETTINGS

COUNTRIES = ["US", "GB", "DE", "FR", "IN", "SG", "AE", "CA", "AU", "NL"]
HIGH_RISK = ["IR", "KP", "PA", "KY", "SC"]
SEGMENTS = ["retail", "sme", "corporate", "private_wealth"]
OCCUPATIONS = [
    "salaried",
    "self_employed",
    "business_owner",
    "student",
    "retired",
    "consultant",
]
CHANNELS = ["branch", "atm", "online", "mobile", "wire"]
TXN_TYPES = ["deposit", "withdrawal", "transfer", "payment", "cash"]


@dataclass
class GenConfig:
    n_customers: int = 800
    n_normal_txns: int = 40_000
    days: int = 120
    seed: int = SETTINGS.random_seed
    # How many customers exhibit each typology.
    n_structurers: int = 12
    n_smurf_collectors: int = 6
    n_rapid_cashout: int = 10
    n_layering_chains: int = 6


def _rng(seed: int) -> np.random.Generator:
    return np.random.default_rng(seed)


def generate_customers(cfg: GenConfig) -> pd.DataFrame:
    rng = _rng(cfg.seed)
    ids = np.arange(1000, 1000 + cfg.n_customers)
    open_start = datetime(2015, 1, 1)
    rows = []
    for cid in ids:
        # A small share of customers sit in high-risk jurisdictions.
        if rng.random() < 0.06:
            country = rng.choice(HIGH_RISK)
        else:
            country = rng.choice(COUNTRIES)
        rows.append(
            {
                "customer_id": int(cid),
                "name": f"Customer_{cid}",
                "country": country,
                "segment": rng.choice(SEGMENTS, p=[0.55, 0.25, 0.12, 0.08]),
                "occupation": rng.choice(OCCUPATIONS),
                "account_open_date": (
                    open_start + timedelta(days=int(rng.integers(0, 3200)))
                ).date().isoformat(),
                "kyc_risk_rating": rng.choice(
                    ["low", "medium", "high"], p=[0.7, 0.25, 0.05]
                ),
            }
        )
    return pd.DataFrame(rows)


def _base_amount(rng: np.random.Generator, segment: str) -> float:
    """Draw a plausible amount for a customer's segment (log-normal)."""
    means = {"retail": 5.2, "sme": 6.5, "corporate": 7.6, "private_wealth": 7.9}
    sigma = {"retail": 0.9, "sme": 1.0, "corporate": 1.1, "private_wealth": 1.2}
    return float(np.exp(rng.normal(means[segment], sigma[segment])))


def generate_normal_transactions(
    cfg: GenConfig, customers: pd.DataFrame, start_txn_id: int = 1
) -> pd.DataFrame:
    rng = _rng(cfg.seed + 1)
    end = datetime(2024, 1, 1) + timedelta(days=cfg.days)
    start = end - timedelta(days=cfg.days)
    seg_by_id = dict(zip(customers.customer_id, customers.segment))
    ctry_by_id = dict(zip(customers.customer_id, customers.country))
    ids = customers.customer_id.to_numpy()

    rows = []
    tid = start_txn_id
    for _ in range(cfg.n_normal_txns):
        cid = int(rng.choice(ids))
        seg = seg_by_id[cid]
        amount = round(_base_amount(rng, seg), 2)
        ts = start + timedelta(
            seconds=int(rng.integers(0, cfg.days * 24 * 3600))
        )
        ttype = rng.choice(TXN_TYPES, p=[0.28, 0.24, 0.22, 0.18, 0.08])
        rows.append(
            {
                "transaction_id": tid,
                "customer_id": cid,
                "timestamp": ts,
                "amount": amount,
                "type": ttype,
                "channel": rng.choice(CHANNELS),
                "counterparty_id": int(rng.integers(50_000, 90_000)),
                "counterparty_country": ctry_by_id[cid]
                if rng.random() < 0.8
                else rng.choice(COUNTRIES),
                "is_laundering": 0,
                "typology": "none",
            }
        )
        tid += 1
    return pd.DataFrame(rows)


def _inject_structuring(cfg, customers, rng, tid, start):
    """Repeated cash deposits just under the CTR line."""
    rows = []
    victims = rng.choice(customers.customer_id, cfg.n_structurers, replace=False)
    for cid in victims:
        cid = int(cid)
        n = int(rng.integers(4, 10))
        day0 = start + timedelta(days=int(rng.integers(0, cfg.days - 25)))
        for _ in range(n):
            amt = round(float(rng.uniform(9_100, 9_950)), 2)
            ts = day0 + timedelta(
                days=int(rng.integers(0, 22)), hours=int(rng.integers(8, 18))
            )
            rows.append(
                _txn(tid, cid, ts, amt, "cash", "branch", rng, "structuring")
            )
            tid += 1
    return rows, tid


def _inject_smurfing(cfg, customers, rng, tid, start):
    """Many mule counterparties feed one collector account."""
    rows = []
    collectors = rng.choice(
        customers.customer_id, cfg.n_smurf_collectors, replace=False
    )
    for cid in collectors:
        cid = int(cid)
        n_mules = int(rng.integers(6, 14))
        day0 = start + timedelta(days=int(rng.integers(0, cfg.days - 8)))
        for m in range(n_mules):
            amt = round(float(rng.uniform(1_500, 3_500)), 2)
            ts = day0 + timedelta(
                days=int(rng.integers(0, 6)), hours=int(rng.integers(0, 24))
            )
            r = _txn(tid, cid, ts, amt, "transfer", "online", rng, "smurfing")
            r["counterparty_id"] = int(200_000 + m + cid)  # distinct mules
            rows.append(r)
            tid += 1
    return rows, tid


def _inject_rapid_cashout(cfg, customers, rng, tid, start):
    """Large credit drained by withdrawals within a couple of days."""
    rows = []
    victims = rng.choice(
        customers.customer_id, cfg.n_rapid_cashout, replace=False
    )
    for cid in victims:
        cid = int(cid)
        credit = round(float(rng.uniform(45_000, 120_000)), 2)
        t0 = start + timedelta(
            days=int(rng.integers(0, cfg.days - 5)), hours=int(rng.integers(8, 16))
        )
        rows.append(
            _txn(tid, cid, t0, credit, "deposit", "wire", rng, "rapid_cashout")
        )
        tid += 1
        # Drain ~90% over the next 1-3 days in several withdrawals.
        remaining = credit * float(rng.uniform(0.85, 0.95))
        n_out = int(rng.integers(3, 7))
        for k in range(n_out):
            amt = round(remaining / n_out, 2)
            ts = t0 + timedelta(hours=int(rng.integers(2, 70)))
            rows.append(
                _txn(tid, cid, ts, amt, "withdrawal", "atm", rng, "rapid_cashout")
            )
            tid += 1
    return rows, tid


def _inject_layering(cfg, customers, rng, tid, start):
    """Value hops through a chain of accounts in quick succession."""
    rows = []
    for _ in range(cfg.n_layering_chains):
        chain = rng.choice(customers.customer_id, int(rng.integers(3, 6)),
                           replace=False)
        amount = round(float(rng.uniform(20_000, 60_000)), 2)
        t = start + timedelta(days=int(rng.integers(0, cfg.days - 3)),
                             hours=int(rng.integers(8, 16)))
        for i in range(len(chain) - 1):
            src, dst = int(chain[i]), int(chain[i + 1])
            # Small skim at each hop keeps amounts within tolerance.
            amount = round(amount * float(rng.uniform(0.9, 0.99)), 2)
            t = t + timedelta(hours=int(rng.integers(1, 10)))
            r = _txn(tid, src, t, amount, "transfer", "wire", rng, "layering")
            r["counterparty_id"] = dst
            rows.append(r)
            tid += 1
    return rows, tid


def _txn(tid, cid, ts, amount, ttype, channel, rng, typology):
    return {
        "transaction_id": tid,
        "customer_id": cid,
        "timestamp": ts,
        "amount": amount,
        "type": ttype,
        "channel": channel,
        "counterparty_id": int(rng.integers(50_000, 90_000)),
        "counterparty_country": rng.choice(COUNTRIES),
        "is_laundering": 1,
        "typology": typology,
    }


def generate(cfg: GenConfig | None = None):
    """Return ``(customers_df, transactions_df)`` with injected typologies."""
    cfg = cfg or GenConfig()
    customers = generate_customers(cfg)
    normal = generate_normal_transactions(cfg, customers)
    rng = _rng(cfg.seed + 2)
    start = normal.timestamp.min()
    tid = int(normal.transaction_id.max()) + 1

    injected = []
    for fn in (
        _inject_structuring,
        _inject_smurfing,
        _inject_rapid_cashout,
        _inject_layering,
    ):
        rows, tid = fn(cfg, customers, rng, tid, start)
        injected.extend(rows)

    txns = pd.concat([normal, pd.DataFrame(injected)], ignore_index=True)
    txns = txns.sort_values("timestamp").reset_index(drop=True)
    txns["transaction_id"] = np.arange(1, len(txns) + 1)
    return customers, txns


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate synthetic AML data")
    parser.add_argument("--customers", type=int, default=GenConfig.n_customers)
    parser.add_argument("--transactions", type=int,
                       default=GenConfig.n_normal_txns)
    parser.add_argument("--days", type=int, default=GenConfig.days)
    parser.add_argument("--seed", type=int, default=SETTINGS.random_seed)
    args = parser.parse_args()

    cfg = GenConfig(
        n_customers=args.customers,
        n_normal_txns=args.transactions,
        days=args.days,
        seed=args.seed,
    )
    customers, txns = generate(cfg)
    DEFAULT_CUSTOMERS.parent.mkdir(parents=True, exist_ok=True)
    customers.to_csv(DEFAULT_CUSTOMERS, index=False)
    txns.to_csv(DEFAULT_TRANSACTIONS, index=False)
    n_laundering = int(txns.is_laundering.sum())
    print(f"Wrote {len(customers):,} customers -> {DEFAULT_CUSTOMERS}")
    print(f"Wrote {len(txns):,} transactions -> {DEFAULT_TRANSACTIONS}")
    print(
        f"Injected {n_laundering:,} laundering transactions "
        f"({n_laundering / len(txns):.2%}) across "
        f"{txns[txns.is_laundering == 1].typology.nunique()} typologies"
    )


if __name__ == "__main__":
    main()
