"""Unit tests for the half-up metric rounding helper (T14, SPEC "Metric definitions").

SPEC fixes one rounding rule for every metric: four decimal places, half-up, at
persistence and display. Python's built-in ``round`` is half-even (banker's
rounding), so each test here pairs the helper with the built-in and asserts the
two disagree on a tie - the only way to prove the rule is actually half-up.

No model is loaded and no socket is opened here (SPEC AC8, Locked intent #12).
"""

from __future__ import annotations

from decimal import ROUND_HALF_EVEN, Decimal

import pytest

from khaleev.evals.metrics.rounding import METRIC_PLACES, format_metric, round_half_up


def test_metric_precision_is_four_decimal_places() -> None:
    assert METRIC_PLACES == 4


def test_rounds_to_four_places_by_default() -> None:
    assert round_half_up(0.6666666666666666) == 0.6667
    assert round_half_up(0.75) == 0.75
    assert format_metric(round_half_up(0.75)) == "0.7500"


def test_returns_a_float_not_a_decimal() -> None:
    result = round_half_up(Decimal("0.5"))

    assert isinstance(result, float)
    assert result == 0.5


def test_half_up_where_bankers_rounding_rounds_to_even() -> None:
    # 0.03125 is exactly representable in binary and the digit before the cut is
    # even, so half-even drops the 5 and half-up carries it.
    assert round(0.03125, 4) == 0.0312
    assert round_half_up(0.03125) == 0.0313


def test_half_up_at_a_smaller_precision() -> None:
    # 0.125 -> 0.13 under half-up, 0.12 under banker's rounding.
    assert round(0.125, 2) == 0.12
    assert round_half_up(0.125, places=2) == 0.13


def test_half_up_with_a_five_in_the_fifth_decimal_place() -> None:
    # Passing a Decimal keeps the tie exact, so this is purely about the rule,
    # not about binary representation: HALF_EVEN would give 0.1234.
    tie = Decimal("0.12345")
    assert tie.quantize(Decimal("0.0001"), rounding=ROUND_HALF_EVEN) == Decimal("0.1234")

    assert round_half_up(tie) == 0.1235


def test_truncates_below_the_fifth_decimal_place() -> None:
    assert round_half_up(0.12344) == 0.1234
    assert round_half_up(0.12346) == 0.1235


def test_accepts_integers_and_strings() -> None:
    assert round_half_up(1) == 1.0
    assert round_half_up("0.66665") == 0.6667


def test_formats_a_metric_to_four_decimals() -> None:
    assert format_metric(0.7) == "0.7000"
    assert format_metric(0.6666666666666666) == "0.6667"
    assert format_metric(1.0) == "1.0000"
    assert format_metric(0.0) == "0.0000"


def test_negative_precision_is_rejected() -> None:
    with pytest.raises(ValueError, match="places must be >= 0"):
        round_half_up(0.5, places=-1)


def test_non_finite_values_are_rejected() -> None:
    with pytest.raises(ValueError, match="finite"):
        round_half_up(float("nan"))
    with pytest.raises(ValueError, match="finite"):
        round_half_up(float("inf"))
