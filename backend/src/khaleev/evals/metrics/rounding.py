"""Half-up rounding for metric values (T14, SPEC "Metric definitions").

SPEC fixes a single rounding rule for both metrics: four decimal places, half-up,
at persistence and display. Python's built-in ``round`` is half-even (banker's
rounding), so ``round(0.03125, 4)`` is ``0.0312`` while this module's
``round_half_up(0.03125)`` is ``0.0313``. Ties must carry upward, so everything
goes through :class:`decimal.Decimal` with ``ROUND_HALF_UP``.

Floats are converted with ``Decimal(repr(value))`` rather than
``Decimal(value)``: the former reads the shortest decimal that round-trips to the
float (what the programmer wrote, e.g. ``0.03125``), while the latter expands the
binary fraction and can turn an intended tie into a near-tie. ``Decimal`` and
``str`` inputs are taken exactly as given, which lets callers hand over an exact
ratio without any float representation in the way.

Only the standard library is imported, so the module is safe in tests that load
no model and touch no network (SPEC AC8, Locked intent #12).
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

#: Decimals kept for every metric persisted or displayed (SPEC "Metric definitions").
METRIC_PLACES = 4

Number = Decimal | float | int | str


def _as_decimal(value: Number) -> Decimal:
    """Return ``value`` as an exact Decimal, rejecting non-finite numbers."""
    if isinstance(value, Decimal):
        decimal = value
    elif isinstance(value, str):
        decimal = Decimal(value)
    elif isinstance(value, int):
        decimal = Decimal(value)
    elif isinstance(value, float):
        decimal = Decimal(repr(value))
    else:
        raise TypeError(f"cannot round {value!r}: expected Decimal, float, int or str")

    if not decimal.is_finite():
        raise ValueError(f"cannot round {value!r}: metric values must be finite")
    return decimal


def _quantize(value: Number, places: int) -> Decimal:
    """Round ``value`` to ``places`` decimals, half-up, and return the Decimal."""
    if isinstance(places, bool) or not isinstance(places, int):
        raise TypeError(f"places must be an integer, got {places!r}")
    if places < 0:
        raise ValueError(f"places must be >= 0, got {places}")

    try:
        decimal = _as_decimal(value)
    except InvalidOperation as exc:
        raise ValueError(f"cannot round {value!r}: not a decimal number") from exc

    return decimal.quantize(Decimal(1).scaleb(-places), rounding=ROUND_HALF_UP)


def round_half_up(value: Number, places: int = METRIC_PLACES) -> float:
    """Round ``value`` to ``places`` decimals with half-up ties and return a float.

    ``0.66666...`` -> ``0.6667`` and ``0.03125`` -> ``0.0313`` at the default four
    decimal places. This is the value persisted in ``eval_runs`` and
    ``eval_run_entries`` (SPEC "Metric definitions").
    """
    return float(_quantize(value, places))


def format_metric(value: Number, places: int = METRIC_PLACES) -> str:
    """Format a metric for display, padded to exactly ``places`` decimals.

    ``0.7`` -> ``"0.7000"`` and ``0.03125`` -> ``"0.0313"``: the display form of
    the same half-up rule, so a rounded-to-``0.7`` metric never renders as
    ``"0.7"`` and loses its precision.
    """
    return format(_quantize(value, places), "f")


__all__ = ["METRIC_PLACES", "format_metric", "round_half_up"]
