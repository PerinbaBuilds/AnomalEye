"""AnomalEye — interactive Streamlit dashboard.

Run with:

    pip install -r requirements.txt
    streamlit run app.py

The UI is a thin shell over :class:`anomaleye.agent.orchestrator.Agent`: you
type a natural-language instruction, and it shows what the agent *decided*
(intent, filters, tools invoked) alongside the flagged entities, their
explanations, and supporting charts.
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

from anomaleye.agent.orchestrator import Agent
from anomaleye.data.loader import load_dataset
from anomaleye.tools import eda

st.set_page_config(page_title="AnomalEye — AML Agent", page_icon="🦅",
                  layout="wide")

LEVEL_COLORS = {"high": "#e5484d", "medium": "#f5a623", "low": "#30a46c"}

EXAMPLES = [
    "Analyse this dataset for suspicious activity",
    "Find structuring patterns in the last 30 days",
    "Which customers made 10+ transactions under $10,000?",
    "Flag high-risk customers",
    "Is customer ID 1528 suspicious?",
    "Give me an overview of the data",
    "Look for smurfing across all customers",
    "Detect layering chains",
]


@st.cache_resource
def get_agent() -> Agent:
    return Agent(dataset=load_dataset(), top_n=25)


def risk_badge(level: str) -> str:
    color = LEVEL_COLORS.get(level, "#888")
    return (
        f"<span style='background:{color};color:white;padding:2px 10px;"
        f"border-radius:10px;font-weight:600'>{level.upper()}</span>"
    )


def main() -> None:
    agent = get_agent()
    ds = agent.dataset

    st.title("🦅 AnomalEye")
    st.caption(
        "An agentic AI for AML suspicious-activity detection. Ask in plain "
        "English — the agent plans which tools to run, detects laundering "
        "typologies, scores risk, and explains every flag."
    )

    # ---- Sidebar ----
    with st.sidebar:
        st.header("Dataset")
        st.metric("Transactions", f"{len(ds.transactions):,}")
        st.metric("Customers", f"{ds.customers['customer_id'].nunique():,}")
        span = pd.to_datetime(ds.transactions["timestamp"])
        st.caption(
            f"Span: {span.min().date()} → {span.max().date()}"
        )
        st.divider()
        st.header("Try an example")
        for ex in EXAMPLES:
            if st.button(ex, use_container_width=True, key=f"ex_{ex}"):
                st.session_state["query"] = ex

    # ---- Query box ----
    query = st.text_input(
        "Your instruction",
        value=st.session_state.get("query", EXAMPLES[0]),
        key="query_box",
    )
    run = st.button("Run analysis", type="primary")

    if not run and "last_query" not in st.session_state:
        st.info("Enter a query or pick an example from the sidebar.")
        return

    if run:
        st.session_state["last_query"] = query

    result = agent.run(st.session_state["last_query"])
    es = result["execution_summary"]

    # ---- Execution plan ----
    st.subheader("🧭 What the agent decided")
    c1, c2, c3 = st.columns(3)
    c1.metric("Intent", es["detected_intent"])
    c2.metric("Transactions in scope", f"{es['transactions_in_scope']:,}")
    c3.metric("Entities flagged", result["counts"]["total_flagged"])

    with st.expander("Execution plan detail", expanded=True):
        if es["detected_filters"]:
            st.write("**Filters detected:**", es["detected_filters"])
        if es["detected_customer_id"] is not None:
            st.write("**Customer:**", es["detected_customer_id"])
        if es["detected_typologies"]:
            st.write("**Typologies:**", ", ".join(es["detected_typologies"]))
        st.write("**Tools invoked:**", " → ".join(es["tools_invoked"]))
        for r in es["planning_rationale"]:
            st.caption("• " + r)

    # ---- EDA panel ----
    if "eda" in result:
        _render_eda(result["eda"], ds.transactions)

    # ---- Risk summary ----
    counts = result["counts"]
    st.subheader("⚖️ Risk summary")
    a, b, c, d = st.columns(4)
    a.metric("Total flagged", counts["total_flagged"])
    b.metric("High", counts["high"])
    c.metric("Medium", counts["medium"])
    d.metric("Low", counts["low"])

    # ---- Flagged entities table ----
    if result["flagged_entities"]:
        st.subheader("🚩 Flagged entities")
        df = pd.DataFrame(result["flagged_entities"])
        df["typologies"] = df["typologies"].apply(lambda t: ", ".join(t))
        st.dataframe(
            df[["customer_id", "risk_level", "risk_score", "escalation",
                "typologies"]],
            use_container_width=True,
            hide_index=True,
        )

        st.subheader("🧾 Explanations")
        for ex in result["explanations"]:
            with st.expander(
                f"Customer {ex['customer_id']} — {ex['risk_level'].upper()} "
                f"(score {ex['risk_score']}) — {ex['escalation'].upper()}"
            ):
                st.markdown(risk_badge(ex["risk_level"]),
                          unsafe_allow_html=True)
                st.write(ex["summary"])
                for reason in ex["reasons"]:
                    st.markdown(f"- {reason}")
                st.info(ex["escalation_rationale"])
                if ex.get("score_breakdown"):
                    st.caption("Score contribution by signal:")
                    st.bar_chart(pd.Series(ex["score_breakdown"]))
    else:
        st.success("No entities matched the criteria for this query.")

    with st.expander("Raw JSON result"):
        st.json(result)


def _render_eda(eda_block: dict, txns: pd.DataFrame) -> None:
    st.subheader("🔎 Exploratory data analysis")
    prof = eda_block["profile"]
    scan = eda_block["structuring_scan"]

    col1, col2 = st.columns([2, 1])
    with col1:
        st.caption("Transaction amount distribution (clipped at $15k)")
        hist = scan["histogram"]
        chart_df = pd.DataFrame(
            {"count": hist["counts"]},
            index=[f"${int(e):,}" for e in hist["bin_edges"][:-1]],
        )
        st.bar_chart(chart_df)
    with col2:
        amt = prof.get("amount", {})
        st.metric("Mean amount", f"${amt.get('mean', 0):,.0f}")
        st.metric("Median amount", f"${amt.get('median', 0):,.0f}")
        st.metric("CTR-band share",
                 f"{prof.get('ctr_band_share', 0) * 100:.2f}%")

    if prof.get("top_customers_by_volume"):
        st.caption("Top customers by transaction volume")
        st.dataframe(
            pd.DataFrame(prof["top_customers_by_volume"]),
            use_container_width=True,
            hide_index=True,
        )


if __name__ == "__main__":
    main()
