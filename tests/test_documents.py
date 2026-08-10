from __future__ import annotations

import json

import pytest

from app.documents import (
    DocumentChunker,
    DocumentReadError,
    DocumentReader,
    DocumentService,
    LocalDocumentRepository,
)


def test_html_is_parsed_as_inert_text(tmp_path):
    service = DocumentService(repository=LocalDocumentRepository(tmp_path / "documents"))
    document = service.ingest(
        b"<html><head><title>Brand</title></head><body><h1>Rules</h1>"
        b"<script>window.__executed = true</script><p>Keep the logo clear.</p></body></html>",
        filename="guide.html",
    )

    assert document.title == "Brand"
    assert "window.__executed = true" in document.raw_text
    assert "html_script_preserved_as_inert_text" in document.warnings
    assert service.get(document.document_id).raw_text == document.raw_text
    assert service.get_chunks(document.document_id)


def test_json_sections_and_chunks_are_durable(tmp_path):
    repository = LocalDocumentRepository(tmp_path / "documents")
    service = DocumentService(
        chunker=DocumentChunker(max_chars=100, overlap_chars=10),
        repository=repository,
    )
    document = service.ingest(
        json.dumps({"brand": {"name": "Example"}, "rules": ["red", "clear space"]}).encode(),
        filename="brand.json",
    )

    assert [section.heading for section in document.sections] == ["brand", "rules"]
    chunks = repository.get_chunks(document.document_id)
    assert chunks
    assert all(chunk.document_id == document.document_id for chunk in chunks)


def test_reader_rejects_unknown_and_oversized_documents():
    reader = DocumentReader(max_bytes=4)
    with pytest.raises(DocumentReadError):
        reader.read(b"hello", filename="notes.txt")
    with pytest.raises(DocumentReadError):
        DocumentReader().read(b"hello", filename="notes.exe")
