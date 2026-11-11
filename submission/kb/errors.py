"""Error registry: stable ``KB-Exx`` codes, one-line messages that each end with a fix."""
from __future__ import annotations

import sys
from typing import Dict, Set

MESSAGES: Dict[str, str] = {
    "KB-E01": "data file {path} is stale (data {data_version}, code {code_version}): running without it. Fix: git checkout -- {path} or re-run its scripts/build_*.py builder.",
    "KB-E02": "{key} is set but ignored: grading never uses API keys. Fix: unset it, or set KB_LLM_INGEST=1 only when rebuilding data files offline.",
    "KB-E03": "this submission targets Python 3.11 (found {found}): it runs, but only 3.11 is verified. Fix: create a venv with python3.11 and reinstall.",
    "KB-E04": "as_of {value!r} is not an ISO date (YYYY-MM-DD): the question was refused. Fix: pass a date such as 2026-06-02, or omit as_of for the latest snapshot.",
    "KB-E05": "question is empty, not text or over {limit} characters: an empty or non-text one was refused, a longer one was cut to its first {limit} characters and answered. Fix: send one plain-text question of at most {limit} characters.",
    "KB-E06": "unexpected {error} while answering: the question was refused. Fix: run explain() on the same question and report its output.",
    "KB-E07": "curated conflict {topic!r} dropped: {why}. Fix: re-copy the quote and value from the page in that crawl, or remove the entry.",
    "KB-E08": "curated prose fact {product_id}/{attribute} on {url} @{snapshot_id} dropped: {why}. Fix: re-copy the quote from the page in that crawl, or remove the crawl from the entry.",
}

_warned: Set[str] = set()


class _Fields(dict):
    """Format fields where a missing key renders as ``?``, so a message always builds."""

    def __missing__(self, key: str) -> str:
        return "?"


def _render(code: str, fmt: Dict[str, object]) -> str:
    template = MESSAGES.get(code, "unknown error code")
    try:
        message = template.format_map(_Fields(fmt))
    except Exception:  # a malformed field must not hide the code itself
        message = template
    return "kb: [{}] {}".format(code, message)


class KBError(Exception):
    """A failure with a stable ``KB-Exx`` code; ``str(error)`` is its registry line."""

    def __init__(self, code: str, **fmt: object) -> None:
        self.code = code
        super().__init__(_render(code, fmt))


def warn_once(code: str, **fmt: object) -> None:
    """Write the registry line for ``code`` to stderr the first time only; never raises."""
    try:
        if code in _warned:
            return
        _warned.add(code)
        print(_render(code, fmt), file=sys.stderr)
    except Exception:  # reporting a problem must never become one
        pass
