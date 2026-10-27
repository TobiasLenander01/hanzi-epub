"""Read an EPUB (2 or 3) into chapters of plain-text blocks.

Chapters follow the book's table of contents. Many EPUBs (pandoc / Calibre conversions
especially) put a whole part, or the whole book, in one XHTML file with the TOC pointing at
anchors inside it, so documents are split at those anchors, falling back to splitting very
long documents at their headings.
"""

from __future__ import annotations

import posixpath
import re
import zipfile
from dataclasses import dataclass, field
from io import BytesIO
from urllib.parse import unquote, urldefrag

from lxml import etree, html

WORDS_PER_PAGE = 250  # roughly one printed paperback page
SPLIT_BY_HEADINGS_OVER = 6000  # words; only when the TOC gives no anchors

NS = {
    "c": "urn:oasis:names:tc:opendocument:xmlns:container",
    "opf": "http://www.idpf.org/2007/opf",
    "dc": "http://purl.org/dc/elements/1.1/",
    "ncx": "http://www.daisy.org/z3986/2005/ncx/",
}

BLOCK_TAGS = {
    "p", "h1", "h2", "h3", "h4", "h5", "h6", "li", "blockquote", "dd", "dt",
    "figcaption", "pre", "div", "td", "th", "caption", "section", "article",
    "aside", "header", "footer", "main", "ul", "ol", "dl", "table", "tr",
    "tbody", "thead", "figure", "hr", "body",
}
HEADING_TAGS = {"h1", "h2", "h3", "h4", "h5", "h6"}
SKIP_TAGS = {"script", "style", "head", "rt", "rp", "svg", "math", "img", "audio", "video", "title"}
WORD_RE = re.compile(r"[A-Za-z0-9]+(?:['’][A-Za-z]+)?")
BARE_NUMBER = re.compile(r"(?:\d+|[IVXLCDM]+)\.?", re.I)


@dataclass
class Block:
    kind: str  # "heading" | "text"
    text: str
    level: int = 0  # heading level 1-6
    anchor: str | None = None  # TOC anchor that starts here
    page: int = 1

    @property
    def words(self) -> int:
        return len(WORD_RE.findall(self.text))


@dataclass
class Chapter:
    index: int
    title: str
    part: str = ""  # parent TOC entry, e.g. "Part One: Chiba City Blues"
    blocks: list[Block] = field(default_factory=list)
    start_page: int = 1
    end_page: int = 1

    @property
    def word_count(self) -> int:
        return sum(b.words for b in self.blocks)


@dataclass
class Book:
    title: str
    author: str
    language: str
    chapters: list[Chapter]
    cover: bytes | None = None
    cover_type: str | None = None

    @property
    def total_pages(self) -> int:
        return max((c.end_page for c in self.chapters), default=1)


@dataclass
class TocEntry:
    path: str
    fragment: str
    label: str
    parent: str


class EpubError(ValueError):
    pass


def _local(tag) -> str:
    if not isinstance(tag, str):
        return ""
    return tag.rsplit("}", 1)[-1].lower()


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text.replace("­", "")).strip()


def _split_href(base_dir: str, href: str) -> tuple[str, str]:
    path, frag = urldefrag(href)
    return posixpath.normpath(posixpath.join(base_dir, unquote(path))), unquote(frag)


def _parse_html(data: bytes):
    m = re.search(rb'encoding=["\']([\w-]+)["\']', data[:200])
    parser = html.HTMLParser(encoding=(m.group(1).decode() if m else "utf-8"), remove_comments=True)
    return html.document_fromstring(data, parser=parser)


def _is_noteref(el) -> bool:
    etype = (el.get("epub:type") or el.get("type") or "").lower()
    if "noteref" in etype:
        return True
    # bare superscript footnote markers like <sup>12</sup> or <sup>*</sup>
    if _local(el.tag) == "sup":
        return re.fullmatch(r"[\s\d*†‡§\[\]]*", el.text_content() or "") is not None
    return False


def _inline_text(el) -> str:
    if _local(el.tag) in SKIP_TAGS or _is_noteref(el):
        return ""
    if _local(el.tag) == "br":
        return " "
    parts = [el.text or ""]
    for child in el:
        if isinstance(child.tag, str):
            parts.append(_inline_text(child))
        parts.append(child.tail or "")
    return "".join(parts)


def _extract_blocks(body, anchors: set[str]) -> list[Block]:
    has_block: dict = {}

    def contains_block(el) -> bool:
        if el not in has_block:
            has_block[el] = any(
                _local(d.tag) in BLOCK_TAGS for d in el.iterdescendants() if isinstance(d.tag, str)
            )
        return has_block[el]

    out: list[Block] = []
    pending: list[str | None] = [None]  # anchor waiting for the next block with text

    def flush(buf: list[str], tag: str):
        text = _norm("".join(buf))
        if text and re.search(r"[A-Za-z0-9]", text):
            heading = tag in HEADING_TAGS
            out.append(Block("heading" if heading else "text", text, int(tag[1]) if heading else 0, pending[0]))
            pending[0] = None

    def walk(el):
        tag = _local(el.tag)
        if el.get("id") in anchors:
            pending[0] = el.get("id")
        buf = [el.text or ""]
        for child in el:
            ctag = _local(child.tag)
            if not ctag or ctag in SKIP_TAGS:
                buf.append(child.tail or "")
                continue
            if ctag in BLOCK_TAGS or contains_block(child):
                flush(buf, tag)
                walk(child)
                buf = [child.tail or ""]
            else:
                if child.get("id") in anchors and not _norm("".join(buf)):
                    pending[0] = child.get("id")
                buf.append(_inline_text(child))
                buf.append(child.tail or "")
        flush(buf, tag)

    walk(body)
    return out


def _pretty_label(label: str) -> str:
    return f"Chapter {label.rstrip('.')}" if BARE_NUMBER.fullmatch(label) else label


def _read_toc(zf: zipfile.ZipFile, manifest: dict, spine_toc: str | None) -> list[TocEntry]:
    """Flatten the TOC in reading order, remembering each entry's parent label."""
    entries: list[TocEntry] = []
    nav = next((m for m in manifest.values() if "nav" in m["props"].split()), None)
    if nav:
        try:
            doc = _parse_html(zf.read(nav["path"]))
            base = posixpath.dirname(nav["path"])
            navs = [n for n in doc.iter("nav") if "toc" in (n.get("epub:type") or n.get("role") or "").lower()]
            root = navs[0] if navs else doc

            def walk_ol(ol, parent: str):
                for li in ol.iterchildren("li"):
                    a = next(li.iterchildren("a", "span"), None)
                    label = _norm(a.text_content()) if a is not None else ""
                    if a is not None and a.get("href") and label:
                        entries.append(TocEntry(*_split_href(base, a.get("href")), label, parent))
                    for sub in li.iterchildren("ol", "ul"):
                        walk_ol(sub, label or parent)

            for ol in root.iter("ol", "ul"):
                if ol.getparent() is not None and _local(ol.getparent().tag) == "li":
                    continue
                walk_ol(ol, "")
                break
        except Exception:
            entries = []
    if entries:
        return _regroup_parts(entries)

    ncx = manifest.get(spine_toc) if spine_toc else None
    ncx = ncx or next((m for m in manifest.values() if m["type"] == "application/x-dtbncx+xml"), None)
    if ncx:
        try:
            root = etree.fromstring(zf.read(ncx["path"]), etree.XMLParser(recover=True))
            base = posixpath.dirname(ncx["path"])

            def walk_points(el, parent: str):
                for point in el.iterchildren("{%s}navPoint" % NS["ncx"]):
                    text = point.find("ncx:navLabel/ncx:text", NS)
                    content = point.find("ncx:content", NS)
                    label = _norm(text.text or "") if text is not None else ""
                    if content is not None and label:
                        entries.append(TocEntry(*_split_href(base, content.get("src", "")), label, parent))
                    walk_points(point, label or parent)

            nav_map = root.find("ncx:navMap", NS)
            if nav_map is not None:
                walk_points(nav_map, "")
        except Exception:
            pass
    return _regroup_parts(entries)


PART_LABEL = re.compile(r"(part|book|volume)\b", re.I)


def _regroup_parts(entries: list[TocEntry]) -> list[TocEntry]:
    """Some TOCs list "Part Two" as a sibling of the chapters under "Part One" instead of
    nesting them; let a part-like entry become the parent of the siblings that follow it."""
    override: dict[str, str] = {}
    for e in entries:
        if e.parent and PART_LABEL.match(e.label):
            override[e.parent] = e.label
        elif e.parent in override:
            e.parent = override[e.parent]
    return entries


def _segments(blocks: list[Block], doc_entries: list[TocEntry]) -> list[tuple[str, str, list[Block]]]:
    """Split one document's blocks into (title, part, blocks) chapters."""
    by_anchor = {e.fragment: e for e in doc_entries if e.fragment}
    whole = next((e for e in doc_entries if not e.fragment), None)
    first_heading = next((b.text for b in blocks[:3] if b.kind == "heading"), None)
    default_title = whole.label if whole else (doc_entries[0].label if doc_entries else first_heading)

    split_at: dict[int, tuple[str, str]] = {}
    for i, b in enumerate(blocks):
        if b.anchor in by_anchor:
            e = by_anchor[b.anchor]
            split_at[i] = (_pretty_label(e.label), e.parent)

    if not split_at and sum(b.words for b in blocks) > SPLIT_BY_HEADINGS_OVER:
        levels = [b.level for b in blocks if b.kind == "heading"]
        if levels:
            # split at the most common heading level that occurs at least 3 times
            for level in sorted(set(levels), key=lambda lv: (-levels.count(lv), lv)):
                if levels.count(level) >= 3:
                    top = next((b.text for b in blocks if b.kind == "heading" and b.level < level), "")
                    for i, b in enumerate(blocks):
                        if b.kind == "heading" and b.level == level:
                            split_at[i] = (_pretty_label(b.text), top)
                    break

    segments: list[tuple[str, str, list[Block]]] = []
    title, part, current = default_title or "", "", []
    for i, b in enumerate(blocks):
        if i in split_at:
            # a heading-only run (e.g. a part title right before chapter 1) stays with the next chapter
            if any(x.kind == "text" for x in current):
                segments.append((title, part, current))
                current = []
            title, part = split_at[i]
        current.append(b)
    if current:
        segments.append((title, part, current))
    return segments


def read_epub(data: bytes) -> Book:
    try:
        zf = zipfile.ZipFile(BytesIO(data))
    except zipfile.BadZipFile as e:
        raise EpubError("This file isn't a valid EPUB (not a zip archive).") from e

    try:
        container = etree.fromstring(zf.read("META-INF/container.xml"))
        opf_path = container.find(".//c:rootfile", NS).get("full-path")
        opf = etree.fromstring(zf.read(opf_path), etree.XMLParser(recover=True))
    except (KeyError, AttributeError, etree.XMLSyntaxError) as e:
        raise EpubError("Couldn't find the EPUB package document (container.xml / OPF).") from e

    opf_dir = posixpath.dirname(opf_path)
    meta = opf.find("opf:metadata", NS)

    def dc(name: str) -> str:
        el = meta.find(f"dc:{name}", NS) if meta is not None else None
        return _norm(el.text) if el is not None and el.text else ""

    manifest: dict[str, dict] = {}
    for item in opf.iterfind("opf:manifest/opf:item", NS):
        manifest[item.get("id")] = {
            "path": _split_href(opf_dir, item.get("href", ""))[0],
            "type": item.get("media-type", ""),
            "props": item.get("properties", ""),
        }

    spine = opf.find("opf:spine", NS)
    if spine is None:
        raise EpubError("The EPUB has no reading order (spine).")
    toc = _read_toc(zf, manifest, spine.get("toc"))

    chapters: list[Chapter] = []
    for ref in spine.iterfind("opf:itemref", NS):
        item = manifest.get(ref.get("idref"))
        if not item or "html" not in item["type"] or "nav" in item["props"].split():
            continue
        try:
            doc = _parse_html(zf.read(item["path"]))
        except (KeyError, etree.ParserError):
            continue
        doc_entries = [e for e in toc if e.path == item["path"]]
        body = doc.find("body")
        blocks = _extract_blocks(body if body is not None else doc, {e.fragment for e in doc_entries if e.fragment})
        for title, part, seg in _segments(blocks, doc_entries):
            title = title or f"Section {len(chapters) + 1}"
            chapters.append(Chapter(len(chapters), title[:120], part[:120], seg))

    if not chapters:
        raise EpubError("No readable text was found in this EPUB.")

    # Virtual pagination across the whole book.
    words = 0
    for ch in chapters:
        ch.start_page = words // WORDS_PER_PAGE + 1
        for b in ch.blocks:
            b.page = words // WORDS_PER_PAGE + 1
            words += b.words
        ch.end_page = max(ch.start_page, (words - 1) // WORDS_PER_PAGE + 1)

    cover, cover_type = _find_cover(zf, opf, manifest)
    return Book(
        title=dc("title") or "Untitled",
        author=dc("creator"),
        language=dc("language") or "en",
        chapters=chapters,
        cover=cover,
        cover_type=cover_type,
    )


def _find_cover(zf: zipfile.ZipFile, opf, manifest: dict) -> tuple[bytes | None, str | None]:
    item = next((m for m in manifest.values() if "cover-image" in m["props"].split()), None)
    if item is None:
        meta = opf.find("opf:metadata/opf:meta[@name='cover']", NS)
        if meta is not None:
            item = manifest.get(meta.get("content"))
    if item is None:
        item = next(
            (m for k, m in manifest.items() if m["type"].startswith("image/") and "cover" in (k or "").lower()),
            None,
        )
    if item is None or not item["type"].startswith("image/"):
        return None, None
    try:
        return zf.read(item["path"]), item["type"]
    except KeyError:
        return None, None
