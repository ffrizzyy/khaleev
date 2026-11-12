"""The generator boundary: one tiny protocol the whole app depends on.

Everything that needs an answer (the ask endpoint, the eval runner) talks to
``Generator`` and never to Ollama or a cloud SDK. That boundary is what lets the
entire test suite run offline with ``FakeGenerator`` (Locked intent #12, AC8) and
what keeps the zero-key local path the default (Locked intent #10, #11).

Failures are reported as ``GenerationError`` (or its narrower subclass
``GeneratorNotConfiguredError``) so callers can turn them into a clear message
instead of leaking an ``httpx`` traceback. An empty answer is a failure too: a
blank string would otherwise flow into the citation path and ship as an answer
with no citations (Locked intent #4).
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol, runtime_checkable


class GenerationError(RuntimeError):
    """A generator could not produce an answer; the message must be actionable."""


class GeneratorNotConfiguredError(GenerationError):
    """The selected generator is missing configuration (for example, no key)."""


@runtime_checkable
class Generator(Protocol):
    """What the rest of the app needs from an answer generator."""

    def generate(self, prompt: str) -> str:
        """Return the model's answer text for ``prompt``.

        Implementations raise :class:`GenerationError` on connection failure,
        a non-200 response, a malformed payload, or an empty answer.
        """
        ...


class FakeGenerator:
    """A deterministic stand-in used by every test that needs an answer.

    ``responses`` is consumed in order; the last response repeats, so a single
    scripted answer serves an ask plus several eval entries. ``prompts`` records
    what the app actually sent, which lets tests assert the retrieved chunks
    reached the model. No model is loaded and no socket is opened.
    """

    def __init__(
        self,
        responses: str | Sequence[str] | None = None,
        *,
        default_response: str = "The retrieved excerpts support this answer. [page 1]",
    ) -> None:
        if responses is None:
            scripted: list[str] = []
        elif isinstance(responses, str):
            scripted = [responses]
        else:
            scripted = list(responses)
        self._responses = scripted
        self.default_response = default_response
        self.prompts: list[str] = []

    def generate(self, prompt: str) -> str:
        self.prompts.append(prompt)
        if not self._responses:
            return self.default_response
        if len(self._responses) > 1:
            return self._responses.pop(0)
        return self._responses[0]


__all__ = [
    "FakeGenerator",
    "GenerationError",
    "Generator",
    "GeneratorNotConfiguredError",
]
