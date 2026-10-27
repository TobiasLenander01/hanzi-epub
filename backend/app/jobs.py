"""Conversion jobs: selection -> sentences -> translation -> ruby -> EPUB."""

from __future__ import annotations

import asyncio
import re
import tempfile
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from .annotate import HAN, ruby_html
from .epub_reader import Block, Book, Chapter
from .epub_writer import OutBook, OutSection, Pair, write_epub
from .sentences import split_sentences
from .translate import TranslationError, Translator, Unit

OUTPUT_DIR = Path(tempfile.gettempdir()) / "hanzi-epub"
PREVIEW_LIMIT = 40


@dataclass
class Selection:
    mode: str  # "chapters" | "pages"
    chapters: list[int] = field(default_factory=list)
    page_start: int = 1
    page_end: int = 1


def select_blocks(book: Book, sel: Selection) -> list[tuple[Chapter, list[Block]]]:
    if sel.mode == "pages":
        lo, hi = sorted((sel.page_start, sel.page_end))
        picked = [(ch, [b for b in ch.blocks if lo <= b.page <= hi]) for ch in book.chapters]
    else:
        wanted = set(sel.chapters)
        picked = [(ch, ch.blocks) for ch in book.chapters if ch.index in wanted]
    return [(ch, blocks) for ch, blocks in picked if blocks]


def _key(text: str) -> str:
    return re.sub(r"[^a-z0-9]", "", text.lower())


@dataclass
class _Section:
    title: Unit
    body: list[tuple[str, list[Unit]]]


def build_units(book: Book, picked: list[tuple[Chapter, list[Block]]]) -> tuple[Unit, list[_Section], list[Unit]]:
    units: list[Unit] = []

    def unit(kind: str, en: str) -> Unit:
        u = Unit(len(units), kind, en)
        units.append(u)
        return u

    book_title = unit("title", book.title)
    sections = []
    for ch, blocks in picked:
        title = unit("title", ch.title)
        body: list[tuple[str, list[Unit]]] = []
        for i, b in enumerate(blocks):
            if b.kind == "heading":
                # the chapter's own heading is already rendered as the title
                if i < 2 and _key(b.text) and _key(b.text) in _key(ch.title):
                    continue
                body.append(("heading", [unit("heading", b.text)]))
            else:
                body.append(("para", [unit("sentence", s) for s in split_sentences(b.text)]))
        sections.append(_Section(title, body))
    return book_title, sections, units


@dataclass
class Job:
    id: str
    book_title: str
    status: str = "running"  # running | done | error | cancelled
    stage: str = "preparing"  # preparing | translating | packaging | done
    total: int = 0
    done: int = 0
    error: str = ""
    preview: list[dict] = field(default_factory=list)
    stats: dict = field(default_factory=dict)
    output: Path | None = None
    filename: str = ""
    started: float = field(default_factory=time.time)
    task: asyncio.Task | None = None
    _changed: asyncio.Event = field(default_factory=asyncio.Event)

    def touch(self) -> None:
        self._changed.set()
        self._changed = asyncio.Event()

    async def wait_change(self, timeout: float) -> None:
        try:
            await asyncio.wait_for(self._changed.wait(), timeout)
        except TimeoutError:
            pass

    def snapshot(self) -> dict:
        return {
            "id": self.id,
            "status": self.status,
            "stage": self.stage,
            "total": self.total,
            "done": self.done,
            "error": self.error,
            "preview": self.preview,
            "stats": self.stats,
            "filename": self.filename,
            "elapsed": round(time.time() - self.started, 1),
        }


JOBS: dict[str, Job] = {}


def _safe_filename(title: str) -> str:
    name = re.sub(r'[\\/:*?"<>|]+', "", title).strip()[:80] or "book"
    return f"{name} - Hanzi Reader.epub"


def start_job(book: Book, sel: Selection, script: str, client) -> Job:
    job = Job(uuid.uuid4().hex[:12], book.title)
    JOBS[job.id] = job
    job.task = asyncio.create_task(_run(job, book, sel, script, client))
    return job


async def _run(job: Job, book: Book, sel: Selection, script: str, client) -> None:
    try:
        picked = select_blocks(book, sel)
        if not picked:
            raise TranslationError("Nothing selected to translate.")
        book_title, sections, units = build_units(book, picked)
        job.total = len(units)
        job.stage = "translating"
        job.touch()

        translator = Translator(client, script, book.title)

        async def on_batch(batch: list[Unit]) -> None:
            job.done += len(batch)
            for u in batch:
                if u.kind == "sentence" and u.zh:
                    job.preview.append({"id": u.id, "en": u.en, "html": ruby_html(u.zh)})
            job.preview = job.preview[-PREVIEW_LIMIT:]
            job.touch()

        await translator.translate_all(units, on_batch)

        if not any(u.zh for u in units):
            raise TranslationError("No sentences could be translated.")

        job.stage = "packaging"
        job.touch()

        out = OutBook(
            title_en=book.title,
            title_zh=book_title.zh,
            author=book.author,
            lang="zh-Hant" if script == "traditional" else "zh-Hans",
            sections=[
                OutSection(
                    title_en=s.title.en,
                    title_zh=s.title.zh,
                    body=[(kind, [Pair(u.en, u.zh) for u in us]) for kind, us in s.body],
                )
                for s in sections
            ],
            cover=book.cover,
            cover_type=book.cover_type,
        )
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        path = OUTPUT_DIR / f"{job.id}.epub"
        await asyncio.to_thread(write_epub, out, path)

        hanzi = "".join(u.zh for u in units)
        chars = HAN.findall(hanzi)
        sentences = [u for u in units if u.kind == "sentence"]
        job.stats = {
            "sentences": len(sentences),
            "translated": sum(1 for u in sentences if u.zh),
            "chapters": len(sections),
            "characters": len(chars),
            "unique_characters": len(set(chars)),
            "size_kb": round(path.stat().st_size / 1024),
        }
        job.output = path
        job.filename = _safe_filename(book.title)
        job.stage = "done"
        job.status = "done"
    except asyncio.CancelledError:
        job.status = "cancelled"
        job.touch()
        raise
    except TranslationError as e:
        job.status, job.error = "error", str(e)
    except Exception as e:  # surface unexpected failures to the UI instead of hanging
        job.status, job.error = "error", f"Unexpected error: {type(e).__name__}: {e}"
    job.touch()
