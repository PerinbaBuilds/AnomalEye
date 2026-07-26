"""Export the synthetic dataset to a single Excel workbook.

Produces ``data/anomaleye_dataset.xlsx`` with four sheets so reviewers can
inspect the data (and the injected ground truth) as proof/reference:

* **Overview**       — dataset summary + injected-typology counts
* **Customers**      — customer reference table
* **Transactions**   — every transaction, incl. the hidden ``is_laundering`` /
                       ``typology`` labels used only for evaluation
* **Data Dictionary**— column definitions

Run: ``python -m anomaleye.data.export_excel``
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from anomaleye.config import DATA_DIR, DEFAULT_CUSTOMERS, DEFAULT_TRANSACTIONS

OUTPUT = DATA_DIR / "anomaleye_dataset.xlsx"

DICTIONARY = [
    ("customer_id", "customers/transactions", "Unique customer identifier"),
    ("name", "customers", "Customer display name (synthetic)"),
    ("country", "customers", "Customer home country (ISO-2)"),
    ("segment", "customers", "retail / sme / corporate / private_wealth"),
    ("occupation", "customers", "Declared occupation"),
    ("account_open_date", "customers", "Account opening date"),
    ("kyc_risk_rating", "customers", "KYC risk rating: low / medium / high"),
    ("transaction_id", "transactions", "Unique transaction identifier"),
    ("timestamp", "transactions", "Transaction datetime"),
    ("amount", "transactions", "Transaction amount in USD"),
    ("type", "transactions", "deposit / withdrawal / transfer / payment / cash"),
    ("channel", "transactions", "branch / atm / online / mobile / wire"),
    ("counterparty_id", "transactions", "Counterparty account identifier"),
    ("counterparty_country", "transactions", "Counterparty country (ISO-2)"),
    ("is_laundering", "transactions", "GROUND TRUTH: 1 if injected laundering "
     "(evaluation only, hidden from detectors)"),
    ("typology", "transactions", "GROUND TRUTH: injected scheme "
     "(structuring/smurfing/rapid_cashout/layering/none)"),
]


def build_workbook(
    customers_path: Path | str = DEFAULT_CUSTOMERS,
    transactions_path: Path | str = DEFAULT_TRANSACTIONS,
    output: Path | str = OUTPUT,
) -> Path:
    customers = pd.read_csv(customers_path)
    txns = pd.read_csv(transactions_path)

    n_l = int(txns["is_laundering"].sum()) if "is_laundering" in txns else 0
    typ_counts = (
        txns[txns.get("is_laundering", 0) == 1]["typology"].value_counts()
        if "typology" in txns
        else pd.Series(dtype=int)
    )
    overview = pd.DataFrame(
        [
            ("Total customers", len(customers)),
            ("Total transactions", len(txns)),
            ("Date range", f"{txns['timestamp'].min()} → {txns['timestamp'].max()}"),
            ("Total volume (USD)", round(float(txns["amount"].sum()), 2)),
            ("Injected laundering transactions", n_l),
            ("Laundering share", f"{n_l / max(len(txns), 1):.2%}"),
            *[(f"  · {t}", int(c)) for t, c in typ_counts.items()],
        ],
        columns=["Metric", "Value"],
    )
    dictionary = pd.DataFrame(
        DICTIONARY, columns=["Column", "Sheet", "Description"]
    )

    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(output, engine="openpyxl") as xl:
        overview.to_excel(xl, sheet_name="Overview", index=False)
        customers.to_excel(xl, sheet_name="Customers", index=False)
        txns.to_excel(xl, sheet_name="Transactions", index=False)
        dictionary.to_excel(xl, sheet_name="Data Dictionary", index=False)

        # Widen columns a little for readability.
        for sheet in xl.book.worksheets:
            for col in sheet.columns:
                width = max(
                    (len(str(c.value)) for c in col if c.value is not None),
                    default=10,
                )
                sheet.column_dimensions[col[0].column_letter].width = min(
                    max(width + 2, 12), 48
                )
    return output


def main() -> None:  # pragma: no cover - thin CLI
    path = build_workbook()
    size_mb = path.stat().st_size / 1e6
    print(f"Wrote {path} ({size_mb:.1f} MB)")


if __name__ == "__main__":
    main()
