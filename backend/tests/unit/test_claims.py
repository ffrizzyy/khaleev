"""Unit tests for answer claim splitting (T15, SPEC "Metric definitions").

SPEC decomposes a generated answer into claims, one per sentence that asserts
content, and the faithfulness denominator is the number of those claims. The
splitter is therefore part of the metric contract, not a formatting helper:
these tests pin how sentences, abbreviations, decimals, soft line wraps, blank
lines, page tags and bullet lists behave. Everything is a plain string, so no
model is loaded and no socket is opened (SPEC AC8, Locked intent #12).
"""

from __future__ import annotations

from khaleev.evals.claims import split_claims

# --- empty input -----------------------------------------------------------


def test_an_empty_answer_has_no_claims() -> None:
    assert split_claims("") == []


def test_a_whitespace_only_answer_has_no_claims() -> None:
    assert split_claims("   \n\t \n  ") == []


def test_punctuation_only_answers_have_no_claims() -> None:
    # Page tags and ellipses assert nothing once the tag is removed.
    assert split_claims("[page 4]. ...") == []


# --- sentence boundaries ---------------------------------------------------


def test_a_single_sentence_is_one_claim() -> None:
    assert split_claims("Late filings incur a flat 200 credit penalty.") == [
        "Late filings incur a flat 200 credit penalty."
    ]


def test_each_sentence_is_a_separate_claim() -> None:
    assert split_claims("Penalties apply. Interest accrues daily! File early?") == [
        "Penalties apply.",
        "Interest accrues daily!",
        "File early?",
    ]


def test_abbreviations_do_not_end_a_sentence() -> None:
    assert split_claims("Dr. Smith filed late. The penalty is 200 credits.") == [
        "Dr. Smith filed late.",
        "The penalty is 200 credits.",
    ]


def test_latin_abbreviations_stay_inside_their_claim() -> None:
    assert split_claims("Use e.g. form 200. The deadline is April 15.") == [
        "Use e.g. form 200.",
        "The deadline is April 15.",
    ]
    assert split_claims("Fees, i.e. late charges, apply. File early.") == [
        "Fees, i.e. late charges, apply.",
        "File early.",
    ]


def test_a_decimal_point_is_not_a_sentence_end() -> None:
    assert split_claims("The rate is 3.5 percent. It applies to late returns.") == [
        "The rate is 3.5 percent.",
        "It applies to late returns.",
    ]


def test_a_leading_negative_number_is_preserved() -> None:
    assert split_claims("-5 percent growth was reported.") == ["-5 percent growth was reported."]


def test_a_single_initial_is_not_a_sentence_end() -> None:
    assert split_claims("J. Smith filed late. The penalty is 200 credits.") == [
        "J. Smith filed late.",
        "The penalty is 200 credits.",
    ]


# --- newlines and lists ----------------------------------------------------


def test_newlines_separate_sentences() -> None:
    assert split_claims("Late filings incur a penalty.\nThe penalty is 200 credits.") == [
        "Late filings incur a penalty.",
        "The penalty is 200 credits.",
    ]


def test_a_soft_wrapped_line_does_not_split_a_claim() -> None:
    # A hard-wrapped prose line is still one sentence and must stay one claim.
    assert split_claims("Late filings incur a flat\n200 credit penalty.") == [
        "Late filings incur a flat 200 credit penalty."
    ]


def test_bullet_list_items_are_individual_claims() -> None:
    answer = (
        "- Late filings incur a 200 credit penalty.\n"
        "- Interest accrues daily.\n"
        "- Filing early avoids both."
    )

    assert split_claims(answer) == [
        "Late filings incur a 200 credit penalty.",
        "Interest accrues daily.",
        "Filing early avoids both.",
    ]


def test_numbered_list_markers_are_stripped() -> None:
    answer = "1. Late filings incur a penalty.\n2. The penalty is 200 credits."

    assert split_claims(answer) == [
        "Late filings incur a penalty.",
        "The penalty is 200 credits.",
    ]


def test_a_blank_line_between_claims_is_harmless() -> None:
    answer = "Late filings incur a penalty.\n\nThe penalty is 200 credits."

    assert split_claims(answer) == [
        "Late filings incur a penalty.",
        "The penalty is 200 credits.",
    ]


# --- page tags are not claim content --------------------------------------


def test_a_page_tag_is_not_part_of_the_claim() -> None:
    assert split_claims("Late filings incur a penalty [page 4].") == [
        "Late filings incur a penalty."
    ]


def test_a_bare_bracketed_page_number_is_stripped() -> None:
    assert split_claims("The penalty is 200 credits [4].") == ["The penalty is 200 credits."]


def test_a_parenthesised_page_tag_is_stripped() -> None:
    assert split_claims("The penalty is 200 credits (p. 4).") == ["The penalty is 200 credits."]


# --- determinism -----------------------------------------------------------


def test_splitting_is_deterministic() -> None:
    answer = "Dr. Smith filed late [page 4].\n- Interest accrues daily.\n- File early."

    first = split_claims(answer)
    second = split_claims(answer)

    assert first == second
    assert all(claim.strip() for claim in first)
