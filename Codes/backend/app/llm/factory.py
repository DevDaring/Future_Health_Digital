"""Builds the configured provider. Unknown or unconfigured providers fall back to mock,
so the system always runs with zero keys."""

from __future__ import annotations

import logging
from functools import lru_cache
from typing import Any

from app.config import get_settings
from app.llm.mock import MockProvider
from app.llm.relay_provider import Endpoint, RelayProvider

log = logging.getLogger("wasl.llm")


@lru_cache
def get_provider() -> Any:
    s = get_settings()
    kind = s.llm_provider.lower()
    if kind == "anthropic" and s.anthropic_api_key:
        from app.llm.anthropic_provider import AnthropicProvider

        return AnthropicProvider(s.anthropic_api_key, s.llm_model)
    if kind in {"relay", "nanogpt", "linkapi"}:
        nano = (
            [Endpoint("nanogpt", s.nanogpt_base_url, s.nanogpt_api_key, s.nanogpt_model)] if s.nanogpt_api_key else []
        )
        link = (
            [Endpoint("linkapi", s.linkapi_base_url, s.linkapi_api_key, s.linkapi_model)] if s.linkapi_api_key else []
        )
        if nano or link:
            if kind == "linkapi":
                return RelayProvider(fast=link + nano, quality=link + nano, timeout_s=s.llm_timeout_s)
            if kind == "nanogpt":
                return RelayProvider(fast=nano + link, quality=nano + link, timeout_s=s.llm_timeout_s)
            # relay: fast model first for chat understanding, best model first for translation
            return RelayProvider(fast=link + nano, quality=nano + link, timeout_s=s.llm_timeout_s)
    if kind == "azure_openai" and s.azure_openai_api_key and s.azure_openai_endpoint:
        ep = Endpoint("azure", s.azure_openai_endpoint, s.azure_openai_api_key, s.azure_openai_deployment, azure=True)
        return RelayProvider(fast=[ep], quality=[ep], timeout_s=s.llm_timeout_s)
    if kind != "mock":
        log.warning("LLM provider %s not configured; using mock", kind)
    return MockProvider()


def provider_name() -> str:
    return getattr(get_provider(), "name", "mock")
