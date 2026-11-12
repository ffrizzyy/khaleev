"""The eval metrics (T14-T15): pure scoring over constructed inputs.

``rounding`` is the single half-up-to-four-decimals rule every metric obeys at
persistence and display; ``hit_rate`` is the retrieval hit rate @ k. Both import
only the standard library, so nothing in this package loads a model, opens a
database or reaches the network (SPEC AC8, Locked intent #12). The answer
faithfulness metric lands here in T15 and reuses the same rounding helper.
"""

from __future__ import annotations

from khaleev.evals.metrics.hit_rate import (
    DEFAULT_K,
    HitRateEntry,
    MetricUndefinedError,
    PageTagged,
    entry_hit,
    hit_rate,
)
from khaleev.evals.metrics.rounding import METRIC_PLACES, format_metric, round_half_up

__all__ = [
    "DEFAULT_K",
    "METRIC_PLACES",
    "HitRateEntry",
    "MetricUndefinedError",
    "PageTagged",
    "entry_hit",
    "format_metric",
    "hit_rate",
    "round_half_up",
]
