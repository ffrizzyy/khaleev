"""The optional cloud generator (T08).

This exists so a user with a cloud key can choose a stronger model, and for no
other reason. It is never the default, it is only built when
``KHALEEV_GENERATOR=cloud`` and both a key and a model are configured, and the
whole app works with no key at all (Locked intent #10, #11, AC3).

The wire format is the widely supported OpenAI-compatible chat-completions
shape, which is what lets a free-tier provider be used through a preset. The
endpoint is injectable for exactly the same reason as the Ollama client: tests
use ``httpx.MockTransport`` and open no socket (Locked intent #12, AC8).

``base_url`` is normalised here as well as in ``Settings`` (whitespace and
trailing slashes stripped; query strings, fragments and ``//`` path segments
rejected) so a programmatic caller cannot bypass the settings validation.
"""

from __future__ import annotations

import httpx

from khaleev.cloud_providers import DEFAULT_CLOUD_BASE_URL, normalise_cloud_base_url
from khaleev.generation.base import GenerationError, GeneratorNotConfiguredError

DEFAULT_TIMEOUT_SECONDS = 120.0


class CloudGenerator:
    """Answer generation through an OpenAI-compatible chat-completions API."""

    def __init__(
        self,
        api_key: str,
        model: str,
        *,
        base_url: str = DEFAULT_CLOUD_BASE_URL,
        client: httpx.Client | None = None,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
    ) -> None:
        if not api_key.strip():
            raise GeneratorNotConfiguredError(
                "cloud generation needs KHALEEV_CLOUD_API_KEY; set it or switch "
                "KHALEEV_GENERATOR back to 'ollama'"
            )
        if not model.strip():
            raise GeneratorNotConfiguredError(
                "cloud generation needs KHALEEV_CLOUD_MODEL; set it or switch "
                "KHALEEV_GENERATOR back to 'ollama'"
            )
        try:
            resolved_base_url = normalise_cloud_base_url(base_url)
        except ValueError as exc:
            raise GeneratorNotConfiguredError(str(exc)) from None
        self.api_key = api_key
        self.model = model
        self.base_url = resolved_base_url
        self.timeout = timeout
        self._client = client

    @property
    def completions_url(self) -> str:
        return f"{self.base_url}/chat/completions"

    def generate(self, prompt: str) -> str:
        """Return the cloud model's answer text for ``prompt``."""
        url = self.completions_url
        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
        }
        headers = {"Authorization": f"Bearer {self.api_key}"}
        response = self._post(url, payload, headers)

        if response.status_code != httpx.codes.OK:
            detail = response.text.strip()[:500] or "(empty response body)"
            raise GenerationError(
                f"cloud generator request to {url} failed with HTTP "
                f"{response.status_code}: {detail}. Check KHALEEV_CLOUD_API_KEY "
                "and KHALEEV_CLOUD_MODEL, or switch back to the local Ollama "
                "generator."
            )

        try:
            data = response.json()
        except ValueError as exc:
            raise GenerationError(
                f"cloud generator at {url} returned a response that is not JSON. "
                "Check the configured cloud endpoint and retry."
            ) from exc

        text = self._answer_text(data)
        if text is None or not text.strip():
            raise GenerationError(
                f"cloud generator at {url} returned no answer text for model "
                f"'{self.model}'. Check the configured cloud endpoint and model."
            )
        return text

    @staticmethod
    def _answer_text(data: object) -> str | None:
        """Read ``choices[0].message.content`` defensively from a payload."""
        if not isinstance(data, dict):
            return None
        choices = data.get("choices")
        if not isinstance(choices, list) or not choices:
            return None
        first = choices[0]
        if not isinstance(first, dict):
            return None
        message = first.get("message")
        if not isinstance(message, dict):
            return None
        content = message.get("content")
        return content if isinstance(content, str) else None

    def _post(
        self,
        url: str,
        payload: dict[str, object],
        headers: dict[str, str],
    ) -> httpx.Response:
        """POST with the injected client, or a short-lived one we must close."""
        if self._client is not None:
            client = self._client
            owned = False
        else:
            client = httpx.Client(timeout=self.timeout)
            owned = True

        try:
            return client.post(url, json=payload, headers=headers)
        except httpx.HTTPError as exc:
            raise GenerationError(
                f"could not reach the cloud generator at {url}: {exc}. "
                "Check your network connection and the configured cloud endpoint, "
                "or switch back to the local Ollama generator."
            ) from exc
        finally:
            if owned:
                client.close()


__all__ = ["DEFAULT_CLOUD_BASE_URL", "CloudGenerator"]
