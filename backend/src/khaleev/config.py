"""Application settings for Khaleev.

Values come from ``KHALEEV_*`` environment variables (or a local ``.env``
file), and every one has a working local default: the app runs with zero API
keys (SPEC Locked intent #10, #11, AC3). Nothing here creates directories;
call ``Settings.ensure_data_dir`` for that.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from khaleev import paths

ENV_PREFIX = "KHALEEV_"


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
    retrieval_k: int = Field(default=5, ge=1)
    chunk_size: int = Field(default=600, ge=400, le=800)
    chunk_overlap_ratio: float = Field(default=0.12, ge=0.10, le=0.15)

    @property
    def golden_dir(self) -> Path:
        """Directory holding the per-document golden-set JSON files."""
        return self.data_dir / paths.GOLDEN_DIRNAME

    def ensure_data_dir(self) -> paths.DataPaths:
        """Create the data directory layout and return its resolved paths."""
        return paths.DataPaths.from_data_dir(self.data_dir).create()
