from types import SimpleNamespace

import anthropic
import httpx2
import pytest

from card_gen.config import ConfigError, Settings
from card_gen.llm import FALLBACK_BETA, AnthropicClient, LLMError
from card_gen.prompts import DRAFT_SCHEMA

REQUEST = httpx2.Request("POST", "https://api.anthropic.com/v1/messages")


def response(text='{"ok": true}', stop_reason="end_turn"):
    return SimpleNamespace(
        stop_reason=stop_reason,
        _request_id="req_test",
        content=[SimpleNamespace(type="thinking", thinking=""), SimpleNamespace(type="text", text=text)],
    )


class FakeMessages:
    def __init__(self, result):
        self.result = result
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


class FakeSDK:
    def __init__(self, result):
        self.messages = FakeMessages(result)
        self.beta = SimpleNamespace(messages=FakeMessages(result))


def make_client(result, **settings):
    sdk = FakeSDK(result)
    return AnthropicClient(Settings(api_key="test", **settings), sdk_client=sdk), sdk


def status_error(cls, code, message="error"):
    return cls(message, response=httpx2.Response(code, request=REQUEST), body=None)


def test_request_uses_structured_output_and_fallbacks():
    client, sdk = make_client(response())
    assert client.complete("system", "user", DRAFT_SCHEMA) == '{"ok": true}'
    call = sdk.beta.messages.calls[0]
    assert call["model"] == "claude-sonnet-5-5"
    assert call["output_config"]["format"] == {"type": "json_schema", "schema": DRAFT_SCHEMA}
    assert call["betas"] == [FALLBACK_BETA] and call["fallbacks"] == "default"
    assert "temperature" not in call


def test_fallbacks_can_be_disabled():
    client, sdk = make_client(response(), fallbacks="off")
    client.complete("s", "u", {})
    assert sdk.messages.calls and not sdk.beta.messages.calls


@pytest.mark.parametrize(
    "error, message",
    [
        (status_error(anthropic.AuthenticationError, 401), "API-ключ не принят"),
        (status_error(anthropic.PermissionDeniedError, 403), "нет доступа"),
        (status_error(anthropic.NotFoundError, 404), "не найдена"),
        (status_error(anthropic.RateLimitError, 429), "лимит запросов"),
        (status_error(anthropic.BadRequestError, 400, "bad schema"), "bad schema"),
        (status_error(anthropic.InternalServerError, 500), "временно недоступен"),
        (anthropic.APITimeoutError(request=REQUEST), "не ответила"),
        (anthropic.APIConnectionError(request=REQUEST), "Нет связи"),
    ],
)
def test_api_errors_become_readable(error, message):
    client, _ = make_client(error)
    with pytest.raises(LLMError, match=message):
        client.complete("s", "u", {})


@pytest.mark.parametrize(
    "result, message",
    [
        (response(stop_reason="refusal"), "отказалась"),
        (response(stop_reason="max_tokens"), "обрезан"),
        (response(text="  "), "пустой ответ"),
    ],
)
def test_bad_stop_reasons(result, message):
    client, _ = make_client(result)
    with pytest.raises(LLMError, match=message):
        client.complete("s", "u", {})


def test_missing_key_is_config_error(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)  # без .env
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(ConfigError, match="ANTHROPIC_API_KEY"):
        Settings.from_env()


def test_settings_from_env(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "k")
    monkeypatch.setenv("LLM_MODEL", "claude-opus-5-5")
    monkeypatch.setenv("LLM_EFFORT", "extreme")
    with pytest.raises(ConfigError, match="LLM_EFFORT"):
        Settings.from_env()
    monkeypatch.setenv("LLM_EFFORT", "high")
    settings = Settings.from_env()
    assert settings.model == "claude-opus-5-5" and settings.effort == "high"
