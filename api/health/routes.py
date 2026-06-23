from typing import Any

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from core import metrics as app_metrics
from core.database.database import crm_engine

health_router = APIRouter()


async def check_db() -> dict[str, Any]:
    try:
        async with crm_engine.connect() as connection:
            await connection.execute(text("SELECT 1"))
        return {"ok": True}
    except SQLAlchemyError as exc:
        return {"ok": False, "error": str(exc)}


@health_router.get("/liveness", tags=["Health"])
async def liveness():
    return {"status": "alive"}


@health_router.get("/readiness", tags=["Health"])
async def readiness() -> JSONResponse:
    checks = {
        "database": await check_db(),
    }

    # Emit one counter point per component per probe so the metrics backend
    # can plot the failure rate (rate(health_checks_total{ok="false"}[5m]))
    # and alert on it without parsing log lines.
    for component, result in checks.items():
        app_metrics.health_checks.add(
            1,
            {"component": component, "ok": "true" if result["ok"] else "false"},
        )

    is_ready = all(result["ok"] for result in checks.values())

    payload = {
        "status": "healthy" if is_ready else "unhealthy",
        "checks": checks,
    }

    return JSONResponse(
        status_code=200 if is_ready else 503,
        content=payload,
    )


@health_router.get("/health", tags=["Health"])
async def health():
    return await readiness()
