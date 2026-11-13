"""The declared runtime dependencies match what the app is documented to need (T20).

SPEC's run command is ``uv run uvicorn khaleev.app:app --reload --port 8000``.
The live run of the finished app found that command failing with
``Failed to spawn: uvicorn`` because uvicorn was used but never declared. These
assertions are metadata-only — no network, no subprocess — so they stay cheap and
offline:

* ``uvicorn`` is in ``backend/pyproject.toml`` ``[project].dependencies``;
* it is resolved in ``uv.lock``, so a clean ``uv sync`` installs it;
* it is importable in the environment the tests run in;
* no document falls back to the undocumented ``--with uvicorn`` overlay.
"""

from __future__ import annotations

import importlib.util
import re
import tomllib
from pathlib import Path

from khaleev import paths

#: A PEP 508 requirement's project name: everything before an extra or specifier.
_REQUIREMENT_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*")
_WITH_OVERLAY = "--with uvicorn"


def _backend_pyproject() -> dict[str, object]:
    with (paths.BACKEND_ROOT / "pyproject.toml").open("rb") as handle:
        return tomllib.load(handle)


def _declared_runtime_dependencies() -> set[str]:
    project = _backend_pyproject()["project"]
    assert isinstance(project, dict)
    requirements = project["dependencies"]
    assert isinstance(requirements, list)
    names: set[str] = set()
    for requirement in requirements:
        match = _REQUIREMENT_NAME.match(str(requirement))
        assert match is not None, f"unparseable requirement: {requirement!r}"
        names.add(match.group(0).lower().replace("_", "-"))
    return names


def test_uvicorn_is_a_declared_runtime_dependency() -> None:
    assert "uvicorn" in _declared_runtime_dependencies()


def test_uvicorn_is_importable_in_this_environment() -> None:
    assert importlib.util.find_spec("uvicorn") is not None


def test_the_lockfile_resolves_uvicorn() -> None:
    lock = (paths.BACKEND_ROOT / "uv.lock").read_text(encoding="utf-8")

    assert re.search(r'^name = "uvicorn"$', lock, flags=re.MULTILINE) is not None


def test_the_documented_run_command_needs_no_with_overlay() -> None:
    """The workaround must not creep back into the docs or the code."""
    documents: list[Path] = [paths.REPO_ROOT / "README.md"]
    documents.extend(sorted((paths.REPO_ROOT / "docs").rglob("*.md")))
    documents.extend(sorted((paths.BACKEND_ROOT / "src").rglob("*.py")))

    offenders = [
        document.relative_to(paths.REPO_ROOT)
        for document in documents
        if document.is_file() and _WITH_OVERLAY in document.read_text(encoding="utf-8")
    ]

    assert offenders == []
