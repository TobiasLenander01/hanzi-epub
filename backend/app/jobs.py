"""Conversion jobs: selection -> sentences -> translation -> ruby -> library.

Chapters are translated concurrently and each one is saved to the library as soon as it
is finished, so reading can start while the rest of the book is still being translated.
"""

from __future__ import annotations

import asyncio
import itertools
import re
import threading
import time
import uuid
from dataclasses import dataclass, field

from . import library
from .annotate import HAN, ruby_html
from .epub_reader import Block, Book, Chapter
from .sentences import split_sentences
from .translate import TranslationError, Translator, Unit

PREVIEW_LIMIT = 40
CHAPTERS_IN_FLIGHT = 3
TINY_CHAPTER = 40  # words; title pages, colophons

_render_lock = threading.Lock()  # jieba isn't safe to run from several threads at once


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
    key: int  # source chapter index
    part: str
    partial: bool  # only some pages of the chapter were selected
    title: Unit
    body: list[tuple[str, list[Unit]]]

    @property
    def units(self) -> list[Unit]:
        return [self.title] + [u for _, us in self.body for u in us]


def build_sections(picked: list[tuple[Chapter, list[Block]]]) -> list[_Section]:
    ids = itertools.count(1)
    sections = []
    for ch, blocks in picked:
        body: list[tuple[str, list[Unit]]] = []
        for i, b in enumerate(blocks):
            if b.kind == "heading":
                # the chapter's own heading is already rendered as the title
                if i < 2 and _key(b.text) and _key(b.text) in _key(ch.title):
                    continue
                body.append(("heading", [Unit(next(ids), "heading", b.text)]))
            else:
                body.append(("para", [Unit(next(ids), "sentence", s) for s in split_sentences(b.text)]))
        title = Unit(next(ids), "title", ch.title)
        sections.append(_Section(ch.index, ch.part, len(blocks) < len(ch.blocks), title, body))
    return sections


def _html(zh: str) -> str:
    return ruby_html(zh) if zh else ""


def chapter_record(sec: _Section) -> dict:
    with _render_lock:
        body = []
        for kind, units in sec.body:
            if kind == "heading":
                u = units[0]
                body.append({"kind": "heading", "en": u.en, "zh": u.zh, "html": _html(u.zh)})
            else:
                body.append({"kind": "para", "pairs": [{"en": u.en, "zh": u.zh, "html": _html(u.zh)} for u in units]})
        title_html = _html(sec.title.zh)
    sentences = [u for _, us in sec.body for u in us if u.kind == "sentence"]
    return {
        "key": sec.key,
        "title_en": sec.title.en,
        "title_zh": sec.title.zh,
        "title_html": title_html,
        "part": sec.part,
        "partial": sec.partial,
        "sentences": len(sentences),
        "characters": sum(len(HAN.findall(u.zh)) for u in sentences),
        "body": body,
    }


@dataclass
class Job:
    id: str
    book_title: str
    status: str = "running"  # running | done | error | cancelled
    stage: str = "preparing"  # preparing | translating | done
    total: int = 0
    done: int = 0
    error: str = ""
    library_id: str = ""
    saved: list[int] = field(default_factory=list)  # chapter keys already in the library
    preview: list[dict] = field(default_factory=list)
    stats: dict = field(default_factory=dict)
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
            "library_id": self.library_id,
            "saved": sorted(self.saved),
            "preview": self.preview,
            "stats": self.stats,
            "elapsed": round(time.time() - self.started, 1),
        }


JOBS: dict[str, Job] = {}


def start_job(book: Book, source: bytes | None, sel: Selection, script: str, client) -> Job:
    job = Job(uuid.uuid4().hex[:12], book.title)
    JOBS[job.id] = job
    job.task = asyncio.create_task(run_job(job, book, source, sel, script, client))
    return job


def _first_error(e: BaseException) -> BaseException:
    while isinstance(e, BaseExceptionGroup):
        e = e.exceptions[0]
    return e


async def _ensure_library_book(book: Book, source: bytes | None, script: str, translator: Translator) -> str:
    book_id = library.make_id(book.title, book.author, script)
    try:
        library.get_meta(book_id)
    except library.NotFound:
        title = Unit(0, "title", book.title)
        await translator.translate_batch([title])
        library.ensure_book(
            book_id,
            title=book.title,
            title_zh=title.zh,
            title_html=_html(title.zh),
            author=book.author,
            script=script,
            source_chapters=sum(1 for c in book.chapters if c.word_count >= TINY_CHAPTER),
            source=source,
            cover=book.cover,
            cover_type=book.cover_type,
        )
    return book_id


async def run_job(job: Job, book: Book, source: bytes | None, sel: Selection, script: str, client) -> None:
    try:
        picked = select_blocks(book, sel)
        if not picked:
            raise TranslationError("Nothing selected to translate.")
        sections = build_sections(picked)
        job.total = sum(len(s.units) for s in sections)
        job.stage = "translating"
        job.touch()

        translator = Translator(client, script, book.title)
        job.library_id = await _ensure_library_book(book, source, script, translator)
        job.touch()

        async def on_batch(batch: list[Unit]) -> None:
            job.done += len(batch)
            for u in batch:
                if u.kind == "sentence" and u.zh:
                    job.preview.append({"id": u.id, "en": u.en, "html": ruby_html(u.zh)})
            job.preview = job.preview[-PREVIEW_LIMIT:]
            job.touch()

        in_flight = asyncio.Semaphore(CHAPTERS_IN_FLIGHT)

        async def convert(sec: _Section) -> None:
            async with in_flight:
                await translator.translate_all(sec.units, on_batch)
            if not any(u.zh for u in sec.units):
                raise TranslationError(f"No sentences in “{sec.title.en}” could be translated.")
            record = await asyncio.to_thread(chapter_record, sec)
            library.save_chapter(job.library_id, record)
            job.saved.append(sec.key)
            job.touch()

        async with asyncio.TaskGroup() as tg:
            for sec in sections:
                tg.create_task(convert(sec))

        sentences = [u for s in sections for _, us in s.body for u in us if u.kind == "sentence"]
        chars = HAN.findall("".join(u.zh for u in sentences))
        job.stats = {
            "sentences": len(sentences),
            "translated": sum(1 for u in sentences if u.zh),
            "chapters": len(sections),
            "characters": len(chars),
            "unique_characters": len(set(chars)),
        }
        job.stage = "done"
        job.status = "done"
    except asyncio.CancelledError:
        job.status = "cancelled"
        job.touch()
        raise
    except Exception as e:  # surface failures to the UI instead of hanging
        err = _first_error(e)
        job.status = "error"
        job.error = str(err) if isinstance(err, TranslationError) else f"Unexpected error: {type(err).__name__}: {err}"
    job.touch()
