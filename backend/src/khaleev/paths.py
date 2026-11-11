"""Filesystem locations used by Khaleev.

Every path is derived from this file so the backend can run from a checkout
without depending on the current working directory. Nothing here creates
directories on import; callers that need them ask explicitly (see
``DataPaths.create`` and ``khaleev.config.Settings.ensure_data_dir``).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parent
BACKEND_ROOT = PACKAGE_ROOT.parents[1]
REPO_ROOT = BACKEND_ROOT.parent
DEFAULT_DATA_DIR = REPO_ROOT / "data"

PDFS_DIRNAME = "pdfs"
INDEX_DIRNAME = "index"
GOLDEN_DIRNAME = "golden"


def default_data_dir() -> Path:
    """Return the default local data directory without creating it."""
    return DEFAULT_DATA_DIR


@dataclass(frozen=True, slots=True)
class DataPaths:
    """The resolved directories that make up the local data layout."""

    root: Path
    pdfs: Path
    index: Path
    golden: Path

    @classmethod
    def from_data_dir(cls, data_dir: Path) -> DataPaths:
        """Resolve ``data_dir`` and derive every directory beneath it."""
        root = Path(data_dir).expanduser().resolve()
        return cls(
            root=root,
            pdfs=root / PDFS_DIRNAME,
            index=root / INDEX_DIRNAME,
            golden=root / GOLDEN_DIRNAME,
        )

    def create(self) -> DataPaths:
        """Create the whole layout, idempotently, and return it."""
        for directory in (self.root, self.pdfs, self.index, self.golden):
            directory.mkdir(parents=True, exist_ok=True)
        return self
