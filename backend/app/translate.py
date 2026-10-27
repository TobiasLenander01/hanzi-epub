"""Sentence-aligned English -> Mandarin translation with Claude Haiku 5.5."""

from __future__ import annotations

import asyncio
import json
import os
from dataclasses import dataclass
from typing import Awaitable, Callable

import anthropic

MODEL = os.environ.get("HANZI_MODEL", "claude-haiku-5-5")
MAX_BATCH_ITEMS = 24
MAX_BATCH_CHARS = 3500
CONCURRENCY = int(os.environ.get("HANZI_CONCURRENCY", "6"))

SCRIPTS = {
    "simplified": "Simplified Chinese characters (简体字), as used in mainland China",
    "traditional": "Traditional Chinese characters (繁體字), as used in Taiwan",
}

SYSTEM_PROMPT = """You translate English books into Mandarin Chinese for a bilingual graded reader. \
The reader is an English speaker learning to read Chinese: each Chinese sentence is printed with \
pinyin above it and the original English below it, so every translation must line up with exactly \
one English sentence.

Write in {script}.

Guidelines:
- Return exactly one translation for every input id. Never merge, split, skip or reorder items.
- Write natural, idiomatic Mandarin, the way a skilled literary translator would, not word-for-word \
calques. Keep the register and voice: dialogue should sound like real speech, narration like prose.
- When two phrasings are equally faithful, prefer the more common, high-frequency vocabulary; the \
reader is a learner.
- Use full-width Chinese punctuation (，。！？：；“”‘’《》……——).
- Give people and places their established Chinese names when one exists; otherwise use a \
standard phonetic transliteration. Follow the glossary of names already used in this book exactly.
- Translations contain only Chinese text and punctuation: no pinyin, no notes, no English, \
except for acronyms or brand names that are normally left in Latin letters.
- Items marked (heading) or (title) are headings: translate them as concise headings \
(e.g. "Chapter 3" → "第三章").

Also list in "names" each proper noun (person, place, organization) that appears in this batch, \
with the Chinese form you used."""

RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "translations": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"id": {"type": "integer"}, "zh": {"type": "string"}},
                "required": ["id", "zh"],
                "additionalProperties": False,
            },
        },
        "names": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"en": {"type": "string"}, "zh": {"type": "string"}},
                "required": ["en", "zh"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["translations", "names"],
    "additionalProperties": False,
}


@dataclass
class Unit:
    id: int
    kind: str  # "sentence" | "heading" | "title"
    en: str
    zh: str = ""


class TranslationError(RuntimeError):
    pass


def make_client() -> anthropic.AsyncAnthropic:
    return anthropic.AsyncAnthropic(max_retries=5, timeout=180.0)


async def check_credentials(client: anthropic.AsyncAnthropic) -> tuple[bool, str]:
    try:
        await client.models.retrieve(MODEL)
        return True, ""
    except anthropic.AuthenticationError:
        return False, "The Anthropic API key was rejected. Check ANTHROPIC_API_KEY in backend/.env."
    except anthropic.NotFoundError:
        return False, f"Your API key doesn't have access to {MODEL}."
    except anthropic.APIConnectionError:
        return False, "Couldn't reach the Anthropic API. Check your internet connection."
    except Exception as e:  # missing credentials surface as a client-side error
        return False, f"No Anthropic credentials found. Add ANTHROPIC_API_KEY to backend/.env. ({type(e).__name__})"


def make_batches(units: list[Unit]) -> list[list[Unit]]:
    batches, current, chars = [], [], 0
    for u in units:
        if current and (len(current) >= MAX_BATCH_ITEMS or chars + len(u.en) > MAX_BATCH_CHARS):
            batches.append(current)
            current, chars = [], 0
        current.append(u)
        chars += len(u.en)
    if current:
        batches.append(current)
    return batches


class Translator:
    def __init__(self, client: anthropic.AsyncAnthropic, script: str, book_title: str):
        self.client = client
        self.system = SYSTEM_PROMPT.format(script=SCRIPTS.get(script, SCRIPTS["simplified"]))
        self.book_title = book_title
        self.glossary: dict[str, str] = {}
        self.sem = asyncio.Semaphore(CONCURRENCY)
        self._seeding: asyncio.Task | None = None

    def _prompt(self, batch: list[Unit]) -> str:
        lines = []
        for u in batch:
            tag = f" ({u.kind})" if u.kind != "sentence" else ""
            lines.append(f"[{u.id}]{tag} {u.en}")
        glossary = "\n".join(f"- {en}: {zh}" for en, zh in list(self.glossary.items())[:200])
        return (
            f"Book: {self.book_title}\n\n"
            + (f"Names already used in this book:\n{glossary}\n\n" if glossary else "")
            + "Translate each item. The items are consecutive passages of the book, so use the "
            "surrounding sentences as context.\n\n"
            + "\n".join(lines)
        )

    async def _call(self, batch: list[Unit]) -> dict[int, str]:
        async with self.sem:
            response = await self.client.messages.create(
                model=MODEL,
                max_tokens=16000,
                system=self.system,
                messages=[{"role": "user", "content": self._prompt(batch)}],
                output_config={
                    "effort": "low",
                    "format": {"type": "json_schema", "schema": RESPONSE_SCHEMA},
                },
            )
        if response.stop_reason == "refusal":
            return {}
        if response.stop_reason == "max_tokens":
            if len(batch) == 1:
                return {}
            mid = len(batch) // 2
            first, second = await asyncio.gather(self._call(batch[:mid]), self._call(batch[mid:]))
            return first | second
        text = next((b.text for b in response.content if b.type == "text"), "")
        data = json.loads(text)
        for name in data.get("names", []):
            if name["en"] and name["zh"]:
                self.glossary.setdefault(name["en"], name["zh"])
        wanted = {u.id for u in batch}
        return {t["id"]: t["zh"].strip() for t in data["translations"] if t["id"] in wanted and t["zh"].strip()}

    async def translate_batch(self, batch: list[Unit]) -> None:
        """Fill in .zh on each unit. Items the model skipped are retried one at a time;
        anything still missing stays empty and is rendered English-only."""
        try:
            result = await self._call(batch)
            missing = [u for u in batch if u.id not in result]
            if missing and len(batch) > 1:
                for part in await asyncio.gather(*(self._call([u]) for u in missing)):
                    result |= part
        except anthropic.AuthenticationError as e:
            raise TranslationError("The Anthropic API key was rejected.") from e
        except anthropic.PermissionDeniedError as e:
            raise TranslationError(f"Your API key can't use {MODEL}.") from e
        except anthropic.BadRequestError as e:
            raise TranslationError(f"The translation request was rejected: {e.message}") from e
        except anthropic.APIConnectionError as e:
            raise TranslationError("Lost connection to the Anthropic API.") from e
        except anthropic.APIStatusError as e:
            raise TranslationError(f"The Anthropic API returned an error ({e.status_code}).") from e
        for u in batch:
            u.zh = result.get(u.id, "")

    async def translate_all(
        self, units: list[Unit], on_batch: Callable[[list[Unit]], Awaitable[None]]
    ) -> None:
        batches = make_batches(units)
        if not batches:
            return

        async def run(batch: list[Unit]):
            await self.translate_batch(batch)
            await on_batch(batch)

        # The book's very first batch runs alone so its names seed the glossary for
        # everything after it, including other chapters translating concurrently.
        if self._seeding is None:
            self._seeding = asyncio.ensure_future(run(batches.pop(0)))
        await self._seeding
        async with asyncio.TaskGroup() as tg:
            for b in batches:
                tg.create_task(run(b))
