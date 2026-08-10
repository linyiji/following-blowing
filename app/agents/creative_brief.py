"""Merge both branches and user intent into a prioritized creative brief."""

from __future__ import annotations

from app.schemas import (
    BrandFeaturePool,
    CreativeBrief,
    IPIntelligenceResult,
    TransformationLevel,
)
from app.workflow.graph import AgentNames

from .base import AgentContext, AgentDecision, BaseAgent


class CreativeBriefAgent(BaseAgent[CreativeBrief]):
    name = AgentNames.CREATIVE_BRIEF
    prompt_id = "creative_brief"
    responsibility = "Merge IP identity, brand features, and user intent in the mandated priority order."
    handoff = "Prioritized Creative Brief → Fusion Decision Agent"

    def input_summary(self, context: AgentContext) -> str:
        return (
            f"Merge IP DNA, brand feature pool, {len(context.user_intent.selected_goals)} "
            "selected goal(s), user text, and any adopted AI suggestion."
        )

    def process(self, context: AgentContext) -> AgentDecision[CreativeBrief]:
        ip_result = context.require_output(
            AgentNames.IP_INTELLIGENCE, IPIntelligenceResult
        )
        brand_pool = context.require_output(AgentNames.BRAND_FEATURE, BrandFeaturePool)
        grammar = ip_result.identity_grammar
        if grammar is None:
            raise ValueError("Creative Brief requires IP Identity Grammar")
        intent = context.user_intent
        priorities = intent.prioritized_constraints()
        ai_contribution = intent.adopted_suggestion_text()
        objective = intent.goal_text or "Create a recognizable, commercially usable IP × Brand collaboration."

        must_include: list[str] = []
        if intent.goal_text:
            must_include.append(f"User direction: {intent.goal_text}")
        must_include.extend(f"Selected goal: {goal}" for goal in intent.selected_goals)
        if ai_contribution:
            must_include.append(f"Adopted AI supplement: {ai_contribution}")
        if not must_include:
            must_include.append("Balanced character-and-brand collaboration key visual")

        action_terms = ("坐", "站", "跑", "挥", "拿", "抱", "转身", "侧身", "正面", "3/4")
        if any(term in intent.goal_text for term in action_terms):
            transformation_level = TransformationLevel.HIGH
        elif {"服装融合", "产品元素"}.intersection(intent.selected_goals):
            transformation_level = TransformationLevel.MEDIUM
        else:
            transformation_level = TransformationLevel.LOW
        desired_action = (
            intent.goal_text
            if any(term in intent.goal_text for term in action_terms)
            else (
                "hold and interact with a selected brand product"
                if "产品元素" in intent.selected_goals
                else "perform a friendly brand-relevant greeting"
            )
        )

        demo_output = CreativeBrief(
            theme_name="快乐好朋友联名计划",
            objective=objective,
            priority_stack=priorities,
            must_include=must_include,
            must_preserve=grammar.core_identity_anchors,
            creative_direction=(
                f"Make {brand_pool.brand_name} part of the character's behavior, product interaction, "
                "role, apparel, or scene while the IP remains recognizable through its grammar."
            ),
            ai_contribution=ai_contribution,
            evidence=[
                "User free text has highest priority",
                "Selected goals have second priority",
                "Only explicitly adopted AI suggestions have third priority",
                *brand_pool.evidence,
            ],
            desired_character_role="brand-world participant rather than a passive logo carrier",
            desired_action=desired_action,
            desired_interaction="interact naturally with a product, role, apparel, or environment",
            desired_view="choose the clearest view for the target action",
            transformation_level=transformation_level,
        )
        if self.ai_provider is None:
            raise RuntimeError("Creative Brief requires an AI provider")
        output = self.ai_provider.generate_structured(
            prompt=self.prompt_text,
            response_model=CreativeBrief,
            context={
                "user_free_text": intent.goal_text,
                "user_selected_goals": list(intent.selected_goals),
                "adopted_ai_supplement": ai_contribution,
                "ip_dna": ip_result.ip_dna.model_dump(mode="json"),
                "ip_identity_grammar": grammar.model_dump(mode="json"),
                "brand_feature_pool": brand_pool.model_dump(mode="json"),
            },
            model_role="main",
            demo_output=demo_output.model_dump(mode="json"),
        )
        if not isinstance(output, CreativeBrief):
            output = CreativeBrief.model_validate(output)

        # Enforce the conflict hierarchy in Python after generation as well as in the prompt.
        generated_additions = [item for item in output.must_include if item not in must_include]
        preserved = list(
            dict.fromkeys([*grammar.core_identity_anchors, *output.must_preserve])
        )
        evidence = list(
            dict.fromkeys(
                [
                    "Priority enforced: user free text > user selection > adopted AI supplement",
                    *output.evidence,
                    *brand_pool.evidence,
                ]
            )
        )
        output = output.model_copy(
            update={
                "objective": objective if intent.goal_text else output.objective,
                "priority_stack": priorities,
                "must_include": [*must_include, *generated_additions],
                "must_preserve": preserved,
                "ai_contribution": ai_contribution,
                "evidence": evidence,
                "desired_action": (
                    desired_action if intent.goal_text and any(
                        term in intent.goal_text for term in action_terms
                    ) else output.desired_action
                ),
                "transformation_level": (
                    TransformationLevel.HIGH
                    if intent.goal_text and any(
                        term in intent.goal_text for term in action_terms
                    )
                    else output.transformation_level
                ),
            }
        )
        warnings: tuple[str, ...] = ()
        if intent.ai_suggestion is not None and not intent.ai_suggestion_adopted:
            warnings = ("Unadopted AI suggestion was intentionally excluded from the brief.",)
        return AgentDecision(
            output=output,
            decision_summary="Merged constraints in user text > selected goals > adopted AI supplement order.",
            output_summary=f"Terra creative brief '{output.theme_name}' is ready.",
            evidence=tuple(output.evidence),
            warnings=warnings,
        )
