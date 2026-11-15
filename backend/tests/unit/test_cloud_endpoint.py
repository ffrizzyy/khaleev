"""Unit tests for the configurable cloud endpoint and its provider presets (T29).

Locked intent 18 makes the cloud endpoint configurable by environment or
``.env``, with a closed set of five OpenAI-compatible provider presets, without
inventing a third resolution rule:

* an explicit ``KHALEEV_CLOUD_BASE_URL`` always wins;
* the ``KHALEEV_CLOUD_PROVIDER`` preset applies **only** when the base URL is
  ``None``;
* neither set resolves to today's OpenAI endpoint;
* the empty string is an invalid URL, never "unset" — unset is ``None``;
* surrounding whitespace and a trailing slash are normalised, while a query
  string, a fragment or a ``//`` path segment is rejected in both layers,
  because the client appends ``/chat/completions`` to the base.

The five URLs are assumptions (A) that age, so they live in one table and are
pinned here: ``PINNED_CLOUD_BASE_URLS`` in this file is the single place to
correct an aged URL, after which the table mirrors it. Per amended item 18 the
test also carries ``PRESETS_VERIFIED_ON``, the date the set was last checked
against the providers' live documentation.

Nothing here opens a socket or loads a model (Locked intent #12, AC8): the
settings are pure pydantic validation and the factory builds a client that is
never called.
"""

from __future__ import annotations

import ast
import importlib
from pathlib import Path

import pytest
from pydantic import ValidationError

from khaleev.cloud_providers import CLOUD_PROVIDER_BASE_URLS, DEFAULT_CLOUD_BASE_URL
from khaleev.config import Settings
from khaleev.generation import build_generator
from khaleev.generation.base import GeneratorNotConfiguredError
from khaleev.generation.cloud import CloudGenerator
from khaleev.generation.ollama import OllamaGenerator

#: The date this five-URL set was last verified against the providers' live
#: documentation (amended SPEC item 18: the test carries the date so a reader
#: can tell how fresh the table is without opening the spec).
PRESETS_VERIFIED_ON = "2026-11-15"

#: The pinned preset table — SPEC item 18's (A) URLs, copied verbatim.
#:
#: ``github`` is deliberately absent. GitHub Models was retired on 2026-07-30
#: (verified 2026-11-15 against https://docs.github.com/en/github-models), so
#: the preset was dropped and must not be restored "for symmetry": the five
#: names below are the whole set.
PINNED_CLOUD_BASE_URLS = {
    "openai": "https://api.openai.com/v1",
    "openrouter": "https://openrouter.ai/api/v1",
    "groq": "https://api.groq.com/openai/v1",
    "gemini": "https://generativelanguage.googleapis.com/v1beta/openai/",
    "cerebras": "https://api.cerebras.ai/v1",
}

BASE_URL = "https://cloud.example.test/v1"
API_KEY = "test-key"
MODEL = "cloud-model-1"

MISSING_KEY_MESSAGE = (
    "cloud generation is selected but KHALEEV_CLOUD_API_KEY is not set; "
    "set it or set KHALEEV_GENERATOR=ollama for the zero-key local default"
)
MISSING_MODEL_MESSAGE = (
    "cloud generation is selected but KHALEEV_CLOUD_MODEL is not set; "
    "set it or set KHALEEV_GENERATOR=ollama for the zero-key local default"
)


# ---------------------------------------------------------------------------
# The pinned table of (A) URLs
# ---------------------------------------------------------------------------


def test_the_provider_table_pins_the_five_spec_urls() -> None:
    """The single place to correct an aged URL: the dict above, then the table."""
    assert PRESETS_VERIFIED_ON == "2026-11-15"
    assert CLOUD_PROVIDER_BASE_URLS == PINNED_CLOUD_BASE_URLS


def test_the_provider_name_set_is_exactly_the_closed_set() -> None:
    assert set(CLOUD_PROVIDER_BASE_URLS) == {
        "openai",
        "openrouter",
        "groq",
        "gemini",
        "cerebras",
    }


def test_the_default_endpoint_is_the_openai_one() -> None:
    assert DEFAULT_CLOUD_BASE_URL == "https://api.openai.com/v1"
    assert DEFAULT_CLOUD_BASE_URL == PINNED_CLOUD_BASE_URLS["openai"]


def test_the_cloud_client_exports_that_same_default() -> None:
    """One definition: the client re-exports the neutral module's constant."""
    from khaleev.generation import cloud

    assert cloud.DEFAULT_CLOUD_BASE_URL == DEFAULT_CLOUD_BASE_URL


def test_the_preset_table_lives_in_a_neutral_module() -> None:
    """``config`` imports the table, so the table must import nothing of ours.

    A table under ``khaleev.generation`` would mean ``config -> generation`` and
    a circular import, because ``khaleev.generation`` imports ``khaleev.config``.
    """
    module = importlib.import_module("khaleev.cloud_providers")
    source = Path(module.__file__ or "").read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)

    assert Path(module.__file__ or "").parent.name == "khaleev"
    assert [name for name in imported if name.startswith("khaleev")] == []


# ---------------------------------------------------------------------------
# The one resolution rule
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("provider", list(PINNED_CLOUD_BASE_URLS))
def test_each_preset_resolves_to_its_pinned_url(provider: str) -> None:
    settings = Settings(_env_file=None, cloud_provider=provider)

    assert settings.resolved_cloud_base_url == PINNED_CLOUD_BASE_URLS[provider].rstrip("/")


def test_an_explicit_base_url_wins_over_the_preset() -> None:
    settings = Settings(_env_file=None, cloud_provider="groq", cloud_base_url=BASE_URL)

    assert settings.cloud_base_url == BASE_URL
    assert settings.cloud_provider == "groq"
    assert settings.resolved_cloud_base_url == BASE_URL


def test_neither_setting_resolves_to_the_default_endpoint() -> None:
    settings = Settings(_env_file=None)

    assert settings.cloud_base_url is None
    assert settings.cloud_provider is None
    assert settings.resolved_cloud_base_url == "https://api.openai.com/v1"


def test_explicit_none_is_the_same_as_unset() -> None:
    settings = Settings(_env_file=None, cloud_base_url=None, cloud_provider=None)

    assert settings.resolved_cloud_base_url == "https://api.openai.com/v1"


@pytest.mark.parametrize(
    "kwargs",
    [{}, {"cloud_provider": "gemini"}, {"cloud_base_url": "https://cloud.example.test/v1/"}],
    ids=["default", "preset", "explicit"],
)
def test_the_resolved_url_never_ends_with_a_slash(kwargs: dict[str, str]) -> None:
    assert not Settings(_env_file=None, **kwargs).resolved_cloud_base_url.endswith("/")


# ---------------------------------------------------------------------------
# Normalisation: a trailing slash is not an error
# ---------------------------------------------------------------------------


def test_a_trailing_slash_is_normalised_not_rejected() -> None:
    settings = Settings(_env_file=None, cloud_base_url="https://cloud.example.test/v1/")

    assert settings.cloud_base_url == "https://cloud.example.test/v1"
    assert settings.resolved_cloud_base_url == "https://cloud.example.test/v1"


def test_a_base_url_assigned_after_construction_is_normalised_too() -> None:
    settings = Settings(_env_file=None)

    settings.cloud_base_url = "https://cloud.example.test/v1/"

    assert settings.resolved_cloud_base_url == "https://cloud.example.test/v1"


def test_the_pinned_gemini_url_keeps_its_trailing_slash_in_the_table() -> None:
    """The table mirrors the spec verbatim; the resolver is what strips it."""
    assert CLOUD_PROVIDER_BASE_URLS["gemini"] == (
        "https://generativelanguage.googleapis.com/v1beta/openai/"
    )
    assert Settings(_env_file=None, cloud_provider="gemini").resolved_cloud_base_url == (
        "https://generativelanguage.googleapis.com/v1beta/openai"
    )


def test_surrounding_whitespace_is_stripped_like_a_trailing_slash() -> None:
    settings = Settings(_env_file=None, cloud_base_url="  https://cloud.example.test/v1/  ")

    assert settings.cloud_base_url == "https://cloud.example.test/v1"
    assert settings.resolved_cloud_base_url == "https://cloud.example.test/v1"


# ---------------------------------------------------------------------------
# Uncomposable base URLs are rejected in both layers (amended item 18)
# ---------------------------------------------------------------------------

UNFORMABLE_BASE_URLS = [
    "https://cloud.example.test/v1?x=1",
    "https://cloud.example.test/v1#frag",
]
UNFORMABLE_IDS = ["query", "fragment"]


@pytest.mark.parametrize("value", UNFORMABLE_BASE_URLS, ids=UNFORMABLE_IDS)
def test_settings_reject_a_query_or_fragment_base_url(value: str) -> None:
    """The client appends ``/chat/completions``; a query/fragment breaks it."""
    with pytest.raises(ValidationError) as excinfo:
        Settings(_env_file=None, cloud_base_url=value)

    message = str(excinfo.value)
    assert "KHALEEV_CLOUD_BASE_URL" in message
    assert "query string" in message
    assert "fragment" in message
    assert "/chat/completions" in message
    assert "malformed request URL" in message


@pytest.mark.parametrize("value", UNFORMABLE_BASE_URLS, ids=UNFORMABLE_IDS)
def test_a_directly_constructed_generator_rejects_a_query_or_fragment(
    value: str,
) -> None:
    """A programmatic caller cannot bypass the settings validator."""
    with pytest.raises(GeneratorNotConfiguredError) as excinfo:
        CloudGenerator(API_KEY, MODEL, base_url=value)

    message = str(excinfo.value)
    assert "KHALEEV_CLOUD_BASE_URL" in message
    assert "/chat/completions" in message
    assert "malformed request URL" in message
    assert API_KEY not in message


def test_a_directly_constructed_generator_strips_surrounding_whitespace() -> None:
    generator = CloudGenerator(
        API_KEY, MODEL, base_url="  https://cloud.example.test/v1/  "
    )

    assert generator.base_url == "https://cloud.example.test/v1"
    assert generator.completions_url == "https://cloud.example.test/v1/chat/completions"


def test_a_duplicated_path_slash_is_rejected_in_both_layers() -> None:
    """``https://host//v1//`` would compose ``//v1/chat/completions``."""
    value = "https://cloud.example.test//v1//"

    with pytest.raises(ValidationError) as excinfo:
        Settings(_env_file=None, cloud_base_url=value)
    assert "KHALEEV_CLOUD_BASE_URL" in str(excinfo.value)

    with pytest.raises(GeneratorNotConfiguredError) as excinfo:
        CloudGenerator(API_KEY, MODEL, base_url=value)
    assert "KHALEEV_CLOUD_BASE_URL" in str(excinfo.value)


# ---------------------------------------------------------------------------
# Validation with actionable messages
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("provider", ["together", "OPENAI", "OpenRouter", "azure", ""])
def test_an_unknown_provider_names_the_setting_and_the_accepted_values(
    provider: str,
) -> None:
    with pytest.raises(ValidationError) as excinfo:
        Settings(_env_file=None, cloud_provider=provider)

    message = str(excinfo.value)
    assert "KHALEEV_CLOUD_PROVIDER" in message
    for accepted in PINNED_CLOUD_BASE_URLS:
        assert accepted in message


def test_an_unknown_provider_is_rejected_even_with_an_explicit_base_url() -> None:
    """The base URL wins the resolution, not the validation."""
    with pytest.raises(ValidationError) as excinfo:
        Settings(_env_file=None, cloud_provider="together", cloud_base_url=BASE_URL)

    assert "KHALEEV_CLOUD_PROVIDER" in str(excinfo.value)


def test_github_is_rejected_as_an_unknown_provider() -> None:
    """The preset is dropped: GitHub Models was retired on 2026-07-30."""
    assert "github" not in CLOUD_PROVIDER_BASE_URLS

    with pytest.raises(ValidationError) as excinfo:
        Settings(_env_file=None, cloud_provider="github")

    # Pydantic echoes the rejected input in a separate field, so the absence
    # check is against our message, which lists exactly the five names.
    message = excinfo.value.errors()[0]["msg"]
    assert "KHALEEV_CLOUD_PROVIDER" in message
    for accepted in ("openai", "openrouter", "groq", "gemini", "cerebras"):
        assert accepted in message
    assert "github" not in message


@pytest.mark.parametrize(
    "value",
    [
        "",
        "   ",
        "cloud.example.test/v1",
        "/v1",
        "ftp://cloud.example.test/v1",
        "https://",
        "http:/cloud.example.test",
    ],
    ids=["empty", "whitespace", "no-scheme", "relative", "ftp", "no-host", "one-slash"],
)
def test_a_non_absolute_http_url_names_the_setting_and_both_schemes(value: str) -> None:
    with pytest.raises(ValidationError) as excinfo:
        Settings(_env_file=None, cloud_base_url=value)

    message = str(excinfo.value)
    assert "KHALEEV_CLOUD_BASE_URL" in message
    assert "absolute" in message
    assert "http://" in message
    assert "https://" in message


def test_an_empty_base_url_is_rejected_not_treated_as_unset() -> None:
    """``None`` is unset; the empty string is an invalid URL (SPEC item 18 (A))."""
    with pytest.raises(ValidationError):
        Settings(_env_file=None, cloud_base_url="")


# ---------------------------------------------------------------------------
# Environment and .env
# ---------------------------------------------------------------------------


def test_the_two_env_vars_are_read(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("KHALEEV_CLOUD_BASE_URL", "https://env.example.test/v1/")
    monkeypatch.setenv("KHALEEV_CLOUD_PROVIDER", "cerebras")

    settings = Settings(_env_file=None)

    assert settings.cloud_base_url == "https://env.example.test/v1"
    assert settings.cloud_provider == "cerebras"
    assert settings.resolved_cloud_base_url == "https://env.example.test/v1"


def test_the_provider_env_var_alone_resolves_its_preset(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("KHALEEV_CLOUD_PROVIDER", "openrouter")

    settings = Settings(_env_file=None)

    assert settings.resolved_cloud_base_url == "https://openrouter.ai/api/v1"


# ---------------------------------------------------------------------------
# The factory passes the resolved endpoint
# ---------------------------------------------------------------------------


def test_the_factory_hands_the_resolved_preset_to_the_cloud_generator() -> None:
    settings = Settings(
        _env_file=None,
        generator="cloud",
        cloud_api_key=API_KEY,
        cloud_model=MODEL,
        cloud_provider="groq",
    )

    generator = build_generator(settings)

    assert isinstance(generator, CloudGenerator)
    assert generator.base_url == "https://api.groq.com/openai/v1"
    assert generator.completions_url == "https://api.groq.com/openai/v1/chat/completions"


def test_the_factory_hands_an_explicit_base_url_to_the_cloud_generator() -> None:
    settings = Settings(
        _env_file=None,
        generator="cloud",
        cloud_api_key=API_KEY,
        cloud_model=MODEL,
        cloud_provider="groq",
        cloud_base_url=f"{BASE_URL}/",
    )

    generator = build_generator(settings)

    assert isinstance(generator, CloudGenerator)
    assert generator.base_url == BASE_URL
    assert generator.completions_url == f"{BASE_URL}/chat/completions"


def test_todays_cloud_dotenv_shape_keeps_todays_endpoint() -> None:
    """Backward compatibility: the three old variables alone behave as before."""
    settings = Settings(
        _env_file=None,
        generator="cloud",
        cloud_api_key=API_KEY,
        cloud_model=MODEL,
    )

    generator = build_generator(settings)

    assert isinstance(generator, CloudGenerator)
    assert generator.base_url == "https://api.openai.com/v1"
    assert generator.completions_url == "https://api.openai.com/v1/chat/completions"


# ---------------------------------------------------------------------------
# Unchanged errors and the untouched local default
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("kwargs", "expected"),
    [
        ({"cloud_api_key": None, "cloud_model": MODEL}, MISSING_KEY_MESSAGE),
        ({"cloud_api_key": API_KEY, "cloud_model": None}, MISSING_MODEL_MESSAGE),
    ],
    ids=["missing-key", "missing-model"],
)
def test_the_missing_key_and_missing_model_messages_are_verbatim(
    kwargs: dict[str, str | None], expected: str
) -> None:
    settings = Settings(_env_file=None, generator="cloud", **kwargs)

    with pytest.raises(GeneratorNotConfiguredError) as excinfo:
        build_generator(settings)

    assert str(excinfo.value) == expected


def test_the_missing_model_message_never_echoes_the_key() -> None:
    settings = Settings(
        _env_file=None,
        generator="cloud",
        cloud_api_key="sk-secret-value",
        cloud_model=None,
    )

    with pytest.raises(GeneratorNotConfiguredError) as excinfo:
        build_generator(settings)

    assert "sk-secret-value" not in str(excinfo.value)


def test_the_new_validation_messages_never_echo_the_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("KHALEEV_CLOUD_API_KEY", "sk-secret-value")

    for bad_settings in ({"cloud_provider": "together"}, {"cloud_base_url": "not-a-url"}):
        with pytest.raises(ValidationError) as excinfo:
            Settings(_env_file=None, **bad_settings)
        assert "sk-secret-value" not in str(excinfo.value)


def test_the_default_generator_is_still_ollama_with_no_key_and_no_endpoint() -> None:
    generator = build_generator(Settings(_env_file=None))

    assert isinstance(generator, OllamaGenerator)
    assert generator.base_url == "http://localhost:11434"
    assert generator.model == "llama3.1:8b"


@pytest.mark.parametrize(
    "kwargs",
    [
        {"cloud_api_key": API_KEY},
        {"cloud_provider": "groq"},
        {"cloud_base_url": BASE_URL},
        {"cloud_api_key": API_KEY, "cloud_provider": "groq", "cloud_base_url": BASE_URL},
    ],
    ids=["key-only", "provider-only", "endpoint-only", "all-three"],
)
def test_cloud_settings_alone_never_change_the_default_generator(
    kwargs: dict[str, str],
) -> None:
    assert isinstance(build_generator(Settings(_env_file=None, **kwargs)), OllamaGenerator)
