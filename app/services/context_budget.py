"""Explicit context projections for latency-sensitive model calls.

Identity analysis and Guardian comparison intentionally keep rich structural
evidence. Planning agents receive only the fields they actually consume, so a
checkpoint can stay complete without repeatedly sending the whole checkpoint
back to the model.
"""

from __future__ import annotations

from typing import Any

from app.schemas import (
    BrandFeaturePool,
    CollaborationResearch,
    IPIdentityGrammar,
    IPIntelligenceResult,
)


def _items(values: list[Any], limit: int) -> list[Any]:
    return list(values[:limit])


def compact_collaboration_research(
    research: CollaborationResearch,
) -> dict[str, Any]:
    """Keep sourced patterns while bounding verbose search summaries."""

    return {
        "brand_name": research.brand_name,
        "patterns": _items(research.patterns, 8),
        "evidence_gap": research.evidence_gap,
        "warnings": _items(research.warnings, 5),
        "search_mode": research.search_mode,
        "results": [
            {
                "title": result.title,
                "url": result.url,
                "summary": result.summary[:500],
            }
            for result in research.results[:6]
        ],
    }


def compact_ip_for_brief(result: IPIntelligenceResult) -> dict[str, Any]:
    """Retain recognition evidence, omitting pose-engineering detail."""

    grammar = result.identity_grammar
    if grammar is None:
        raise ValueError("IP Identity Grammar is required")
    dna = result.ip_dna
    return {
        "ip_dna": {
            "character_type": dna.character_type,
            "silhouette": dna.silhouette,
            "head_body_relationship": dna.head_body_relationship,
            "ear_structure": dna.ear_structure,
            "eye_structure": dna.eye_structure,
            "nose_mouth": dna.nose_mouth,
            "body_proportions": dna.body_proportions,
            "line_language": dna.line_language,
            "immutable_features": dna.immutable_features,
            "mutable_features": dna.mutable_features,
            "identity_risks": dna.identity_risks,
        },
        "identity_grammar": {
            "core_identity_anchors": grammar.core_identity_anchors,
            "relational_geometry": grammar.relational_geometry,
            "proportion_signature": grammar.proportion_signature,
            "facial_grammar": grammar.facial_grammar,
            "ear_grammar": grammar.ear_grammar,
            "line_style_grammar": grammar.line_style_grammar,
            "mutable_features": grammar.mutable_features,
            "forbidden_drift": grammar.forbidden_drift,
        },
    }


def compact_brand_pool(pool: BrandFeaturePool) -> dict[str, Any]:
    """Keep usable brand cues and risks without repeating full evidence text."""

    return {
        "brand_name": pool.brand_name,
        "logo_features": pool.logo_features,
        "color_palette": pool.color_palette,
        "product_elements": pool.product_elements,
        "scene_elements": pool.scene_elements,
        "collaboration_patterns": _items(pool.collaboration_patterns, 8),
        "organic_fusion_guidance": _items(pool.organic_fusion_guidance, 8),
        "features": [
            {
                "feature_id": feature.feature_id,
                "name": feature.name,
                "category": feature.category,
                "recognition_strength": feature.recognition_strength,
                "integration_affordances": feature.integration_affordances,
                "preferred_uses": _items(feature.preferred_uses, 5),
                "avoid_uses": _items(feature.avoid_uses, 5),
                "attachment_targets": _items(feature.attachment_targets, 5),
                "occlusion_risk": feature.occlusion_risk,
                "identity_conflict_risk": feature.identity_conflict_risk,
            }
            for feature in pool.features[:8]
        ],
    }


def compact_identity_for_fusion(grammar: IPIdentityGrammar) -> dict[str, Any]:
    """Fusion chooses relationships; detailed pose grammar belongs downstream."""

    return {
        "core_identity_anchors": grammar.core_identity_anchors,
        "accessory_attachment_rules": grammar.accessory_attachment_rules,
        "clothing_adaptation_rules": grammar.clothing_adaptation_rules,
        "occlusion_rules": grammar.occlusion_rules,
        "forbidden_drift": grammar.forbidden_drift,
    }

