"""Package a library book as an EPUB 3 (with an EPUB 2 NCX for older readers)."""

from __future__ import annotations

import uuid
import zipfile
from datetime import datetime, timezone
from html import escape
from pathlib import Path

from .annotate import ruby_html
from .library import COVER_EXT

CSS_PATH = Path(__file__).with_name("hanzi.css")


def _xhtml(title: str, body: str, lang: str) -> str:
    return (
        '<?xml version="1.0" encoding="utf-8"?>\n<!DOCTYPE html>\n'
        f'<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops" '
        f'lang="{lang}" xml:lang="{lang}">\n<head>\n<meta charset="utf-8"/>\n'
        f"<title>{escape(title)}</title>\n"
        '<link rel="stylesheet" type="text/css" href="../styles/hanzi.css"/>\n'
        f"</head>\n<body>\n{body}\n</body>\n</html>\n"
    )


def _en(text: str, tag: str = "p", cls: str = "en") -> str:
    return f'<{tag} class="{cls}" lang="en" xml:lang="en">{escape(text)}</{tag}>'


def _pair(p: dict) -> str:
    if not p["zh"]:  # translation unavailable: show the English at full strength
        return f'<div class="pair untranslated">{_en(p["en"], cls="en solo")}</div>'
    return f'<div class="pair"><p class="zh">{p["html"]}</p>{_en(p["en"])}</div>'


def _chapter_body(ch: dict) -> str:
    head = (
        '<header class="chapter-head">'
        + (f'<h1 class="zh">{ch["title_html"]}</h1>' if ch["title_zh"] else "")
        + _en(ch["title_en"], "p", "chapter-en" if ch["title_zh"] else "chapter-en solo")
        + "</header>"
    )
    parts = ['<section class="chapter" epub:type="chapter">', head]
    for block in ch["body"]:
        if block["kind"] == "heading":
            parts.append(
                '<div class="subhead">'
                + (f'<h2 class="zh">{block["html"]}</h2>' if block["zh"] else "")
                + _en(block["en"], "p", "subhead-en" if block["zh"] else "subhead-en solo")
                + "</div>"
            )
        elif block["pairs"]:
            parts.append('<div class="para">' + "".join(_pair(p) for p in block["pairs"]) + "</div>")
    parts.append("</section>")
    return "\n".join(parts)


def _title_page(meta: dict) -> str:
    return (
        '<section class="titlepage" epub:type="titlepage">'
        + (f'<h1 class="zh book-title">{meta["title_html"]}</h1>' if meta["title_zh"] else "")
        + _en(meta["title"], "p", "book-title-en")
        + (_en(meta["author"], "p", "book-author") if meta["author"] else "")
        + '<div class="howto">'
        + f'<p class="zh howto-zh">{ruby_html("先读汉字。")}</p>'
        + _en("Read the characters first. Glance up at the pinyin when a character is new, "
              "and check the English underneath only to confirm what you understood.",
              "p", "en howto-en")
        + "</div></section>"
    )


def _nav_label(ch: dict) -> str:
    return f"{ch['title_zh']} · {ch['title_en']}" if ch["title_zh"] else ch["title_en"]


def write_epub(meta: dict, chapters: list[dict], cover: bytes | None, path: Path) -> None:
    book_id = f"urn:uuid:{uuid.uuid4()}"
    modified = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    full_title = f"{meta['title']} (汉英对照)"
    lang = meta["lang"]

    docs: list[tuple[str, str, str]] = []  # (id, href, content)
    docs.append(("titlepage", "text/titlepage.xhtml", _xhtml(full_title, _title_page(meta), lang)))
    for i, ch in enumerate(chapters, 1):
        docs.append((f"ch{i:03d}", f"text/ch{i:03d}.xhtml", _xhtml(_nav_label(ch), _chapter_body(ch), lang)))

    cover_ext = COVER_EXT.get(meta.get("cover_type") or "")
    has_cover = bool(cover and cover_ext)

    nav_items = "\n".join(
        f'<li><a href="{href.removeprefix("text/")}">{escape(_nav_label(ch))}</a></li>'
        for (_, href, _), ch in zip(docs[1:], chapters)
    )
    nav = _xhtml(
        "目录 Contents",
        f'<nav epub:type="toc" id="toc"><h1>目录 · Contents</h1><ol>\n{nav_items}\n</ol></nav>',
        lang,
    )

    ncx_points = "\n".join(
        f'<navPoint id="np{i}" playOrder="{i}"><navLabel><text>{escape(_nav_label(ch))}</text></navLabel>'
        f'<content src="{href}"/></navPoint>'
        for i, ((_, href, _), ch) in enumerate(zip(docs[1:], chapters), 1)
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
            f'<item id="cover-image" href="images/cover.{cover_ext}" media-type="{meta["cover_type"]}" properties="cover-image"/>'
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
{f'<dc:creator>{escape(meta["author"])}</dc:creator>' if meta["author"] else ''}
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

    tmp = path.with_suffix(".tmp")
    with zipfile.ZipFile(tmp, "w") as zf:
        # mimetype must be first and stored uncompressed
        zf.writestr(zipfile.ZipInfo("mimetype"), "application/epub+zip", compress_type=zipfile.ZIP_STORED)
        z = lambda name, data: zf.writestr(name, data, compress_type=zipfile.ZIP_DEFLATED)  # noqa: E731
        z("META-INF/container.xml", container)
        z("OEBPS/content.opf", opf)
        z("OEBPS/toc.ncx", ncx)
        z("OEBPS/text/nav.xhtml", nav)
        z("OEBPS/styles/hanzi.css", CSS_PATH.read_text(encoding="utf-8"))
        if has_cover:
            z(f"OEBPS/images/cover.{cover_ext}", cover)
            z(
                "OEBPS/text/cover.xhtml",
                _xhtml(
                    "Cover",
                    f'<div class="cover"><img src="../images/cover.{cover_ext}" alt="{escape(meta["title"])}"/></div>',
                    lang,
                ),
            )
        for _, href, content in docs:
            z(f"OEBPS/{href}", content)
    tmp.replace(path)
