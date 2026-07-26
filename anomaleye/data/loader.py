"""Dataset loading and validation.

Loads the transaction/customer CSVs, normalises dtypes, and guarantees the
columns the tools rely on exist. If the CSVs are missing, it generates them on
the fly so the demo always works out of the box.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from anomaleye.config import DEFAULT_CUSTOMERS, DEFAULT_TRANSACTIONS

REQUIRED_TXN_COLS = {
    "transaction_id",
    "customer_id",
    "timestamp",
    "amount",
    "type",
}

# Columns that encode the injected ground truth. Detectors must not read these;
# they are stripped from the working frame and kept aside for evaluation only.
GROUND_TRUTH_COLS = ["is_laundering", "typology"]


class Dataset:
    """A validated transaction + customer dataset.

    Attributes
    ----------
    transactions : pd.DataFrame
        Working transactions (ground-truth columns removed).
    customers : pd.DataFrame
        Customer reference data.
    ground_truth : pd.DataFrame | None
        ``transaction_id`` -> injected label, when available.
    """

    def __init__(self, transactions: pd.DataFrame, customers: pd.DataFrame):
        self.ground_truth = None
        gt_cols = [c for c in GROUND_TRUTH_COLS if c in transactions.columns]
        if gt_cols:
            self.ground_truth = transactions[["transaction_id", *gt_cols]].copy()
        self.transactions = self._normalise(
            transactions.drop(columns=gt_cols, errors="ignore")
        )
        self.customers = customers.copy()
        self._validate()

    @staticmethod
    def _normalise(df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
        df["amount"] = pd.to_numeric(df["amount"], errors="coerce")
        df = df.dropna(subset=["timestamp", "amount"])
        for col in ("type", "channel", "country", "counterparty_country"):
            if col in df.columns:
                df[col] = df[col].astype("string").str.lower()
        return df.sort_values("timestamp").reset_index(drop=True)

    def _validate(self) -> None:
        missing = REQUIRED_TXN_COLS - set(self.transactions.columns)
        if missing:
            raise ValueError(
                f"Transactions missing required columns: {sorted(missing)}"
            )

    def enriched(self) -> pd.DataFrame:
        """Transactions joined with customer attributes."""
        if "customer_id" not in self.customers.columns:
            return self.transactions
        cust = self.customers.rename(columns={"country": "customer_country"})
        return self.transactions.merge(cust, on="customer_id", how="left")

    def __repr__(self) -> str:  # pragma: no cover - cosmetic
        return (
            f"Dataset(transactions={len(self.transactions):,}, "
            f"customers={len(self.customers):,})"
        )


def load_dataset(
    transactions_path: str | Path | None = None,
    customers_path: str | Path | None = None,
    auto_generate: bool = True,
) -> Dataset:
    """Load a :class:`Dataset`, generating the CSVs if they are absent."""
    tpath = Path(transactions_path or DEFAULT_TRANSACTIONS)
    cpath = Path(customers_path or DEFAULT_CUSTOMERS)

    if not tpath.exists() or not cpath.exists():
        if not auto_generate:
            raise FileNotFoundError(
                f"Dataset not found at {tpath} / {cpath}. "
                "Run `python -m anomaleye.data.generate` first."
            )
        from anomaleye.data.generate import generate

        customers, txns = generate()
        tpath.parent.mkdir(parents=True, exist_ok=True)
        customers.to_csv(cpath, index=False)
        txns.to_csv(tpath, index=False)

    transactions = pd.read_csv(tpath)
    customers = pd.read_csv(cpath)
    return Dataset(transactions, customers)
