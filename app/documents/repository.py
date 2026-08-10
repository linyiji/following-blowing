from __future__ import annotations

import json
import os
import re
import tempfile
from pathlib import Path
from threading import RLock
from typing import Protocol

from .models import DocumentChunk, ParsedDocument


_DOCUMENT_ID = re.compile(r"^doc_[0-9a-f]{24}$")


class DocumentRepository(Protocol):
    def save(self, document: ParsedDocument, chunks: list[DocumentChunk]) -> None: ...
    def get(self, document_id: str) -> ParsedDocument: ...
    def get_chunks(self, document_id: str) -> list[DocumentChunk]: ...


class InMemoryDocumentRepository:
    def __init__(self) -> None:
        self._documents: dict[str, ParsedDocument] = {}
        self._chunks: dict[str, list[DocumentChunk]] = {}

    def save(self, document: ParsedDocument, chunks: list[DocumentChunk]) -> None:
        self._documents[document.document_id] = document
        self._chunks[document.document_id] = list(chunks)

    def get(self, document_id: str) -> ParsedDocument:
        try:
            return self._documents[document_id]
        except KeyError as exc:
            raise FileNotFoundError(f"Document not found: {document_id}") from exc

    def get_chunks(self, document_id: str) -> list[DocumentChunk]:
        if document_id not in self._documents:
            raise FileNotFoundError(f"Document not found: {document_id}")
        return list(self._chunks.get(document_id, []))

    def delete(self, document_id: str) -> None:
        self._documents.pop(document_id, None)
        self._chunks.pop(document_id, None)


class LocalDocumentRepository:
    def __init__(self, root: Path | str) -> None:
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self._lock = RLock()

    @staticmethod
    def _validate_id(document_id: str) -> None:
        if not _DOCUMENT_ID.fullmatch(document_id):
            raise ValueError("Invalid document_id")

    def _document_path(self, document_id: str) -> Path:
        self._validate_id(document_id)
        return self.root / f"{document_id}.json"

    def _chunks_path(self, document_id: str) -> Path:
        self._validate_id(document_id)
        return self.root / f"{document_id}.chunks.json"

    @staticmethod
    def _atomic_json(path: Path, value: object) -> None:
        payload = json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8")
        with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as handle:
            temporary = Path(handle.name)
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        temporary.replace(path)

    def save(self, document: ParsedDocument, chunks: list[DocumentChunk]) -> None:
        with self._lock:
            self._atomic_json(self._document_path(document.document_id), document.to_dict())
            self._atomic_json(self._chunks_path(document.document_id), [chunk.to_dict() for chunk in chunks])

    def get(self, document_id: str) -> ParsedDocument:
        path = self._document_path(document_id)
        if not path.is_file():
            raise FileNotFoundError(f"Document not found: {document_id}")
        return ParsedDocument.from_dict(json.loads(path.read_text(encoding="utf-8")))

    def get_chunks(self, document_id: str) -> list[DocumentChunk]:
        self._validate_id(document_id)
        path = self._chunks_path(document_id)
        if not path.is_file():
            if self._document_path(document_id).is_file():
                return []
            raise FileNotFoundError(f"Document not found: {document_id}")
        values = json.loads(path.read_text(encoding="utf-8"))
        return [DocumentChunk.from_dict(item) for item in values]

    def delete(self, document_id: str) -> None:
        with self._lock:
            self._document_path(document_id).unlink(missing_ok=True)
            self._chunks_path(document_id).unlink(missing_ok=True)


__all__ = [
    "DocumentRepository",
    "InMemoryDocumentRepository",
    "LocalDocumentRepository",
]
