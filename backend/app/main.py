"""FastAPI app: the library and reader API, plus the upload -> convert wizard."""

from __future__ import annotations

import asyncio
import json
import re
import time
import uuid
from collections import OrderedDict
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from fastapi import FastAPI, File, HTTPException, UploadFile  # noqa: E402
from fastapi.middleware.gzip import GZipMiddleware  # noqa: E402
from fastapi.responses import FileResponse, Response, StreamingResponse  # noqa: E402
from fastapi.staticfiles import StaticFiles  # noqa: E402
from pydantic import BaseModel, Field  # noqa: E402

from . import annotate, library  # noqa: E402
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
app.add_middleware(GZipMiddleware, minimum_size=1024)  # chapters are hundreds of KB of JSON
BOOKS: OrderedDict[str, tuple[Book, bytes]] = OrderedDict()  # uploads being set up in the wizard
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


# ---------- Library & reader ----------


def _converting(book_id: str) -> dict | None:
    job = next((j for j in JOBS.values() if j.library_id == book_id and j.status == "running"), None)
    return {"job_id": job.id, "done": job.done, "total": job.total} if job else None


@app.get("/api/library")
async def list_library():
    return [
        {
            "id": m["id"],
            "title": m["title"],
            "title_zh": m["title_zh"],
            "author": m["author"],
            "script": m["script"],
            "has_cover": bool(m.get("cover")),
            "source_chapters": m["source_chapters"],
            "keys": [c["key"] for c in m["chapters"]],
            "sentences": sum(c["sentences"] for c in m["chapters"]),
            "characters": sum(c["characters"] for c in m["chapters"]),
            "updated": m["updated"],
            "converting": _converting(m["id"]),
        }
        for m in library.list_books()
    ]


def _meta(book_id: str) -> dict:
    try:
        return library.get_meta(book_id)
    except library.NotFound:
        raise HTTPException(404, "That book isn't in your library.")


@app.get("/api/library/{book_id}")
async def library_book(book_id: str):
    return _meta(book_id) | {"converting": _converting(book_id)}


@app.get("/api/library/{book_id}/chapters/{key}")
async def library_chapter(book_id: str, key: int):
    try:
        return Response(library.chapter_json_for_web(book_id, key), media_type="application/json")
    except library.NotFound:
        raise HTTPException(404, "That chapter hasn't been translated yet.")


@app.get("/api/library/{book_id}/cover")
async def library_cover(book_id: str):
    try:
        path, media_type = library.cover_path(book_id)
    except library.NotFound:
        raise HTTPException(404, "No cover")
    return FileResponse(path, media_type=media_type, headers={"Cache-Control": "max-age=86400"})


@app.get("/api/library/{book_id}/epub")
async def library_epub(book_id: str):
    meta = _meta(book_id)
    if not meta["chapters"]:
        raise HTTPException(409, "No chapters have been translated yet.")
    path = await asyncio.to_thread(library.epub_path, book_id)
    name = re.sub(r'[\\/:*?"<>|]+', "", meta["title"]).strip()[:80] or "book"
    return FileResponse(path, media_type="application/epub+zip", filename=f"{name} - Hanzi Reader.epub")


@app.delete("/api/library/{book_id}")
async def delete_library_book(book_id: str):
    if _converting(book_id):
        raise HTTPException(409, "This book is still being translated.")
    try:
        library.delete_book(book_id)
    except library.NotFound:
        raise HTTPException(404, "That book isn't in your library.")
    return {"ok": True}


# ---------- Wizard: upload, choose, convert ----------


def _book_info(upload_id: str, book: Book) -> dict:
    return {
        "id": upload_id,
        "title": book.title,
        "author": book.author,
        "has_cover": book.cover is not None,
        "total_pages": book.total_pages,
        "words_per_page": WORDS_PER_PAGE,
        "word_count": sum(c.word_count for c in book.chapters),
        "translated": library.translated_keys(book.title, book.author),
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


async def _load(data: bytes) -> dict:
    try:
        book = await asyncio.to_thread(read_epub, data)
    except EpubError as e:
        raise HTTPException(422, str(e))
    upload_id = uuid.uuid4().hex[:12]
    BOOKS[upload_id] = (book, data)
    while len(BOOKS) > MAX_BOOKS:
        BOOKS.popitem(last=False)
    return _book_info(upload_id, book)


@app.post("/api/books")
async def upload_book(file: UploadFile = File(...)):
    data = await file.read(MAX_UPLOAD + 1)
    if len(data) > MAX_UPLOAD:
        raise HTTPException(413, "That file is larger than 100 MB.")
    return await _load(data)


@app.post("/api/library/{book_id}/source")
async def reopen_source(book_id: str):
    """Load a library book's original EPUB back into the wizard to translate more of it."""
    try:
        data = library.source_path(book_id).read_bytes()
    except library.NotFound:
        raise HTTPException(404, "The original EPUB for this book isn't available. Upload it again.")
    return await _load(data)


def _get_upload(upload_id: str) -> tuple[Book, bytes]:
    entry = BOOKS.get(upload_id)
    if entry is None:
        raise HTTPException(404, "That book is no longer loaded. Please upload it again.")
    return entry


@app.get("/api/books/{upload_id}/cover")
async def book_cover(upload_id: str):
    book, _ = _get_upload(upload_id)
    if not book.cover:
        raise HTTPException(404, "No cover")
    return Response(book.cover, media_type=book.cover_type, headers={"Cache-Control": "max-age=3600"})


class ConvertRequest(BaseModel):
    mode: Literal["chapters", "pages"]
    chapters: list[int] = Field(default_factory=list)
    page_start: int = 1
    page_end: int = 1
    script: Literal["simplified", "traditional"] = "simplified"


@app.post("/api/books/{upload_id}/convert")
async def convert(upload_id: str, req: ConvertRequest):
    book, data = _get_upload(upload_id)
    sel = Selection(req.mode, req.chapters, req.page_start, req.page_end)
    if not select_blocks(book, sel):
        raise HTTPException(400, "Select at least one chapter or page with text.")
    job = start_job(book, data, sel, req.script, client())
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


# Serve the built frontend (npm run build) when present.
_dist = Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"
if _dist.exists():
    app.mount("/", StaticFiles(directory=_dist, html=True), name="frontend")
