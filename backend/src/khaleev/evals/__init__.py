"""The evaluation layer: golden sets today, metrics and runs next (T13-T17).

``khaleev.evals.golden`` owns the per-document golden set: the hand-editable JSON
file, its validation rules and the content-hash revision that eval runs record.
It imports no web framework, so the API, the eval runner and the tests all load
golden sets through the same code path.
"""

from __future__ import annotations

from khaleev.evals.golden import (
    GOLDEN_SUFFIX,
    GoldenEntry,
    GoldenSet,
    GoldenSetError,
    GoldenSetNotFoundError,
    GoldenSetValidationError,
    golden_path,
    load_golden_set,
    parse_golden_entries,
    persist_golden_set,
    seed_golden_file,
    sync_golden_set,
    write_golden_file,
)

__all__ = [
    "GOLDEN_SUFFIX",
    "GoldenEntry",
    "GoldenSet",
    "GoldenSetError",
    "GoldenSetNotFoundError",
    "GoldenSetValidationError",
    "golden_path",
    "load_golden_set",
    "parse_golden_entries",
    "persist_golden_set",
    "seed_golden_file",
    "sync_golden_set",
    "write_golden_file",
]
