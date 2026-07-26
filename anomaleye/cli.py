"""Command-line interface for AnomalEye.

Examples
--------
    python -m anomaleye "Analyse this dataset for suspicious activity"
    python -m anomaleye "Find structuring patterns in the last 30 days"
    python -m anomaleye "Is customer ID 1528 suspicious?" --json
    python -m anomaleye --demo          # run the canned example queries
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from anomaleye.agent.orchestrator import Agent

DEMO_QUERIES = [
    "Analyse this dataset for suspicious activity",
    "Find structuring patterns in the last 30 days",
    "Which customers made 10+ transactions under $10,000?",
    "Flag high-risk customers",
    "Is customer ID 1528 suspicious?",
    "Give me an overview of the data",
]

_LEVEL_COLOR = {
    "high": "\033[91m",     # red
    "medium": "\033[93m",   # yellow
    "low": "\033[92m",      # green
}
_RESET = "\033[0m"
_BOLD = "\033[1m"
_DIM = "\033[2m"


def _c(text: str, code: str, use_color: bool) -> str:
    return f"{code}{text}{_RESET}" if use_color else text


def render(result: dict[str, Any], use_color: bool = True) -> str:
    es = result["execution_summary"]
    lines: list[str] = []
    add = lines.append

    add(_c("═" * 74, _DIM, use_color))
    add(_c(f"  QUERY: {es['user_query']}", _BOLD, use_color))
    add(_c("═" * 74, _DIM, use_color))

    add(_c("\n▸ Execution plan (what the agent decided)", _BOLD, use_color))
    add(f"    intent            : {es['detected_intent']}")
    if es["detected_customer_id"] is not None:
        add(f"    customer          : {es['detected_customer_id']}")
    if es["detected_filters"]:
        add(f"    filters           : {es['detected_filters']}")
    if es["detected_typologies"]:
        add(f"    typologies         : {', '.join(es['detected_typologies'])}")
    add(f"    tools invoked     : {' -> '.join(es['tools_invoked'])}")
    add(f"    transactions used : {es['transactions_in_scope']:,}")
    for r in es["planning_rationale"]:
        add(_c(f"      · {r}", _DIM, use_color))

    if "eda" in result:
        prof = result["eda"]["profile"]
        add(_c("\n▸ EDA profile", _BOLD, use_color))
        add(f"    transactions      : {prof.get('n_transactions'):,}")
        add(f"    customers         : {prof.get('n_customers')}")
        amt = prof.get("amount", {})
        if amt:
            add(f"    amount mean/median: "
                f"${amt.get('mean'):,.2f} / ${amt.get('median'):,.2f}")
            add(f"    amount p99 / max  : "
                f"${amt.get('p99'):,.2f} / ${amt.get('max'):,.2f}")
        add(f"    CTR-band share    : {prof.get('ctr_band_share')}")

    counts = result["counts"]
    add(_c("\n▸ Risk summary", _BOLD, use_color))
    add(f"    flagged entities  : {counts['total_flagged']}  "
        f"(high={counts['high']}, medium={counts['medium']}, "
        f"low={counts['low']})")

    if result["explanations"]:
        add(_c("\n▸ Top flagged entities", _BOLD, use_color))
        for ex in result["explanations"]:
            color = _LEVEL_COLOR.get(ex["risk_level"], "")
            badge = _c(f"[{ex['risk_level'].upper()}]", color, use_color)
            add(f"\n  {badge} Customer {ex['customer_id']} — "
                f"score {ex['risk_score']}/100 — "
                f"action: {_c(ex['escalation'].upper(), _BOLD, use_color)}")
            for reason in ex["reasons"]:
                add(f"      • {reason}")
            add(_c(f"      → {ex['escalation_rationale']}", _DIM, use_color))
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="anomaleye",
        description="Agentic AML suspicious-activity detection.",
    )
    parser.add_argument("query", nargs="*", help="natural-language instruction")
    parser.add_argument("--json", action="store_true",
                       help="emit raw JSON result")
    parser.add_argument("--demo", action="store_true",
                       help="run the canned example queries")
    parser.add_argument("--no-color", action="store_true")
    parser.add_argument("--top", type=int, default=10,
                       help="max flagged entities to return")
    parser.add_argument("--transactions", default=None)
    parser.add_argument("--customers", default=None)
    args = parser.parse_args(argv)

    from anomaleye.data.loader import load_dataset

    dataset = load_dataset(args.transactions, args.customers)
    agent = Agent(dataset=dataset, top_n=args.top)
    use_color = not args.no_color and sys.stdout.isatty()

    queries = DEMO_QUERIES if args.demo else [" ".join(args.query)]
    if not queries or not queries[0].strip():
        parser.print_help()
        return 1

    for q in queries:
        result = agent.run(q)
        if args.json:
            print(json.dumps(result, indent=2, default=str))
        else:
            print(render(result, use_color=use_color))
            print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
