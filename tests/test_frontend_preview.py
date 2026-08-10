from __future__ import annotations

import importlib.util
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
FRONTEND_DIR = PROJECT_ROOT / "app" / "ui" / "frontend"
BUILDER_PATH = PROJECT_ROOT / "scripts" / "build_frontend_preview.py"
PREVIEW_PATH = FRONTEND_DIR / "preview.html"


def _load_builder():
    spec = importlib.util.spec_from_file_location(
        "build_frontend_preview_test_module", BUILDER_PATH
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_static_preview_is_complete_and_source_faithful(tmp_path: Path) -> None:
    builder = _load_builder()
    output = builder.build_preview(tmp_path / "preview.html")
    page = output.read_text(encoding="utf-8")
    lower = page.lower()
    fragment = (FRONTEND_DIR / "component.html").read_text(encoding="utf-8").rstrip()
    stylesheet = (FRONTEND_DIR / "component.css").read_text(encoding="utf-8").rstrip()

    assert lower.lstrip().startswith("<!doctype html>")
    assert lower.count("<html") == lower.count("</html>") == 1
    assert lower.count("<head") == lower.count("</head>") == 1
    assert lower.count("<body") == lower.count("</body>") == 1
    assert '<meta charset="utf-8">' in lower
    assert 'name="viewport"' in lower
    assert "width=device-width" in lower
    assert "<title>Following blowing · Frontend Preview</title>" in page

    assert page.count(fragment) == 1
    assert page.count(stylesheet) == 1
    assert '<style data-source="component.css">' in page
    assert '<link rel="stylesheet"' not in lower

    assert '<script' not in lower
    assert 'src="component.js"' not in lower
    assert "export default function(component)" not in page
    assert 'data-preview-mode="static"' in page
    assert 'id="previewDevelopmentNotice"' in page
    assert "Following blowing · Static UI Preview" in page
    assert "This file is for visual preview only." in page
    assert "Live Agent interaction requires Streamlit." in page
    assert "image upload is not connected to the backend" in page
    assert "http://localhost:8501" in page
    assert str(PROJECT_ROOT) not in page


def test_static_preview_build_is_idempotent_and_checked_in_file_is_current(
    tmp_path: Path,
) -> None:
    builder = _load_builder()
    output = tmp_path / "preview.html"

    builder.build_preview(output)
    first = output.read_bytes()
    builder.build_preview(output)

    assert output.read_bytes() == first
    assert PREVIEW_PATH.read_bytes() == first
