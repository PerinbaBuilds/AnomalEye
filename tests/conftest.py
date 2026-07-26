"""Shared pytest fixtures.

A single small synthetic dataset is generated once per session and reused, so
the suite stays fast while exercising the real detection code paths.
"""

from __future__ import annotations

import pytest

from anomaleye.data.generate import GenConfig, generate
from anomaleye.data.loader import Dataset


@pytest.fixture(scope="session")
def dataset() -> Dataset:
    cfg = GenConfig(
        n_customers=300,
        n_normal_txns=12_000,
        days=90,
        seed=7,
    )
    customers, txns = generate(cfg)
    return Dataset(txns, customers)


@pytest.fixture(scope="session")
def agent(dataset):
    from anomaleye.agent.orchestrator import Agent

    return Agent(dataset=dataset, top_n=15)
