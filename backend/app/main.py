"""FastAPI app: upload an EPUB, pick chapters/pages, stream conversion progress, download."""

from __future__ import annotations

import asyncio
import json
import time
import uuid
from collections import OrderedDict
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from fastapi import FastAPI, File, HTTPException, UploadFile  # noqa: E402
from fastapi.responses import FileResponse, Response, StreamingResponse  # noqa: E402
from fastapi.staticfiles import StaticFiles  # noqa: E402
from pydantic import BaseModel, Field  # noqa: E402

from . import annotate  # noqa: E402
from .epub_reader import WORDS_PER_PAGE, Book, EpubError, read_epub  # noqa: E402
from .jobs import JOBS, Selection, select_blocks, start_job  # noqa: E402
from .translate import MODEL, check_credentials, make_client  # noqa: E402

MAX_UPLOAD = 100 * 1024 * 1024
MAX_BOOKS = 20


@asynccontextmanager
async def lifespan(_app):
    await asyncio.to_thread(annotate.init)  # load jieba's dictionary before the first request
    yield


app = FastAPI(title="Hanzi Reader", lifespan=lifespan)
BOOKS: OrderedDict[str, Book] = OrderedDict()
_client = None
_cred_cache: tuple[float, bool, str] | None = None


def client():
    global _client
    if _client is None:
        _client = make_client()
    return _client


@app.get("/api/health")
async def health():
    global _cred_cache
    if _cred_cache is None or not _cred_cache[1] and time.time() - _cred_cache[0] > 10:
        try:
            ok, msg = await check_credentials(client())
        except Exception as e:
            ok, msg = False, f"No Anthropic credentials found. Add ANTHROPIC_API_KEY to backend/.env. ({e})"
        _cred_cache = (time.time(), ok, msg)
    return {"ok": True, "model": MODEL, "api_ready": _cred_cache[1], "api_message": _cred_cache[2]}


def _book_info(book_id: str, book: Book) -> dict:
    return {
        "id": book_id,
        "title": book.title,
        "author": book.author,
        "has_cover": book.cover is not None,
        "total_pages": book.total_pages,
        "words_per_page": WORDS_PER_PAGE,
        "word_count": sum(c.word_count for c in book.chapters),
        "chapters": [
            {
                "index": c.index,
                "title": c.title,
                "part": c.part,
                "word_count": c.word_count,
                "start_page": c.start_page,
                "end_page": c.end_page,
                "preview": next((b.text for b in c.blocks if b.kind == "text"), c.blocks[0].text)[:180],
            }
            for c in book.chapters
        ],
    }


@app.post("/api/books")
async def upload_book(file: UploadFile = File(...)):
    data = await file.read(MAX_UPLOAD + 1)
    if len(data) > MAX_UPLOAD:
        raise HTTPException(413, "That file is larger than 100 MB.")
    try:
        book = await asyncio.to_thread(read_epub, data)
    except EpubError as e:
        raise HTTPException(422, str(e))
    book_id = uuid.uuid4().hex[:12]
    BOOKS[book_id] = book
    while len(BOOKS) > MAX_BOOKS:
        BOOKS.popitem(last=False)
    return _book_info(book_id, book)


def _get_book(book_id: str) -> Book:
    book = BOOKS.get(book_id)
    if book is None:
        raise HTTPException(404, "That book is no longer loaded. Please upload it again.")
    return book


@app.get("/api/books/{book_id}/cover")
async def book_cover(book_id: str):
    book = _get_book(book_id)
    if not book.cover:
        raise HTTPException(404, "No cover")
    return Response(book.cover, media_type=book.cover_type, headers={"Cache-Control": "max-age=3600"})


class ConvertRequest(BaseModel):
    mode: Literal["chapters", "pages"]
    chapters: list[int] = Field(default_factory=list)
    page_start: int = 1
    page_end: int = 1
    script: Literal["simplified", "traditional"] = "simplified"


@app.post("/api/books/{book_id}/convert")
async def convert(book_id: str, req: ConvertRequest):
    book = _get_book(book_id)
    sel = Selection(req.mode, req.chapters, req.page_start, req.page_end)
    if not select_blocks(book, sel):
        raise HTTPException(400, "Select at least one chapter or page with text.")
    job = start_job(book, sel, req.script, client())
    return {"job_id": job.id}


def _get_job(job_id: str):
    job = JOBS.get(job_id)
    if job is None:
        raise HTTPException(404, "Unknown job")
    return job


@app.get("/api/jobs/{job_id}")
async def job_status(job_id: str):
    return _get_job(job_id).snapshot()


@app.get("/api/jobs/{job_id}/events")
async def job_events(job_id: str):
    job = _get_job(job_id)

    async def stream():
        while True:
            snap = job.snapshot()
            yield f"data: {json.dumps(snap, ensure_ascii=False)}\n\n"
            if snap["status"] != "running":
                return
            await job.wait_change(timeout=15)

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.post("/api/jobs/{job_id}/cancel")
async def cancel_job(job_id: str):
    job = _get_job(job_id)
    if job.task and not job.task.done():
        job.task.cancel()
    return {"ok": True}


@app.get("/api/jobs/{job_id}/download")
async def download(job_id: str):
    job = _get_job(job_id)
    if job.status != "done" or not job.output or not job.output.exists():
        raise HTTPException(409, "The EPUB isn't ready yet.")
    return FileResponse(job.output, media_type="application/epub+zip", filename=job.filename)


# Serve the built frontend (npm run build) when present.
_dist = Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"
if _dist.exists():
    app.mount("/", StaticFiles(directory=_dist, html=True), name="frontend")
