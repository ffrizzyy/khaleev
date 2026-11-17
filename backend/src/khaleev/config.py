"""Application settings for Khaleev.

``Settings`` is **environment-only**: it reads ``KHALEEV_*`` process environment
variables plus its field defaults, and never a dotenv file. Reading ``.env`` is
an explicit act through ``load_settings()``, which is the only dotenv reader
here and resolves the file against the current working directory
(``backend/.env`` when the app is started from ``backend/``).

Every setting has a working local default: the app runs with zero API keys
(SPEC Locked intent #10, #11, AC3). That includes the optional cloud endpoint:
``cloud_base_url`` and ``cloud_provider`` both default to ``None``, and the
resolved endpoint is then today's OpenAI URL, so an existing ``.env`` behaves
exactly as it did before Locked intent 18. Nothing here creates directories;
call ``Settings.ensure_data_dir`` for that.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from khaleev import paths
from khaleev.cloud_providers import (
    CLOUD_PROVIDER_BASE_URLS,
    DEFAULT_CLOUD_BASE_URL,
    normalise_cloud_base_url,
)

ENV_PREFIX = "KHALEEV_"
ENV_FILE_NAME = ".env"

CloudProvider = Literal["openai", "openrouter", "groq", "gemini", "cerebras"]

_INVALID_CLOUD_BASE_URL = (
    "KHALEEV_CLOUD_BASE_URL must be an absolute URL starting with http:// or https://"
)


class Settings(BaseSettings):
    """Runtime configuration; ``Settings()`` needs no environment or API key."""

    model_config = SettingsConfigDict(
        env_prefix=ENV_PREFIX,
        env_file_encoding="utf-8",
        extra="ignore",
    )

    data_dir: Path = Field(default_factory=paths.default_data_dir)
    embedder_id: str = "all-MiniLM-L6-v2"
    generator: Literal["ollama", "cloud"] = "ollama"
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "llama3.1:8b"
    cloud_api_key: str | None = None
    cloud_model: str | None = None
    cloud_base_url: str | None = None
    cloud_provider: CloudProvider | None = None
    cloud_fallback_models: str | None = None
    retrieval_k: int = Field(default=5, ge=1)
    max_upload_bytes: int = Field(default=50 * 1024 * 1024, ge=1)
    chunk_size: int = Field(default=600, ge=400, le=800)
    chunk_overlap_ratio: float = Field(default=0.12, ge=0.10, le=0.15)

    @field_validator("cloud_provider", mode="before")
    @classmethod
    def _known_cloud_provider(cls, value: object) -> object:
        """Reject an unknown preset, naming the setting and the accepted names.

        The match is exact (lower case): ``OpenRouter`` is not ``openrouter``.
        A ``mode="before"`` validator is used so this message — not pydantic's
        generic ``Literal`` error — is what the user reads.
        """
        if value is None:
            return None
        if not isinstance(value, str) or value not in CLOUD_PROVIDER_BASE_URLS:
            accepted = ", ".join(CLOUD_PROVIDER_BASE_URLS)
            raise ValueError(
                f"KHALEEV_CLOUD_PROVIDER must be one of {accepted} (lower case, exactly)"
            )
        return value

    @field_validator("cloud_base_url", mode="before")
    @classmethod
    def _absolute_http_base_url(cls, value: object) -> object:
        """Accept only an absolute ``http``/``https`` URL that can compose a request.

        Surrounding whitespace and a trailing slash are normalised, not errors.
        A query string or fragment is rejected through the shared normaliser:
        the client appends ``/chat/completions``, so such a base can only
        produce a malformed request URL (Locked intent 18). ``None`` is the
        *only* "unset" value: ``""`` and whitespace are invalid URLs, never a
        third resolution path (SPEC item 18's (A) clarification).
        """
        if value is None:
            return None
        if not isinstance(value, str):
            raise ValueError(_INVALID_CLOUD_BASE_URL)
        candidate = value.strip()
        try:
            parts = urlsplit(candidate)
        except ValueError:
            raise ValueError(_INVALID_CLOUD_BASE_URL) from None
        if parts.scheme not in {"http", "https"} or not parts.netloc:
            raise ValueError(_INVALID_CLOUD_BASE_URL)
        return normalise_cloud_base_url(candidate)

    @property
    def resolved_cloud_base_url(self) -> str:
        """The cloud endpoint: explicit base URL, then preset, then the default.

        Exactly one rule (Locked intent 18): an explicit ``cloud_base_url``
        always wins; the ``cloud_provider`` preset applies only while
        ``cloud_base_url`` is ``None``; neither set means the OpenAI default.
        The trailing slash is stripped on every path, so the resolved URL never
        ends with one — the pinned ``gemini`` entry keeps its slash in the table
        and is normalised here (``CloudGenerator`` strips it too, so the request
        URL is identical either way).
        """
        if self.cloud_base_url is not None:
            return self.cloud_base_url.rstrip("/")
        if self.cloud_provider is not None:
            return CLOUD_PROVIDER_BASE_URLS[self.cloud_provider].rstrip("/")
        return DEFAULT_CLOUD_BASE_URL

    @property
    def resolved_cloud_fallback_models(self) -> list[str]:
        """The ordered fallback model ids, parsed from the comma-separated setting.

        Split on ``,``, strip every entry, drop the empties, keep the user's
        order. Absent, ``""``, whitespace-only and commas-only all mean *no
        fallbacks* — deliberately not an error, unlike ``KHALEEV_CLOUD_BASE_URL``
        where the empty string is invalid (Locked intent 19): "no fallbacks" is a
        meaningful state, not a third resolution path.
        """
        raw = self.cloud_fallback_models
        if raw is None:
            return []
        return [entry.strip() for entry in raw.split(",") if entry.strip()]

    @model_validator(mode="after")
    def _valid_cloud_fallback_models(self) -> Settings:
        """Reject a bad fallback list — but only while cloud generation is selected.

        The list is dormant on ``KHALEEV_GENERATOR=ollama``, exactly like the
        other cloud settings the local factory ignores (SPEC item 19 as amended
        2026-11-16), so switching back to the local generator never forces a user
        to delete a variable. Inside the cloud branch there are three rules: the
        primary may not be repeated, an entry may not be duplicated (order is
        priority, so a silent dedupe would hide a mistake), and a non-empty list
        requires the ``openrouter`` **preset** — ``cloud_provider ==
        "openrouter"`` and no explicit base URL — because ``models`` is
        OpenRouter-specific and the preset is the one honest signal the endpoint
        understands it. Every message names the setting and never the API key.
        """
        if self.generator != "cloud":
            return self

        fallbacks = self.resolved_cloud_fallback_models
        if not fallbacks:
            return self

        primary = (self.cloud_model or "").strip()
        if primary:
            for entry in fallbacks:
                if entry == primary:
                    raise ValueError(
                        "KHALEEV_CLOUD_FALLBACK_MODELS must not repeat the primary "
                        f"model '{primary}' from KHALEEV_CLOUD_MODEL: the primary is "
                        "always tried first, so a copy in the fallback list only "
                        "hides a mistake in the priority order"
                    )

        seen: set[str] = set()
        for entry in fallbacks:
            if entry in seen:
                raise ValueError(
                    f"KHALEEV_CLOUD_FALLBACK_MODELS lists '{entry}' more than once: "
                    "the entries are tried in priority order, so every model may "
                    "appear only once"
                )
            seen.add(entry)

        if self.cloud_provider != "openrouter" or self.cloud_base_url is not None:
            raise ValueError(
                "KHALEEV_CLOUD_FALLBACK_MODELS is OpenRouter-specific: fallback "
                "models are accepted only when the cloud endpoint is the OpenRouter "
                "preset (KHALEEV_CLOUD_PROVIDER=openrouter with "
                "KHALEEV_CLOUD_BASE_URL unset), not with another provider or an "
                "explicit base URL"
            )
        return self

    @property
    def golden_dir(self) -> Path:
        """Directory holding the per-document golden-set JSON files."""
        return self.data_dir / paths.GOLDEN_DIRNAME

    def ensure_data_dir(self) -> paths.DataPaths:
        """Create the data directory layout and return its resolved paths."""
        return paths.DataPaths.from_data_dir(self.data_dir).create()


def load_settings(**overrides: object) -> Settings:
    """Build settings, reading ``.env`` from the current working directory.

    This is the single dotenv entry point in the application: it passes
    ``_env_file`` explicitly, resolves the file against the process working
    directory exactly like the constructor used to (``backend/.env`` when the
    app is started from ``backend/``), and keeps the model config's ``utf-8``
    encoding. Keyword overrides win over the file without disabling it.

    Nothing is caught or delayed: a malformed ``.env`` raises the same
    ``pydantic.ValidationError`` at the same moment it always did. Callers that
    want a file-free load construct ``Settings`` directly, which is
    environment-only.
    """
    return Settings(_env_file=ENV_FILE_NAME, **overrides)
