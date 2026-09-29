from __future__ import annotations

import os
from typing import Any

from fastapi import FastAPI, Header, HTTPException

from scheduler import build_plan

app = FastAPI(title="ai-os-scheduler HTTP API", version="1")


def _authorize(authorization: str | None) -> None:
    token = os.getenv("AIOS_SERVICE_TOKEN")
    if not token:
        raise HTTPException(status_code=503, detail="AIOS_SERVICE_TOKEN is not configured")
    if authorization != f"Bearer {token}":
        raise HTTPException(status_code=401, detail="unauthorized")


@app.get("/api/health")
def health() -> dict[str, Any]:
    return {"ok": True, "service": "ai-os-scheduler"}


@app.post("/api/scheduler/plan")
def plan(
    payload: dict[str, Any],
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    _authorize(authorization)
    try:
        view = payload["view"]
        manifest = payload.get("manifest")
        limit = int(payload.get("limit", 1))
        process = payload.get("process")
        return build_plan(view, manifest, limit=limit, process=process)
    except (KeyError, TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
