from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Mapping


@dataclass(frozen=True, slots=True)
class Section:
    section_id: str
    heading: str
    text: str
    page_number: int | None
    order: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "Section":
        page = value.get("page_number")
        return cls(
            section_id=str(value["section_id"]),
            heading=str(value.get("heading", "")),
            text=str(value.get("text", "")),
            page_number=int(page) if page is not None else None,
            order=int(value.get("order", 0)),
        )


@dataclass(frozen=True, slots=True)
class DocumentChunk:
    chunk_id: str
    document_id: str
    section: str
    text: str
    page: int | None
    token_estimate: int
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "DocumentChunk":
        page = value.get("page")
        metadata = value.get("metadata", {})
        return cls(
            chunk_id=str(value["chunk_id"]),
            document_id=str(value["document_id"]),
            section=str(value.get("section", "")),
            text=str(value.get("text", "")),
            page=int(page) if page is not None else None,
            token_estimate=int(value.get("token_estimate", 0)),
            metadata=dict(metadata) if isinstance(metadata, Mapping) else {},
        )


@dataclass(frozen=True, slots=True)
class ParsedDocument:
    document_id: str
    filename: str
    mime_type: str
    source_type: str
    title: str
    raw_text: str
    sections: list[Section]
    metadata: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["sections"] = [section.to_dict() for section in self.sections]
        return value

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "ParsedDocument":
        sections = value.get("sections", [])
        metadata = value.get("metadata", {})
        warnings = value.get("warnings", [])
        return cls(
            document_id=str(value["document_id"]),
            filename=str(value["filename"]),
            mime_type=str(value.get("mime_type", "application/octet-stream")),
            source_type=str(value.get("source_type", "upload")),
            title=str(value.get("title", "")),
            raw_text=str(value.get("raw_text", "")),
            sections=[Section.from_dict(item) for item in sections if isinstance(item, Mapping)],
            metadata=dict(metadata) if isinstance(metadata, Mapping) else {},
            warnings=[str(item) for item in warnings],
        )
