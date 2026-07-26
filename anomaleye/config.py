"""Central configuration for AnomalEye.

Thresholds live here so business logic is auditable and tunable in one place
rather than scattered across the tools. Regulators care about *why* a number
was chosen, so every constant carries a short rationale.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

# --- Paths ----------------------------------------------------------------
ROOT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT_DIR / "data"
DEFAULT_TRANSACTIONS = DATA_DIR / "transactions.csv"
DEFAULT_CUSTOMERS = DATA_DIR / "customers.csv"


@dataclass(frozen=True)
class Thresholds:
    """AML business thresholds.

    The US Bank Secrecy Act requires a Currency Transaction Report (CTR) for
    cash transactions above USD 10,000. Structuring is the practice of keeping
    transactions *just under* that line to avoid the report, so most of our
    detection logic is anchored to it.
    """

    # Regulatory reporting line (CTR).
    ctr_threshold: float = 10_000.0

    # A transaction is "just under" the CTR line if it falls in this band.
    # 9,000-9,999 is the classic structuring footprint.
    structuring_band_low: float = 9_000.0
    structuring_band_high: float = 9_999.99

    # How many just-under transactions in the window before we call it
    # structuring. FinCEN advisories treat repeated sub-threshold cash as the
    # primary red flag.
    structuring_min_count: int = 3
    structuring_window_days: int = 30

    # Smurfing: many *small* inbound transfers from distinct counterparties
    # that aggregate above the CTR line within a short window. Only inbound
    # amounts below ``smurfing_max_txn_amount`` count, since breaking a large
    # sum into small pieces is the defining feature.
    smurfing_min_counterparties: int = 6
    smurfing_window_days: int = 7
    smurfing_aggregate_multiplier: float = 1.0  # x ctr_threshold
    smurfing_max_txn_amount: float = 5_000.0

    # Rapid cash-out (placement then quick removal): a large credit followed by
    # withdrawals draining most of it within the window.
    rapid_cashout_window_hours: int = 72
    rapid_cashout_drain_ratio: float = 0.8  # 80% of the credit leaves

    # Layering: a chain of transfers moving similar value through several hops
    # in a short time.
    layering_window_hours: int = 48
    layering_min_hops: int = 3
    layering_amount_tolerance: float = 0.15  # amounts within +/-15%

    # Velocity: transaction count spike vs the customer's own baseline.
    velocity_zscore: float = 3.0

    # Risk band cut-offs applied to the normalised 0-100 risk score.
    risk_high: float = 70.0
    risk_medium: float = 40.0


@dataclass(frozen=True)
class Weights:
    """Relative contribution of each signal to the blended risk score.

    Kept explicit so an analyst can see exactly how a score was assembled.
    Values are summed then normalised, so only their ratios matter.
    """

    structuring: float = 30.0
    smurfing: float = 25.0
    rapid_cashout: float = 20.0
    layering: float = 15.0
    velocity: float = 10.0
    amount_deviation: float = 10.0
    ml_anomaly: float = 25.0
    high_risk_geography: float = 10.0


# Jurisdictions commonly cited on FATF grey/black lists or as high-risk for
# illicit finance. Used only as a mild risk amplifier, never as sole cause.
HIGH_RISK_COUNTRIES = frozenset(
    {"IR", "KP", "SY", "MM", "AF", "YE", "PA", "KY", "VG", "SC"}
)


@dataclass(frozen=True)
class Settings:
    thresholds: Thresholds = field(default_factory=Thresholds)
    weights: Weights = field(default_factory=Weights)
    random_seed: int = 42


SETTINGS = Settings()
