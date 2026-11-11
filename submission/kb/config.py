"""Runtime configuration. The only module that reads ``os.environ``, and only ``KB_LLM_INGEST``."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# Resolved from this file, never from the cwd; nothing here creates or writes the directory.
DEFAULT_DATA_DIR = Path(__file__).resolve().parent.parent / "data"


@dataclass(frozen=True)
class Config:
    data_dir: Path
    refuse_threshold: float = 0.0
    log_level: str = "WARNING"
    max_question_chars: int = 1000
    llm_ingest: bool = False

    @classmethod
    def from_env(cls, **overrides: Any) -> Config:
        """Defaults, then ``KB_LLM_INGEST=1``, then ``overrides``, which have the last word."""
        values: dict = {
            "data_dir": DEFAULT_DATA_DIR,
            "llm_ingest": os.environ.get("KB_LLM_INGEST") == "1",
        }
        values.update(overrides)
        return cls(**values)
