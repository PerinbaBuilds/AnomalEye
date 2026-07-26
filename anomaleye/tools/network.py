"""Link-analysis tool — builds counterparty network graphs.

Money-laundering is a *relational* phenomenon: structuring hides in one
account, but smurfing (many senders → one collector) and layering (a chain of
hops) only reveal themselves as a graph. This tool turns a customer's
transactions into nodes + edges the frontend can render as a link chart, and
extracts the layering chains discovered by the detector as explicit paths.
"""

from __future__ import annotations

from typing import Any, Iterable

import pandas as pd


def build_customer_network(
    transactions: pd.DataFrame,
    customer_id: int,
    flagged_ids: Iterable[int] | None = None,
    max_counterparties: int = 40,
) -> dict[str, Any]:
    """Return ``{nodes, edges}`` for a customer and their counterparties.

    Edge direction encodes fund flow (``in`` = counterparty → customer,
    ``out`` = customer → counterparty); weight is the aggregated amount.
    """
    flagged = set(int(x) for x in (flagged_ids or []))
    df = transactions[transactions["customer_id"] == customer_id].copy()
    if df.empty or "counterparty_id" not in df:
        return {"nodes": [], "edges": [], "center": int(customer_id)}

    inbound_types = {"deposit", "transfer", "payment"}
    df["direction"] = df["type"].apply(
        lambda t: "in" if t in inbound_types else "out"
    )

    agg = (
        df.groupby(["counterparty_id", "direction"])
        .agg(amount=("amount", "sum"), count=("amount", "size"))
        .reset_index()
    )
    # Keep the heaviest counterparties so the graph stays legible.
    top_cp = (
        agg.groupby("counterparty_id")["amount"].sum()
        .sort_values(ascending=False)
        .head(max_counterparties)
        .index
    )
    agg = agg[agg["counterparty_id"].isin(top_cp)]

    nodes: list[dict[str, Any]] = [
        {
            "id": int(customer_id),
            "label": f"Customer {customer_id}",
            "kind": "focus",
            "flagged": int(customer_id) in flagged,
        }
    ]
    edges: list[dict[str, Any]] = []
    seen_cp: set[int] = set()
    for _, r in agg.iterrows():
        cp = int(r["counterparty_id"])
        if cp not in seen_cp:
            seen_cp.add(cp)
            nodes.append(
                {
                    "id": cp,
                    "label": f"CP {cp}",
                    "kind": "customer" if cp in flagged else "counterparty",
                    "flagged": cp in flagged,
                }
            )
        src, dst = (cp, customer_id) if r["direction"] == "in" else (
            customer_id, cp)
        edges.append(
            {
                "source": int(src),
                "target": int(dst),
                "amount": round(float(r["amount"]), 2),
                "count": int(r["count"]),
                "direction": r["direction"],
            }
        )
    return {
        "nodes": nodes,
        "edges": edges,
        "center": int(customer_id),
        "n_counterparties": len(seen_cp),
    }


def layering_paths(findings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Extract distinct layering chains (as node paths) from findings."""
    seen: set[tuple] = set()
    paths: list[dict[str, Any]] = []
    for f in findings:
        if f.get("typology") != "layering":
            continue
        path = tuple(f["evidence"].get("path", []))
        if len(path) < 2 or path in seen:
            continue
        seen.add(path)
        paths.append(
            {
                "path": list(path),
                "hops": f["evidence"].get("n_hops"),
                "amounts": f["evidence"].get("amounts", []),
            }
        )
    return paths
