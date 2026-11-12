"""Config routes: read and update k, the embedder and the generator (T09).

The config is the live ``Settings`` object the app was built with, so an update
takes effect for the rest of the process lifetime — no restart, no database, and
no API key required (Locked intent #11). Generator choice is exposed even when a
cloud key is absent: selecting a generator and configuring a key are separate
concerns, and the ask route reports the missing key as an actionable 503.
"""

from __future__ import annotations

from fastapi import APIRouter

from khaleev.api import schemas
from khaleev.api.deps import ServicesDep
from khaleev.config import Settings

router = APIRouter(prefix="/config", tags=["config"])


def _as_config(settings: Settings) -> schemas.AppConfig:
    """The public view of the live settings."""
    return schemas.AppConfig(
        k=settings.retrieval_k,
        embedder=settings.embedder_id,
        generator=settings.generator,
        ollama_base_url=settings.ollama_base_url,
        ollama_model=settings.ollama_model,
    )


@router.get("", response_model=schemas.AppConfig)
def read_config(services: ServicesDep) -> schemas.AppConfig:
    """The current retrieval size, embedder id and generator choice."""
    return _as_config(services.settings)


@router.put("", response_model=schemas.AppConfig)
def update_config(update: schemas.ConfigUpdate, services: ServicesDep) -> schemas.AppConfig:
    """Apply a partial update; omitted fields keep their current value."""
    services.update_config(k=update.k, embedder=update.embedder, generator=update.generator)
    return _as_config(services.settings)
