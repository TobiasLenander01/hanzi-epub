"""English sentence segmentation."""

from __future__ import annotations

import re
import warnings

with warnings.catch_warnings():
    warnings.simplefilter("ignore", SyntaxWarning)
    import pysbd

_segmenter = pysbd.Segmenter(language="en", clean=False)
_HAS_WORD = re.compile(r"[A-Za-z0-9]")


def split_sentences(text: str) -> list[str]:
    """Split a paragraph into sentences, folding stray fragments (a lone quote mark,
    a closing bracket) back into the sentence before them."""
    out: list[str] = []
    for raw in _segmenter.segment(text):
        s = raw.strip()
        if not s:
            continue
        if out and not _HAS_WORD.search(s):
            out[-1] = f"{out[-1]}{s}" if s[0] in "\"'”’)]" else f"{out[-1]} {s}"
        else:
            out.append(s)
    return out or [text.strip()]
