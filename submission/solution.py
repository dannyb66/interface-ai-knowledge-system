"""Submission entry point: the harness loads this file and calls ``build()``."""
from __future__ import annotations

import sys
from pathlib import Path


def _harness_dir():
    """The kit's ``harness`` folder: beside a parent of this file (the repo layout), else none when a folder already
    on ``sys.path`` holds ``contract.py`` (``run_eval.py`` puts its own there), else beside the working directory;
    ``None`` leaves the import of ``contract`` to fail with its own error."""
    for base in Path(__file__).resolve().parents:
        if (base / "harness" / "contract.py").is_file():
            return base / "harness"
    if any((Path(entry or ".") / "contract.py").is_file() for entry in sys.path):
        return None
    cwd = Path.cwd() / "harness"
    return cwd if (cwd / "contract.py").is_file() else None


_HARNESS = _harness_dir()
if _HARNESS is not None:
    sys.path.insert(0, str(_HARNESS))
from kb.config import Config  # noqa: E402
from kb.system import KnowledgeSystem  # noqa: E402


def build(**overrides) -> KnowledgeSystem:
    """Return a ready ``KnowledgeSystem``; keyword overrides replace ``Config`` fields."""
    return KnowledgeSystem(Config.from_env(**overrides))
