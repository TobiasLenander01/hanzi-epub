"""Build a small sample EPUB (original text) for trying the app and for tests.

    python tests/make_sample.py sample.epub
"""

import struct
import sys
import zipfile
import zlib
from pathlib import Path

CHAPTERS = [
    (
        "Chapter One: The Lantern Shop",
        [
            "Mei had walked past the lantern shop every morning for three years. She had never once gone inside.",
            "On the first cold day of autumn, the door was open. A small bell rang as the wind pushed it back and forth.",
            '"Are you coming in, or are you only looking?" asked an old man behind the counter.',
            "Mei laughed. \"I think I'm only looking,\" she said. Then she stepped inside anyway.",
        ],
    ),
    (
        "Chapter Two: Red Paper",
        [
            "The shop smelled of glue, bamboo and red paper. Hundreds of lanterns hung from the ceiling like quiet moons.",
            "The old man's name was Mr. Lin. He had made lanterns since he was eight years old.",
            "\"Every lantern needs a story,\" he told her. \"Otherwise it is just paper and light.\"",
            "Mei picked up a brush. Her hand was shaking a little, but she painted a single bird.",
        ],
    ),
    (
        "Chapter Three: Light",
        [
            "That night, the whole street came to see the new lantern in the window.",
            "It was not perfect. One wing of the bird was longer than the other.",
            "But when the candle was lit, the bird seemed to fly. Mei decided she would come back tomorrow.",
        ],
    ),
]


def _png(w=60, h=90, rgb=(180, 30, 40)) -> bytes:
    raw = b"".join(b"\x00" + bytes(rgb) * w for _ in range(h))
    chunk = lambda t, d: struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d))  # noqa: E731
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)) + chunk(
        b"IDAT", zlib.compress(raw)
    ) + chunk(b"IEND", b"")


def build(path: Path) -> None:
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr(zipfile.ZipInfo("mimetype"), "application/epub+zip")
        zf.writestr(
            "META-INF/container.xml",
            '<?xml version="1.0"?><container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">'
            '<rootfiles><rootfile full-path="OPS/package.opf" media-type="application/oebps-package+xml"/></rootfiles></container>',
        )
        items, spine, nav = [], [], []
        for i, (title, paras) in enumerate(CHAPTERS, 1):
            body = "".join(f"<p>{p.replace('&', '&amp;')}</p>" for p in paras)
            if i == 2:
                body += '<p>He wiped his hands on his apron.<sup><a epub:type="noteref" href="#n1">1</a></sup></p>'
            zf.writestr(
                f"OPS/xhtml/ch{i}.xhtml",
                '<?xml version="1.0" encoding="utf-8"?><html xmlns="http://www.w3.org/1999/xhtml" '
                'xmlns:epub="http://www.idpf.org/2007/ops"><head><title>x</title></head><body>'
                f"<section><h2>{title.split(':')[0]}</h2>{body}</section></body></html>",
            )
            items.append(f'<item id="c{i}" href="xhtml/ch{i}.xhtml" media-type="application/xhtml+xml"/>')
            spine.append(f'<itemref idref="c{i}"/>')
            nav.append(f'<li><a href="xhtml/ch{i}.xhtml">{title}</a></li>')
        zf.writestr(
            "OPS/nav.xhtml",
            '<?xml version="1.0" encoding="utf-8"?><html xmlns="http://www.w3.org/1999/xhtml" '
            'xmlns:epub="http://www.idpf.org/2007/ops"><head><title>Nav</title></head><body>'
            f'<nav epub:type="toc"><ol>{"".join(nav)}</ol></nav></body></html>',
        )
        zf.writestr("OPS/cover.png", _png())
        zf.writestr(
            "OPS/package.opf",
            '<?xml version="1.0" encoding="utf-8"?><package xmlns="http://www.idpf.org/2007/opf" version="3.0" '
            'unique-identifier="id"><metadata xmlns:dc="http://purl.org/dc/elements/1.1/">'
            '<dc:identifier id="id">sample-lantern</dc:identifier><dc:title>The Lantern Shop</dc:title>'
            "<dc:creator>Hanzi Reader Sample</dc:creator><dc:language>en</dc:language></metadata><manifest>"
            '<item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>'
            '<item id="cover" href="cover.png" media-type="image/png" properties="cover-image"/>'
            f'{"".join(items)}</manifest><spine>{"".join(spine)}</spine></package>',
        )


if __name__ == "__main__":
    build(Path(sys.argv[1] if len(sys.argv) > 1 else "sample.epub"))
