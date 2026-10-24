"""Real-provider code paths, exercised without network: relay (OpenAI-compatible) over a
mocked HTTP transport, the Anthropic SDK provider with a fake client, the LLM task layer
with a scripted provider, and refusal → fallback + escalation."""

from __future__ import annotations

import json
import types
import uuid
from typing import Any

import httpx
import pytest
from sqlalchemy import select

from app.llm.anthropic_provider import AnthropicProvider, strict_schema
from app.llm.base import LLMError, LLMRefusal
from app.llm.relay_provider import Endpoint, RelayProvider, _extract_json
from app.llm.tasks import Tasks

# ------------------------------------------------------------------ relay provider

def _relay(handler: Any) -> RelayProvider:
    eps = [Endpoint("a", "https://a.example/v1", "k1", "m1"), Endpoint("b", "https://b.example/v1", "k2", "m2")]
    prov = RelayProvider(fast=eps, quality=eps)
    prov._client = httpx.Client(transport=httpx.MockTransport(handler))
    return prov


def _chat(content: str, finish: str = "stop") -> httpx.Response:
    body = {"choices": [{"message": {"content": content}, "finish_reason": finish}]}
    return httpx.Response(200, content=json.dumps(body, ensure_ascii=False).encode("utf-8"))  # no charset header


def test_relay_text_json_and_failover():
    calls: list[str] = []

    def handler(req: httpx.Request) -> httpx.Response:
        calls.append(req.url.host)
        if req.url.host == "a.example":
            return httpx.Response(503)
        payload = json.loads(req.content)
        assert payload["messages"][0]["role"] == "system"
        if payload.get("response_format"):
            return _chat('```json\n{"score": 0.9, "discrepancies": []}\n```')
        return _chat("نتيجتك 6.1%")

    prov = _relay(handler)
    assert prov.complete_text("s", "u") == "نتيجتك 6.1%"  # UTF-8 decoded even without charset
    assert prov.complete_json("s", "u", {"type": "object"})["score"] == 0.9
    assert calls[:2] == ["a.example", "b.example"]


def test_relay_rejects_echoed_schema_and_fails_over():
    hosts: list[str] = []

    def handler(req: httpx.Request) -> httpx.Response:
        hosts.append(req.url.host)
        if req.url.host == "a.example":
            return _chat('{"type": "object", "properties": {"score": {"type": "number"}}}')
        return _chat('{"score": 0.97, "discrepancies": []}')

    out = _relay(handler).complete_json("s", "u", {"type": "object", "properties": {"score": {"type": "number"}, "discrepancies": {"type": "array"}}})
    assert out["score"] == 0.97 and hosts == ["a.example", "b.example"]


def test_relay_refusal_tries_other_family_then_propagates():
    def refuse(req: httpx.Request) -> httpx.Response:
        return _chat("", "content_filter")

    with pytest.raises(LLMRefusal):
        _relay(refuse).complete_text("s", "u")

    def one_refuses(req: httpx.Request) -> httpx.Response:
        return _chat("", "content_filter") if req.url.host == "a.example" else _chat("ok")

    assert _relay(one_refuses).complete_text("s", "u") == "ok"

    def trunc(req: httpx.Request) -> httpx.Response:
        return _chat("partial", "length")

    with pytest.raises(LLMRefusal) as exc:
        _relay(trunc).complete_text("s", "u")
    assert exc.value.reason == "max_tokens"


def test_relay_all_down_raises_llm_error():
    with pytest.raises(LLMError):
        _relay(lambda req: httpx.Response(500)).complete_text("s", "u")
    with pytest.raises(LLMError):
        _relay(lambda req: _chat("not json at all")).complete_json("s", "u", {})


def test_extract_json_variants():
    assert _extract_json('noise {"a": 1} tail') == {"a": 1}
    assert _extract_json('{"a": 1}\n{"b": 2}') == {"a": 1}  # second object ignored
    assert _extract_json('{"t": "line1\nline2"}')["t"] == "line1\nline2"


# --------------------------------------------------------------- anthropic provider

class _FakeErrors:
    class RateLimitError(Exception):
        pass

    class APIConnectionError(Exception):
        pass

    class APIStatusError(Exception):
        status_code = 500


def _anthropic(responses: list[Any]) -> tuple[AnthropicProvider, list[dict[str, Any]]]:
    sent: list[dict[str, Any]] = []
    prov = AnthropicProvider.__new__(AnthropicProvider)
    prov._anthropic = _FakeErrors
    prov.model = "claude-opus-5-5"
    prov.name = "anthropic:test"

    def create(**kw: Any) -> Any:
        sent.append(kw)
        r = responses.pop(0)
        if isinstance(r, Exception):
            raise r
        return r

    prov.client = types.SimpleNamespace(messages=types.SimpleNamespace(create=create))
    return prov, sent


def _resp(text: str, stop: str = "end_turn") -> Any:
    return types.SimpleNamespace(stop_reason=stop, content=[types.SimpleNamespace(type="text", text=text)])


def test_anthropic_json_uses_strict_schema_and_low_effort():
    prov, sent = _anthropic([_resp('{"score": 1.0, "discrepancies": []}')])
    out = prov.complete_json("sys", "user", {"type": "object", "properties": {"score": {"type": "number"}, "discrepancies": {"type": "array"}}})
    assert out["score"] == 1.0
    cfg = sent[0]["output_config"]
    assert cfg["effort"] == "low" and cfg["format"]["type"] == "json_schema"
    assert cfg["format"]["schema"]["additionalProperties"] is False
    assert set(cfg["format"]["schema"]["required"]) == {"score", "discrepancies"}
    for banned in ("temperature", "top_p", "thinking"):
        assert banned not in sent[0]
    assert sent[0]["max_tokens"] == 2000


def test_anthropic_refusal_and_errors():
    prov, _ = _anthropic([_resp("", "refusal"), _resp("x", "max_tokens"), _FakeErrors.RateLimitError(), _FakeErrors.APIConnectionError(), _FakeErrors.APIStatusError()])
    with pytest.raises(LLMRefusal):
        prov.complete_text("s", "u")
    with pytest.raises(LLMRefusal):
        prov.complete_text("s", "u")
    for _ in range(3):
        with pytest.raises(LLMError):
            prov.complete_text("s", "u")


def test_strict_schema_nested():
    s = strict_schema({"type": "object", "properties": {"a": {"type": "object", "properties": {"b": {"type": "string"}}}}})
    assert s["properties"]["a"]["additionalProperties"] is False and s["properties"]["a"]["required"] == ["b"]


# ----------------------------------------------------------------- task layer (LLM)

class ScriptedProvider:
    """A non-mock provider: answers by matching the system prompt."""

    name = "scripted"

    def __init__(self, fail: set[str] | None = None) -> None:
        self.fail = fail or set()

    def complete_text(self, system: str, user: str, tier: str = "quality") -> str:
        if "Translate the user's message from English" in system:
            if "translate" in self.fail:
                raise LLMError("down")
            return "[ml] " + user
        if "as literally as possible" in system:
            return user.replace("[ml] ", "")
        if "Rewrite" in user or "navigator" in system:
            return user.split("\n\n", 1)[-1]
        return user

    def complete_json(self, system: str, user: str, schema: dict[str, Any], tier: str = "quality") -> dict[str, Any]:
        if "teach-back" in system:  # checked first: its prompt also says "Judge"
            return {"understands_result": True, "knows_next_step": True, "knows_when": True, "feedback": "Clear."}
        if "judge" in system.lower():
            if "judge" in self.fail:
                raise LLMError("down")
            return {"score": 0.93, "discrepancies": []}
        return {"answer_en": "I have chest pain", "intent": "other", "barrier": "none", "red_flag": True, "red_flag_reason": "chest pain"}


def test_tasks_with_real_provider_paths():
    t = Tasks(ScriptedProvider())
    assert not t.is_mock
    assert t.simplify("HbA1c 6.1%", 2) == "HbA1c 6.1%"
    assert t.translate("Hello", "ml", None) == "[ml] Hello"
    assert t.back_translate("[ml] Hello", "ml", "Hello") == "Hello"
    assert t.judge("a", "b", "a", "ml")["score"] == 0.93
    u = t.understand("എനിക്ക് നെഞ്ചുവേദന", "ml", "barrier", "DIABETES")
    assert u["red_flag"] and u["red_flag_source"] in {"llm", "lexicon"}
    g = t.grade_teach_back("my sugar is high", "DIABETES", {"understands_result": ["sugar"]})
    assert g["passed"] and g["method"] == "llm"


def test_tasks_fall_back_to_mock_on_errors():
    t = Tasks(ScriptedProvider(fail={"translate", "judge"}))
    assert t.translate("Hello", "ml", "ഹലോ") == "ഹലോ"
    assert t.judge("value 7.4", "value 7.4", "value 7.4", "ml")["score"] >= 0.85
    assert set(t.fallbacks) == {"translate", "judge"}


def test_llm_refusal_falls_back_and_escalates(client, tokens, personas, db, monkeypatch):
    """A refusal mid-pipeline: approved text is sent and an llm_refusal escalation opens."""
    from app.models import Escalation
    from app.navigator import messaging

    class Refuser(ScriptedProvider):
        def complete_text(self, system: str, user: str, tier: str = "quality") -> str:
            raise LLMRefusal("refusal")

    monkeypatch.setattr(messaging, "get_provider", lambda: Refuser())
    loop_id = personas["sara"]["loop_id"]
    r = client.post(f"/api/loops/{loop_id}/outreach", json={}, headers=tokens["coordinator"])
    tok = r.json()["token"]
    s = client.get(f"/api/c/{tok}").json()
    assert s["messages"], "patient still gets approved text"
    esc = db.scalar(select(Escalation).where(Escalation.loop_id == uuid.UUID(loop_id), Escalation.reason == "llm_refusal"))
    assert esc is not None


def test_model_card_written(seeded, tmp_path, monkeypatch):
    from app.config import get_settings
    from app.ml.model_card import END, START, write_model_card

    monkeypatch.setattr(get_settings(), "docs_dir", str(tmp_path))
    (tmp_path / "MODEL_CARD.md").write_text(f"# Card\n\nHand-written intro.\n\n{START}\nold\n{END}\n\nHand-written outro.\n")
    path = write_model_card(seeded["bundle"])
    text = path.read_text()
    assert "Hand-written intro." in text and "Hand-written outro." in text and "old" not in text
    assert "AUROC" in text and "AUUC vs true effect" in text


def test_factory_falls_back_to_mock(monkeypatch):
    from app.config import get_settings
    from app.llm import factory

    factory.get_provider.cache_clear()
    monkeypatch.setattr(get_settings(), "llm_provider", "nanogpt")
    monkeypatch.setattr(get_settings(), "nanogpt_api_key", "")
    monkeypatch.setattr(get_settings(), "linkapi_api_key", "")
    assert factory.get_provider().name == "mock"
    factory.get_provider.cache_clear()
    monkeypatch.setattr(get_settings(), "nanogpt_api_key", "x")
    assert factory.get_provider().name.startswith("relay:")
    factory.get_provider.cache_clear()
