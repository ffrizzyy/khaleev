"""Unit tests for the optional cloud generator and the generator factory (T08).

The cloud path is deliberately second-class: it is only reachable when the user
sets a key, it is never the default, and with no keys at all the factory must
still hand back a working Ollama generator (Locked intent #10, #11, AC3).
Requests are intercepted by ``httpx.MockTransport``; no socket is opened
(Locked intent #12, AC8).
"""

from __future__ import annotations

import json
from collections.abc import Callable

import httpx
import pytest

from khaleev.config import Settings
from khaleev.generation import build_generator
from khaleev.generation.base import GenerationError, GeneratorNotConfiguredError
from khaleev.generation.cloud import CloudGenerator
from khaleev.generation.ollama import OllamaGenerator

BASE_URL = "https://cloud.example.test/v1"
MODEL = "cloud-model-1"
API_KEY = "test-key"
Handler = Callable[[httpx.Request], httpx.Response]


def _client(handler: Handler) -> httpx.Client:
    """An httpx client whose transport never leaves the process."""
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_posts_to_chat_completions_with_bearer_key() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["authorization"] = request.headers.get("authorization")
        captured["payload"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={"choices": [{"message": {"role": "assistant", "content": "Answer [page 3]"}}]},
        )

    generator = CloudGenerator(API_KEY, MODEL, base_url=BASE_URL, client=_client(handler))

    answer = generator.generate("prompt")

    assert answer == "Answer [page 3]"
    assert captured["url"] == f"{BASE_URL}/chat/completions"
    assert captured["authorization"] == f"Bearer {API_KEY}"
    payload = captured["payload"]
    assert isinstance(payload, dict)
    assert payload["model"] == MODEL
    assert payload["messages"] == [{"role": "user", "content": "prompt"}]


def test_connection_failure_raises_actionable_domain_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    generator = CloudGenerator(API_KEY, MODEL, base_url=BASE_URL, client=_client(handler))

    with pytest.raises(GenerationError) as excinfo:
        generator.generate("prompt")

    assert "cloud" in str(excinfo.value).lower()


def test_non_200_response_names_the_key_to_check() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": {"message": "invalid key"}})

    generator = CloudGenerator(API_KEY, MODEL, base_url=BASE_URL, client=_client(handler))

    with pytest.raises(GenerationError) as excinfo:
        generator.generate("prompt")

    message = str(excinfo.value)
    assert "401" in message
    assert "CLOUD_API_KEY" in message


def test_malformed_payload_is_a_domain_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"choices": []})

    generator = CloudGenerator(API_KEY, MODEL, base_url=BASE_URL, client=_client(handler))

    with pytest.raises(GenerationError):
        generator.generate("prompt")


def test_empty_cloud_answer_is_an_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"choices": [{"message": {"content": "  "}}]})

    generator = CloudGenerator(API_KEY, MODEL, base_url=BASE_URL, client=_client(handler))

    with pytest.raises(GenerationError):
        generator.generate("prompt")


# ---------------------------------------------------------------------------
# Factory: local by default, cloud only with an explicit key
# ---------------------------------------------------------------------------


def test_default_settings_build_the_ollama_generator() -> None:
    generator = build_generator(Settings())

    assert isinstance(generator, OllamaGenerator)
    assert generator.base_url == "http://localhost:11434"
    assert generator.model == "llama3.1:8b"


def test_zero_key_settings_are_fully_usable() -> None:
    """No keys configured at all still yields a working local generator."""
    settings = Settings(cloud_api_key=None, cloud_model=None)

    generator = build_generator(settings)

    assert isinstance(generator, OllamaGenerator)


def test_a_cloud_key_alone_does_not_change_the_default_generator() -> None:
    """Cloud is never the default; the choice must be explicit."""
    settings = Settings(cloud_api_key=API_KEY, cloud_model=MODEL)

    generator = build_generator(settings)

    assert isinstance(generator, OllamaGenerator)


def test_selecting_cloud_without_a_key_is_a_clear_error() -> None:
    settings = Settings(generator="cloud", cloud_api_key=None, cloud_model=MODEL)

    with pytest.raises(GeneratorNotConfiguredError) as excinfo:
        build_generator(settings)

    assert "CLOUD_API_KEY" in str(excinfo.value)


def test_selecting_cloud_without_a_model_is_a_clear_error() -> None:
    settings = Settings(generator="cloud", cloud_api_key=API_KEY, cloud_model=None)

    with pytest.raises(GeneratorNotConfiguredError) as excinfo:
        build_generator(settings)

    assert "CLOUD_MODEL" in str(excinfo.value)


def test_selecting_cloud_with_key_and_model_builds_the_cloud_generator() -> None:
    settings = Settings(generator="cloud", cloud_api_key=API_KEY, cloud_model=MODEL)

    generator = build_generator(settings)

    assert isinstance(generator, CloudGenerator)
    assert generator.model == MODEL
