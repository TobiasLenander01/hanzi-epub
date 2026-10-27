"""Package annotated bilingual chapters as an EPUB 3 (with an EPUB 2 NCX for older readers)."""

from __future__ import annotations

import uuid
import zipfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from html import escape
from pathlib import Path

from .annotate import ruby_html

CSS_PATH = Path(__file__).with_name("hanzi.css")


@dataclass
class Pair:
    en: str
    zh: str


@dataclass
class OutSection:
    title_en: str
    title_zh: str
    # ("heading", [pair]) for a heading inside the chapter, ("para", pairs) for a paragraph
    body: list[tuple[str, list[Pair]]] = field(default_factory=list)


@dataclass
class OutBook:
    title_en: str
    title_zh: str
    author: str
    lang: str  # "zh-Hans" | "zh-Hant"
    sections: list[OutSection]
    cover: bytes | None = None
    cover_type: str | None = None


def _xhtml(title: str, body: str, lang: str, extra_head: str = "") -> str:
    return (
        '<?xml version="1.0" encoding="utf-8"?>\n<!DOCTYPE html>\n'
        f'<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops" '
        f'lang="{lang}" xml:lang="{lang}">\n<head>\n<meta charset="utf-8"/>\n'
        f"<title>{escape(title)}</title>\n"
        '<link rel="stylesheet" type="text/css" href="../styles/hanzi.css"/>\n'
        f"{extra_head}</head>\n<body>\n{body}\n</body>\n</html>\n"
    )


def _en(text: str, tag: str = "p", cls: str = "en") -> str:
    return f'<{tag} class="{cls}" lang="en" xml:lang="en">{escape(text)}</{tag}>'


def _pair(p: Pair) -> str:
    if not p.zh:  # translation unavailable: show the English at full strength
        return f'<div class="pair untranslated">{_en(p.en, cls="en solo")}</div>'
    return f'<div class="pair"><p class="zh">{ruby_html(p.zh)}</p>{_en(p.en)}</div>'


def _chapter_body(sec: OutSection) -> str:
    head = (
        '<header class="chapter-head">'
        + (f'<h1 class="zh">{ruby_html(sec.title_zh)}</h1>' if sec.title_zh else "")
        + _en(sec.title_en, "p", "chapter-en" if sec.title_zh else "chapter-en solo")
        + "</header>"
    )
    parts = ['<section class="chapter" epub:type="chapter">', head]
    for kind, pairs in sec.body:
        if kind == "heading":
            h = pairs[0]
            parts.append(
                '<div class="subhead">'
                + (f'<h2 class="zh">{ruby_html(h.zh)}</h2>' if h.zh else "")
                + _en(h.en, "p", "subhead-en" if h.zh else "subhead-en solo")
                + "</div>"
            )
        elif pairs:
            parts.append('<div class="para">' + "".join(_pair(p) for p in pairs) + "</div>")
    parts.append("</section>")
    return "\n".join(parts)


def _title_page(book: OutBook) -> str:
    return (
        '<section class="titlepage" epub:type="titlepage">'
        + (f'<h1 class="zh book-title">{ruby_html(book.title_zh)}</h1>' if book.title_zh else "")
        + _en(book.title_en, "p", "book-title-en")
        + (_en(book.author, "p", "book-author") if book.author else "")
        + '<div class="howto">'
        + f'<p class="zh howto-zh">{ruby_html("先读汉字。")}</p>'
        + _en("Read the characters first. Glance up at the pinyin when a character is new, "
              "and check the English underneath only to confirm what you understood.",
              "p", "en howto-en")
        + "</div></section>"
    )


def _nav_label(sec: OutSection) -> str:
    return f"{sec.title_zh} · {sec.title_en}" if sec.title_zh else sec.title_en


def write_epub(book: OutBook, path: Path) -> None:
    book_id = f"urn:uuid:{uuid.uuid4()}"
    modified = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    full_title = f"{book.title_en} (汉英对照)"
    lang = book.lang

    docs: list[tuple[str, str, str]] = []  # (id, href, content)
    docs.append(("titlepage", "text/titlepage.xhtml", _xhtml(full_title, _title_page(book), lang)))
    for i, sec in enumerate(book.sections, 1):
        docs.append((f"ch{i:03d}", f"text/ch{i:03d}.xhtml", _xhtml(_nav_label(sec), _chapter_body(sec), lang)))

    cover_ext = {"image/jpeg": "jpg", "image/png": "png", "image/gif": "gif", "image/webp": "webp"}.get(
        book.cover_type or "", None
    )
    has_cover = bool(book.cover and cover_ext)

    nav_items = "\n".join(
        f'<li><a href="{href.removeprefix("text/")}">{escape(_nav_label(sec))}</a></li>'
        for (_, href, _), sec in zip(docs[1:], book.sections)
    )
    nav = _xhtml(
        "目录 Contents",
        f'<nav epub:type="toc" id="toc"><h1>目录 · Contents</h1><ol>\n{nav_items}\n</ol></nav>',
        lang,
    )

    ncx_points = "\n".join(
        f'<navPoint id="np{i}" playOrder="{i}"><navLabel><text>{escape(_nav_label(sec))}</text></navLabel>'
        f'<content src="{href}"/></navPoint>'
        for i, ((_, href, _), sec) in enumerate(zip(docs[1:], book.sections), 1)
    )
    ncx = (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<ncx xmlns="http://www.daisy.org/z3986/2005/ncx/" version="2005-1">\n'
        f'<head><meta name="dtb:uid" content="{book_id}"/><meta name="dtb:depth" content="1"/></head>\n'
        f"<docTitle><text>{escape(full_title)}</text></docTitle>\n<navMap>\n{ncx_points}\n</navMap>\n</ncx>\n"
    )

    manifest = [
        '<item id="nav" href="text/nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>',
        '<item id="ncx" href="toc.ncx" media-type="application/x-dtbncx+xml"/>',
        '<item id="css" href="styles/hanzi.css" media-type="text/css"/>',
    ]
    spine = []
    if has_cover:
        manifest.append(
            f'<item id="cover-image" href="images/cover.{cover_ext}" media-type="{book.cover_type}" properties="cover-image"/>'
        )
        manifest.append('<item id="cover" href="text/cover.xhtml" media-type="application/xhtml+xml"/>')
        spine.append('<itemref idref="cover" linear="no"/>')
    for doc_id, href, _ in docs:
        manifest.append(f'<item id="{doc_id}" href="{href}" media-type="application/xhtml+xml"/>')
        spine.append(f'<itemref idref="{doc_id}"/>')

    opf = f"""<?xml version="1.0" encoding="utf-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="bookid" xml:lang="{lang}">
<metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
<dc:identifier id="bookid">{book_id}</dc:identifier>
<dc:title>{escape(full_title)}</dc:title>
{f'<dc:creator>{escape(book.author)}</dc:creator>' if book.author else ''}
<dc:language>{lang}</dc:language>
<dc:language>en</dc:language>
<meta property="dcterms:modified">{modified}</meta>
{'<meta name="cover" content="cover-image"/>' if has_cover else ''}
</metadata>
<manifest>
{chr(10).join(manifest)}
</manifest>
<spine toc="ncx">
{chr(10).join(spine)}
</spine>
</package>
"""

    container = (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">'
        '<rootfiles><rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/>'
        "</rootfiles></container>\n"
    )

    with zipfile.ZipFile(path, "w") as zf:
        # mimetype must be first and stored uncompressed
        zf.writestr(zipfile.ZipInfo("mimetype"), "application/epub+zip", compress_type=zipfile.ZIP_STORED)
        z = lambda name, data: zf.writestr(name, data, compress_type=zipfile.ZIP_DEFLATED)  # noqa: E731
        z("META-INF/container.xml", container)
        z("OEBPS/content.opf", opf)
        z("OEBPS/toc.ncx", ncx)
        z("OEBPS/text/nav.xhtml", nav)
        z("OEBPS/styles/hanzi.css", CSS_PATH.read_text(encoding="utf-8"))
        if has_cover:
            z(f"OEBPS/images/cover.{cover_ext}", book.cover)
            z(
                "OEBPS/text/cover.xhtml",
                _xhtml(
                    "Cover",
                    f'<div class="cover"><img src="../images/cover.{cover_ext}" alt="{escape(book.title_en)}"/></div>',
                    lang,
                ),
            )
        for _, href, content in docs:
            z(f"OEBPS/{href}", content)
