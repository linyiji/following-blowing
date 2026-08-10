from __future__ import annotations

from pathlib import Path, PurePosixPath

from scripts.secret_scan import (
    EXCLUDED_DIRECTORY_NAMES,
    find_runtime_credential_files,
    forbidden_release_paths,
    release_manifest,
    scan_source_credentials,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _credential_shaped_value() -> str:
    # The fixture is assembled at runtime so the test suite never bundles a
    # credential-shaped literal of its own.
    return "".join(("s", "k", "-", "A9b_C7d-E5f_G3h-I1j_K8m-N6p_Q4r"))


def _finding_paths(root: Path) -> set[str]:
    return {
        finding.relative_path
        for finding in scan_source_credentials(root)
    }


def test_dependency_venv_secret_shape_is_outside_source_scan(tmp_path: Path) -> None:
    dependency = tmp_path / ".venv" / "lib" / "site-packages" / "vendor.py"
    dependency.parent.mkdir(parents=True)
    dependency.write_text(
        "".join(("API", "_KEY"))
        + f' = "{_credential_shaped_value()}"\n',
        encoding="utf-8",
    )

    assert scan_source_credentials(tmp_path) == []


def test_real_credential_shape_in_app_python_fails_scan(tmp_path: Path) -> None:
    source = tmp_path / "app" / "leak.py"
    source.parent.mkdir(parents=True)
    source.write_text(
        "".join(("API", "_KEY"))
        + f' = "{_credential_shaped_value()}"\n',
        encoding="utf-8",
    )

    assert _finding_paths(tmp_path) == {"app/leak.py"}


def test_real_credential_shape_in_docs_markdown_fails_scan(tmp_path: Path) -> None:
    source = tmp_path / "docs" / "leak.md"
    source.parent.mkdir(parents=True)
    source.write_text(
        f"Accidentally published: `{_credential_shaped_value()}`\n",
        encoding="utf-8",
    )

    assert _finding_paths(tmp_path) == {"docs/leak.md"}


def test_real_authorization_bearer_value_fails_scan(tmp_path: Path) -> None:
    source = tmp_path / "app" / "request.py"
    source.parent.mkdir(parents=True)
    bearer = "".join(("live", "_", "A9b7C5d3E1f8G6h4I2j0K"))
    source.write_text(
        f'HEADERS = {{"Authorization": "Bearer {bearer}"}}\n',
        encoding="utf-8",
    )

    assert _finding_paths(tmp_path) == {"app/request.py"}


def test_runtime_streamlit_secrets_file_fails_even_when_empty(tmp_path: Path) -> None:
    credential_file = tmp_path / ".streamlit" / "secrets.toml"
    credential_file.parent.mkdir(parents=True)
    credential_file.write_text('MULTIMODAL_API_KEY = ""\n', encoding="utf-8")

    assert find_runtime_credential_files(tmp_path) == [
        ".streamlit/secrets.toml"
    ]


def test_empty_streamlit_secrets_example_is_allowed(tmp_path: Path) -> None:
    example = tmp_path / ".streamlit" / "secrets.toml.example"
    example.parent.mkdir(parents=True)
    example.write_text(
        'MULTIMODAL_API_KEY = ""\nIMAGE_API_KEY = ""\n',
        encoding="utf-8",
    )

    assert find_runtime_credential_files(tmp_path) == []
    assert scan_source_credentials(tmp_path) == []


def test_dependency_module_named_secrets_is_not_a_credential_file(
    tmp_path: Path,
) -> None:
    dependency = (
        tmp_path
        / ".venv"
        / "lib"
        / "site-packages"
        / "streamlit"
        / "runtime"
        / "secrets.py"
    )
    dependency.parent.mkdir(parents=True)
    dependency.write_text(
        f'TEST_FIXTURE = "{_credential_shaped_value()}"\n',
        encoding="utf-8",
    )

    assert find_runtime_credential_files(tmp_path) == []
    assert scan_source_credentials(tmp_path) == []


def test_release_packaging_manifest_has_no_forbidden_paths() -> None:
    assert forbidden_release_paths(release_manifest(PROJECT_ROOT)) == []


def test_packaging_safety_check_rejects_each_forbidden_path_class() -> None:
    unsafe_manifest = (
        PurePosixPath(".git/config"),
        PurePosixPath(".venv/lib/site-packages/vendor.py"),
        PurePosixPath("venv/bin/python"),
        PurePosixPath("env/bin/python"),
        PurePosixPath("node_modules/vendor/index.js"),
        PurePosixPath("data/runs/run-123/checkpoint.json"),
        PurePosixPath(".streamlit/secrets.toml"),
        PurePosixPath(".env"),
    )

    assert forbidden_release_paths(unsafe_manifest) == sorted(
        path.as_posix() for path in unsafe_manifest
    )


def test_release_gitignore_keeps_dependency_and_runtime_material_out() -> None:
    ignore_rules = {
        line.strip()
        for line in (PROJECT_ROOT / ".gitignore").read_text(
            encoding="utf-8"
        ).splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    }
    required_rules = {
        ".venv/",
        "venv/",
        "env/",
        ".mypy_cache/",
        "node_modules/",
        ".env",
        ".streamlit/secrets.toml",
        "data/runs/",
    }

    assert required_rules <= ignore_rules
    assert "!data/runs/.gitkeep" not in ignore_rules


def test_all_required_secret_scan_exclusions_are_declared() -> None:
    assert {
        ".git",
        ".venv",
        "venv",
        "env",
        "__pycache__",
        ".pytest_cache",
        ".mypy_cache",
        ".ruff_cache",
        "node_modules",
    } <= EXCLUDED_DIRECTORY_NAMES
