"""AnomalEye FastAPI application.

Exposes the detection engine as a REST API and serves the built React frontend
(if present) as static files, so the whole product runs from one process:

    uvicorn backend.main:app --reload
"""

from __future__ import annotations

import asyncio
import json
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from anomaleye import __version__
from backend.service import get_service


@asynccontextmanager
async def lifespan(_: FastAPI):
    # Build the cached analysis at startup so the first request is fast.
    get_service()
    yield


app = FastAPI(
    title="AnomalEye API",
    version=__version__,
    description="Agentic AI for AML suspicious-activity detection.",
    lifespan=lifespan,
)

# Dev CORS: the Vite dev server runs on :5173.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class QueryRequest(BaseModel):
    query: str


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok", "version": __version__}


@app.get("/api/overview")
def overview() -> dict:
    return get_service().overview()


@app.get("/api/timeline")
def timeline(freq: str = "W") -> list:
    return get_service().alerts_timeline(freq=freq)


@app.get("/api/alerts")
def alerts(
    level: str | None = None,
    typology: str | None = None,
    escalation: str | None = None,
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
) -> dict:
    return get_service().alerts(
        level=level, typology=typology, escalation=escalation,
        limit=limit, offset=offset,
    )


@app.get("/api/customers/{customer_id}")
def customer(customer_id: int) -> dict:
    result = get_service().customer(customer_id)
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return result


@app.get("/api/customers/{customer_id}/network")
def customer_network(customer_id: int) -> dict:
    return get_service().network(customer_id)


@app.get("/api/layering-chains")
def layering_chains() -> list:
    return get_service().layering_chains()


@app.post("/api/agent/query")
def agent_query(req: QueryRequest) -> dict:
    if not req.query.strip():
        raise HTTPException(status_code=400, detail="query must not be empty")
    return get_service().agent_query(req.query)


@app.get("/api/performance")
def performance() -> dict:
    return get_service().performance()


@app.get("/api/methodology")
def methodology() -> dict:
    return get_service().methodology()


@app.get("/api/stream/transactions")
async def stream_transactions(rate: float = Query(4.0, ge=0.5, le=50.0)):
    """Server-Sent Events feed simulating live transaction scoring.

    Emits pre-scored transactions at ``rate`` per second so the frontend can
    animate a real-time monitoring blotter.
    """
    svc = get_service()
    batch = svc.sample_transaction_stream(n=400)

    async def gen():
        for txn in batch:
            yield f"data: {json.dumps(txn)}\n\n"
            await asyncio.sleep(1.0 / rate)
        yield "event: end\ndata: {}\n\n"

    return StreamingResponse(gen(), media_type="text/event-stream")


# --- Serve the built frontend (production) --------------------------------
# Mount hashed assets, then fall back to index.html for every non-API route so
# client-side routing (deep links, refresh on /alerts, etc.) works.
_FRONTEND_DIST = Path(__file__).resolve().parent.parent / "frontend" / "dist"
if _FRONTEND_DIST.exists():
    app.mount(
        "/assets",
        StaticFiles(directory=str(_FRONTEND_DIST / "assets")),
        name="assets",
    )

    _INDEX = _FRONTEND_DIST / "index.html"

    @app.get("/{full_path:path}", include_in_schema=False)
    def spa(full_path: str):
        # API routes are declared above and take precedence; anything else is
        # a frontend route → serve the SPA shell (or a real static file).
        if full_path.startswith("api/"):
            raise HTTPException(status_code=404, detail="not found")
        candidate = _FRONTEND_DIST / full_path
        if full_path and candidate.is_file():
            return FileResponse(str(candidate))
        return FileResponse(str(_INDEX))
