"""The service and generation layers must not depend on the API layer.

``khaleev.api.schemas`` is the REST contract: it is where FastAPI-specific
request bodies live and where the frontend contract is read from. A service or a
generation module importing it would invert the dependency direction and force
every non-web consumer (the eval runner, a future CLI) to load the web layer.

The models those modules genuinely share — ``Citation`` and ``AnswerResponse`` —
live in the neutral ``khaleev.schemas`` instead. ``khaleev.api.schemas``
re-exports them, so every existing route, test and import path keeps working and
the response contract is unchanged.
"""

from __future__ import annotations

import ast
import importlib
from pathlib import Path

#: Modules below the API layer that must stay web-framework-free.
LOWER_LAYER_MODULES = ("khaleev.services.qa", "khaleev.generation.citations")


def _imported_modules(module_name: str) -> set[str]:
    """Every module ``module_name`` imports, read from its own source."""
    module = importlib.import_module(module_name)
    source = Path(module.__file__ or "").read_text(encoding="utf-8")
    names: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
    return names


def test_lower_layers_do_not_import_the_api_layer() -> None:
    offenders = {
        module: sorted(
            name for name in _imported_modules(module) if name.startswith("khaleev.api")
        )
        for module in LOWER_LAYER_MODULES
    }

    assert offenders == {module: [] for module in LOWER_LAYER_MODULES}


def test_the_api_schemas_reexport_the_shared_models() -> None:
    """One class object, two import paths: the REST contract cannot drift."""
    from khaleev import schemas as shared
    from khaleev.api import schemas as api_schemas

    assert api_schemas.Citation is shared.Citation
    assert api_schemas.AnswerResponse is shared.AnswerResponse
