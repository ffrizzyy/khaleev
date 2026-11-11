"""Filesystem locations used by Khaleev.

Every path is derived from this file so the backend can run from a checkout
without depending on the current working directory. Nothing here creates
directories; callers that need them ask explicitly (see ``config``).
"""

from __future__ import annotations

from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parent
BACKEND_ROOT = PACKAGE_ROOT.parents[1]
REPO_ROOT = BACKEND_ROOT.parent
DEFAULT_DATA_DIR = REPO_ROOT / "data"


def default_data_dir() -> Path:
    """Return the default local data directory without creating it."""
    return DEFAULT_DATA_DIR
