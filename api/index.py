from __future__ import annotations

from typing import Any

from fastapi import FastAPI, HTTPException

from scheduler import build_plan

app = FastAPI(title="ai-os-scheduler HTTP API", version="1")


@app.get("/api/health")
def health() -> dict[str, Any]:
    return {"ok": True, "service": "ai-os-scheduler"}


@app.post("/api/scheduler/plan")
def plan(payload: dict[str, Any]) -> dict[str, Any]:
    try:
        view = payload["view"]
        manifest = payload.get("manifest")
        limit = int(payload.get("limit", 1))
        process = payload.get("process")
        return build_plan(view, manifest, limit=limit, process=process)
    except (KeyError, TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
