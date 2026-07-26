"""Smoke tests for the FastAPI backend.

These exercise the real service (which runs a full detection pass), so they
double as an integration test of the whole engine behind the HTTP layer.
"""

from __future__ import annotations

import pytest

fastapi = pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient  # noqa: E402

from backend.main import app  # noqa: E402


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def test_health(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_overview_shape(client):
    d = client.get("/api/overview").json()
    assert d["dataset"]["transactions"] > 0
    assert set(d["risk_distribution"]) == {"high", "medium", "low"}
    assert "amount_histogram" in d


def test_alerts_filtering(client):
    high = client.get("/api/alerts?level=high&limit=100").json()
    assert all(i["risk_level"] == "high" for i in high["items"])


def test_agent_query_endpoint(client):
    r = client.post("/api/agent/query", json={"query": "Flag high-risk customers"})
    assert r.status_code == 200
    body = r.json()
    assert body["execution_summary"]["detected_intent"] == "high_risk_customers"


def test_agent_query_rejects_empty(client):
    assert client.post("/api/agent/query", json={"query": "  "}).status_code == 400


def test_customer_detail_and_network(client):
    d = client.get("/api/customers/1528").json()
    assert d["customer_id"] == 1528
    assert "assessment" in d and "network" in d
    assert len(d["timeline"]) > 0


def test_customer_not_found(client):
    assert client.get("/api/customers/999999").status_code == 404


def test_performance_endpoint(client):
    d = client.get("/api/performance").json()
    assert 0 <= d["customer_level"]["f1"] <= 1


def test_methodology_endpoint(client):
    d = client.get("/api/methodology").json()
    assert "thresholds" in d and "weights" in d
