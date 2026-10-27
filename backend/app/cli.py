"""Translate a book into the library from the command line.

    python -m app.cli ../books/Neuromancer.epub                 # every chapter
    python -m app.cli book.epub --list                         # show chapter numbers
    python -m app.cli book.epub --chapters 3,5-8 --script traditional
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from . import annotate  # noqa: E402
from .epub_reader import read_epub  # noqa: E402
from .jobs import TINY_CHAPTER, Job, Selection, run_job  # noqa: E402
from .translate import make_client  # noqa: E402


def parse_chapters(spec: str) -> list[int]:
    out: list[int] = []
    for part in spec.split(","):
        lo, _, hi = part.strip().partition("-")
        out.extend(range(int(lo), int(hi or lo) + 1))
    return out


async def main() -> int:
    parser = argparse.ArgumentParser(description="Translate an EPUB into the Hanzi Reader library.")
    parser.add_argument("epub", type=Path)
    parser.add_argument("--chapters", help="chapter numbers from --list, e.g. 2,4-9 (default: all)")
    parser.add_argument("--script", choices=["simplified", "traditional"], default="simplified")
    parser.add_argument("--list", action="store_true", help="list chapters and exit")
    args = parser.parse_args()

    data = args.epub.read_bytes()
    book = read_epub(data)
    if args.list:
        for c in book.chapters:
            part = f"{c.part} › " if c.part else ""
            print(f"{c.index:4}  {part}{c.title}  ({c.word_count} words)")
        return 0

    indices = (
        parse_chapters(args.chapters)
        if args.chapters
        else [c.index for c in book.chapters if c.word_count >= TINY_CHAPTER]
    )
    annotate.init()
    job = Job("cli", book.title)
    task = asyncio.create_task(run_job(job, book, data, Selection("chapters", indices), args.script, make_client()))
    print(f"Translating {len(indices)} chapters of {book.title}…", flush=True)
    while not task.done():
        await job.wait_change(timeout=10)
        print(
            f"\r  {job.done}/{job.total} lines · {len(job.saved)}/{len(indices)} chapters saved · {job.snapshot()['elapsed']:.0f}s",
            end="",
            flush=True,
        )
    print()
    if job.status != "done":
        print(f"Failed: {job.error}", file=sys.stderr)
        return 1
    print(f"Done: {job.stats} → library/{job.library_id}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
