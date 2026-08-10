from __future__ import annotations

import hashlib
import mimetypes
from pathlib import Path
from typing import Any, BinaryIO

from .models import ParsedDocument
from .parser import DocumentParseError, DocumentParser


SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".txt", ".md", ".html", ".json", ".yaml", ".yml"}
MIME_OVERRIDES = {
    ".md": "text/markdown",
    ".yaml": "application/yaml",
    ".yml": "application/yaml",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}


class DocumentReadError(ValueError):
    pass


class DocumentReader:
    def __init__(self, parser: DocumentParser | None = None, *, max_bytes: int = 25 * 1024 * 1024) -> None:
        self.parser = parser or DocumentParser()
        self.max_bytes = max_bytes

    @staticmethod
    def _read_source(file: bytes | bytearray | Path | str | BinaryIO | Any) -> tuple[bytes, str | None, str | None]:
        if isinstance(file, (bytes, bytearray)):
            return bytes(file), None, None
        if isinstance(file, (Path, str)):
            path = Path(file)
            if not path.is_file():
                raise DocumentReadError(f"Document not found: {path.name}")
            return path.read_bytes(), path.name, None
        name = getattr(file, "name", None)
        declared_mime = getattr(file, "type", None)
        if hasattr(file, "getvalue"):
            return bytes(file.getvalue()), name, declared_mime
        if hasattr(file, "read"):
            value = file.read()
            if isinstance(value, str):
                value = value.encode("utf-8")
            return bytes(value), name, declared_mime
        raise TypeError("Document source must be bytes, a path, or a file object")

    def read(
        self,
        file: bytes | bytearray | Path | str | BinaryIO | Any,
        *,
        filename: str | None = None,
        source_type: str = "upload",
        mime_type: str | None = None,
    ) -> ParsedDocument:
        data, inferred_name, inferred_mime = self._read_source(file)
        if not data:
            raise DocumentReadError("Document is empty")
        if len(data) > self.max_bytes:
            raise DocumentReadError(f"Document exceeds the {self.max_bytes} byte limit")
        original_name = filename or inferred_name
        if not original_name:
            raise DocumentReadError("A filename with a supported extension is required")
        safe_name = Path(str(original_name).replace("\\", "/")).name
        extension = Path(safe_name).suffix.lower()
        if extension not in SUPPORTED_EXTENSIONS:
            raise DocumentReadError(f"Unsupported document type: {extension or 'none'}")
        detected_mime = MIME_OVERRIDES.get(extension) or mimetypes.guess_type(safe_name)[0] or "application/octet-stream"
        declared = mime_type or inferred_mime
        # Browser MIME declarations are advisory, but obvious cross-type content
        # should never cause uploaded HTML to be rendered; all formats stay bytes.
        metadata = {"size_bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}
        if declared:
            metadata["declared_mime_type"] = str(declared)
        try:
            parsed = self.parser.parse(data, extension, filename=safe_name)
        except DocumentParseError as exc:
            raise DocumentReadError(str(exc)) from exc
        metadata.update(parsed.metadata)
        digest = metadata["sha256"]
        return ParsedDocument(
            document_id=f"doc_{digest[:24]}",
            filename=safe_name,
            mime_type=detected_mime,
            source_type=source_type,
            title=parsed.title or Path(safe_name).stem,
            raw_text=parsed.raw_text,
            sections=parsed.sections,
            metadata=metadata,
            warnings=parsed.warnings,
        )


__all__ = ["DocumentReadError", "DocumentReader", "SUPPORTED_EXTENSIONS"]
