"""Loader for the clinician-editable screening thresholds."""

from __future__ import annotations

from functools import lru_cache
from typing import Any

import yaml

from app.config import FIXTURES_DIR


@lru_cache
def screening_rules() -> dict[str, Any]:
    with (FIXTURES_DIR / "screening_rules.yaml").open() as fh:
        return yaml.safe_load(fh)
