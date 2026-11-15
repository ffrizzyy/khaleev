"""Integration test: a configured cloud endpoint with no key still boots (T29).

Locked intent 18 keeps the key and the model required exactly as before while the
endpoint becomes configurable. The failure mode this pins is the important one: a
misconfigured endpoint must never turn a missing key into an endpoint or
connection error. With ``KHALEEV_GENERATOR=cloud`` and a base URL but no key, the
app boots, ``GET /api/config`` answers 200, and an ask answers the same actionable
503 the missing key produced before — proving the URL was accepted and no request
to it was ever attempted (the suite-wide socket guard would raise otherwise).

The factory is deliberately not stubbed here: no generator is injected, so the
ask route really calls ``build_generator()`` and the new ``base_url`` wiring is
exercised.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi import FastAPI
from fixtures.api_client import ApiClient
from fixtures.pdf_factory import build_pdf
from pydantic import ValidationError
from sqlalchemy.engine import Engine

from khaleev.app import create_app
from khaleev.config import Settings
from khaleev.ingest.embedding import FakeEmbedder

BASE_URL = "https://cloud.example.test/v1"
MISSING_KEY_MESSAGE = (
    "cloud generation is selected but KHALEEV_CLOUD_API_KEY is not set; "
    "set it or set KHALEEV_GENERATOR=ollama for the zero-key local default"
)

PAGE_TEXTS = [
    "Late filings incur a 200 credit penalty per return.",
    "Refunds are processed within ten business days.",
    "Appeals must be filed within thirty days of the notice.",
]

TODAYS_CONFIG_FIELDS = {"k", "embedder", "generator", "ollama_base_url", "ollama_model"}


@pytest.fixture
def settings(monkeypatch: pytest.MonkeyPatch) -> Settings:
    """Cloud selected, an endpoint configured, and deliberately no key at all."""
    monkeypatch.setenv("KHALEEV_GENERATOR", "cloud")
    monkeypatch.setenv("KHALEEV_CLOUD_BASE_URL", BASE_URL)
    monkeypatch.delenv("KHALEEV_CLOUD_API_KEY", raising=False)
    monkeypatch.delenv("KHALEEV_CLOUD_MODEL", raising=False)
    return Settings(_env_file=None)


@pytest.fixture
def app(migrated_engine: Engine, settings: Settings) -> FastAPI:
    """The real app with a fake embedder and **no** injected generator."""
    return create_app(settings=settings, embedder=FakeEmbedder())


@pytest.fixture
def client(app: FastAPI) -> Iterator[ApiClient]:
    with ApiClient(app) as client:
        yield client


def _upload(client: ApiClient) -> int:
    response = client.post(
        "/api/documents",
        files={"file": ("tax-guide.pdf", build_pdf(PAGE_TEXTS), "application/pdf")},
    )
    assert response.status_code == 201, response.text
    return int(response.json()["id"])


def test_the_configured_endpoint_is_accepted_by_the_settings(settings: Settings) -> None:
    """A silently ignored setting would boot too — so pin that it took effect."""
    assert settings.generator == "cloud"
    assert settings.cloud_api_key is None
    assert settings.cloud_base_url == BASE_URL
    assert settings.resolved_cloud_base_url == BASE_URL


def test_a_missing_key_with_a_configured_endpoint_is_the_actionable_503(
    client: ApiClient,
) -> None:
    document_id = _upload(client)

    response = client.post(f"/api/documents/{document_id}/ask", json={"question": "Why?"})

    assert response.status_code == 503
    detail = response.json()["detail"]
    assert detail == MISSING_KEY_MESSAGE
    # Not an endpoint, connection or DNS failure: the URL was never called.
    assert BASE_URL not in detail
    assert "cloud.example.test" not in detail


def test_the_config_endpoint_still_answers_200_with_todays_five_fields(
    client: ApiClient,
) -> None:
    response = client.get("/api/config")

    assert response.status_code == 200
    payload = response.json()
    assert set(payload) == TODAYS_CONFIG_FIELDS
    assert payload["generator"] == "cloud"
    text = response.text
    assert "cloud_base_url" not in text
    assert "cloud_provider" not in text


def test_a_boot_with_the_retired_github_preset_is_refused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """GitHub Models was retired 2026-07-30; the boot refuses the name."""
    monkeypatch.setenv("KHALEEV_CLOUD_PROVIDER", "github")

    with pytest.raises(ValidationError) as excinfo:
        Settings(_env_file=None)

    message = excinfo.value.errors()[0]["msg"]
    assert "KHALEEV_CLOUD_PROVIDER" in message
    for accepted in ("openai", "openrouter", "groq", "gemini", "cerebras"):
        assert accepted in message
    assert "github" not in message


def test_a_boot_with_a_query_bearing_base_url_is_refused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An Azure-style ``?api-version=`` base would compose a malformed URL."""
    monkeypatch.setenv("KHALEEV_GENERATOR", "cloud")
    monkeypatch.setenv("KHALEEV_CLOUD_BASE_URL", f"{BASE_URL}?api-version=2024-01-01")

    with pytest.raises(ValidationError) as excinfo:
        Settings(_env_file=None)

    message = str(excinfo.value)
    assert "KHALEEV_CLOUD_BASE_URL" in message
    assert "/chat/completions" in message
