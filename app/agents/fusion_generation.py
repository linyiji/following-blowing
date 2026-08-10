"""Generate or revise a candidate through the configured ImageProvider."""

from __future__ import annotations

import base64
import json
from hashlib import sha256
from pathlib import Path
from typing import Any

from app.errors import ImageGenerationError
from app.schemas import (
    BrandFeaturePool,
    CandidateDesign,
    FusionStrategy,
    GuardianResult,
    IPAdaptationPlan,
    IPIntelligenceResult,
    TransformationLevel,
)
from app.workflow.graph import AgentNames

from .base import AgentContext, AgentDecision, BaseAgent


def _provider_image_uri(value: Any) -> str:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, str):
        return value
    if isinstance(value, bytes):
        encoded = base64.b64encode(value).decode("ascii")
        return f"data:image/png;base64,{encoded}"
    for attribute in ("local_file", "local_path", "absolute_path"):
        local_value = getattr(value, attribute, None)
        if local_value:
            return str(local_value)
    if hasattr(value, "path"):
        return str(value.path)
    if hasattr(value, "url"):
        return str(value.url)
    raise ImageGenerationError(
        "ImageProvider returned an unsupported image result",
        context={"result_type": type(value).__name__},
    )


class FusionGenerationAgent(BaseAgent[CandidateDesign]):
    name = AgentNames.FUSION_GENERATION
    prompt_id = "fusion_generation"
    responsibility = "Create a candidate image from the approved strategy and revision instructions."
    handoff = "Candidate image → IP Guardian Agent"

    def __init__(self, *, image_provider: Any | None = None) -> None:
        super().__init__()
        self.image_provider = image_provider

    def input_summary(self, context: AgentContext) -> str:
        strategy = context.require_output(AgentNames.FUSION_DECISION, FusionStrategy)
        return f"Generate '{strategy.theme_name}' revision {context.guardian_retries}."

    def process(self, context: AgentContext) -> AgentDecision[CandidateDesign]:
        strategy = context.require_output(AgentNames.FUSION_DECISION, FusionStrategy)
        grammar = context.require_output(
            AgentNames.IP_INTELLIGENCE, IPIntelligenceResult
        ).identity_grammar
        if grammar is None:
            raise ValueError("Fusion Generation requires IP Identity Grammar")
        adaptation = context.require_output(
            AgentNames.IP_ADAPTATION, IPAdaptationPlan
        )
        brand_features = context.require_output(
            AgentNames.BRAND_FEATURE, BrandFeaturePool
        )
        revision_instruction = ""
        previous_guardian = context.outputs.get(AgentNames.IP_GUARDIAN)
        if previous_guardian:
            result = GuardianResult.model_validate(previous_guardian)
            revision_instruction = result.revision_instruction or ""

        prompt = (
            f"{self.prompt_text}\n\n"
            f"{strategy.generation_prompt}\n\n"
            "FUSION_STRATEGY:\n"
            f"{json.dumps(strategy.model_dump(mode='json'), ensure_ascii=False)}\n\n"
            "FUSION_RELATIONSHIP:\n"
            f"{json.dumps(strategy.fusion_relationship.model_dump(mode='json'), ensure_ascii=False)}\n\n"
            "IP_IDENTITY_GRAMMAR (identity rules, not a frozen pose):\n"
            f"{json.dumps(grammar.model_dump(mode='json'), ensure_ascii=False)}\n\n"
            "IP_ADAPTATION_PLAN:\n"
            f"{json.dumps(adaptation.model_dump(mode='json'), ensure_ascii=False)}\n\n"
            "BRAND_FEATURE_POOL (apply as textual design constraints; the brand "
            "reference image is not a default edit input):\n"
            f"{json.dumps(brand_features.model_dump(mode='json'), ensure_ascii=False)}\n\n"
            "USER_INTENT_CONSTRAINTS:\n"
            f"{json.dumps(context.user_intent.prioritized_constraints(), ensure_ascii=False)}"
        )
        if adaptation.transformation_level == TransformationLevel.HIGH:
            prompt += (
                "\n\nHIGH TRANSFORMATION REQUIREMENT: Re-pose the character. Do not simply "
                "overlay brand assets on the original pose. Reconstruct the pose while preserving "
                "the IP Identity Grammar."
            )
        if revision_instruction:
            prompt += f"\n\nRevision required: {revision_instruction}"
            if previous_guardian:
                prompt += (
                    "\nRevision correction groups:\n"
                    + json.dumps(
                        {
                            "identity_corrections": result.identity_corrections,
                            "pose_corrections": result.pose_corrections,
                            "brand_corrections": result.brand_corrections,
                            "style_corrections": result.style_corrections,
                        },
                        ensure_ascii=False,
                    )
                )
        prompt += (
            f"\n\nNegative constraints: {strategy.negative_prompt}; "
            + "; ".join(adaptation.negative_constraints)
        )

        warnings: list[str] = []
        provider_name = "deterministic-fallback"
        if self.image_provider is not None:
            provider_name = type(self.image_provider).__name__
            try:
                multi_reference = bool(
                    getattr(self.image_provider, "multi_reference_image_edit", False)
                )
                references = [context.input_assets.ip_image]
                if multi_reference:
                    references.append(context.input_assets.brand_image)
                raw_image = self.image_provider.edit_with_reference(
                    reference_images=references,
                    prompt=prompt,
                    output_path=None,
                )
                image_uri = _provider_image_uri(raw_image)
            except ImageGenerationError:
                raise
            except Exception as exc:
                raise ImageGenerationError(
                    "Candidate image generation failed",
                    context={"provider_type": provider_name},
                ) from exc
        else:
            image_uri = "assets/demo/final_result.png"
            warnings.append(
                "No ImageProvider was injected; using the packaged demo image reference."
            )

        revision = context.guardian_retries
        candidate_seed = f"{context.run_id}:{revision}:{prompt}".encode("utf-8")
        candidate_id = f"candidate-{sha256(candidate_seed).hexdigest()[:12]}"

        artifact_metadata = (
            raw_image.model_dump(mode="json")
            if self.image_provider is not None and hasattr(raw_image, "model_dump")
            else None
        )
        output = CandidateDesign(
            candidate_id=candidate_id,
            image_uri=image_uri,
            theme_name=strategy.theme_name,
            fusion_logic=strategy.fusion_logic,
            design_tags=strategy.design_tags,
            generation_prompt=prompt,
            revision_number=revision,
            metadata={
                "image_provider": provider_name,
                "image_provider_used": self.image_provider is not None,
                "revision_instruction_applied": revision_instruction,
                "reference_image_count": (
                    len(references) if self.image_provider is not None else 0
                ),
                "multi_reference_image_edit": (
                    bool(getattr(self.image_provider, "multi_reference_image_edit", False))
                    if self.image_provider is not None
                    else False
                ),
                "multi_reference_image_edit_status": (
                    str(
                        getattr(
                            self.image_provider,
                            "multi_reference_image_edit_status",
                            "UNVERIFIED",
                        )
                    )
                    if self.image_provider is not None
                    else "UNVERIFIED"
                ),
                "image_artifact": artifact_metadata,
            },
        )
        return AgentDecision(
            output=output,
            decision_summary=(
                "Generated a revised candidate using the Guardian instruction."
                if revision_instruction
                else "Generated the first candidate from the approved fusion strategy."
            ),
            output_summary=f"Candidate {candidate_id}, revision {revision}, is ready for Guardian review.",
            evidence=(
                f"Image provider: {provider_name}",
                f"Target pose: {adaptation.target_pose}",
                f"Fusion depth: {strategy.fusion_relationship.fusion_depth.value}",
                strategy.negative_prompt,
            ),
            warnings=tuple(warnings),
        )
