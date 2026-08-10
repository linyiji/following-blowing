from __future__ import annotations

import io
import json
import re
from dataclasses import dataclass, field
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Mapping

from .models import Section


class DocumentParseError(ValueError):
    pass


@dataclass(slots=True)
class ParsedContent:
    raw_text: str
    sections: list[Section]
    title: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)


def _clean_text(value: str) -> str:
    value = value.replace("\x00", "")
    value = re.sub(r"[ \t]+", " ", value)
    value = re.sub(r"\n[ \t]+", "\n", value)
    value = re.sub(r"\n{3,}", "\n\n", value)
    return value.strip()


def _section(section_id: str, heading: str, text: str, order: int, page: int | None = None) -> Section:
    return Section(
        section_id=section_id,
        heading=_clean_text(heading),
        text=_clean_text(text),
        page_number=page,
        order=order,
    )


class _SafeHTMLTextParser(HTMLParser):
    """Extract text without rendering or evaluating HTML/JavaScript."""

    BLOCK_TAGS = {
        "address",
        "article",
        "aside",
        "blockquote",
        "br",
        "div",
        "footer",
        "form",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "header",
        "hr",
        "li",
        "main",
        "nav",
        "ol",
        "p",
        "pre",
        "section",
        "table",
        "td",
        "th",
        "tr",
        "ul",
    }

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.title_parts: list[str] = []
        self.heading_parts: list[str] = []
        self.headings: list[tuple[str, int]] = []
        self._in_title = False
        self._heading_tag: str | None = None
        self.script_seen = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        del attrs
        tag = tag.lower()
        if tag in self.BLOCK_TAGS:
            self.parts.append("\n")
        if tag == "title":
            self._in_title = True
        if tag in {"h1", "h2", "h3", "h4", "h5", "h6"}:
            self._heading_tag = tag
            self.heading_parts = []
        if tag == "script":
            self.script_seen = True

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag == "title":
            self._in_title = False
        if tag == self._heading_tag:
            heading = _clean_text("".join(self.heading_parts))
            if heading:
                # Offset indexes are only hints for section normalization.
                self.headings.append((heading, len("".join(self.parts))))
            self._heading_tag = None
            self.heading_parts = []
        if tag in self.BLOCK_TAGS:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        # Script contents remain inert text. They are never rendered or executed.
        self.parts.append(data)
        if self._in_title:
            self.title_parts.append(data)
        if self._heading_tag:
            self.heading_parts.append(data)


class DocumentParser:
    def parse(self, data: bytes, extension: str, *, filename: str) -> ParsedContent:
        extension = extension.lower()
        if extension in {".txt", ".md"}:
            return self._parse_text(data, filename, markdown=extension == ".md")
        if extension == ".html":
            return self._parse_html(data, filename)
        if extension == ".json":
            return self._parse_json(data, filename)
        if extension in {".yaml", ".yml"}:
            return self._parse_yaml(data, filename)
        if extension == ".pdf":
            return self._parse_pdf(data, filename)
        if extension == ".docx":
            return self._parse_docx(data, filename)
        raise DocumentParseError(f"Unsupported document extension: {extension}")

    @staticmethod
    def _decode(data: bytes) -> tuple[str, list[str]]:
        try:
            return data.decode("utf-8"), []
        except UnicodeDecodeError:
            try:
                return data.decode("utf-8-sig"), ["document_decoded_with_utf8_bom"]
            except UnicodeDecodeError:
                return data.decode("latin-1"), ["document_decoded_with_latin1_fallback"]

    def _parse_text(self, data: bytes, filename: str, *, markdown: bool) -> ParsedContent:
        raw, warnings = self._decode(data)
        text = _clean_text(raw)
        sections: list[Section] = []
        if markdown:
            current_heading = ""
            current_lines: list[str] = []
            for line in raw.splitlines():
                match = re.match(r"^\s{0,3}#{1,6}\s+(.+?)\s*#*\s*$", line)
                if match:
                    if current_lines or current_heading:
                        sections.append(
                            _section(f"section_{len(sections) + 1:04d}", current_heading, "\n".join(current_lines), len(sections))
                        )
                    current_heading = match.group(1)
                    current_lines = []
                else:
                    current_lines.append(line)
            if current_lines or current_heading:
                sections.append(
                    _section(f"section_{len(sections) + 1:04d}", current_heading, "\n".join(current_lines), len(sections))
                )
        if not sections:
            sections = [_section("section_0001", Path(filename).stem, text, 0)]
        title = next((item.heading for item in sections if item.heading), Path(filename).stem)
        return ParsedContent(text, sections, title=title, warnings=warnings)

    def _parse_html(self, data: bytes, filename: str) -> ParsedContent:
        raw, warnings = self._decode(data)
        parser = _SafeHTMLTextParser()
        try:
            parser.feed(raw)
            parser.close()
        except Exception as exc:
            raise DocumentParseError("HTML could not be parsed safely") from exc
        text = _clean_text("".join(parser.parts))
        if parser.script_seen:
            warnings.append("html_script_preserved_as_inert_text")
        title = _clean_text("".join(parser.title_parts)) or Path(filename).stem
        # HTML is deliberately never rendered. A single normalized section is
        # more reliable than reconstructing offsets after whitespace cleanup.
        sections = [_section("section_0001", title, text, 0)]
        return ParsedContent(text, sections, title=title, warnings=warnings)

    def _parse_json(self, data: bytes, filename: str) -> ParsedContent:
        raw, warnings = self._decode(data)
        try:
            value = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise DocumentParseError(f"Invalid JSON: {exc.msg}") from exc
        text = json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True)
        sections = self._structured_sections(value)
        if not sections:
            sections = [_section("section_0001", Path(filename).stem, text, 0)]
        return ParsedContent(text, sections, title=Path(filename).stem, warnings=warnings)

    def _parse_yaml(self, data: bytes, filename: str) -> ParsedContent:
        raw, warnings = self._decode(data)
        try:
            import yaml  # type: ignore
        except ImportError as exc:
            raise DocumentParseError("PyYAML is required to read YAML documents") from exc
        try:
            value = yaml.safe_load(raw)
        except yaml.YAMLError as exc:  # type: ignore[attr-defined]
            raise DocumentParseError("Invalid YAML document") from exc
        text = json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True, default=str)
        sections = self._structured_sections(value)
        if not sections:
            sections = [_section("section_0001", Path(filename).stem, text, 0)]
        return ParsedContent(text, sections, title=Path(filename).stem, warnings=warnings)

    @staticmethod
    def _structured_sections(value: Any) -> list[Section]:
        if not isinstance(value, Mapping):
            return []
        sections: list[Section] = []
        for key, item in value.items():
            text = json.dumps(item, ensure_ascii=False, indent=2, sort_keys=True, default=str)
            sections.append(_section(f"section_{len(sections) + 1:04d}", str(key), text, len(sections)))
        return sections

    def _parse_pdf(self, data: bytes, filename: str) -> ParsedContent:
        try:
            from pypdf import PdfReader  # type: ignore
        except ImportError as exc:
            raise DocumentParseError("pypdf is required to read PDF documents") from exc
        try:
            reader = PdfReader(io.BytesIO(data), strict=False)
            sections: list[Section] = []
            for index, page in enumerate(reader.pages):
                page_text = _clean_text(page.extract_text() or "")
                sections.append(_section(f"page_{index + 1:04d}", f"Page {index + 1}", page_text, index, index + 1))
        except Exception as exc:
            raise DocumentParseError("PDF could not be parsed") from exc
        text = "\n\n".join(item.text for item in sections if item.text)
        warnings: list[str] = []
        if not text:
            warnings.append("no_usable_text_layer_ocr_fallback_required")
        metadata = {"page_count": len(sections)}
        return ParsedContent(text, sections, title=Path(filename).stem, metadata=metadata, warnings=warnings)

    def _parse_docx(self, data: bytes, filename: str) -> ParsedContent:
        try:
            from docx import Document  # type: ignore
        except ImportError as exc:
            raise DocumentParseError("python-docx is required to read DOCX documents") from exc
        try:
            document = Document(io.BytesIO(data))
        except Exception as exc:
            raise DocumentParseError("DOCX could not be parsed") from exc
        sections: list[Section] = []
        heading = ""
        lines: list[str] = []
        for paragraph in document.paragraphs:
            value = paragraph.text.strip()
            style_name = str(getattr(paragraph.style, "name", ""))
            if value and style_name.lower().startswith("heading"):
                if lines or heading:
                    sections.append(_section(f"section_{len(sections) + 1:04d}", heading, "\n".join(lines), len(sections)))
                heading = value
                lines = []
            elif value:
                lines.append(value)
        if lines or heading:
            sections.append(_section(f"section_{len(sections) + 1:04d}", heading, "\n".join(lines), len(sections)))
        text = "\n\n".join(filter(None, [f"{item.heading}\n{item.text}".strip() for item in sections]))
        if not sections:
            sections = [_section("section_0001", Path(filename).stem, "", 0)]
        title = next((item.heading for item in sections if item.heading), Path(filename).stem)
        return ParsedContent(text, sections, title=title)


__all__ = ["DocumentParseError", "DocumentParser", "ParsedContent"]
