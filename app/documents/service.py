from __future__ import annotations

from pathlib import Path
from typing import Any, BinaryIO

from app.config import PROJECT_ROOT

from .chunker import DocumentChunker
from .models import DocumentChunk, ParsedDocument
from .reader import DocumentReader
from .repository import DocumentRepository, LocalDocumentRepository


class DocumentService:
    """The only document ingestion entry point for agents and providers."""

    def __init__(
        self,
        reader: DocumentReader | None = None,
        chunker: DocumentChunker | None = None,
        repository: DocumentRepository | None = None,
    ) -> None:
        self.reader = reader or DocumentReader()
        self.chunker = chunker or DocumentChunker()
        self.repository = repository or LocalDocumentRepository(PROJECT_ROOT / "data" / "documents")

    def ingest(
        self,
        file: bytes | bytearray | Path | str | BinaryIO | Any,
        *,
        filename: str | None = None,
        source_type: str = "upload",
        mime_type: str | None = None,
    ) -> ParsedDocument:
        document = self.reader.read(
            file,
            filename=filename,
            source_type=source_type,
            mime_type=mime_type,
        )
        chunks = self.chunker.chunk(document)
        self.repository.save(document, chunks)
        return document

    def get(self, document_id: str) -> ParsedDocument:
        return self.repository.get(document_id)

    def get_chunks(self, document_id: str) -> list[DocumentChunk]:
        return self.repository.get_chunks(document_id)


__all__ = ["DocumentService"]
