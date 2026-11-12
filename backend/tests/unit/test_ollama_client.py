"""Unit tests for the Ollama generator client (T08).

The client is exercised through ``httpx.MockTransport``, so the request URL,
payload and response handling are real code while no socket is ever opened
(Locked intent #12, AC8). The failures matter as much as the happy path: a user
whose Ollama is not running must get a clear, actionable domain error rather
than a raw traceback (Locked intent #10, AC3).
"""

from __future__ import annotations

import json
from collections.abc import Callable

import httpx
import pytest

from khaleev.generation.base import GenerationError
from khaleev.generation.ollama import OllamaGenerator

BASE_URL = "http://localhost:11434"
MODEL = "llama3.1:8b"

Handler = Callable[[httpx.Request], httpx.Response]


def _client(handler: Handler) -> httpx.Client:
    """An httpx client whose transport never leaves the process."""
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_posts_the_prompt_to_api_generate() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["payload"] = json.loads(request.content)
        return httpx.Response(200, json={"response": "Late filings incur a penalty. [page 3]"})

    generator = OllamaGenerator(BASE_URL, MODEL, client=_client(handler))

    answer = generator.generate("Answer this question from the excerpts.")

    assert answer == "Late filings incur a penalty. [page 3]"
    assert captured["url"] == f"{BASE_URL}/api/generate"
    assert captured["payload"] == {
        "model": MODEL,
        "prompt": "Answer this question from the excerpts.",
        "stream": False,
    }


def test_trailing_slash_in_base_url_is_normalised() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == f"{BASE_URL}/api/generate"
        return httpx.Response(200, json={"response": "ok"})

    generator = OllamaGenerator(f"{BASE_URL}/", MODEL, client=_client(handler))

    assert generator.generate("prompt") == "ok"


def test_connection_failure_raises_actionable_domain_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    generator = OllamaGenerator(BASE_URL, MODEL, client=_client(handler))

    with pytest.raises(GenerationError) as excinfo:
        generator.generate("prompt")

    message = str(excinfo.value)
    assert "Ollama" in message
    assert "running" in message.lower()
    assert BASE_URL in message


def test_non_200_response_raises_actionable_domain_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="model not found")

    generator = OllamaGenerator(BASE_URL, MODEL, client=_client(handler))

    with pytest.raises(GenerationError) as excinfo:
        generator.generate("prompt")

    message = str(excinfo.value)
    assert "500" in message
    assert "model not found" in message


def test_malformed_json_is_a_domain_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="not json")

    generator = OllamaGenerator(BASE_URL, MODEL, client=_client(handler))

    with pytest.raises(GenerationError):
        generator.generate("prompt")


def test_missing_response_field_is_a_domain_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"done": True})

    generator = OllamaGenerator(BASE_URL, MODEL, client=_client(handler))

    with pytest.raises(GenerationError):
        generator.generate("prompt")


def test_empty_model_response_is_an_error_not_an_answer() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"response": "   "})

    generator = OllamaGenerator(BASE_URL, MODEL, client=_client(handler))

    with pytest.raises(GenerationError):
        generator.generate("prompt")


def test_generator_is_constructible_without_network() -> None:
    """Constructing the default generator must not connect to anything."""
    generator = OllamaGenerator(BASE_URL, MODEL)

    assert generator.base_url == BASE_URL
    assert generator.model == MODEL
