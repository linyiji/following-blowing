from __future__ import annotations

import base64
import json
import os
import re
import tempfile
import uuid
from dataclasses import asdict, is_dataclass
from datetime import date, datetime, timezone
from enum import Enum
from pathlib import Path
from threading import RLock
from typing import Any, Iterable, Mapping

from app.config import PROJECT_ROOT


_RUN_ID = re.compile(r"^run[-_][A-Za-z0-9_-]{8,80}$")
_SAFE_PART = re.compile(r"[^A-Za-z0-9._-]+")
_SECRET_KEYS = {"api_key", "apikey", "authorization", "password", "secret", "access_token"}


DEFAULT_GRAPH: dict[str, set[str]] = {
    "ip_preparation": {"ip_intelligence"},
    "ip_intelligence": {"creative_brief"},
    "brand_intelligence": {"brand_collaboration"},
    "brand_collaboration": {"brand_feature"},
    "brand_feature": {"creative_brief"},
    "creative_brief": {"fusion_decision"},
    "fusion_decision": {"ip_adaptation"},
    "ip_adaptation": {"fusion_generation"},
    "fusion_generation": {"ip_guardian"},
    "ip_guardian": {"ranking"},
    "ranking": {"design_package"},
}

FIELD_ROOTS: dict[str, set[str]] = {
    "ip_asset_id": {"ip_preparation"},
    "brand_asset_id": {"brand_intelligence"},
    "selected_goals": {"creative_brief"},
    "goal_text": {"creative_brief"},
    "ai_supplement": {"creative_brief"},
    "ai_suggestion": {"creative_brief"},
    "user_intent": {"creative_brief"},
}


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def _canonical_agent_name(value: str) -> str:
    normalized = _SAFE_PART.sub("_", value.strip().lower()).strip("._")
    if normalized.endswith("_agent"):
        normalized = normalized[: -len("_agent")]
    # UI labels may include an ordinal prefix such as "01 IP Preparation".
    normalized = re.sub(r"^\d+_", "", normalized)
    return normalized


def _jsonable(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return _jsonable(value.model_dump(mode="json"))
    if hasattr(value, "dict") and callable(value.dict):
        return _jsonable(value.dict())
    if is_dataclass(value):
        return _jsonable(asdict(value))
    if isinstance(value, Mapping):
        result: dict[str, Any] = {}
        for key, item in value.items():
            name = str(key)
            lowered = name.lower()
            if lowered in _SECRET_KEYS or lowered.endswith("_api_key"):
                result[name] = "[REDACTED]"
            else:
                result[name] = _jsonable(item)
        return result
    if isinstance(value, (list, tuple, set, frozenset)):
        return [_jsonable(item) for item in value]
    if isinstance(value, Enum):
        return _jsonable(value.value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, bytes):
        return {"encoding": "base64", "data": base64.b64encode(value).decode("ascii")}
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


class LocalRunRepository:
    """Durable JSON checkpoints and artifacts for local/Streamlit deployment."""

    ARTIFACT_DIRECTORIES = ("input", "documents", "agents", "candidates", "guardian", "output")

    def __init__(self, root: Path | str | None = None) -> None:
        self.root = Path(root or PROJECT_ROOT / "data" / "runs").resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self._lock = RLock()

    @staticmethod
    def new_run_id() -> str:
        return f"run_{uuid.uuid4().hex}"

    @staticmethod
    def _validate_run_id(run_id: str) -> None:
        if not _RUN_ID.fullmatch(run_id):
            raise ValueError("Invalid run_id")

    def run_dir(self, run_id: str) -> Path:
        self._validate_run_id(run_id)
        return self.root / run_id

    def ensure_artifact_layout(self, run_id: str) -> Path:
        path = self.run_dir(run_id)
        path.mkdir(parents=True, exist_ok=True)
        for name in self.ARTIFACT_DIRECTORIES:
            (path / name).mkdir(exist_ok=True)
        return path

    @staticmethod
    def _atomic_json(path: Path, value: Any) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(_jsonable(value), ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8")
        with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as handle:
            temporary = Path(handle.name)
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        temporary.replace(path)

    def _run_path(self, run_id: str) -> Path:
        return self.run_dir(run_id) / "run.json"

    def create_run(self, run: Any | None = None, **fields: Any) -> dict[str, Any]:
        supplied = _jsonable(run) if run is not None else {}
        if supplied is None:
            supplied = {}
        if not isinstance(supplied, Mapping):
            raise TypeError("run must be a model, dataclass, or mapping")
        data = dict(supplied)
        data.update(_jsonable(fields))
        run_id = str(data.get("run_id") or self.new_run_id())
        self._validate_run_id(run_id)
        now = _utcnow()
        defaults: dict[str, Any] = {
            "run_id": run_id,
            "created_at": now,
            "updated_at": now,
            "status": "CREATED",
            "workflow_schema_version": 2,
            "app_name": None,
            "competition_mode": False,
            "provider_mode": "unknown",
            "search_mode": "unknown",
            "image_provider_verified": False,
            "multi_reference_image_edit": "UNVERIFIED",
            "started_at": None,
            "completed_at": None,
            "ip_asset_id": None,
            "brand_asset_id": None,
            "selected_goals": [],
            "goal_text": "",
            "ai_supplement": None,
            "current_agent": None,
            "current_step": 0,
            "agent_results": {},
            "guardian_retry_count": 0,
            "final_candidate_id": None,
            "ranking_result": None,
            "design_package_id": None,
            "error": None,
            "multimodal_calls": 0,
            "image_generation_calls": 0,
            "search_calls": 0,
            "input_tokens": 0,
            "output_tokens": 0,
            "estimated_cost": 0.0,
            "guardian_regenerations": 0,
        }
        defaults.update(data)
        defaults["run_id"] = run_id
        with self._lock:
            self.ensure_artifact_layout(run_id)
            if self._run_path(run_id).exists():
                raise FileExistsError(f"Workflow run already exists: {run_id}")
            self._atomic_json(self._run_path(run_id), defaults)
            self._atomic_json(self.run_dir(run_id) / "workflow.json", {"run_id": run_id, "checkpoint": None})
        return self.get_run(run_id)

    def get_run(self, run_id: str, *, model_cls: type | None = None) -> Any:
        path = self._run_path(run_id)
        if not path.is_file():
            raise FileNotFoundError(f"Workflow run not found: {run_id}")
        value = json.loads(path.read_text(encoding="utf-8"))
        if model_cls is None:
            return value
        if hasattr(model_cls, "model_validate"):
            return model_cls.model_validate(value)
        if hasattr(model_cls, "parse_obj"):
            return model_cls.parse_obj(value)
        return model_cls(**value)

    def update_run(self, run_id: str, run: Any | None = None, **updates: Any) -> dict[str, Any]:
        with self._lock:
            current = self.get_run(run_id)
            if run is not None:
                replacement = _jsonable(run)
                if not isinstance(replacement, Mapping):
                    raise TypeError("run must be a model, dataclass, or mapping")
                current.update(dict(replacement))
            current.update(_jsonable(updates))
            current["run_id"] = run_id
            current["updated_at"] = _utcnow()
            self._atomic_json(self._run_path(run_id), current)
        return self.get_run(run_id)

    def save_agent_result(self, run_id: str, agent_name: str, result: Any) -> Path:
        safe_name = _SAFE_PART.sub("_", agent_name.strip().lower()).strip("._")
        if not safe_name:
            raise ValueError("agent_name is required")
        path = self.run_dir(run_id) / "agents" / f"{safe_name}.json"
        value = _jsonable(result)
        with self._lock:
            self.ensure_artifact_layout(run_id)
            self._atomic_json(path, value)
            run = self.get_run(run_id)
            agent_results = run.get("agent_results")
            if not isinstance(agent_results, dict):
                agent_results = {}
            agent_results[agent_name] = value
            self.update_run(run_id, agent_results=agent_results, current_agent=agent_name)
        return path

    def save_checkpoint(self, run_id: str, snapshot: Any) -> Path:
        path = self.run_dir(run_id) / "workflow.json"
        value = _jsonable(snapshot)
        with self._lock:
            self.ensure_artifact_layout(run_id)
            schema_version = (
                value.get("workflow_schema_version", 1)
                if isinstance(value, Mapping)
                else 1
            )
            self._atomic_json(
                path,
                {
                    "run_id": run_id,
                    "saved_at": _utcnow(),
                    "workflow_schema_version": schema_version,
                    "checkpoint": value,
                },
            )
            self.update_run(
                run_id,
                workflow_schema_version=schema_version,
                workflow_snapshot=value,
            )
        return path

    def get_checkpoint(self, run_id: str) -> Any:
        path = self.run_dir(run_id) / "workflow.json"
        if not path.is_file():
            return None
        return json.loads(path.read_text(encoding="utf-8")).get("checkpoint")

    def write_artifact(self, run_id: str, relative_path: Path | str, data: bytes | str | Any) -> Path:
        run_path = self.ensure_artifact_layout(run_id).resolve()
        relative = Path(relative_path)
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError("Artifact path must be relative and cannot traverse directories")
        destination = (run_path / relative).resolve()
        if run_path not in destination.parents:
            raise ValueError("Artifact path escaped the run directory")
        destination.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(data, bytes):
            payload = data
        elif isinstance(data, str):
            payload = data.encode("utf-8")
        else:
            payload = json.dumps(_jsonable(data), ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8")
        with tempfile.NamedTemporaryFile(dir=destination.parent, delete=False) as handle:
            temporary = Path(handle.name)
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        temporary.replace(destination)
        return destination

    def invalidate_dependencies(
        self,
        run_id: str,
        changed_fields: str | Iterable[str],
        *,
        graph: Mapping[str, Iterable[str]] | None = None,
    ) -> list[str]:
        fields = {changed_fields} if isinstance(changed_fields, str) else set(changed_fields)
        roots = set().union(*(FIELD_ROOTS.get(field, set()) for field in fields)) if fields else set()
        adjacency = {key: set(value) for key, value in (graph or DEFAULT_GRAPH).items()}
        invalidated = set(roots)
        queue = list(roots)
        while queue:
            node = queue.pop(0)
            for dependent in adjacency.get(node, set()):
                if dependent not in invalidated:
                    invalidated.add(dependent)
                    queue.append(dependent)
        if not invalidated:
            return []
        run = self.get_run(run_id)
        results = run.get("agent_results", {})
        if isinstance(results, dict):
            for key in list(results):
                normalized = _canonical_agent_name(key)
                if normalized in invalidated:
                    results.pop(key, None)
        event = {
            "changed_fields": sorted(fields),
            "invalidated_agents": sorted(invalidated),
            "invalidated_at": _utcnow(),
        }
        history = run.get("invalidation_history", [])
        if not isinstance(history, list):
            history = []
        history.append(event)
        reset: dict[str, Any] = {
            "agent_results": results,
            "invalidation_history": history,
            "status": "READY",
            "current_agent": None,
            "error": None,
            "completed_at": None,
        }
        if "fusion_generation" in invalidated:
            reset.update(
                guardian_retry_count=0,
                final_candidate_id=None,
                final_image_path=None,
                ranking_result=None,
                design_package_id=None,
            )
        self.update_run(run_id, **reset)
        return sorted(invalidated)

    # Short alias used by callers that model input changes as invalidation.
    invalidate = invalidate_dependencies

    def list_runs(self) -> list[str]:
        return sorted(
            path.name
            for path in self.root.iterdir()
            if path.is_dir() and _RUN_ID.fullmatch(path.name)
        )


# Explicit interface name from the specification.
RunRepository = LocalRunRepository


__all__ = ["FIELD_ROOTS", "LocalRunRepository", "RunRepository"]
