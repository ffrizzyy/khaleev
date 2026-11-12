"""A small synchronous HTTP client that drives the ASGI app in-process.

``fastapi.testclient.TestClient`` drives the app through an anyio blocking
portal, which creates a *new* asyncio event loop inside the test. On Windows that
loop's self-pipe is a loopback socketpair, so starting the loop calls
``socket.connect`` — and the suite-wide socket guard (SPEC AC8, Locked intent
#12) blocks it. That is a false positive: the connect belongs to the event loop
bootstrapping, not to the application talking to a network.

This client keeps the guard exactly as strict as it is and sidesteps the false
positive: the event loop is created when the module is imported (before any test
fixture patches the socket module), and each request is driven with
``run_until_complete`` over ``httpx.ASGITransport``. Requests go straight into the
application object, so no socket is opened and no packet leaves the process.
"""

from __future__ import annotations

import asyncio
from typing import Any

import httpx
from fastapi import FastAPI

#: Created at import time, before the per-test socket guard exists.
_LOOP = asyncio.new_event_loop()

BASE_URL = "http://khaleev.test"


class ApiClient:
    """Minimal ``get``/``post``/``put``/``delete`` surface over the ASGI app."""

    def __init__(self, app: FastAPI) -> None:
        self._client = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url=BASE_URL,
        )
        self._closed = False

    def request(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        """Send one request and return the fully read response."""
        return _LOOP.run_until_complete(self._client.request(method, url, **kwargs))

    def get(self, url: str, **kwargs: Any) -> httpx.Response:
        return self.request("GET", url, **kwargs)

    def post(self, url: str, **kwargs: Any) -> httpx.Response:
        return self.request("POST", url, **kwargs)

    def put(self, url: str, **kwargs: Any) -> httpx.Response:
        return self.request("PUT", url, **kwargs)

    def delete(self, url: str, **kwargs: Any) -> httpx.Response:
        return self.request("DELETE", url, **kwargs)

    def close(self) -> None:
        """Close the underlying async client once."""
        if not self._closed:
            _LOOP.run_until_complete(self._client.aclose())
            self._closed = True

    def __enter__(self) -> ApiClient:
        return self

    def __exit__(self, *_exc_info: object) -> None:
        self.close()


__all__ = ["ApiClient"]
