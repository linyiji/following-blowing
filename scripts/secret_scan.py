from __future__ import annotations

import math
import os
import re
import subprocess
from collections import Counter
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Iterable, Iterator, Sequence


# These directories are never Following blowing source. Keep this list explicit:
# a local dependency environment must not expand the security scan boundary.
EXCLUDED_DIRECTORY_NAMES = frozenset(
    {
        ".cache",
        ".eggs",
        ".git",
        ".mypy_cache",
        ".nox",
        ".pytest_cache",
        ".ruff_cache",
        ".tox",
        ".venv",
        ".venvs",
        "__pycache__",
        "build",
        "dist",
        "dist-packages",
        "env",
        "htmlcov",
        "node_modules",
        "site-packages",
        "venv",
    }
)
EXCLUDED_DIRECTORY_SUFFIXES = (".egg-info",)

# Generated runtime material is not release-eligible source. Packaging safety is
# tested separately; excluding it here is not used as proof that packaging is safe.
EXCLUDED_RUNTIME_PREFIXES = (
    PurePosixPath("data/assets"),
    PurePosixPath("data/documents"),
    PurePosixPath("data/generated"),
    PurePosixPath("data/runs"),
)

SOURCE_SUFFIXES = frozenset(
    {
        ".command",
        ".css",
        ".html",
        ".js",
        ".json",
        ".md",
        ".py",
        ".toml",
        ".txt",
        ".yaml",
        ".yml",
    }
)
EXAMPLE_SOURCE_SUFFIXES = tuple(f"{suffix}.example" for suffix in SOURCE_SUFFIXES)

# Runtime credentials are identified by exact project-owned locations or by
# credential-container extensions. A Python module merely named ``secrets.py``
# is ordinary source and is never classified as a credential file.
RUNTIME_CREDENTIAL_PATHS = (
    PurePosixPath(".env"),
    PurePosixPath(".env.development"),
    PurePosixPath(".env.local"),
    PurePosixPath(".env.production"),
    PurePosixPath(".streamlit/secrets.json"),
    PurePosixPath(".streamlit/secrets.toml"),
    PurePosixPath("config/credentials.json"),
    PurePosixPath("config/secrets.toml"),
)
RUNTIME_CREDENTIAL_SUFFIXES = frozenset({".key", ".p12", ".pem", ".pfx"})
RUNTIME_CREDENTIAL_BASENAMES = frozenset({"id_ed25519", "id_rsa"})

FORBIDDEN_RELEASE_DIRECTORY_NAMES = frozenset(
    {".git", ".venv", "venv", "env", "node_modules"}
)
FORBIDDEN_RELEASE_PREFIXES = (PurePosixPath("data/runs"),)
FORBIDDEN_RELEASE_FILES = frozenset(
    {PurePosixPath(".env"), PurePosixPath(".streamlit/secrets.toml")}
)


@dataclass(frozen=True, order=True)
class SecretFinding:
    relative_path: str
    line: int
    rule: str

    def __str__(self) -> str:
        return f"{self.relative_path}:{self.line} ({self.rule})"


def _is_excluded_directory(name: str) -> bool:
    return name in EXCLUDED_DIRECTORY_NAMES or name.endswith(
        EXCLUDED_DIRECTORY_SUFFIXES
    )


def _is_within_prefix(path: PurePosixPath, prefix: PurePosixPath) -> bool:
    return path == prefix or prefix in path.parents


def _has_excluded_part(relative_path: PurePosixPath) -> bool:
    return any(_is_excluded_directory(part) for part in relative_path.parts[:-1])


def _is_runtime_material(relative_path: PurePosixPath) -> bool:
    return any(
        _is_within_prefix(relative_path, prefix)
        for prefix in EXCLUDED_RUNTIME_PREFIXES
    )


def _git_tracked_files(root: Path) -> tuple[Path, ...]:
    """Return tracked files scoped to root, or an empty tuple when unavailable.

    An empty result deliberately does not become the scan scope. A copied release
    can sit below an unrelated or not-yet-initialized Git repository; in that case
    callers must use the explicit recursive fallback.
    """

    root = root.resolve()
    try:
        top_level_result = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "--show-toplevel"],
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return ()
    if top_level_result.returncode != 0:
        return ()

    git_root = Path(top_level_result.stdout.strip()).resolve()
    try:
        root_prefix = root.relative_to(git_root)
    except ValueError:
        return ()

    pathspec = root_prefix.as_posix() if root_prefix.parts else "."
    try:
        tracked_result = subprocess.run(
            [
                "git",
                "-C",
                str(git_root),
                "ls-files",
                "-z",
                "--full-name",
                "--",
                pathspec,
            ],
            check=False,
            capture_output=True,
            timeout=5,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return ()
    if tracked_result.returncode != 0 or not tracked_result.stdout:
        return ()

    resolved: list[Path] = []
    for raw_path in tracked_result.stdout.split(b"\0"):
        if not raw_path:
            continue
        try:
            candidate = (git_root / os.fsdecode(raw_path)).resolve()
            candidate.relative_to(root)
        except (UnicodeDecodeError, ValueError):
            continue
        resolved.append(candidate)
    return tuple(sorted(set(resolved)))


def _walk_project_files(root: Path) -> Iterator[Path]:
    root = root.resolve()
    for directory, child_directories, filenames in os.walk(root, topdown=True):
        current = Path(directory)
        relative_directory = current.relative_to(root)

        kept_directories: list[str] = []
        for name in sorted(child_directories):
            if _is_excluded_directory(name):
                continue
            child_relative = PurePosixPath(
                *(relative_directory.parts + (name,))
            )
            if any(
                _is_within_prefix(child_relative, prefix)
                for prefix in EXCLUDED_RUNTIME_PREFIXES
            ):
                continue
            kept_directories.append(name)
        child_directories[:] = kept_directories

        for filename in sorted(filenames):
            yield current / filename


def iter_release_eligible_files(root: Path) -> Iterator[Path]:
    """Yield project-controlled files, preferring a non-empty Git manifest."""

    root = root.resolve()
    tracked = _git_tracked_files(root)
    candidates: Iterable[Path] = tracked if tracked else _walk_project_files(root)
    for path in candidates:
        if not path.is_file():
            continue
        try:
            relative = PurePosixPath(path.resolve().relative_to(root).as_posix())
        except ValueError:
            continue
        if _has_excluded_part(relative) or _is_runtime_material(relative):
            continue
        yield path


def _is_source_file(path: Path) -> bool:
    lower_name = path.name.lower()
    return (
        path.suffix.lower() in SOURCE_SUFFIXES
        or lower_name == ".env.example"
        or lower_name.endswith(EXAMPLE_SOURCE_SUFFIXES)
    )


def iter_release_source_files(root: Path) -> Iterator[Path]:
    for path in iter_release_eligible_files(root):
        if _is_source_file(path):
            yield path


def _line_number(source: str, offset: int) -> int:
    return source.count("\n", 0, offset) + 1


def _shannon_entropy(value: str) -> float:
    frequencies = Counter(value)
    length = len(value)
    return -sum(
        (count / length) * math.log2(count / length)
        for count in frequencies.values()
    )


def _is_obvious_placeholder(value: str) -> bool:
    stripped = value.strip().strip("'\"")
    if not stripped:
        return True
    if (stripped.startswith("<") and stripped.endswith(">")) or (
        stripped.startswith("${") and stripped.endswith("}")
    ):
        return True
    normalized = stripped.lower()
    exact_placeholders = {
        "changeme",
        "dummy",
        "dummy_test_token",
        "example",
        "fake",
        "none",
        "not-configured",
        "placeholder",
        "redacted",
        "replace-me",
        "replace_me",
        "sample",
        "test",
        "your-api-key",
        "your_api_key",
    }
    return normalized in exact_placeholders


def _looks_like_unprefixed_secret(value: str) -> bool:
    stripped = value.strip().strip("'\"")
    if len(stripped) < 20 or _is_obvious_placeholder(stripped):
        return False
    if stripped.startswith(("http://", "https://")):
        return False
    character_classes = sum(
        (
            any(character.islower() for character in stripped),
            any(character.isupper() for character in stripped),
            any(character.isdigit() for character in stripped),
            any(not character.isalnum() for character in stripped),
        )
    )
    return character_classes >= 2 and _shannon_entropy(stripped) >= 3.0


def scan_source_credentials(root: Path) -> list[SecretFinding]:
    """Find credential-shaped values in Following blowing-controlled source."""

    prefix_specs = (
        ("".join(("s", "k", "-", "t", "e", "a", "m", "o", "-")), 12, "team API key"),
        ("".join(("s", "k", "-")), 16, "API key"),
        ("".join(("g", "h", "p", "_")), 30, "GitHub token"),
        ("".join(("x", "o", "x", "b", "-")), 20, "Slack token"),
        ("".join(("A", "K", "I", "A")), 16, "AWS access key"),
    )
    prefix_patterns = tuple(
        (
            re.compile(re.escape(prefix) + rf"[A-Za-z0-9_-]{{{minimum},}}"),
            rule,
        )
        for prefix, minimum, rule in prefix_specs
    )
    bearer_pattern = re.compile(
        r"(?i)Authorization[\"']?\s*:\s*[\"']?Bearer\s+"
        r"([A-Za-z0-9._~+/=-]{20,})"
    )
    assignment_pattern = re.compile(
        r"(?i)[\"']?(?:api[_-]?key|access[_-]?token|secret|token|password)"
        r"[\"']?\s*[:=]\s*[\"']([^\"'\s,]{12,})[\"']"
    )

    root = root.resolve()
    findings: set[SecretFinding] = set()
    for path in iter_release_source_files(root):
        try:
            source = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        relative_path = path.resolve().relative_to(root).as_posix()

        for pattern, rule in prefix_patterns:
            for match in pattern.finditer(source):
                findings.add(
                    SecretFinding(
                        relative_path,
                        _line_number(source, match.start()),
                        rule,
                    )
                )
        for match in bearer_pattern.finditer(source):
            findings.add(
                SecretFinding(
                    relative_path,
                    _line_number(source, match.start()),
                    "Authorization bearer token",
                )
            )
        for match in assignment_pattern.finditer(source):
            if not _looks_like_unprefixed_secret(match.group(1)):
                continue
            findings.add(
                SecretFinding(
                    relative_path,
                    _line_number(source, match.start()),
                    "credential assigned to a sensitive field",
                )
            )

    return sorted(findings)


def find_runtime_credential_files(root: Path) -> list[str]:
    """Return exact project-owned credential files, excluding dependencies."""

    root = root.resolve()
    findings: set[str] = set()
    for relative in RUNTIME_CREDENTIAL_PATHS:
        if (root / Path(*relative.parts)).is_file():
            findings.add(relative.as_posix())

    for path in iter_release_eligible_files(root):
        if (
            path.suffix.lower() not in RUNTIME_CREDENTIAL_SUFFIXES
            and path.name.lower() not in RUNTIME_CREDENTIAL_BASENAMES
        ):
            continue
        findings.add(path.resolve().relative_to(root).as_posix())
    return sorted(findings)


def release_manifest(root: Path) -> tuple[PurePosixPath, ...]:
    """Return tracked release paths, or the explicit release-eligible fallback."""

    root = root.resolve()
    tracked = _git_tracked_files(root)
    if tracked:
        paths = (
            PurePosixPath(path.relative_to(root).as_posix())
            for path in tracked
        )
    else:
        paths = (
            PurePosixPath(path.relative_to(root).as_posix())
            for path in _walk_project_files(root)
        )
    return tuple(sorted(set(paths)))


def forbidden_release_paths(paths: Sequence[PurePosixPath]) -> list[str]:
    findings: set[str] = set()
    for raw_path in paths:
        path = PurePosixPath(raw_path)
        if path in FORBIDDEN_RELEASE_FILES:
            findings.add(path.as_posix())
            continue
        if any(part in FORBIDDEN_RELEASE_DIRECTORY_NAMES for part in path.parts[:-1]):
            findings.add(path.as_posix())
            continue
        if any(
            _is_within_prefix(path, prefix)
            for prefix in FORBIDDEN_RELEASE_PREFIXES
        ):
            findings.add(path.as_posix())
    return sorted(findings)


def release_security_findings(root: Path) -> list[str]:
    findings = [str(finding) for finding in scan_source_credentials(root)]
    findings.extend(
        f"{path} (runtime credential file)"
        for path in find_runtime_credential_files(root)
    )
    findings.extend(
        f"{path} (forbidden release path)"
        for path in forbidden_release_paths(release_manifest(root))
    )
    return sorted(findings)


if __name__ == "__main__":
    project_root = Path(__file__).resolve().parents[1]
    violations = release_security_findings(project_root)
    if violations:
        raise SystemExit("\n".join(violations))
    print("Release source secret scan: PASS")
