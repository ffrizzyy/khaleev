"""The Khaleev FastAPI application and its factory (T09).

``create_app`` is the only way the app is built, and it takes every model-backed
dependency as an argument (``settings``, ``embedder``, ``generator``). Tests build
the real application with fakes, so the suite exercises the real routes and the
real service layer without loading a model or opening a socket (Locked intent
#12, AC8). Production calls ``create_app()`` with no arguments: settings come from
the environment and the real embedder/generator are built lazily on first use.

Domain errors are mapped here, once, so no route has to guess a status code and
no caller ever receives a traceback:

* ``NotAPdfError`` -> 400 (the upload is not a PDF at all);
* ``CorruptPdfError`` -> 422 (it is a PDF, but unreadable);
* ``DocumentNotFoundError`` / ``PageOutOfRangeError`` -> 404;
* ``GoldenSetNotFoundError`` -> 404 (the document has no golden file) and
  ``GoldenSetValidationError`` -> 422 (it exists but is empty or invalid);
* ``MetricUndefinedError`` -> 422 (an empty golden set makes the metric undefined);
* ``EvalRunNotFoundError`` -> 404 (no run with that id);
* ``NoContextError`` -> 422 (the document has no indexed text to answer from);
* ``GenerationError`` -> 503 (the generator is unreachable or unconfigured),
  with the actionable message the client came up with.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

from khaleev.api.deps import AppServices
from khaleev.api.routes import api_router
from khaleev.config import Settings
from khaleev.evals.golden import GoldenSetNotFoundError, GoldenSetValidationError
from khaleev.evals.metrics.hit_rate import MetricUndefinedError
from khaleev.evals.scorer import EntailmentScorer
from khaleev.generation import GenerationError, Generator
from khaleev.ingest.embedding import Embedder
from khaleev.ingest.pdf import CorruptPdfError, NotAPdfError
from khaleev.services.documents import DocumentNotFoundError, PageOutOfRangeError
from khaleev.services.evals import EvalRunNotFoundError
from khaleev.services.qa import NoContextError

APP_TITLE = "Khaleev"
APP_VERSION = "0.1.0"

ExceptionHandler = Callable[[Request, Exception], JSONResponse]


def _json_error(status_code: int) -> ExceptionHandler:
    """A handler that answers ``{"detail": str(exc)}`` with one status code."""

    def handler(_request: Request, exc: Exception) -> JSONResponse:
        return JSONResponse(status_code=status_code, content={"detail": str(exc)})

    return handler


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Release the lazily opened database engine when the app shuts down."""
    try:
        yield
    finally:
        app.state.services.dispose()


def create_app(
    settings: Settings | None = None,
    *,
    embedder: Embedder | None = None,
    generator: Generator | None = None,
    scorer: EntailmentScorer | None = None,
) -> FastAPI:
    """Build the application, injecting fakes in tests and nothing in production.

    ``settings`` defaults to ``Settings()`` (environment or ``.env``) and the
    embedder/generator/scorer are built only when a route first needs them, so
    importing this module never creates a directory, loads a model, or opens a
    socket.
    """
    application = FastAPI(title=APP_TITLE, version=APP_VERSION, lifespan=_lifespan)
    application.state.services = AppServices(
        settings if settings is not None else Settings(),
        embedder=embedder,
        generator=generator,
        scorer=scorer,
    )
    application.include_router(api_router)

    application.add_exception_handler(NotAPdfError, _json_error(status.HTTP_400_BAD_REQUEST))
    application.add_exception_handler(
        CorruptPdfError, _json_error(status.HTTP_422_UNPROCESSABLE_CONTENT)
    )
    application.add_exception_handler(
        DocumentNotFoundError, _json_error(status.HTTP_404_NOT_FOUND)
    )
    application.add_exception_handler(
        PageOutOfRangeError, _json_error(status.HTTP_404_NOT_FOUND)
    )
    application.add_exception_handler(
        GoldenSetNotFoundError, _json_error(status.HTTP_404_NOT_FOUND)
    )
    application.add_exception_handler(
        GoldenSetValidationError, _json_error(status.HTTP_422_UNPROCESSABLE_CONTENT)
    )
    application.add_exception_handler(
        MetricUndefinedError, _json_error(status.HTTP_422_UNPROCESSABLE_CONTENT)
    )
    application.add_exception_handler(
        EvalRunNotFoundError, _json_error(status.HTTP_404_NOT_FOUND)
    )
    application.add_exception_handler(
        NoContextError, _json_error(status.HTTP_422_UNPROCESSABLE_CONTENT)
    )
    application.add_exception_handler(
        GenerationError, _json_error(status.HTTP_503_SERVICE_UNAVAILABLE)
    )
    return application


app = create_app()

__all__ = ["app", "create_app"]
