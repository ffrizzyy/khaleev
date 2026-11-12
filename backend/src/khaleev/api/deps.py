"""Dependency wiring for the API: one container, a few tiny providers.

The container lives on ``app.state`` (built by ``khaleev.app.create_app``), so a
test injects a fake embedder or generator by constructing the app with it — no
monkeypatching, no real model, no socket. Everything is created lazily:

* the SQLite engine is opened on first use, so importing the app never creates a
  data directory;
* the embedder and the generator are only built when a route actually needs them,
  so ``GET /api/config`` and the document list never load a model (Locked intent
  #12);
* an injected dependency always wins, and a config update never discards it, so a
  test that injects fakes keeps fakes for the whole test.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from khaleev import db
from khaleev.config import Settings
from khaleev.generation import Generator, build_generator
from khaleev.ingest.embedding import Embedder, SentenceTransformerEmbedder


class AppServices:
    """Process-lifetime dependencies behind one application instance."""

    def __init__(
        self,
        settings: Settings,
        *,
        embedder: Embedder | None = None,
        generator: Generator | None = None,
    ) -> None:
        self.settings = settings
        self._embedder = embedder
        self._generator = generator
        self._injected_embedder = embedder is not None
        self._injected_generator = generator is not None
        self._engine: Engine | None = None

    @property
    def engine(self) -> Engine:
        """The engine for the configured data directory, opened on first use."""
        if self._engine is None:
            self._engine = db.create_engine(self.settings.data_dir)
        return self._engine

    @contextmanager
    def session(self) -> Iterator[Session]:
        """A request-scoped session, closed when the request ends."""
        with db.create_session_factory(self.engine)() as session:
            yield session

    @property
    def embedder(self) -> Embedder:
        """The configured embedder, loaded only when something embeds."""
        if self._embedder is None:
            self._embedder = SentenceTransformerEmbedder(self.settings.embedder_id)
        return self._embedder

    @property
    def generator(self) -> Generator:
        """The selected answer generator (Ollama by default, zero keys needed)."""
        if self._generator is None:
            self._generator = build_generator(self.settings)
        return self._generator

    def update_config(
        self,
        *,
        k: int | None = None,
        embedder: str | None = None,
        generator: str | None = None,
    ) -> None:
        """Apply a config update for the rest of the process lifetime.

        Changing the embedder or the generator drops the cached instance so the
        next call rebuilds it from the new setting — unless the dependency was
        injected (tests), in which case the injected instance keeps winning.
        """
        if k is not None:
            self.settings.retrieval_k = k
        if embedder is not None and embedder != self.settings.embedder_id:
            self.settings.embedder_id = embedder
            if not self._injected_embedder:
                self._embedder = None
        if generator is not None and generator != self.settings.generator:
            self.settings.generator = generator
            if not self._injected_generator:
                self._generator = None

    def dispose(self) -> None:
        """Close the engine's pooled connections (used when an app shuts down)."""
        if self._engine is not None:
            self._engine.dispose()
            self._engine = None


def get_services(request: Request) -> AppServices:
    """The container ``create_app`` attached to this application."""
    return request.app.state.services


ServicesDep = Annotated[AppServices, Depends(get_services)]


def get_session(services: ServicesDep) -> Iterator[Session]:
    """One database session per request."""
    with services.session() as session:
        yield session


SessionDep = Annotated[Session, Depends(get_session)]


def get_embedder(services: ServicesDep) -> Embedder:
    """The injected or configured embedder, built on first use."""
    return services.embedder


EmbedderDep = Annotated[Embedder, Depends(get_embedder)]


def get_generator(services: ServicesDep) -> Generator:
    """The injected or configured generator, built on first use."""
    return services.generator


GeneratorDep = Annotated[Generator, Depends(get_generator)]


__all__ = [
    "AppServices",
    "EmbedderDep",
    "GeneratorDep",
    "ServicesDep",
    "SessionDep",
    "get_embedder",
    "get_generator",
    "get_services",
    "get_session",
]
