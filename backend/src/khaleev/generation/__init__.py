"""Answer generation: the protocol, the two clients, prompts and citations (T08).

``build_generator`` is the single place the configured generator is chosen. Its
rules are the product rules:

* the default is Ollama, and settings with no keys still build it (Locked
  intent #10, #11, AC3);
* ``cloud`` is only built when the user explicitly selected it **and** supplied
  both a key and a model; otherwise the error says exactly what is missing;
  the endpoint it is built with is the settings' resolved one — an explicit
  ``KHALEEV_CLOUD_BASE_URL``, else the ``KHALEEV_CLOUD_PROVIDER`` preset, else
  the OpenAI default (Locked intent 18);
* a cloud key alone never changes the default, because the app must not send
  document content off-machine unless the user asked for it (Boundaries ->
  Never).

Nothing here performs I/O at import time, so ``import khaleev.generation`` never
loads a model or opens a socket (Locked intent #12).
"""

from __future__ import annotations

from khaleev.config import Settings
from khaleev.generation.base import (
    FakeGenerator,
    GenerationError,
    Generator,
    GeneratorNotConfiguredError,
)
from khaleev.generation.citations import parse_citations
from khaleev.generation.cloud import CloudGenerator
from khaleev.generation.ollama import OllamaGenerator
from khaleev.generation.prompts import build_prompt

__all__ = [
    "CloudGenerator",
    "FakeGenerator",
    "GenerationError",
    "Generator",
    "GeneratorNotConfiguredError",
    "OllamaGenerator",
    "build_generator",
    "build_prompt",
    "parse_citations",
]


def build_generator(settings: Settings | None = None) -> Generator:
    """Return the generator selected by ``settings`` (Ollama by default)."""
    config = settings if settings is not None else Settings()

    if config.generator == "cloud":
        if not config.cloud_api_key:
            raise GeneratorNotConfiguredError(
                "cloud generation is selected but KHALEEV_CLOUD_API_KEY is not set; "
                "set it or set KHALEEV_GENERATOR=ollama for the zero-key local default"
            )
        if not config.cloud_model:
            raise GeneratorNotConfiguredError(
                "cloud generation is selected but KHALEEV_CLOUD_MODEL is not set; "
                "set it or set KHALEEV_GENERATOR=ollama for the zero-key local default"
            )
        return CloudGenerator(
            config.cloud_api_key,
            config.cloud_model,
            base_url=config.resolved_cloud_base_url,
        )

    return OllamaGenerator(config.ollama_base_url, config.ollama_model)
