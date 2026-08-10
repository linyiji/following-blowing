from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_build_info_records_rename_without_runtime_state() -> None:
    payload = json.loads((PROJECT_ROOT / "BUILD_INFO.json").read_text(encoding="utf-8"))

    assert payload == {
        "project": "Following blowing",
        "former_project": "ai-ip-brand",
        "build_started_at": "2026-08-09T10:32:00+08:00",
        "build_type": "competition-preparation",
        "schema_version": "1.0",
    }
    assert datetime.fromisoformat(payload["build_started_at"]).utcoffset() is not None
    assert "started_at" not in payload
