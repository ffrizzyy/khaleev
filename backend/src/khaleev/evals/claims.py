"""Split a generated answer into sentence-level claims (T15, SPEC "Metric definitions").

SPEC defines one claim per sentence that asserts content, and faithfulness is
the fraction of those claims an entailment scorer judges supported. The splitter
is therefore part of the metric contract and has to be stable: the same answer
must always produce the same claims, or the denominator moves between runs.

Rules encoded here:

* Every sentence of prose is one claim. Sentences end at ``.``, ``!`` or ``?``
  followed by whitespace or the end of the text.
* Abbreviations (``Dr.``, ``e.g.``, ``i.e.``, ``etc.``, ``Fig.``, ``U.S.``, an
  initial such as ``J.``) and decimal points do not end a sentence.
* A newline ends a claim when the preceding line already ended a sentence;
  otherwise it is a soft wrap and the lines are joined, because a hard-wrapped
  prose line is still one sentence.
* Bullet and numbered list markers are stripped, and each item is its own claim.
* Page-citation tags (``[page 4]``, ``[4]``, ``(p. 4)``) are removed: they
  attribute a claim to a source, they are not part of what the claim asserts.
* Empty, whitespace-only and punctuation-only fragments are dropped, so an empty
  answer yields ``[]`` and the metric scores ``0.0`` (SPEC "Metric definitions").

Only the standard library is used: splitting loads no model and opens no socket
(SPEC AC8, Locked intent #12).
"""

from __future__ import annotations

import re

#: A bullet or numbered list marker at the start of a line.
_BULLET_RE = re.compile(r"^\(?\d{1,3}[.)]\s+|^[-*+•‣◦–—]\s+")

#: A line that already ends a sentence, so the next line starts a new claim.
_TERMINAL_RE = re.compile(r"[.!?][\"'\u201d\u2019)\]]*$")

#: One page number or a comma/and/range list of them, as citations emit them.
_NUMBER_LIST = r"\d+(?:\s*(?:,|;|&|\band\b|[-–—])\s*\d+)*"

#: ``[page 4]``, ``[pages 3, 5]``, ``[p. 4]``, ``[4]``, ``(page 4)``, ``(p. 4)``.
_PAGE_TAG_RE = re.compile(
    rf"\[\s*(?:(?:pages?|pp?\.?)\s*)?{_NUMBER_LIST}\s*\]"
    rf"|\(\s*(?:pages?|pp?\.?)\s*{_NUMBER_LIST}\s*\)",
    re.IGNORECASE,
)

#: Tokens whose trailing period does not end a sentence.
_ABBREVIATIONS = frozenset(
    {
        "mr",
        "mrs",
        "ms",
        "dr",
        "prof",
        "sr",
        "jr",
        "st",
        "vs",
        "etc",
        "e.g",
        "i.e",
        "eg",
        "ie",
        "fig",
        "figs",
        "no",
        "nos",
        "approx",
        "cf",
        "al",
        "inc",
        "ltd",
        "co",
        "corp",
        "dept",
        "u.s",
        "u.k",
        "a.m",
        "p.m",
        "pp",
        "p",
        "vol",
        "ch",
        "sec",
        "art",
        "ed",
        "eds",
        "ca",
        "est",
        "min",
        "max",
    }
)


def _ends_sentence(line: str) -> bool:
    """True when ``line`` already ends with sentence punctuation."""
    return _TERMINAL_RE.search(line) is not None


def _strip_bullet(line: str) -> str | None:
    """The text after a list marker, or ``None`` when the line is not an item."""
    match = _BULLET_RE.match(line)
    if match is None:
        return None
    return line[match.end() :].strip()


def _segments(answer: str) -> list[str]:
    """Group the answer into prose segments before sentence splitting.

    A blank line or a list item always starts a new segment. A newline inside a
    paragraph is a soft wrap and is joined with a space, unless the previous line
    already ended a sentence.
    """
    segments: list[str] = []
    current: list[str] = []

    def flush() -> None:
        if current:
            segments.append(" ".join(current))
            current.clear()

    normalised = answer.replace("\r\n", "\n").replace("\r", "\n")
    for raw_line in normalised.split("\n"):
        line = " ".join(raw_line.split())
        if not line:
            flush()
            continue

        item = _strip_bullet(line)
        if item is not None:
            flush()
            if item:
                current.append(item)
            continue

        if current and _ends_sentence(current[-1]):
            flush()
        current.append(line)

    flush()
    return segments


def _is_sentence_end(text: str, punct_start: int, punct_end: int) -> bool:
    """True when the punctuation run ``text[punct_start:punct_end + 1]`` ends one."""
    rest = text[punct_end + 1 :]
    if not rest:
        return True

    # A closing quote/bracket may sit between the punctuation and the space.
    following = rest.lstrip("\"'\u201d\u2019)]}")
    if not following:
        return True
    if not following[0].isspace():
        return False

    if text[punct_start] != ".":
        return True

    before = text[:punct_start]
    after = following.lstrip()
    if before and before[-1].isdigit() and after[:1].isdigit():
        return False  # a decimal number, e.g. 3.5

    word = re.search(r"([A-Za-z][A-Za-z.]*)$", text[: punct_end + 1])
    if word is not None and word.group(1).lower().rstrip(".") in _ABBREVIATIONS:
        return False  # Dr., e.g., U.S., etc.

    if re.search(r"(?:^|[\s\"'(])[A-Za-z]\.$", text[: punct_end + 1]):
        return False  # an initial, e.g. "J. Smith"

    return True


def _split_sentences(text: str) -> list[str]:
    """Split one prose segment at sentence-ending punctuation."""
    sentences: list[str] = []
    start = 0
    index = 0
    length = len(text)

    while index < length:
        character = text[index]
        if character not in ".!?":
            index += 1
            continue

        end = index
        while end + 1 < length and text[end + 1] in ".!?":
            end += 1

        if _is_sentence_end(text, index, end):
            sentence = text[start : end + 1].strip()
            if sentence:
                sentences.append(sentence)
            start = end + 1

        index = end + 1

    tail = text[start:].strip()
    if tail:
        sentences.append(tail)
    return sentences


def _clean_claim(raw: str) -> str:
    """Remove page tags, collapse whitespace and fix spacing before punctuation."""
    text = _PAGE_TAG_RE.sub(" ", raw)
    text = " ".join(text.split())
    text = re.sub(r"\s+([,.;:!?])", r"\1", text)
    return text.strip(" \t•‣◦*")


def split_claims(answer: str) -> list[str]:
    """Return every sentence-level claim in ``answer``, in order.

    Deterministic and side-effect free. An empty or whitespace-only answer, and
    an answer that only contains citation/punctuation fragments, returns ``[]``;
    the faithfulness metric then scores the answer ``0.0`` rather than raising
    (SPEC "Metric definitions").
    """
    if not answer or not answer.strip():
        return []

    claims: list[str] = []
    for segment in _segments(answer):
        for sentence in _split_sentences(segment):
            claim = _clean_claim(sentence)
            if claim and any(character.isalnum() for character in claim):
                claims.append(claim)
    return claims


__all__ = ["split_claims"]
