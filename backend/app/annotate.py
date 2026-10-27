"""Chinese text -> HTML <ruby> markup with tone-marked pinyin.

Jieba segments the sentence into words (with part-of-speech tags), and pypinyin reads
each word as a unit so its phrase dictionary picks the right reading for polyphonic
characters (银行 yínháng vs 行走 xíngzǒu). Structural particles get their neutral-tone
reading from the POS tag (慢慢地 → de, not dì).
"""

from __future__ import annotations

import logging
import re
from html import escape

import jieba
import jieba.posseg as pseg
from pypinyin import Style, pinyin

jieba.setLogLevel(logging.WARNING)

HAN = re.compile(r"[㐀-䶿一-鿿豈-﫿\U00020000-\U0002ebef]")

# jieba POS tags for single-character particles -> neutral-tone reading
PARTICLES = {"uj": "de", "uv": "de", "ud": "de", "ul": "le", "uz": "zhe"}


def init() -> None:
    """Load jieba's dictionary up front (takes ~1s) instead of on the first sentence."""
    jieba.initialize()


def _readings(word: str, flag: str) -> list[str | None]:
    if len(word) == 1 and flag in PARTICLES:
        return [PARTICLES[flag]]
    if all(HAN.match(c) for c in word):
        result = [r[0] for r in pinyin(word, style=Style.TONE)]
        if len(result) == len(word):
            return result
    return [pinyin(c, style=Style.TONE)[0][0] if HAN.match(c) else None for c in word]


def _ruby(word: str, readings: list[str | None]) -> str:
    out, inside = [], False
    for char, py in zip(word, readings):
        if py is None:
            if inside:
                out.append("</ruby>")
                inside = False
            out.append(escape(char))
            continue
        if not inside:
            out.append("<ruby>")
            inside = True
        out.append(f"{escape(char)}<rp>(</rp><rt>{escape(py)}</rt><rp>)</rp>")
    if inside:
        out.append("</ruby>")
    return "".join(out)


def ruby_html(zh: str) -> str:
    """One <ruby> element per word, one <rt> per character."""
    parts = []
    for token in pseg.cut(zh):
        word, flag = token.word, token.flag
        if not HAN.search(word):
            parts.append(escape(word))
        else:
            parts.append(_ruby(word, _readings(word, flag)))
    return "".join(parts)
