"""Unit tests for ordered cloud fallback models (T30, Locked intent 19).

The fallback list is one comma-separated setting, parsed leniently (strip each
entry, drop empties; an empty value means *no fallbacks*, not an error) and
validated strictly — but **only while cloud generation is selected**. The three
rejections are a repeated primary, a duplicated entry and a non-empty list on an
endpoint that is not the ``openrouter`` preset (decided on the raw fields, never
by matching a host). A dormant list on ``KHALEEV_GENERATOR=ollama`` fails none
of them, exactly like the other cloud settings the local factory ignores.

The wire shape is the narrow half of the contract: ``model`` stays the primary,
``models`` is added only when a fallback exists, so a single-model request body
is byte-identical to today's. Every request is intercepted by
``httpx.MockTransport``; no socket is opened (Locked intent #12, AC8).
"""

from __future__ import annotations

import json
from collections.abc import Callable

import httpx
import pytest
from pydantic import ValidationError

from khaleev.config import Settings
from khaleev.generation import build_generator
from khaleev.generation.cloud import CloudGenerator

API_KEY = "test-key"
MODEL = "primary/model:free"
FALLBACK_A = "fallback/one:free"
FALLBACK_B = "fallback/two:free"
BASE_URL = "https://cloud.example.test/v1"
Handler = Callable[[httpx.Request], httpx.Response]


def _client(handler: Handler) -> httpx.Client:
    """An httpx client whose transport never leaves the process."""
    return httpx.Client(transport=httpx.MockTransport(handler))


def _cloud(**kwargs: object) -> Settings:
    """Cloud generation selected, through the openrouter preset by default."""
    values: dict[str, object] = {
        "generator": "cloud",
        "cloud_api_key": API_KEY,
        "cloud_model": MODEL,
        "cloud_provider": "openrouter",
    }
    values.update(kwargs)
    return Settings(_env_file=None, **values)


# ---------------------------------------------------------------------------
# Parsing: absent, empty and padded all mean something definite
# ---------------------------------------------------------------------------


def test_the_setting_defaults_to_none_and_no_fallbacks() -> None:
    settings = Settings(_env_file=None)

    assert settings.cloud_fallback_models is None
    assert settings.resolved_cloud_fallback_models == []


@pytest.mark.parametrize(
    "value",
    ["", "   ", ",", ",,", " , ,, "],
    ids=["empty", "whitespace", "comma", "commas", "commas-padded"],
)
def test_an_empty_value_means_no_fallbacks_and_is_not_an_error(value: str) -> None:
    """Unlike KHALEEV_CLOUD_BASE_URL: "no fallbacks" is a meaningful state."""
    settings = Settings(_env_file=None, cloud_fallback_models=value)

    assert settings.resolved_cloud_fallback_models == []


def test_entries_are_stripped_and_empties_dropped_in_the_users_order() -> None:
    settings = Settings(_env_file=None, cloud_fallback_models=" a , b ,,")

    assert settings.resolved_cloud_fallback_models == ["a", "b"]


def test_a_single_entry_is_kept_as_is() -> None:
    settings = Settings(_env_file=None, cloud_fallback_models=FALLBACK_A)

    assert settings.resolved_cloud_fallback_models == [FALLBACK_A]


def test_the_priority_order_is_preserved() -> None:
    settings = Settings(_env_file=None, cloud_fallback_models="z/model, a/model ,m/model")

    assert settings.resolved_cloud_fallback_models == ["z/model", "a/model", "m/model"]


def test_the_env_var_is_read(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("KHALEEV_CLOUD_FALLBACK_MODELS", f" {FALLBACK_A} , {FALLBACK_B} ")

    settings = _cloud()

    assert settings.cloud_fallback_models == f" {FALLBACK_A} , {FALLBACK_B} "
    assert settings.resolved_cloud_fallback_models == [FALLBACK_A, FALLBACK_B]


# ---------------------------------------------------------------------------
# The three rejections, scoped to generator == "cloud"
# ---------------------------------------------------------------------------


def test_a_fallback_equal_to_the_primary_is_rejected() -> None:
    with pytest.raises(ValidationError) as excinfo:
        _cloud(cloud_fallback_models=MODEL)

    message = str(excinfo.value)
    assert "KHALEEV_CLOUD_FALLBACK_MODELS" in message
    assert MODEL in message
    assert API_KEY not in message


def test_a_repeated_primary_is_compared_after_stripping_both_sides() -> None:
    with pytest.raises(ValidationError) as excinfo:
        _cloud(cloud_model=f"  {MODEL}  ", cloud_fallback_models=f" {MODEL} ")

    message = str(excinfo.value)
    assert "KHALEEV_CLOUD_FALLBACK_MODELS" in message
    assert MODEL in message


def test_a_duplicated_entry_is_rejected() -> None:
    with pytest.raises(ValidationError) as excinfo:
        _cloud(cloud_fallback_models=f"{FALLBACK_A},{FALLBACK_A}")

    message = str(excinfo.value)
    assert "KHALEEV_CLOUD_FALLBACK_MODELS" in message
    assert FALLBACK_A in message
    assert API_KEY not in message


def test_a_duplicated_entry_is_detected_across_padding() -> None:
    with pytest.raises(ValidationError) as excinfo:
        _cloud(cloud_fallback_models=f" {FALLBACK_A} , {FALLBACK_A} ")

    assert "KHALEEV_CLOUD_FALLBACK_MODELS" in str(excinfo.value)
    assert FALLBACK_A in str(excinfo.value)


@pytest.mark.parametrize("provider", [None, "openai"])
def test_fallbacks_without_the_openrouter_preset_are_rejected(
    provider: str | None,
) -> None:
    with pytest.raises(ValidationError) as excinfo:
        _cloud(cloud_provider=provider, cloud_fallback_models=FALLBACK_A)

    message = str(excinfo.value)
    assert "KHALEEV_CLOUD_FALLBACK_MODELS" in message
    assert "OpenRouter" in message
    assert API_KEY not in message


def test_an_explicit_openrouter_base_url_does_not_satisfy_the_preset_gate() -> None:
    """The gate is preset-based, never host-based: a proxy is knowingly foreclosed."""
    with pytest.raises(ValidationError) as excinfo:
        _cloud(
            cloud_base_url="https://openrouter.ai/api/v1",
            cloud_fallback_models=FALLBACK_A,
        )

    message = str(excinfo.value)
    assert "KHALEEV_CLOUD_FALLBACK_MODELS" in message
    assert "OpenRouter" in message


def test_two_fallbacks_on_the_openrouter_preset_are_accepted() -> None:
    settings = _cloud(cloud_fallback_models=f"{FALLBACK_A},{FALLBACK_B}")

    assert settings.cloud_provider == "openrouter"
    assert settings.cloud_base_url is None
    assert settings.resolved_cloud_base_url == "https://openrouter.ai/api/v1"
    assert settings.resolved_cloud_fallback_models == [FALLBACK_A, FALLBACK_B]


def test_an_empty_list_is_accepted_on_any_endpoint() -> None:
    """The gate only rejects a *non-empty* list."""
    settings = Settings(
        _env_file=None,
        generator="cloud",
        cloud_api_key=API_KEY,
        cloud_model=MODEL,
        cloud_provider="openai",
        cloud_fallback_models=" , ",
    )

    assert settings.resolved_cloud_fallback_models == []


# ---------------------------------------------------------------------------
# Dormant under the local generator
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "kwargs",
    [
        {"cloud_fallback_models": MODEL},
        {"cloud_fallback_models": f"{FALLBACK_A},{FALLBACK_A}"},
        {"cloud_provider": None, "cloud_fallback_models": FALLBACK_A},
        {"cloud_provider": "openai", "cloud_fallback_models": FALLBACK_A},
        {"cloud_model": MODEL, "cloud_fallback_models": f"{MODEL},{MODEL}"},
    ],
    ids=["repeats-primary", "duplicate", "no-preset", "openai", "all-wrong"],
)
def test_a_dormant_list_on_ollama_fails_none_of_the_checks(
    kwargs: dict[str, object],
) -> None:
    settings = Settings(
        _env_file=None,
        generator="ollama",
        cloud_api_key=API_KEY,
        **kwargs,
    )

    assert settings.generator == "ollama"
    assert settings.resolved_cloud_fallback_models


def test_a_dormant_list_never_reaches_the_local_generator() -> None:
    settings = Settings(
        _env_file=None,
        generator="ollama",
        cloud_model=MODEL,
        cloud_fallback_models=f"{MODEL},{MODEL}",
    )

    generator = build_generator(settings)

    assert not isinstance(generator, CloudGenerator)


# ---------------------------------------------------------------------------
# The wire shape: `model` always, `models` only with a fallback
# ---------------------------------------------------------------------------


def test_a_single_model_payload_is_byte_identical_to_todays() -> None:
    captured: dict[str, bytes] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = request.content
        return httpx.Response(200, json={"choices": [{"message": {"content": "ok"}}]})

    generator = CloudGenerator(API_KEY, MODEL, base_url=BASE_URL, client=_client(handler))

    generator.generate("prompt")

    expected = {
        "model": MODEL,
        "messages": [{"role": "user", "content": "prompt"}],
    }
    assert json.loads(captured["body"]) == expected
    # Byte-for-byte: httpx serialises with "," and ":" separators, no spaces.
    assert captured["body"] == json.dumps(expected, separators=(",", ":")).encode("utf-8")
    assert "models" not in json.loads(captured["body"])


def test_two_fallbacks_are_sent_in_priority_order_after_the_primary() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["payload"] = json.loads(request.content)
        return httpx.Response(200, json={"choices": [{"message": {"content": "ok"}}]})

    generator = CloudGenerator(
        API_KEY,
        MODEL,
        base_url=BASE_URL,
        client=_client(handler),
        fallback_models=[FALLBACK_A, FALLBACK_B],
    )

    generator.generate("prompt")

    payload = captured["payload"]
    assert isinstance(payload, dict)
    assert payload["model"] == MODEL
    assert payload["models"] == [FALLBACK_A, FALLBACK_B]
    assert payload["messages"] == [{"role": "user", "content": "prompt"}]
    assert MODEL not in payload["models"]
    assert set(payload) == {"model", "messages", "models"}


def test_the_factory_hands_the_parsed_fallbacks_to_the_cloud_generator() -> None:
    settings = _cloud(cloud_fallback_models=f" {FALLBACK_A} , {FALLBACK_B} ")

    generator = build_generator(settings)

    assert isinstance(generator, CloudGenerator)
    assert generator.fallback_models == (FALLBACK_A, FALLBACK_B)


def test_the_factory_hands_no_fallbacks_when_none_are_configured() -> None:
    generator = build_generator(_cloud())

    assert isinstance(generator, CloudGenerator)
    assert generator.fallback_models == ()
