"""Load, validate and persist a document's golden set (T13, F4, AC4, AC10).

A golden set is a human-editable JSON file at
``<data_dir>/golden/<document_id>.json`` holding a list of entries::

    [{"question": "...", "expected_answer": "...", "expected_pages": [4]}]

The file is the source of truth; the ``golden_sets`` row is a derived copy so the
rest of the app (and every eval run's configuration) can read the revision and
entries without touching the disk. The revision is the SHA-256 of the file's
bytes, so hand-editing the file always yields a new revision for run
comparability, and reloading an unchanged file is a no-op upsert (AC10).

Validation is deliberately strict because a broken golden set would silently
change every metric: malformed JSON, a non-list top level, an empty set, a
non-object entry, a blank question or answer, a non-integer or ``< 1`` expected
page, and unknown keys are all rejected with a message naming the file and the
offending entry index (Locked intent #8, SPEC "Metric definitions").

No FastAPI import lives here on purpose: the API, the eval runner and the tests
share this module, and no test needs a model or a socket to exercise it.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from khaleev import paths
from khaleev.models import GoldenSet as GoldenSetRow

GOLDEN_SUFFIX = ".json"

#: The exact keys a golden entry may carry; anything else is a typo, not data.
ENTRY_KEYS = frozenset({"question", "expected_answer", "expected_pages"})


class GoldenSetError(Exception):
    """Base class for every golden-set domain error."""


class GoldenSetNotFoundError(GoldenSetError, LookupError):
    """No golden-set file exists for the requested document."""


class GoldenSetValidationError(GoldenSetError, ValueError):
    """The golden-set file exists but does not honour the golden-set rules."""


@dataclass(frozen=True, slots=True)
class GoldenEntry:
    """One curated question, its expected answer and its 1-based source pages."""

    question: str
    expected_answer: str
    expected_pages: list[int]

    def as_dict(self) -> dict[str, Any]:
        """The JSON shape persisted in ``golden_sets.entries`` and returned by the API."""
        return {
            "question": self.question,
            "expected_answer": self.expected_answer,
            "expected_pages": list(self.expected_pages),
        }


@dataclass(frozen=True, slots=True)
class GoldenSet:
    """A validated golden set with the revision computed from its file bytes."""

    document_id: int
    revision: str
    path: Path
    entries: list[GoldenEntry]

    def as_entries(self) -> list[dict[str, Any]]:
        """The entries as plain JSON-ready dicts, in file order."""
        return [entry.as_dict() for entry in self.entries]


def _checked_document_id(document_id: int) -> int:
    """Return ``document_id`` only when it can name a file inside the golden dir.

    The API takes an integer path parameter, but validation happens here too so a
    future caller cannot smuggle a name like ``../notes`` into the filesystem.
    """
    if isinstance(document_id, bool) or not isinstance(document_id, int):
        raise GoldenSetValidationError(
            f"document id must be a positive integer, got {document_id!r}"
        )
    if document_id < 1:
        raise GoldenSetValidationError(f"document id must be >= 1, got {document_id}")
    return document_id


def golden_path(data_dir: Path, document_id: int) -> Path:
    """``<data_dir>/golden/<document_id>.json``, guaranteed inside the golden dir."""
    checked = _checked_document_id(document_id)
    directory = paths.DataPaths.from_data_dir(data_dir).golden
    path = directory / f"{checked}{GOLDEN_SUFFIX}"
    if not path.resolve().is_relative_to(directory.resolve()):
        raise GoldenSetValidationError(f"golden path {path} escapes the golden directory")
    return path


def compute_revision(raw: bytes) -> str:
    """The golden-set revision: SHA-256 of the file's exact bytes."""
    return hashlib.sha256(raw).hexdigest()


def _invalid(path: Path, problem: str) -> GoldenSetValidationError:
    return GoldenSetValidationError(f"invalid golden set {path}: {problem}")


def _required_text(entry: Mapping[str, Any], key: str, index: int, path: Path) -> str:
    if key not in entry:
        raise _invalid(path, f"entry {index}: missing required key {key!r}")
    value = entry[key]
    if not isinstance(value, str):
        raise _invalid(path, f"entry {index}: {key} must be a string")
    if not value.strip():
        raise _invalid(path, f"entry {index}: {key} must not be empty")
    return value


def _expected_pages(entry: Mapping[str, Any], index: int, path: Path) -> list[int]:
    if "expected_pages" not in entry:
        raise _invalid(path, f"entry {index}: missing required key 'expected_pages'")
    pages = entry["expected_pages"]
    if not isinstance(pages, list):
        raise _invalid(path, f"entry {index}: expected_pages must be a list of integers")
    if not pages:
        raise _invalid(path, f"entry {index}: expected_pages must not be empty")
    checked: list[int] = []
    for page in pages:
        # bool is an int subclass, but a page number is never True/False.
        if isinstance(page, bool) or not isinstance(page, int):
            raise _invalid(
                path, f"entry {index}: expected_pages must contain integers, got {page!r}"
            )
        if page < 1:
            raise _invalid(path, f"entry {index}: expected_pages must be >= 1, got {page}")
        checked.append(page)
    return checked


def parse_golden_entries(payload: Any, *, path: Path) -> list[GoldenEntry]:
    """Validate a decoded JSON payload and return its entries.

    ``path`` only appears in error messages; nothing is read or written here, so
    the same rules can validate the sample fixture without a data directory.
    """
    if not isinstance(payload, list):
        raise _invalid(path, "top level must be a JSON list of entries")
    if not payload:
        raise _invalid(path, "the golden set is empty; a run against an empty set is invalid")

    entries: list[GoldenEntry] = []
    for index, raw_entry in enumerate(payload):
        if not isinstance(raw_entry, Mapping):
            raise _invalid(path, f"entry {index}: each entry must be a JSON object")
        unexpected = sorted(set(raw_entry) - ENTRY_KEYS)
        if unexpected:
            names = ", ".join(repr(key) for key in unexpected)
            raise _invalid(path, f"entry {index}: unexpected key(s) {names}")
        entries.append(
            GoldenEntry(
                question=_required_text(raw_entry, "question", index, path),
                expected_answer=_required_text(raw_entry, "expected_answer", index, path),
                expected_pages=_expected_pages(raw_entry, index, path),
            )
        )
    return entries


def load_golden_set(data_dir: Path, document_id: int) -> GoldenSet:
    """Read and validate ``<data_dir>/golden/<document_id>.json``.

    Raises :class:`GoldenSetNotFoundError` when the file is absent and
    :class:`GoldenSetValidationError` when it exists but breaks the rules or is
    an empty set — the SPEC makes a run against an empty golden set invalid.
    """
    checked = _checked_document_id(document_id)
    path = golden_path(data_dir, checked)
    try:
        raw = path.read_bytes()
    except FileNotFoundError as exc:
        raise GoldenSetNotFoundError(
            f"golden set for document {checked} not found at {path}"
        ) from exc

    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise _invalid(path, f"the file is not valid UTF-8: {exc}") from exc

    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise _invalid(
            path,
            f"the file is not valid JSON: {exc.msg} at line {exc.lineno} column {exc.colno}",
        ) from exc

    return GoldenSet(
        document_id=checked,
        revision=compute_revision(raw),
        path=path,
        entries=parse_golden_entries(payload, path=path),
    )


def persist_golden_set(session: Session, golden_set: GoldenSet) -> GoldenSetRow:
    """Upsert the document's ``golden_sets`` row and return it.

    The row is keyed by ``document_id``, so reloading an unchanged file updates
    nothing visible and can never create a duplicate (AC10). The caller owns the
    transaction; :func:`sync_golden_set` commits for the API path.
    """
    row = session.get(GoldenSetRow, golden_set.document_id)
    entries = golden_set.as_entries()
    if row is None:
        row = GoldenSetRow(
            document_id=golden_set.document_id,
            revision=golden_set.revision,
            path=str(golden_set.path),
            entries=entries,
        )
        session.add(row)
    else:
        row.revision = golden_set.revision
        row.path = str(golden_set.path)
        row.entries = entries
    session.flush()
    return row


def sync_golden_set(session: Session, data_dir: Path, document_id: int) -> GoldenSet:
    """Load the file, persist its revision and entries, commit, and return it."""
    golden_set = load_golden_set(data_dir, document_id)
    persist_golden_set(session, golden_set)
    session.commit()
    return golden_set


def seed_golden_file(data_dir: Path, document_id: int) -> Path:
    """Create an empty golden file when the document has none, and return its path.

    Uploading a document calls this so the path always exists and a revision can
    always be recorded; an existing file — including one the user already filled
    in — is never overwritten.
    """
    path = golden_path(data_dir, document_id)
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"{json.dumps([], indent=2)}\n", encoding="utf-8")
    return path


def write_golden_file(
    data_dir: Path, document_id: int, entries: Sequence[Mapping[str, Any]]
) -> GoldenSet:
    """Write ``entries`` as pretty JSON and return the loaded, validated set.

    A small helper for tests and for hand-editing scripts; the production path
    reads whatever the user wrote with :func:`load_golden_set`.
    """
    path = golden_path(data_dir, document_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"{json.dumps(list(entries), indent=2)}\n", encoding="utf-8")
    return load_golden_set(data_dir, document_id)


__all__ = [
    "ENTRY_KEYS",
    "GOLDEN_SUFFIX",
    "GoldenEntry",
    "GoldenSet",
    "GoldenSetError",
    "GoldenSetNotFoundError",
    "GoldenSetValidationError",
    "compute_revision",
    "golden_path",
    "load_golden_set",
    "parse_golden_entries",
    "persist_golden_set",
    "seed_golden_file",
    "sync_golden_set",
    "write_golden_file",
]
