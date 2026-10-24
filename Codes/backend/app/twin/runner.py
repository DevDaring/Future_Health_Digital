"""Background execution of twin runs; results stored in `sim_runs` and polled by the UI."""

from __future__ import annotations

import logging
import threading
import traceback
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from typing import Any

from app.db import session_scope
from app.models import SimRun
from app.twin.system_twin import run_policies, sensitivity

log = logging.getLogger("wasl.twin")
_pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="twin")
_lock = threading.Lock()  # SimPy runs are CPU-bound; one at a time keeps latency predictable


def execute(run_id: uuid.UUID) -> None:
    with session_scope() as db:
        run = db.get(SimRun, run_id)
        if run is None:
            return
        run.status = "running"
        kind, policies, params = run.kind, run.policy.split(","), dict(run.params)
    try:
        with _lock:
            if kind == "sensitivity":
                results: dict[str, Any] = sensitivity(policies, params)
            else:
                results = run_policies(policies, params)
        with session_scope() as db:
            run = db.get(SimRun, run_id)
            assert run is not None
            run.results = _jsonable(results)
            run.status = "done"
            run.finished_at = datetime.now(UTC)
    except Exception as exc:  # pragma: no cover - surfaced in the UI
        log.exception("twin run failed")
        with session_scope() as db:
            run = db.get(SimRun, run_id)
            if run is not None:
                run.status = "error"
                run.error = f"{exc}\n{traceback.format_exc()[-1500:]}"


def submit(run_id: uuid.UUID, background: bool = True) -> None:
    if background:
        _pool.submit(execute, run_id)
    else:
        execute(run_id)


def _jsonable(obj: Any) -> Any:
    import numpy as np

    if isinstance(obj, dict):
        return {str(k): _jsonable(v) for k, v in obj.items()}
    if isinstance(obj, list | tuple):
        return [_jsonable(v) for v in obj]
    if isinstance(obj, np.generic):
        return obj.item()
    return obj
