"""The cloud generator's endpoint presets and base-URL rules (T29).

The cloud endpoint is configurable by environment or ``.env`` so a free-tier
OpenAI-compatible key can be used without editing source (Locked intent 18). The
closed set of providers and their base URLs live here, in a *neutral* top-level
module, because ``khaleev.config`` imports this table while
``khaleev.generation`` imports ``khaleev.config`` — a table under
``khaleev.generation`` would make that a circular import.

The five URLs are assumptions (A), not contracts: a provider can move its
endpoint. They are recorded as data and pinned by
``tests/unit/test_cloud_endpoint.py``, which is **the single place to correct
them**: when one ages, fix the test's expected value and mirror the table here.
An explicit ``KHALEEV_CLOUD_BASE_URL`` always overrides the preset, so a user is
never trapped on an aged entry.

There is deliberately no ``github`` preset: GitHub Models was retired on
2026-07-30 (verified 2026-11-15 against GitHub's own documentation), so an
advertised preset for it could only fail. Do not restore it "for symmetry" —
adding a provider is a deliberate change that must be verified live first.

The lookup is a dict lookup and the normaliser is pure string handling, never a
request: importing this module performs no I/O and opens no socket (Locked
intent #12).
"""

from __future__ import annotations

from urllib.parse import urlsplit

#: OpenAI's public API, and the resolved endpoint when nothing else is set.
DEFAULT_CLOUD_BASE_URL = "https://api.openai.com/v1"

#: The closed set of provider presets, in the order the docs list them.
CLOUD_PROVIDER_BASE_URLS: dict[str, str] = {
    "openai": "https://api.openai.com/v1",
    "openrouter": "https://openrouter.ai/api/v1",
    "groq": "https://api.groq.com/openai/v1",
    "gemini": "https://generativelanguage.googleapis.com/v1beta/openai/",
    "cerebras": "https://api.cerebras.ai/v1",
}

#: Why a base URL that cannot compose a valid request URL is refused. Shared by
#: ``Settings`` and ``CloudGenerator`` so the two validation layers agree.
UNFORMABLE_CLOUD_BASE_URL = (
    "KHALEEV_CLOUD_BASE_URL must not contain a query string, a fragment, or a "
    "duplicated path segment (//): the client appends /chat/completions to the "
    "base, so such a base can only produce a malformed request URL"
)


def normalise_cloud_base_url(value: str) -> str:
    """Strip surrounding whitespace and trailing slashes from a base URL.

    Locked intent 18: whitespace and a trailing slash are normalisation, not
    errors. A query string, a fragment or an empty path segment (``//``) is an
    error, because the client appends ``/chat/completions`` and the composed URL
    would be malformed. Raises ``ValueError`` with the shared message; callers
    translate it (``Settings`` through pydantic, ``CloudGenerator`` to
    ``GeneratorNotConfiguredError``).
    """
    candidate = value.strip().rstrip("/")
    parts = urlsplit(candidate)
    if parts.query or parts.fragment or "//" in parts.path:
        raise ValueError(UNFORMABLE_CLOUD_BASE_URL)
    return candidate


__all__ = [
    "CLOUD_PROVIDER_BASE_URLS",
    "DEFAULT_CLOUD_BASE_URL",
    "UNFORMABLE_CLOUD_BASE_URL",
    "normalise_cloud_base_url",
]
