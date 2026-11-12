"""Unit tests for loading and validating a document's golden set (T13, F4, AC4).

The golden set is the hand-editable JSON file every eval metric is defined
against, so these tests are about content rules rather than HTTP: a valid file
loads with a content-hash revision, an invalid one fails with a message that
names the file and the offending entry, and persisting the result is idempotent
so the same file never creates a second row (AC10).

No model is loaded and no socket is opened here (SPEC AC8, Locked intent #12).
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from khaleev.evals.golden import (
    GoldenEntry,
    GoldenSetNotFoundError,
    GoldenSetValidationError,
    golden_path,
    load_golden_set,
    parse_golden_entries,
    persist_golden_set,
    seed_golden_file,
    write_golden_file,
)
from khaleev.models import Document
from khaleev.models import GoldenSet as GoldenSetRow

SAMPLE_PATH = Path(__file__).resolve().parents[1] / "fixtures" / "golden_sample.json"
SAMPLE_PAYLOAD = json.loads(SAMPLE_PATH.read_text(encoding="utf-8"))

VALID_ENTRY = {
    "question": "What penalty applies to late filings?",
    "expected_answer": "Late filings incur a flat 200 credit penalty per return.",
    "expected_pages": [4],
}


def _write_raw(data_dir: Path, document_id: int, text: str) -> Path:
    """Write raw bytes-as-text into the golden dir, bypassing any validation."""
    path = data_dir / "golden" / f"{document_id}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _add_document(session: Session, page_count: int = 4) -> int:
    """Insert the document a golden set's foreign key needs; return its id."""
    document = Document(content_hash="0" * 64, title="tax-guide.pdf", page_count=page_count)
    session.add(document)
    session.commit()
    return document.id


# --- loading a valid set --------------------------------------------------


def test_loads_a_valid_golden_set_with_a_content_hash_revision(tmp_path: Path) -> None:
    path = _write_raw(tmp_path, 7, json.dumps(SAMPLE_PAYLOAD, indent=2))

    golden = load_golden_set(tmp_path, 7)

    assert golden.document_id == 7
    assert golden.path == path
    assert golden.revision == hashlib.sha256(path.read_bytes()).hexdigest()
    assert [entry.question for entry in golden.entries] == [
        entry["question"] for entry in SAMPLE_PAYLOAD
    ]
    assert [entry.expected_pages for entry in golden.entries] == [
        entry["expected_pages"] for entry in SAMPLE_PAYLOAD
    ]
    assert [entry.expected_answer for entry in golden.entries] == [
        entry["expected_answer"] for entry in SAMPLE_PAYLOAD
    ]


def test_the_sample_fixture_is_valid_and_has_at_least_three_entries() -> None:
    entries = parse_golden_entries(SAMPLE_PAYLOAD, path=SAMPLE_PATH)

    assert len(entries) >= 3
    assert all(isinstance(entry, GoldenEntry) for entry in entries)
    assert all(entry.question.strip() for entry in entries)
    assert all(entry.expected_answer.strip() for entry in entries)
    assert all(entry.expected_pages for entry in entries)


def test_the_golden_path_is_inside_the_golden_directory(tmp_path: Path) -> None:
    assert golden_path(tmp_path, 3) == tmp_path.resolve() / "golden" / "3.json"


def test_a_document_id_cannot_escape_the_golden_directory(tmp_path: Path) -> None:
    # Deliberately the wrong type: an API must never turn a name into a path.
    with pytest.raises(GoldenSetValidationError):
        golden_path(tmp_path, "../escape")  # type: ignore[arg-type]

    with pytest.raises(GoldenSetValidationError):
        golden_path(tmp_path, 0)


# --- revision -------------------------------------------------------------


def test_revision_is_deterministic_for_unchanged_bytes(tmp_path: Path) -> None:
    _write_raw(tmp_path, 1, json.dumps(SAMPLE_PAYLOAD, indent=2))

    first = load_golden_set(tmp_path, 1)
    second = load_golden_set(tmp_path, 1)

    assert first.revision == second.revision


def test_editing_the_file_changes_the_revision(tmp_path: Path) -> None:
    _write_raw(tmp_path, 1, json.dumps(SAMPLE_PAYLOAD, indent=2))
    before = load_golden_set(tmp_path, 1)

    edited = [dict(entry) for entry in SAMPLE_PAYLOAD]
    edited[0]["expected_pages"] = [9]
    _write_raw(tmp_path, 1, json.dumps(edited, indent=2))
    after = load_golden_set(tmp_path, 1)

    assert after.revision != before.revision


def test_a_whitespace_only_edit_also_changes_the_revision(tmp_path: Path) -> None:
    _write_raw(tmp_path, 1, json.dumps(SAMPLE_PAYLOAD, indent=2))
    before = load_golden_set(tmp_path, 1)

    _write_raw(tmp_path, 1, json.dumps(SAMPLE_PAYLOAD, indent=4))

    assert load_golden_set(tmp_path, 1).revision != before.revision


# --- errors ---------------------------------------------------------------


def test_a_missing_file_raises_not_found_naming_the_path(tmp_path: Path) -> None:
    with pytest.raises(GoldenSetNotFoundError) as excinfo:
        load_golden_set(tmp_path, 42)

    assert "42.json" in str(excinfo.value)


def test_malformed_json_names_the_file_and_the_problem(tmp_path: Path) -> None:
    path = _write_raw(tmp_path, 1, '{"question": "truncated"')

    with pytest.raises(GoldenSetValidationError) as excinfo:
        load_golden_set(tmp_path, 1)

    message = str(excinfo.value)
    assert str(path) in message
    assert "JSON" in message


def test_a_top_level_object_is_rejected(tmp_path: Path) -> None:
    path = _write_raw(tmp_path, 1, json.dumps({"entries": SAMPLE_PAYLOAD}))

    with pytest.raises(GoldenSetValidationError) as excinfo:
        load_golden_set(tmp_path, 1)

    assert "list" in str(excinfo.value)
    assert str(path) in str(excinfo.value)


def test_an_empty_golden_set_is_rejected(tmp_path: Path) -> None:
    path = _write_raw(tmp_path, 1, "[]")

    with pytest.raises(GoldenSetValidationError) as excinfo:
        load_golden_set(tmp_path, 1)

    message = str(excinfo.value)
    assert "empty" in message
    assert str(path) in message


@pytest.mark.parametrize(
    ("entry", "needle"),
    [
        ({**VALID_ENTRY, "question": ""}, "question"),
        ({**VALID_ENTRY, "question": "   "}, "question"),
        ({"expected_answer": "a", "expected_pages": [1]}, "question"),
        ({**VALID_ENTRY, "expected_answer": ""}, "expected_answer"),
        ({**VALID_ENTRY, "expected_answer": " \n "}, "expected_answer"),
        ({"question": "q", "expected_pages": [1]}, "expected_answer"),
        ({**VALID_ENTRY, "expected_pages": []}, "expected_pages"),
        ({**VALID_ENTRY, "expected_pages": [0]}, "expected_pages"),
        ({**VALID_ENTRY, "expected_pages": [-2]}, "expected_pages"),
        ({**VALID_ENTRY, "expected_pages": ["3"]}, "expected_pages"),
        ({**VALID_ENTRY, "expected_pages": [1.5]}, "expected_pages"),
        ({**VALID_ENTRY, "expected_pages": [True]}, "expected_pages"),
        ({**VALID_ENTRY, "expected_pages": 4}, "expected_pages"),
        ({"question": "q", "expected_answer": "a"}, "expected_pages"),
        ("not an object", "object"),
        ({**VALID_ENTRY, "expected_page": [4]}, "expected_page"),
    ],
)
def test_an_invalid_entry_names_its_index_and_the_problem(
    tmp_path: Path, entry: object, needle: str
) -> None:
    _write_raw(tmp_path, 1, json.dumps([VALID_ENTRY, entry]))

    with pytest.raises(GoldenSetValidationError) as excinfo:
        load_golden_set(tmp_path, 1)

    message = str(excinfo.value)
    assert "entry 1" in message
    assert needle in message


# --- writing and seeding --------------------------------------------------


def test_write_golden_file_round_trips_the_entries(tmp_path: Path) -> None:
    golden = write_golden_file(tmp_path, 5, SAMPLE_PAYLOAD)

    path = tmp_path / "golden" / "5.json"
    assert path.is_file()
    assert json.loads(path.read_text(encoding="utf-8")) == SAMPLE_PAYLOAD
    assert golden.document_id == 5
    assert len(golden.entries) == len(SAMPLE_PAYLOAD)
    assert golden.revision == hashlib.sha256(path.read_bytes()).hexdigest()


def test_seeding_creates_an_empty_file_only_when_absent(tmp_path: Path) -> None:
    created = seed_golden_file(tmp_path, 9)

    assert created.is_file()
    assert json.loads(created.read_text(encoding="utf-8")) == []

    write_golden_file(tmp_path, 9, SAMPLE_PAYLOAD)
    seed_golden_file(tmp_path, 9)

    assert len(load_golden_set(tmp_path, 9).entries) == len(SAMPLE_PAYLOAD)


# --- persistence ----------------------------------------------------------


def test_persisting_writes_the_revision_and_entries(
    migrated_session: Session, tmp_path: Path
) -> None:
    document_id = _add_document(migrated_session)
    golden = write_golden_file(tmp_path, document_id, SAMPLE_PAYLOAD)

    row = persist_golden_set(migrated_session, golden)
    migrated_session.commit()

    stored = migrated_session.get(GoldenSetRow, document_id)
    assert stored is not None
    assert row.revision == golden.revision
    assert stored.revision == golden.revision
    assert stored.path == str(golden.path)
    assert stored.entries == SAMPLE_PAYLOAD


def test_reloading_an_unchanged_file_keeps_one_row_and_one_revision(
    migrated_session: Session, tmp_path: Path
) -> None:
    document_id = _add_document(migrated_session)
    write_golden_file(tmp_path, document_id, SAMPLE_PAYLOAD)

    first = load_golden_set(tmp_path, document_id)
    persist_golden_set(migrated_session, first)
    migrated_session.commit()
    second = load_golden_set(tmp_path, document_id)
    persist_golden_set(migrated_session, second)
    migrated_session.commit()

    rows = list(migrated_session.scalars(select(GoldenSetRow)))
    assert len(rows) == 1
    assert first.revision == second.revision == rows[0].revision
    assert len(rows[0].entries) == len(SAMPLE_PAYLOAD)


def test_editing_the_file_updates_the_existing_row(
    migrated_session: Session, tmp_path: Path
) -> None:
    document_id = _add_document(migrated_session)
    write_golden_file(tmp_path, document_id, SAMPLE_PAYLOAD)
    first = load_golden_set(tmp_path, document_id)
    persist_golden_set(migrated_session, first)
    migrated_session.commit()

    edited = SAMPLE_PAYLOAD[:2]
    write_golden_file(tmp_path, document_id, edited)
    second = load_golden_set(tmp_path, document_id)
    persist_golden_set(migrated_session, second)
    migrated_session.commit()

    rows = list(migrated_session.scalars(select(GoldenSetRow)))
    assert len(rows) == 1
    assert second.revision != first.revision
    assert rows[0].revision == second.revision
    assert rows[0].entries == edited
