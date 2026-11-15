"""Application settings for Khaleev.

Values come from ``KHALEEV_*`` environment variables (or a local ``.env``
file), and every one has a working local default: the app runs with zero API
keys (SPEC Locked intent #10, #11, AC3). That includes the optional cloud
endpoint: ``cloud_base_url`` and ``cloud_provider`` both default to ``None``,
and the resolved endpoint is then today's OpenAI URL, so an existing ``.env``
behaves exactly as it did before Locked intent 18. Nothing here creates
directories; call ``Settings.ensure_data_dir`` for that.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from khaleev import paths
from khaleev.cloud_providers import CLOUD_PROVIDER_BASE_URLS, DEFAULT_CLOUD_BASE_URL

ENV_PREFIX = "KHALEEV_"

CloudProvider = Literal["openai", "openrouter", "groq", "gemini", "cerebras", "github"]

_INVALID_CLOUD_BASE_URL = (
    "KHALEEV_CLOUD_BASE_URL must be an absolute URL starting with http:// or https://"
)


class Settings(BaseSettings):
    """Runtime configuration; ``Settings()`` needs no environment or API key."""

    model_config = SettingsConfigDict(
        env_prefix=ENV_PREFIX,
        env_file=".env",
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
        """Accept only an absolute ``http``/``https`` URL; strip a trailing slash.

        ``None`` is the *only* "unset" value: ``""`` and whitespace are invalid
        URLs, never a third resolution path (SPEC item 18's (A) clarification).
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
        return candidate.rstrip("/")

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
    def golden_dir(self) -> Path:
        """Directory holding the per-document golden-set JSON files."""
        return self.data_dir / paths.GOLDEN_DIRNAME

    def ensure_data_dir(self) -> paths.DataPaths:
        """Create the data directory layout and return its resolved paths."""
        return paths.DataPaths.from_data_dir(self.data_dir).create()
