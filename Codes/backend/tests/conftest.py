"""Test setup: a dedicated Postgres test database (TEST_DATABASE_URL, falling back to a
local SQLite file), seeded once with the full demo population and a freshly trained model
written to a temporary artifacts directory. Mock LLM, no scheduler."""

from __future__ import annotations

import os
import re
import tempfile
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parent.parent


def _test_db_url() -> str:
    if os.environ.get("TEST_DATABASE_URL"):
        return os.environ["TEST_DATABASE_URL"]
    local = BACKEND / ".env.local"
    if local.exists():
        m = re.search(r"^TEST_DATABASE_URL=(.+)$", local.read_text(), re.M)
        if m:
            return m.group(1).strip()
    return f"sqlite:///{tempfile.gettempdir()}/wasl_test.db"


_TMP = tempfile.mkdtemp(prefix="wasl_test_")
os.environ.update(
    {
        "DATABASE_URL": _test_db_url(),
        "LLM_PROVIDER": "mock",
        "SCHEDULER_ENABLED": "false",
        "DEMO_MODE": "true",
        "ARTIFACTS_DIR": str(Path(_TMP) / "artifacts"),
        "DOCS_DIR": str(Path(_TMP) / "docs"),
        "JWT_SECRET": "test-secret",
        "PUBLIC_URL": "http://test",
    }
)


def _reachable(url: str) -> bool:
    if url.startswith("sqlite"):
        return True
    try:
        from sqlalchemy import create_engine, text

        with create_engine(url).connect() as c:
            c.execute(text("select 1"))
        return True
    except Exception:
        return False


if not _reachable(os.environ["DATABASE_URL"]):
    os.environ["DATABASE_URL"] = f"sqlite:///{_TMP}/wasl_test.db"


@pytest.fixture(scope="session")
def seeded() -> dict:
    from app import db as dbmod
    from app.db import Base

    eng = dbmod.configure(os.environ["DATABASE_URL"])
    import app.models  # noqa: F401

    Base.metadata.drop_all(eng)
    Base.metadata.create_all(eng)
    from app.ml.registry import load_active
    from app.ml.score import score_open_loops
    from app.ml.train import register, train_all
    from app.synth.seed import seed_all

    with dbmod.session_scope() as db:
        info = seed_all(db)
    bundle, _ = train_all(42)
    with dbmod.session_scope() as db:
        register(db, bundle)
        score_open_loops(db, bundle)
    load_active.cache_clear()
    info["bundle"] = bundle
    return info


@pytest.fixture(scope="session")
def client(seeded):  # noqa: ANN001
    from fastapi.testclient import TestClient

    from app.main import app

    return TestClient(app)


def _login(client, user: str, password: str = "demo1234") -> dict[str, str]:  # noqa: ANN001
    r = client.post("/api/auth/login", json={"username": user, "password": password})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.fixture(scope="session")
def tokens(client) -> dict[str, dict[str, str]]:  # noqa: ANN001
    return {
        "admin": _login(client, "admin@wasl.demo"),
        "coordinator": _login(client, "coord@wasl.demo"),
        "clinician": _login(client, "clinician@wasl.demo"),
        "navigator": _login(client, "nav@wasl.demo"),
        "jury": _login(client, "DevTest", "DevTest11"),
    }


@pytest.fixture(scope="session")
def personas(client, tokens) -> dict[str, dict]:  # noqa: ANN001
    return client.get("/api/demo/state", headers=tokens["coordinator"]).json()["personas"]


@pytest.fixture()
def db():
    from app.db import SessionLocal

    s = SessionLocal()
    try:
        yield s
    finally:
        s.close()
