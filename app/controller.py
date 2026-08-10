"""Application-level orchestration used by the thin Streamlit entry point.

The controller binds providers to a durable run, checkpoints every single
agent transition, and exposes a browser-safe view model.  It deliberately does
not import Streamlit so workflow behavior remains testable outside the UI.
"""

from __future__ import annotations

import base64
import mimetypes
import re
from pathlib import Path
from typing import Any, Mapping, Sequence

from pydantic import BaseModel, Field

from app.assets import AssetService, LocalAssetStorage, StoredAsset
from app.config import AppSettings
from app.providers import (
    AIProvider,
    ImageProvider,
    ProviderFactory,
    SearchProvider,
)
from app.schemas import (
    CandidateDesign,
    DesignPackage,
    GuardianResult,
    GuardianVerdict,
    InputAssets,
    RankingResult,
    UserIntent,
    WorkflowSnapshot,
    WorkflowStatus,
)
from app.services.export_service import ExportService
from app.services.image_service import ImageService
from app.services.run_service import LocalRunRepository
from app.workflow.engine import WorkflowEngine
from app.workflow.engine import CURRENT_WORKFLOW_SCHEMA_VERSION
from app.workflow.graph import AgentNames


_SAFE_SLUG = re.compile(r"[^a-z0-9]+")
_SENSITIVE_FIELD = re.compile(
    r"(?:api[_-]?key|authorization|password|secret|access[_-]?token)", re.IGNORECASE
)
_WINDOWS_ABSOLUTE_PATH = re.compile(r"^[A-Za-z]:[\\/]")


class AISuggestion(BaseModel):
    version: int = Field(ge=1)
    primary_focus: str
    supporting_elements: list[str]
    story_direction: str
    identity_constraints: list[str]
    user_input_acknowledgement: str
    items: list[str] = Field(min_length=3)


class _RunImageProvider(ImageProvider):
    """Bind the provider interface expected by an Agent to one run artifact."""

    def __init__(self, service: ImageService, run_id: str) -> None:
        self.service = service
        self.run_id = run_id
        self.multi_reference_image_edit = bool(
            getattr(service.provider, "multi_reference_image_edit", False)
        )
        self.multi_reference_image_edit_status = str(
            getattr(service.provider, "multi_reference_image_edit_status", "UNVERIFIED")
        )

    def generate(self, *, prompt: str, output_path: Path | None = None, **kwargs: Any) -> Path:
        del output_path
        return self._generate_candidate(prompt=prompt, **kwargs)

    def edit_with_reference(
        self,
        *,
        reference_images: Sequence[Any],
        prompt: str,
        output_path: Path | None = None,
        **kwargs: Any,
    ) -> Path:
        del output_path
        return self._generate_candidate(
            prompt=prompt, reference_images=reference_images, **kwargs
        )

    def _generate_candidate(self, *, prompt: str, **kwargs: Any) -> Path:
        """Count attempted provider calls, including failed generations.

        ``ImageService`` records successful calls. A failed provider request must
        also consume the per-run budget; otherwise repeated manual retries can
        bypass the configured hard limit.
        """

        run = self.service.repository.get_run(self.run_id)
        before = int(run.get("image_generation_calls", 0))
        try:
            return self.service.generate_candidate(
                self.run_id, prompt=prompt, **kwargs
            )
        except Exception:
            if before < self.service.max_generations_per_run:
                current = self.service.repository.get_run(self.run_id)
                if int(current.get("image_generation_calls", 0)) == before:
                    self.service.repository.update_run(
                        self.run_id, image_generation_calls=before + 1
                    )
            raise


class _RunAIProvider(AIProvider):
    """Attach durable multimodal call accounting to one workflow run."""

    def __init__(
        self,
        provider: AIProvider,
        repository: LocalRunRepository,
        run_id: str,
    ) -> None:
        self.provider = provider
        self.repository = repository
        self.run_id = run_id

    def _record_call(self) -> None:
        run = self.repository.get_run(self.run_id)
        self.repository.update_run(
            self.run_id,
            multimodal_calls=int(run.get("multimodal_calls", 0)) + 1,
        )

    def analyze_multimodal(self, **kwargs: Any) -> Any:
        self._record_call()
        return self.provider.analyze_multimodal(**kwargs)

    def generate_structured(self, **kwargs: Any) -> Any:
        self._record_call()
        return self.provider.generate_structured(**kwargs)

    def generate_text(self, **kwargs: Any) -> str:
        self._record_call()
        return self.provider.generate_text(**kwargs)


class _RunSearchProvider(SearchProvider):
    def __init__(
        self,
        provider: SearchProvider,
        repository: LocalRunRepository,
        run_id: str,
    ) -> None:
        self.provider = provider
        self.repository = repository
        self.run_id = run_id
        self._mode = str(getattr(provider, "mode", "unverified"))

    @property
    def mode(self) -> str:
        return self._mode

    def search(self, query: str, *, limit: int = 5) -> list[Any]:
        run = self.repository.get_run(self.run_id)
        self.repository.update_run(
            self.run_id,
            search_calls=int(run.get("search_calls", 0)) + 1,
        )
        return self.provider.search(query, limit=limit)


class ApplicationController:
    def __init__(
        self,
        settings: AppSettings,
        *,
        repository: LocalRunRepository | None = None,
        asset_service: AssetService | None = None,
        ai_provider: AIProvider | None = None,
        image_provider: ImageProvider | None = None,
        search_provider: SearchProvider | None = None,
    ) -> None:
        self.settings = settings
        self.repository = repository or LocalRunRepository(settings.runs_dir)
        self.assets = asset_service or AssetService(
            LocalAssetStorage(settings.assets_dir)
        )
        factory = ProviderFactory(settings)
        self.ai_provider = ai_provider or factory.create_ai()
        self.image_provider = image_provider or factory.create_image()
        self.search_provider = search_provider or factory.create_search()
        actual_search_mode = str(
            getattr(self.search_provider, "mode", settings.search_mode)
        ).lower()
        self.search_mode = (
            actual_search_mode
            if actual_search_mode in {"demo", "live", "unverified"}
            else "unverified"
        )
        self.image_service = ImageService(
            self.image_provider,
            self.repository,
            max_generations_per_run=settings.max_image_generations_per_run,
        )
        self.export_service = ExportService(self.repository)

    def bootstrap_demo_assets(self) -> dict[str, StoredAsset]:
        demo_dir = self.settings.project_root / "assets" / "demo"
        return {
            "ip": self.assets.ingest_demo(demo_dir / "ip_reference.jpg"),
            "brand": self.assets.ingest_demo(demo_dir / "brand_reference.jpg"),
            "final": self.assets.ingest_demo(demo_dir / "final_result.png"),
            "guardian_rejected": self.assets.ingest_demo(
                demo_dir / "guardian_rejected.jpg"
            ),
        }

    def asset_payload(self, asset_id: str | None) -> dict[str, Any] | None:
        if not asset_id:
            return None
        asset = self.assets.get(asset_id)
        payload = asset.to_public_dict()
        payload["preview_url"] = self.assets.preview_data_uri(asset_id)
        return payload

    def create_ai_suggestion(
        self,
        *,
        selected_goals: Sequence[str],
        goal_text: str,
        version: int,
    ) -> dict[str, Any]:
        goals = list(selected_goals)
        primary = goals[0] if goals else "服装融合"
        supporting = goals[1:3] or ["品牌Logo", "品牌配色"]
        acknowledgement = (
            f"已吸收你的补充想法：{goal_text.strip()[:80]}"
            if goal_text.strip()
            else "自由输入为空，将以已选目标和资产分析继续补全。"
        )
        story = (
            "建立‘线条小狗成为快乐值班员’的轻量联名故事。"
            if "联名故事" in goals
            else "用轻量故事解释品牌元素，让融合自然且可商用。"
        )
        demo_output = {
            "version": version,
            "primary_focus": primary,
            "supporting_elements": supporting,
            "story_direction": story,
            "identity_constraints": [
                "保持二维极简线条语言",
                "锁定头部、耳朵、脸型与五官位置关系",
                "只在服装、帽子、配饰、手持物与场景层融合",
            ],
            "user_input_acknowledgement": acknowledgement,
            "items": [
                f"主要融合载体：{primary}；其余目标作为辅助层，不机械堆叠。",
                f"辅助识别：{'、'.join(supporting)}，优先落在服装、帽子或局部配饰。",
                story,
                "IP保护：禁止改动核心头部、耳朵、脸型、物种视觉与基础线条语言。",
                acknowledgement,
            ],
        }
        suggestion = self.ai_provider.generate_structured(
            prompt=(
                "生成结构化的 IP × Brand 联名设计补充建议。严格保持用户自由输入高于"
                "多选目标；AI 只能补充可选细节，不能覆盖、改写或弱化任何用户输入。"
            ),
            response_model=AISuggestion,
            context={
                "version": version,
                "selected_goals": goals,
                "user_free_text": goal_text.strip(),
            },
            model_role="fast",
            demo_output=demo_output,
        )
        if not isinstance(suggestion, AISuggestion):
            suggestion = AISuggestion.model_validate(suggestion)
        return suggestion.model_dump(mode="json")

    def start_workflow(
        self,
        *,
        ip_asset_id: str,
        brand_asset_id: str,
        selected_goals: Sequence[str],
        goal_text: str,
        ai_suggestion: Mapping[str, Any] | str | None,
        ai_suggestion_adopted: bool,
    ) -> WorkflowSnapshot:
        ip = self.assets.get(ip_asset_id)
        brand = self.assets.get(brand_asset_id)
        run_id = self.repository.new_run_id()
        self.repository.create_run(
            run_id=run_id,
            status="READY",
            ip_asset_id=ip_asset_id,
            brand_asset_id=brand_asset_id,
            selected_goals=list(selected_goals),
            goal_text=goal_text,
            ai_supplement=ai_suggestion if ai_suggestion_adopted else None,
            app_name=self.settings.app_name,
            competition_mode=self.settings.competition_mode,
            provider_mode=self.settings.provider_mode,
            search_mode=self.search_mode,
            image_provider_verified=self.settings.image_provider_verified,
            multi_reference_image_edit=(
                self.settings.multi_reference_image_edit_status
            ),
            workflow_schema_version=CURRENT_WORKFLOW_SCHEMA_VERSION,
        )
        self.repository.write_artifact(
            run_id, f"input/ip{ip.path.suffix.lower()}", ip.path.read_bytes()
        )
        self.repository.write_artifact(
            run_id, f"input/brand{brand.path.suffix.lower()}", brand.path.read_bytes()
        )
        input_assets = InputAssets(
            ip_image=str(ip.path),
            brand_image=str(brand.path),
            ip_filename=ip.metadata.safe_filename,
            brand_filename=brand.metadata.safe_filename,
            brand_name="麦当劳" if self.settings.demo_mode else "用户品牌",
            metadata={"ip_asset_id": ip_asset_id, "brand_asset_id": brand_asset_id},
        )
        user_intent = UserIntent(
            selected_goals=list(selected_goals),
            goal_text=goal_text,
            ai_suggestion=dict(ai_suggestion) if isinstance(ai_suggestion, Mapping) else ai_suggestion,
            ai_suggestion_adopted=ai_suggestion_adopted,
        )
        engine = self._engine(run_id)
        snapshot = engine.start(
            input_assets=input_assets,
            user_intent=user_intent,
            run_id=run_id,
        )
        self._persist_snapshot(snapshot, new_records=[])
        return snapshot

    def restore_snapshot(self, run_id: str) -> WorkflowSnapshot:
        checkpoint = self.repository.get_checkpoint(run_id)
        if checkpoint is None:
            raise FileNotFoundError(f"Workflow checkpoint not found: {run_id}")
        snapshot = WorkflowSnapshot.model_validate(checkpoint)
        if snapshot.workflow_schema_version < CURRENT_WORKFLOW_SCHEMA_VERSION:
            snapshot.compatibility_warnings = list(
                dict.fromkeys(
                    [
                        *snapshot.compatibility_warnings,
                        "legacy_workflow_schema_v1_audit_restore",
                        "execution_will_invalidate_missing_identity_grammar_or_adaptation",
                    ]
                )
            )
        return snapshot

    def advance_workflow(self, run_id: str) -> WorkflowSnapshot:
        before = self.restore_snapshot(run_id)
        engine = self._engine(run_id, before)
        execution_baseline = engine.snapshot
        assert execution_baseline is not None
        snapshot = engine.run_next_step()
        new_records = snapshot.execution_records[len(execution_baseline.execution_records) :]
        self._persist_snapshot(snapshot, new_records=new_records)
        return snapshot

    def retry_current_agent(self, run_id: str) -> WorkflowSnapshot:
        restored = self.restore_snapshot(run_id)
        engine = self._engine(run_id, restored)
        if restored.workflow_schema_version < CURRENT_WORKFLOW_SCHEMA_VERSION:
            # Execution restore has already converted the legacy failed state
            # into a canonical v2 RUNNING queue. Persist that migration first;
            # there is no longer a failed node to retry directly.
            migrated = engine.snapshot
            assert migrated is not None
            self._persist_snapshot(migrated, new_records=[])
            return migrated
        snapshot = engine.retry_current_agent()
        self._persist_snapshot(snapshot, new_records=[])
        return snapshot

    def invalidate_run(
        self,
        run_id: str,
        change: str,
        *,
        ip_asset_id: str | None = None,
        brand_asset_id: str | None = None,
        selected_goals: Sequence[str] | None = None,
        goal_text: str | None = None,
        ai_suggestion: Mapping[str, Any] | str | None = None,
        ai_suggestion_adopted: bool | None = None,
    ) -> WorkflowSnapshot:
        current = self.restore_snapshot(run_id)
        engine = self._engine(run_id, current)
        if change == "user_intent":
            intent = current.user_intent.model_copy(
                update={
                    "selected_goals": list(selected_goals or []),
                    "goal_text": goal_text or "",
                    "ai_suggestion": ai_suggestion,
                    "ai_suggestion_adopted": bool(ai_suggestion_adopted),
                }
            )
            snapshot = engine.invalidate("user_intent", new_user_intent=intent)
            fields: list[str] = ["selected_goals", "goal_text", "ai_supplement"]
            run_updates: dict[str, Any] = {
                "selected_goals": list(intent.selected_goals),
                "goal_text": intent.goal_text,
                "ai_supplement": (
                    intent.ai_suggestion if intent.ai_suggestion_adopted else None
                ),
            }
        elif change in {"ip_asset", "brand_asset"}:
            asset_id = ip_asset_id if change == "ip_asset" else brand_asset_id
            asset = self.assets.get(asset_id or "")
            artifact_role = "ip" if change == "ip_asset" else "brand"
            artifact = self.repository.write_artifact(
                run_id,
                f"input/{artifact_role}{asset.path.suffix.lower()}",
                asset.path.read_bytes(),
            )
            for stale in artifact.parent.glob(f"{artifact_role}.*"):
                if stale != artifact and stale.is_file():
                    stale.unlink()
            updates = (
                {"ip_image": str(asset.path), "ip_filename": asset.metadata.safe_filename}
                if change == "ip_asset"
                else {"brand_image": str(asset.path), "brand_filename": asset.metadata.safe_filename}
            )
            metadata = dict(current.input_assets.metadata)
            metadata["ip_asset_id" if change == "ip_asset" else "brand_asset_id"] = asset.asset_id
            updates["metadata"] = metadata
            replacement = current.input_assets.model_copy(update=updates)
            snapshot = engine.invalidate(change, new_input_assets=replacement)
            fields = ["ip_asset_id" if change == "ip_asset" else "brand_asset_id"]
            run_updates = {fields[0]: asset.asset_id}
        else:
            raise ValueError(f"Unsupported invalidation change: {change}")
        self.repository.invalidate_dependencies(run_id, fields)
        self.repository.update_run(run_id, **run_updates)
        self._persist_snapshot(snapshot, new_records=[])
        return snapshot

    def export_design_package(self, run_id: str) -> Path:
        snapshot = self.restore_snapshot(run_id)
        if snapshot.status != WorkflowStatus.COMPLETED:
            raise ValueError("Workflow must complete before export")
        try:
            guardian = GuardianResult.model_validate(
                snapshot.outputs[AgentNames.IP_GUARDIAN]
            )
            candidate = CandidateDesign.model_validate(
                snapshot.outputs[AgentNames.FUSION_GENERATION]
            )
            ranking = RankingResult.model_validate(snapshot.outputs[AgentNames.RANKING])
            package_contract = DesignPackage.model_validate(
                snapshot.outputs[AgentNames.DESIGN_PACKAGE]
            )
        except (KeyError, ValueError) as exc:
            raise ValueError("Completed workflow is missing a valid export artifact") from exc
        if guardian.verdict != GuardianVerdict.PASS:
            raise ValueError("Only a Guardian PASS result can be exported")
        if (
            snapshot.workflow_schema_version >= CURRENT_WORKFLOW_SCHEMA_VERSION
            and guardian.scoring_version != "pose_aware_grammar_v3"
        ):
            raise ValueError("Schema-v2 export requires a pose-aware Guardian result")
        if (
            snapshot.workflow_schema_version >= CURRENT_WORKFLOW_SCHEMA_VERSION
            and package_contract.package_schema_version < 2
        ):
            raise ValueError("Schema-v2 export requires a schema-v2 design package")
        if len({candidate.candidate_id, guardian.candidate_id, ranking.candidate_id}) != 1:
            raise ValueError("Export artifacts do not reference the same approved candidate")
        image = self._approved_image(snapshot, candidate)
        if image is None:
            raise FileNotFoundError("Final candidate image is missing")
        guide = self._design_guide(snapshot)
        prompt_trace = [
            {
                "agent_name": item.agent_name,
                "model_route": item.model_route,
                "model": item.model,
                "prompt_id": item.prompt_id,
                "prompt_version": item.prompt_version,
                "prompt_hash": item.prompt_hash,
                "retry_count": item.retry_count,
            }
            for item in snapshot.execution_records
            if item.prompt_version
        ]
        return self.export_service.create_design_package(
            run_id,
            result_image=image,
            creative_brief=snapshot.outputs.get(AgentNames.CREATIVE_BRIEF),
            ip_identity=snapshot.outputs.get(AgentNames.IP_INTELLIGENCE),
            ip_identity_grammar=(
                snapshot.outputs.get(AgentNames.IP_INTELLIGENCE, {}).get(
                    "identity_grammar"
                )
            ),
            brand_profile=snapshot.outputs.get(AgentNames.BRAND_INTELLIGENCE),
            brand_feature_pool=snapshot.outputs.get(AgentNames.BRAND_FEATURE),
            fusion_strategy=snapshot.outputs.get(AgentNames.FUSION_DECISION),
            ip_adaptation=snapshot.outputs.get(AgentNames.IP_ADAPTATION),
            guardian_report=snapshot.outputs.get(AgentNames.IP_GUARDIAN),
            ranking=ranking,
            workflow_trace=self._export_safe_value(
                snapshot.model_dump(mode="json"), run_id=run_id
            ),
            design_guide=guide,
            prompt_trace=prompt_trace,
            package_schema_version=package_contract.package_schema_version,
        )

    def public_snapshot(self, snapshot: WorkflowSnapshot | None) -> dict[str, Any] | None:
        if snapshot is None:
            return None
        records = [
            {
                "status": item.status.value,
                "agent_name": item.agent_name,
                "input_summary": item.input_summary,
                "decision_summary": item.decision_summary,
                "evidence": list(item.evidence),
                "output_summary": item.output_summary,
                "warnings": list(item.warnings),
                "duration_ms": item.duration_ms,
                "started_at": item.started_at.isoformat(),
                "completed_at": (
                    item.completed_at.isoformat() if item.completed_at else None
                ),
                "error": self._safe_error_text(item.error),
                "retryable": item.retryable,
                "retry_count": item.retry_count,
                "responsibility": item.responsibility,
                "handoff": item.handoff,
                "prompt_id": item.prompt_id,
                "prompt_version": item.prompt_version,
                "prompt_hash": item.prompt_hash,
                "model_route": item.model_route,
                "model": item.model,
            }
            for item in snapshot.execution_records
        ]
        try:
            run = self.repository.get_run(snapshot.run_id)
        except (FileNotFoundError, ValueError):
            run = {}
        return {
            "run_id": snapshot.run_id,
            "revision": snapshot.revision,
            "workflow_schema_version": snapshot.workflow_schema_version,
            "compatibility_warnings": list(snapshot.compatibility_warnings),
            "status": snapshot.status.value,
            "current_agent": snapshot.current_agent,
            "last_completed_agent": snapshot.last_completed_agent,
            "pending_agents": list(snapshot.pending_agents),
            "completed_agents": list(snapshot.completed_agents),
            "execution_records": records,
            "guardian_retries": snapshot.guardian_retries,
            "max_guardian_retries": snapshot.max_guardian_retries,
            "failed_agent": snapshot.failed_agent,
            "error": self._safe_error_text(snapshot.error),
            "started_at": snapshot.started_at.isoformat(),
            "updated_at": snapshot.updated_at.isoformat(),
            "completed_at": (
                snapshot.completed_at.isoformat() if snapshot.completed_at else None
            ),
            "competition_mode": bool(run.get("competition_mode", False)),
            "provider_mode": str(run.get("provider_mode") or "unknown"),
            "search_mode": str(run.get("search_mode") or "unknown"),
            "image_provider_verified": bool(
                run.get("image_provider_verified", False)
            ),
            "multi_reference_image_edit": str(
                run.get("multi_reference_image_edit") or "UNVERIFIED"
            ),
        }

    def result_payload(self, snapshot: WorkflowSnapshot | None) -> dict[str, Any] | None:
        if snapshot is None or snapshot.status != WorkflowStatus.COMPLETED:
            return None
        try:
            guardian = GuardianResult.model_validate(snapshot.outputs[AgentNames.IP_GUARDIAN])
            ranking = RankingResult.model_validate(snapshot.outputs[AgentNames.RANKING])
            candidate = CandidateDesign.model_validate(snapshot.outputs[AgentNames.FUSION_GENERATION])
        except (KeyError, ValueError):
            return None
        if (
            guardian.verdict != GuardianVerdict.PASS
            or len({candidate.candidate_id, guardian.candidate_id, ranking.candidate_id}) != 1
        ):
            return None
        final_image = self._approved_image(snapshot, candidate)
        if final_image is None:
            return None
        image_url = self._file_data_uri(final_image)
        if image_url is None:
            return None
        return {
            "theme_name": candidate.theme_name,
            "fusion_logic": candidate.fusion_logic,
            "design_tags": candidate.design_tags,
            "guardian": {
                "verdict": guardian.verdict.value,
                "score": guardian.score,
                "identity_score": guardian.identity_score,
                "findings": guardian.findings,
            },
            "ranking": ranking.model_dump(mode="json"),
            "image_url": image_url,
        }

    def _engine(
        self,
        run_id: str,
        checkpoint: WorkflowSnapshot | None = None,
    ) -> WorkflowEngine:
        ai = _RunAIProvider(self.ai_provider, self.repository, run_id)
        image = _RunImageProvider(self.image_service, run_id)
        search = _RunSearchProvider(self.search_provider, self.repository, run_id)
        return WorkflowEngine(
            ai_provider=ai,
            image_provider=image,
            search_provider=search,
            checkpoint=checkpoint,
            max_guardian_retries=self.settings.max_guardian_retries,
        )

    def _persist_snapshot(
        self,
        snapshot: WorkflowSnapshot,
        *,
        new_records: Sequence[Any],
    ) -> None:
        self._sanitize_snapshot_errors(snapshot)
        current_run = self.repository.get_run(snapshot.run_id)
        agent_results = {
            record.agent_name: record.model_dump(mode="json")
            for record in snapshot.execution_records
        }
        offset = len(snapshot.execution_records) - len(new_records)
        for index, record in enumerate(new_records, start=offset + 1):
            slug = _SAFE_SLUG.sub("_", record.agent_name.lower()).strip("_")
            # Materialize the structured Agent artifact before publishing the
            # completed checkpoint/run summary. A failed artifact write leaves
            # the prior durable checkpoint authoritative.
            self.repository.write_artifact(
                snapshot.run_id,
                f"agents/{slug}.json",
                record,
            )
            self.repository.write_artifact(
                snapshot.run_id,
                f"agents/{index:02d}_{slug}_attempt_{record.retry_count}.json",
                record,
            )
            if record.agent_name == AgentNames.IP_GUARDIAN:
                self.repository.write_artifact(
                    snapshot.run_id,
                    f"guardian/guardian_{record.retry_count + 1:02d}.json",
                    record.output,
                )
            agent_results[record.agent_name] = record.model_dump(mode="json")

        candidate_value = snapshot.outputs.get(AgentNames.FUSION_GENERATION)
        guardian_value = snapshot.outputs.get(AgentNames.IP_GUARDIAN)
        final_candidate_id: str | None = None
        final_image_path: str | None = None
        if candidate_value and guardian_value:
            candidate = CandidateDesign.model_validate(candidate_value)
            guardian = GuardianResult.model_validate(guardian_value)
            if (
                guardian.verdict == GuardianVerdict.PASS
                and guardian.candidate_id == candidate.candidate_id
            ):
                candidate_path = Path(candidate.image_uri)
                try:
                    candidate_exists = candidate_path.is_file()
                except OSError:
                    candidate_exists = False
                if candidate_exists:
                    suffix = candidate_path.suffix.lower() or ".png"
                    expected = (
                        self.repository.run_dir(snapshot.run_id)
                        / "output"
                        / f"result{suffix}"
                    )
                    if (
                        current_run.get("final_candidate_id") == candidate.candidate_id
                        and expected.is_file()
                    ):
                        final_image = expected
                    else:
                        final_image = None
                    if final_image is not None:
                        final_candidate_id = candidate.candidate_id
                        final_image_path = final_image.relative_to(
                            self.repository.run_dir(snapshot.run_id)
                        ).as_posix()

        ranking = snapshot.outputs.get(AgentNames.RANKING)
        prior_guardian_retries = int(current_run.get("guardian_retry_count", 0))
        guardian_regenerations = int(current_run.get("guardian_regenerations", 0))
        guardian_regenerations += max(
            0, snapshot.guardian_retries - prior_guardian_retries
        )
        # Checkpoint is the authority for Agent completion. Only after it is
        # durable do we bind/copy a newly approved final image and publish the
        # denormalized run summary.
        self.repository.save_checkpoint(snapshot.run_id, snapshot)
        if (
            final_candidate_id is None
            and candidate_value
            and guardian_value
        ):
            candidate = CandidateDesign.model_validate(candidate_value)
            guardian = GuardianResult.model_validate(guardian_value)
            candidate_path = Path(candidate.image_uri)
            try:
                candidate_ready = candidate_path.is_file()
            except OSError:
                candidate_ready = False
            if (
                guardian.verdict == GuardianVerdict.PASS
                and guardian.candidate_id == candidate.candidate_id
                and candidate_ready
            ):
                final_image = self.image_service.mark_final_candidate(
                    snapshot.run_id, candidate_path
                )
                final_candidate_id = candidate.candidate_id
                final_image_path = final_image.relative_to(
                    self.repository.run_dir(snapshot.run_id)
                ).as_posix()
        self.repository.update_run(
            snapshot.run_id,
            status=snapshot.status.value.upper(),
            current_agent=snapshot.current_agent,
            current_step=len(snapshot.execution_records),
            guardian_retry_count=snapshot.guardian_retries,
            guardian_regenerations=guardian_regenerations,
            final_candidate_id=final_candidate_id,
            final_image_path=final_image_path,
            ranking_result=ranking,
            design_package_id=(
                current_run.get("design_package_id")
                if (
                    snapshot.status == WorkflowStatus.COMPLETED
                    and AgentNames.DESIGN_PACKAGE in snapshot.outputs
                )
                else None
            ),
            error=snapshot.error,
            workflow_revision=snapshot.revision,
            workflow_schema_version=snapshot.workflow_schema_version,
            started_at=snapshot.started_at.isoformat(),
            completed_at=(
                snapshot.completed_at.isoformat() if snapshot.completed_at else None
            ),
            agent_results=agent_results,
        )

    def _approved_image(
        self,
        snapshot: WorkflowSnapshot,
        candidate: CandidateDesign,
    ) -> Path | None:
        """Return only the run-owned image bound to the approved candidate."""

        try:
            run = self.repository.get_run(snapshot.run_id)
            if run.get("final_candidate_id") != candidate.candidate_id:
                return None
            relative_value = run.get("final_image_path")
            if not relative_value:
                suffix = Path(candidate.image_uri).suffix.lower() or ".png"
                relative_value = f"output/result{suffix}"
            relative = Path(str(relative_value))
            if relative.is_absolute() or ".." in relative.parts:
                return None
            run_dir = self.repository.run_dir(snapshot.run_id).resolve()
            image = (run_dir / relative).resolve()
            if run_dir not in image.parents or not image.is_file():
                return None
            return image
        except (FileNotFoundError, OSError, ValueError):
            return None

    def _export_safe_value(self, value: Any, *, run_id: str) -> Any:
        """Remove credentials and machine-local absolute paths from exports."""

        if isinstance(value, Mapping):
            return {
                str(key): (
                    "[REDACTED]"
                    if _SENSITIVE_FIELD.search(str(key))
                    else self._export_safe_value(item, run_id=run_id)
                )
                for key, item in value.items()
            }
        if isinstance(value, (list, tuple, set, frozenset)):
            return [self._export_safe_value(item, run_id=run_id) for item in value]
        if isinstance(value, Path):
            value = str(value)
        if not isinstance(value, str):
            return value

        if not (Path(value).is_absolute() or _WINDOWS_ABSOLUTE_PATH.match(value)):
            return value
        path = Path(value)
        roots = (
            self.repository.run_dir(run_id).resolve(),
            self.settings.project_root.resolve(),
        )
        for root in roots:
            try:
                return path.resolve().relative_to(root).as_posix()
            except (OSError, ValueError):
                continue
        safe_name = value.replace("\\", "/").rsplit("/", 1)[-1]
        return f"[local-path]/{safe_name or 'file'}"

    @staticmethod
    def _safe_error_text(value: str | None) -> str | None:
        if not value:
            return value
        text = str(value)
        text = re.sub(
            r"(?i)(api[_-]?key|authorization|password|secret|access[_-]?token)"
            r"\s*[:=]\s*[^\s,;]+",
            r"\1=[REDACTED]",
            text,
        )
        text = re.sub(r"\bsk-[A-Za-z0-9_-]{8,}\b", "[REDACTED]", text)
        text = re.sub(
            r"(?<![:/\w])/(?:[^/\s'\"<>]+/)*[^/\s'\"<>]*",
            "[local-path]",
            text,
        )
        text = re.sub(
            r"\b[A-Za-z]:[\\/](?:[^\\/\s'\"<>]+[\\/])*[^\\/\s'\"<>]*",
            "[local-path]",
            text,
        )
        return text[:1000]

    def _sanitize_snapshot_errors(self, snapshot: WorkflowSnapshot) -> None:
        snapshot.error = self._safe_error_text(snapshot.error)
        for record in snapshot.execution_records:
            record.error = self._safe_error_text(record.error)

    @staticmethod
    def _file_data_uri(path: Path, *, max_bytes: int = 20 * 1024 * 1024) -> str | None:
        if not path.is_file() or path.stat().st_size > max_bytes:
            return None
        mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        return f"data:{mime};base64,{base64.b64encode(path.read_bytes()).decode('ascii')}"

    @staticmethod
    def _design_guide(snapshot: WorkflowSnapshot) -> str:
        brief = snapshot.outputs.get(AgentNames.CREATIVE_BRIEF, {})
        strategy = snapshot.outputs.get(AgentNames.FUSION_DECISION, {})
        guardian = snapshot.outputs.get(AgentNames.IP_GUARDIAN, {})
        adaptation = snapshot.outputs.get(AgentNames.IP_ADAPTATION, {})
        package = snapshot.outputs.get(AgentNames.DESIGN_PACKAGE, {})
        copy_description = str(package.get("copy_description", "")).strip()
        return (
            "# AI IP × Brand 联名设计指南\n\n"
            f"- Run ID: `{snapshot.run_id}`\n"
            f"- 主题：{brief.get('theme_name', strategy.get('theme_name', '联名方案'))}\n"
            f"- 融合逻辑：{strategy.get('fusion_logic', '')}\n"
            f"- 目标动作：{adaptation.get('target_action', '')}\n"
            f"- 目标姿势：{adaptation.get('target_pose', '')}\n"
            f"- Guardian：{guardian.get('verdict', '')} / "
            f"{guardian.get('identity_score', guardian.get('score', ''))}\n\n"
            "## 联名文案\n\n"
            f"{copy_description}\n\n"
            "## IP Identity Grammar\n\n"
            "姿势、视角、肢体、表情、服装与互动可以根据目标自然改变；身份通过核心锚点、"
            "关系几何、比例特征、面部语法、耳朵语法与线条语法保持可识别。\n"
        )


__all__ = ["AISuggestion", "ApplicationController"]
