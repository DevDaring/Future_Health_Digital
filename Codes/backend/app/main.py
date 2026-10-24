"""FastAPI application: routers, CORS, the SLA scheduler and health check."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import (
    auth,
    content,
    dashboard,
    demo,
    escalations,
    fhir,
    governance,
    loops,
    patient_chat,
    roi,
    twin,
    worklist,
)
from app.config import get_settings
from app.llm.factory import provider_name

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logging.getLogger("httpx").setLevel(logging.WARNING)
log = logging.getLogger("wasl")

NO_DIAGNOSIS = (
    "WASL does not diagnose. It explains a screening result, helps the person act on it, and escalates to a human."
)


def _start_scheduler() -> object | None:
    s = get_settings()
    if not s.scheduler_enabled:
        return None
    from apscheduler.schedulers.background import BackgroundScheduler

    from app.loop_engine.sla import run_job

    def reminders() -> None:
        from app.db import session_scope
        from app.navigator.flow import send_due_reminders

        try:
            with session_scope() as db:
                send_due_reminders(db)
        except Exception:  # pragma: no cover
            log.exception("reminder job failed")

    sched = BackgroundScheduler(timezone="UTC")
    interval = {"minutes": 1} if s.demo_mode else {"hours": 1}
    sched.add_job(run_job, "interval", id="sla", max_instances=1, coalesce=True, **interval)
    sched.add_job(reminders, "interval", id="reminders", max_instances=1, coalesce=True, **interval)
    sched.start()
    log.info("SLA scheduler started (%s)", interval)
    return sched


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    sched = _start_scheduler()
    log.info("WASL API up · LLM provider: %s", provider_name())
    yield
    if sched is not None:
        sched.shutdown(wait=False)  # type: ignore[attr-defined]


app = FastAPI(
    title="WASL (وصل) API",
    version="1.0.0",
    description="AI care navigation that closes the screening-to-care loop. " + NO_DIAGNOSIS,
    lifespan=lifespan,
    docs_url="/api/docs",
    openapi_url="/api/openapi.json",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

api = APIRouter(prefix="/api")


@api.get("/health", tags=["health"])
def health() -> dict[str, str]:
    return {"status": "ok", "llm_provider": provider_name(), "notice": NO_DIAGNOSIS}


for r in (auth, dashboard, worklist, loops, patient_chat, escalations, twin, governance, content, roi, fhir, demo):
    api.include_router(r.router)
app.include_router(api)
