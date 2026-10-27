"""On-disk library of translated books.

    library/<book-id>/
        meta.json            title, author, script, chapter summaries (no text)
        chapters/0007.json   one file per translated chapter, keyed by source chapter index
        source.epub          the original upload, so more chapters can be translated later
        cover.<ext>          cover image, if the source had one
        book.epub            generated on demand from the chapters; deleted when they change

Each chapter's body is stored with its ruby HTML already rendered, so reading and EPUB
export never re-run jieba / pypinyin.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import threading
import time
from pathlib import Path

LIBRARY_DIR = Path(os.environ.get("HANZI_LIBRARY") or Path(__file__).resolve().parent.parent / "library")
COVER_EXT = {"image/jpeg": "jpg", "image/png": "png", "image/gif": "gif", "image/webp": "webp"}
_ID = re.compile(r"^[a-z0-9-]{1,64}$")
_lock = threading.Lock()


class NotFound(KeyError):
    pass


def make_id(title: str, author: str, script: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:40] or "book"
    digest = hashlib.sha1(f"{title}\n{author}\n{script}".encode()).hexdigest()[:6]
    return f"{slug}-{digest}"


def _dir(book_id: str) -> Path:
    if not _ID.match(book_id):
        raise NotFound(book_id)
    return LIBRARY_DIR / book_id


def _write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    os.replace(tmp, path)


def _read_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None


def list_books() -> list[dict]:
    if not LIBRARY_DIR.exists():
        return []
    books = [m for d in LIBRARY_DIR.iterdir() if (m := _read_json(d / "meta.json"))]
    return sorted(books, key=lambda m: m.get("updated", 0), reverse=True)


def get_meta(book_id: str) -> dict:
    meta = _read_json(_dir(book_id) / "meta.json")
    if meta is None:
        raise NotFound(book_id)
    return meta


def get_chapter(book_id: str, key: int) -> dict:
    chapter = _read_json(_dir(book_id) / "chapters" / f"{key:04d}.json")
    if chapter is None:
        raise NotFound(f"{book_id}/{key}")
    return chapter


def chapter_json_for_web(book_id: str, key: int) -> str:
    """The chapter's JSON without the <rp> fallback parentheses. Browsers never show them,
    but they are two of every three elements inside the ruby markup, and a long chapter
    has tens of thousands of them. The EPUB export keeps them for e-readers without ruby."""
    path = _dir(book_id) / "chapters" / f"{key:04d}.json"
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        raise NotFound(f"{book_id}/{key}")
    return text.replace("<rp>(</rp>", "").replace("<rp>)</rp>", "")


def ensure_book(
    book_id: str,
    *,
    title: str,
    title_zh: str,
    title_html: str,
    author: str,
    script: str,
    source_chapters: int,
    source: bytes | None,
    cover: bytes | None,
    cover_type: str | None,
) -> dict:
    """Create the book entry if needed and return its meta."""
    with _lock:
        d = _dir(book_id)
        meta = _read_json(d / "meta.json")
        if meta is None:
            ext = COVER_EXT.get(cover_type or "")
            meta = {
                "id": book_id,
                "title": title,
                "title_zh": title_zh,
                "title_html": title_html,
                "author": author,
                "script": script,
                "lang": "zh-Hant" if script == "traditional" else "zh-Hans",
                "source_chapters": source_chapters,
                "cover": f"cover.{ext}" if cover and ext else None,
                "cover_type": cover_type if cover and ext else None,
                "created": time.time(),
                "updated": time.time(),
                "chapters": [],
            }
            d.mkdir(parents=True, exist_ok=True)
            if meta["cover"]:
                (d / meta["cover"]).write_bytes(cover)
            if source:
                (d / "source.epub").write_bytes(source)
            _write_json(d / "meta.json", meta)
        return meta


def save_chapter(book_id: str, chapter: dict) -> None:
    summary = {k: v for k, v in chapter.items() if k != "body"}
    with _lock:
        d = _dir(book_id)
        _write_json(d / "chapters" / f"{chapter['key']:04d}.json", chapter)
        meta = get_meta(book_id)
        meta["chapters"] = sorted(
            [c for c in meta["chapters"] if c["key"] != chapter["key"]] + [summary], key=lambda c: c["key"]
        )
        meta["updated"] = time.time()
        _write_json(d / "meta.json", meta)
        (d / "book.epub").unlink(missing_ok=True)


def delete_book(book_id: str) -> None:
    with _lock:
        d = _dir(book_id)
        if not d.exists():
            raise NotFound(book_id)
        shutil.rmtree(d)


def source_path(book_id: str) -> Path:
    path = _dir(book_id) / "source.epub"
    if not path.exists():
        raise NotFound(book_id)
    return path


def cover_path(book_id: str) -> tuple[Path, str]:
    meta = get_meta(book_id)
    if not meta.get("cover"):
        raise NotFound(book_id)
    return _dir(book_id) / meta["cover"], meta["cover_type"]


def epub_path(book_id: str) -> Path:
    """The book as an EPUB with every translated chapter, built on first request."""
    from .epub_writer import write_epub

    d = _dir(book_id)
    path = d / "book.epub"
    with _lock:
        if not path.exists():
            meta = get_meta(book_id)
            chapters = [get_chapter(book_id, c["key"]) for c in meta["chapters"]]
            cover = (d / meta["cover"]).read_bytes() if meta.get("cover") else None
            write_epub(meta, chapters, cover, path)
        return path


def translated_keys(title: str, author: str) -> dict[str, list[int]]:
    """Chapters of this source book already in the library, per script."""
    out = {}
    for script in ("simplified", "traditional"):
        try:
            out[script] = [c["key"] for c in get_meta(make_id(title, author, script))["chapters"]]
        except NotFound:
            out[script] = []
    return out
