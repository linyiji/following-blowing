from __future__ import annotations

import hashlib
import math

from .models import DocumentChunk, ParsedDocument


class DocumentChunker:
    def __init__(self, *, max_chars: int = 2_500, overlap_chars: int = 200) -> None:
        if max_chars < 100:
            raise ValueError("max_chars must be at least 100")
        if overlap_chars < 0 or overlap_chars >= max_chars:
            raise ValueError("overlap_chars must be non-negative and smaller than max_chars")
        self.max_chars = max_chars
        self.overlap_chars = overlap_chars

    def chunk(self, document: ParsedDocument) -> list[DocumentChunk]:
        chunks: list[DocumentChunk] = []
        for section in document.sections:
            text = section.text.strip()
            if not text:
                continue
            start = 0
            part_index = 0
            while start < len(text):
                end = min(len(text), start + self.max_chars)
                if end < len(text):
                    boundary = text.rfind("\n", start, end)
                    if boundary <= start + self.max_chars // 2:
                        boundary = text.rfind(" ", start, end)
                    if boundary > start:
                        end = boundary
                value = text[start:end].strip()
                if value:
                    seed = f"{document.document_id}:{section.section_id}:{part_index}:{value}".encode("utf-8")
                    digest = hashlib.sha256(seed).hexdigest()[:20]
                    chunks.append(
                        DocumentChunk(
                            chunk_id=f"chunk_{digest}",
                            document_id=document.document_id,
                            section=section.heading or section.section_id,
                            text=value,
                            page=section.page_number,
                            token_estimate=max(1, math.ceil(len(value) / 4)),
                            metadata={
                                "section_id": section.section_id,
                                "section_order": section.order,
                                "part_index": part_index,
                            },
                        )
                    )
                if end >= len(text):
                    break
                start = max(start + 1, end - self.overlap_chars)
                part_index += 1
        return chunks


__all__ = ["DocumentChunker"]
