"""The local Ollama answer generator (T08, the default).

Ollama is the zero-key default (Locked intent #10, #11, AC3), so this client is
deliberately small: one POST to ``{base_url}/api/generate`` with ``stream`` off,
one response field read back. Every failure is turned into
:class:`~khaleev.generation.base.GenerationError` with a message a user can act
on — "is Ollama running?" beats a raw ``ConnectError`` traceback.

The HTTP client is injectable. Tests pass an ``httpx.Client`` built on
``httpx.MockTransport``, so the real request/response code runs with no socket
(Locked intent #12, AC8).
"""

from __future__ import annotations

import httpx

from khaleev.generation.base import GenerationError

#: Default per-request timeout. Local models can be slow on first token.
DEFAULT_TIMEOUT_SECONDS = 120.0


class OllamaGenerator:
    """Answer generation through a local Ollama server."""

    def __init__(
        self,
        base_url: str,
        model: str,
        *,
        client: httpx.Client | None = None,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
    ) -> None:
        if not base_url.strip():
            raise ValueError("ollama base_url must not be empty")
        if not model.strip():
            raise ValueError("ollama model must not be empty")
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout
        self._client = client

    @property
    def generate_url(self) -> str:
        return f"{self.base_url}/api/generate"

    def generate(self, prompt: str) -> str:
        """Return Ollama's answer text for ``prompt``.

        Raises :class:`GenerationError` when Ollama is unreachable, returns a
        non-200 status, sends a payload without usable text, or answers blank.
        """
        url = self.generate_url
        payload = {"model": self.model, "prompt": prompt, "stream": False}
        response = self._post(url, payload)

        if response.status_code != httpx.codes.OK:
            detail = response.text.strip()[:500] or "(empty response body)"
            raise GenerationError(
                f"Ollama at {url} returned HTTP {response.status_code}: {detail}. "
                f"Check that the model '{self.model}' is available "
                f"(`ollama pull {self.model}`) and retry."
            )

        try:
            data = response.json()
        except ValueError as exc:
            raise GenerationError(
                f"Ollama at {url} returned a response that is not JSON. "
                "Check the Ollama server logs and retry."
            ) from exc

        text = data.get("response") if isinstance(data, dict) else None
        if not isinstance(text, str) or not text.strip():
            raise GenerationError(
                f"Ollama at {url} returned no answer text for model '{self.model}'. "
                "Check that the model is pulled and the prompt is valid."
            )
        return text

    def _post(self, url: str, payload: dict[str, object]) -> httpx.Response:
        """POST with the injected client, or a short-lived one we must close."""
        if self._client is not None:
            client = self._client
            owned = False
        else:
            client = httpx.Client(timeout=self.timeout)
            owned = True

        try:
            return client.post(url, json=payload)
        except httpx.HTTPError as exc:
            raise GenerationError(
                f"could not reach Ollama at {url}: {exc}. "
                "Is Ollama running? Start it with `ollama serve` and retry."
            ) from exc
        finally:
            if owned:
                client.close()


__all__ = ["DEFAULT_TIMEOUT_SECONDS", "OllamaGenerator"]
