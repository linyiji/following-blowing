"""Unified, non-executing document ingestion pipeline."""

from .chunker import DocumentChunker
from .models import DocumentChunk, ParsedDocument, Section
from .reader import DocumentReadError, DocumentReader
from .repository import InMemoryDocumentRepository, LocalDocumentRepository
from .service import DocumentService

__all__ = [
    "DocumentChunk",
    "DocumentChunker",
    "DocumentReadError",
    "DocumentReader",
    "DocumentService",
    "InMemoryDocumentRepository",
    "LocalDocumentRepository",
    "ParsedDocument",
    "Section",
]
