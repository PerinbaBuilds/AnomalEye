"""AnomalEye — an agentic AI system for AML suspicious-activity detection.

The package exposes a query-driven agent that parses a natural-language
instruction, builds a dynamic execution plan, and invokes only the tools it
needs (EDA, feature engineering, anomaly detection, risk classification and
explanation) to answer that specific query.
"""

from __future__ import annotations

__version__ = "1.0.0"

__all__ = ["Agent", "__version__"]


def __getattr__(name: str):
    # Lazy import so importing sub-modules (e.g. the data generator) does not
    # pull in the whole agent stack.
    if name == "Agent":
        from anomaleye.agent.orchestrator import Agent

        return Agent
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
