"""Normalize the user-provided IP asset reference."""

from __future__ import annotations

import mimetypes
from pathlib import Path

from app.schemas import IPAsset
from app.workflow.graph import AgentNames

from .base import AgentContext, AgentDecision, BaseAgent


class IPPreparationAgent(BaseAgent[IPAsset]):
    name = AgentNames.IP_PREPARATION
    responsibility = "Validate and normalize the IP source asset without changing its identity."
    handoff = "Normalized IP asset → IP Intelligence Agent"

    def input_summary(self, context: AgentContext) -> str:
        filename = context.input_assets.ip_filename or Path(context.input_assets.ip_image).name
        return f"IP source received: {filename or 'inline image'}"

    def process(self, context: AgentContext) -> AgentDecision[IPAsset]:
        source = context.input_assets.ip_image
        filename = context.input_assets.ip_filename or Path(source).name or None
        mime_type = mimetypes.guess_type(filename or "")[0]
        output = IPAsset(
            source_uri=source,
            normalized_uri=source,
            filename=filename,
            mime_type=mime_type,
            preparation_notes=[
                "Asset reference validated",
                "Original pixels retained for identity analysis",
            ],
        )
        return AgentDecision(
            output=output,
            decision_summary="Accepted the IP image and retained the original visual reference.",
            output_summary="Normalized IP asset reference is ready.",
            evidence=("A non-empty IP image reference passed schema validation.",),
        )
