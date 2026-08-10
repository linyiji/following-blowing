"""One-time, deterministic migration of the approved HTML demo.

The source path is deliberately confined to this migration utility. Runtime
code never reads from Downloads or any other machine-specific location.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import re
from pathlib import Path


DEFAULT_SOURCE = Path(
    "/Users/mac/Downloads/AI_IP_Brand_Workflow_Comprehensive_v7_ResultUpdated.html"
)
PROJECT_ROOT = Path(__file__).resolve().parents[1]
FRONTEND_DIR = PROJECT_ROOT / "app" / "ui" / "frontend"
DEMO_DIR = PROJECT_ROOT / "assets" / "demo"
MIGRATION_DIR = PROJECT_ROOT / "docs" / "migration"

DATA_URI_RE = re.compile(
    r"data:image/(?P<ext>png|jpe?g|webp);base64,(?P<data>[A-Za-z0-9+/=]+)",
    re.IGNORECASE,
)


def _between(source: str, start: str, end: str) -> str:
    lower = source.lower()
    first = lower.index(start.lower()) + len(start)
    last = lower.index(end.lower(), first)
    return source[first:last]


def migrate(source_path: Path) -> dict[str, object]:
    if not source_path.is_file():
        raise FileNotFoundError(f"Approved HTML migration source not found: {source_path}")

    raw = source_path.read_text(encoding="utf-8")
    images = list(DATA_URI_RE.finditer(raw))
    if len(images) != 4:
        raise ValueError(f"Expected exactly four embedded demo images, found {len(images)}")

    FRONTEND_DIR.mkdir(parents=True, exist_ok=True)
    DEMO_DIR.mkdir(parents=True, exist_ok=True)
    MIGRATION_DIR.mkdir(parents=True, exist_ok=True)

    # The approved v7 file embeds the result image in markup, followed by the
    # IP, brand, and rejected Guardian example in the interaction script.
    asset_names = (
        "final_result.png",
        "ip_reference.jpg",
        "brand_reference.jpg",
        "guardian_rejected.jpg",
    )
    asset_manifest: list[dict[str, object]] = []
    for match, filename in zip(images, asset_names, strict=True):
        payload = base64.b64decode(match.group("data"), validate=True)
        output = DEMO_DIR / filename
        output.write_bytes(payload)
        asset_manifest.append(
            {
                "filename": filename,
                "bytes": len(payload),
                "sha256": hashlib.sha256(payload).hexdigest(),
            }
        )

    css = _between(raw, "<style>", "</style>").strip() + "\n"
    body = _between(raw, "<body>", "<script>")
    # The only image URI in the markup is the final result. Python supplies it
    # from WorkflowRun.final_candidate at runtime.
    body = DATA_URI_RE.sub("", body, count=1)
    body = body.replace("</body>", "").strip() + "\n"

    (FRONTEND_DIR / "component.css").write_text(css, encoding="utf-8")
    (FRONTEND_DIR / "component.html").write_text(body, encoding="utf-8")

    manifest: dict[str, object] = {
        "source_filename": source_path.name,
        "source_sha256": hashlib.sha256(raw.encode("utf-8")).hexdigest(),
        "source_bytes": source_path.stat().st_size,
        "html_structure_chars": len(body),
        "css_chars": len(css),
        "embedded_assets": asset_manifest,
        "runtime_depends_on_source": False,
    }
    (MIGRATION_DIR / "ui-source-manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", nargs="?", type=Path, default=DEFAULT_SOURCE)
    args = parser.parse_args()
    print(json.dumps(migrate(args.source), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
