"""The cloud generator's endpoint presets (T29).

The cloud endpoint is configurable by environment or ``.env`` so a free-tier
OpenAI-compatible key can be used without editing source (Locked intent 18). The
closed set of providers and their base URLs live here, in a *neutral* top-level
module, because ``khaleev.config`` imports this table while
``khaleev.generation`` imports ``khaleev.config`` — a table under
``khaleev.generation`` would make that a circular import.

The six URLs are assumptions (A), not contracts: a provider can move its
endpoint. They are recorded as data and pinned by
``tests/unit/test_cloud_endpoint.py``, which is **the single place to correct
them**: when one ages, fix the test's expected value and mirror the table here.
An explicit ``KHALEEV_CLOUD_BASE_URL`` always overrides the preset, so a user is
never trapped on an aged entry.

The lookup is a dict lookup, never a request: importing this module performs no
I/O and opens no socket (Locked intent #12).
"""

from __future__ import annotations

#: OpenAI's public API, and the resolved endpoint when nothing else is set.
DEFAULT_CLOUD_BASE_URL = "https://api.openai.com/v1"

#: The closed set of provider presets, in the order the docs list them.
CLOUD_PROVIDER_BASE_URLS: dict[str, str] = {
    "openai": "https://api.openai.com/v1",
    "openrouter": "https://openrouter.ai/api/v1",
    "groq": "https://api.groq.com/openai/v1",
    "gemini": "https://generativelanguage.googleapis.com/v1beta/openai/",
    "cerebras": "https://api.cerebras.ai/v1",
    "github": "https://models.github.ai",
}

__all__ = ["CLOUD_PROVIDER_BASE_URLS", "DEFAULT_CLOUD_BASE_URL"]
