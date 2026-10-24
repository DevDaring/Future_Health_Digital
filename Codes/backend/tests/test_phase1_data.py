"""Phase 0/1: health, synthetic data, personas, determinism."""

from __future__ import annotations

from app.synth.population import draw_abnormal_results, generate_population
from app.synth.seed import checksum


def test_health(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"
    assert "does not diagnose" in r.json()["notice"]


def test_seed_counts(seeded):
    c = seeded["counts"]
    assert 5000 <= c["patients"] <= 5010
    assert 1300 <= c["loops"] <= 1800
    assert c["templates"] >= 40
    assert c["translations"] >= 6 * 40


def test_all_personas_exist(personas):
    assert set(personas) == {"ramesh", "fatima", "joy", "imran", "sara"}
    assert personas["ramesh"]["language"] == "ml"
    assert personas["fatima"]["program"] == "BREAST"


def test_generator_is_deterministic():
    import numpy as np

    a = generate_population(800, 7)
    b = generate_population(800, 7)
    assert a.equals(b)
    ra = draw_abnormal_results(a, np.random.default_rng(1))
    rb = draw_abnormal_results(b, np.random.default_rng(1))
    assert ra == rb


def test_reseed_gives_same_counts_and_checksum(seeded):
    """Re-running the seed with the same seed gives identical counts and checksum."""
    from app.api.demo import reset_everything
    from app.db import session_scope

    with session_scope() as db:
        again = reset_everything(db)
    assert again["counts"] == seeded["counts"]
    assert again["checksum"] == seeded["checksum"]


def test_checksum_changes_with_seed():
    import pandas as pd

    a = generate_population(200, 1)
    b = generate_population(200, 2)
    assert checksum(a, []) != checksum(b, [])
    assert checksum(a, []) == checksum(pd.DataFrame(a), [])
