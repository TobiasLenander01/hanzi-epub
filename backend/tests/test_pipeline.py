"""End-to-end pipeline test with a stubbed translator (no API calls).

    .venv/Scripts/python -m pytest tests -q
"""

import asyncio
import zipfile

from lxml import etree

from app import annotate
from app.epub_reader import read_epub
from app.jobs import Job, Selection, _run, select_blocks
from app.sentences import split_sentences
from app.translate import Translator
from tests.make_sample import build

FAKE = {
    "The Lantern Shop": "灯笼店",
    "Mei laughed.": "美笑了。",
}


def test_ruby_markup():
    html = annotate.ruby_html("他慢慢地走进银行。")
    assert "<ruby>银<rp>(</rp><rt>yín</rt><rp>)</rp>行<rp>(</rp><rt>háng</rt><rp>)</rp></ruby>" in html
    assert "地<rp>(</rp><rt>de</rt>" in html  # structural particle, not dì
    assert html.endswith("。")


def test_sentences():
    s = split_sentences('Mr. Lin smiled. "Every lantern needs a story," he said. "Otherwise it is just paper."')
    assert s[0] == "Mr. Lin smiled."
    assert len(s) == 3


def test_full_pipeline(tmp_path, monkeypatch):
    src = tmp_path / "sample.epub"
    build(src)
    book = read_epub(src.read_bytes())
    assert book.title == "The Lantern Shop"
    assert [c.title for c in book.chapters][0] == "Chapter One: The Lantern Shop"
    assert book.cover is not None
    # footnote marker stripped
    assert not any(b.text.endswith("1") for c in book.chapters for b in c.blocks)

    async def fake_call(self, batch):
        return {u.id: FAKE.get(u.en, "我们一起去长城吧！") for u in batch}

    monkeypatch.setattr(Translator, "_call", fake_call)
    monkeypatch.setattr("app.jobs.OUTPUT_DIR", tmp_path)

    async def go():
        job = Job("t1", book.title)
        await _run(job, book, Selection("chapters", [0, 2]), "simplified", client=None)
        return job

    job = asyncio.run(go())
    assert job.status == "done", job.error
    assert job.stats["chapters"] == 2

    with zipfile.ZipFile(job.output) as zf:
        names = zf.namelist()
        assert names[0] == "mimetype"
        assert zf.getinfo("mimetype").compress_type == zipfile.ZIP_STORED
        for n in names:
            if n.endswith((".xhtml", ".opf", ".ncx", ".xml")):
                etree.fromstring(zf.read(n))  # well-formed XML
        ch = zf.read("OEBPS/text/ch001.xhtml").decode()
        assert '<p class="en" lang="en" xml:lang="en">Mei laughed.</p>' in ch
        assert "<rt>měi</rt>" in ch
        assert ch.count("<h1") == 1  # duplicate chapter heading folded into the title
        assert "page-break-inside: avoid" in zf.read("OEBPS/styles/hanzi.css").decode()


def test_page_range_selection(tmp_path):
    src = tmp_path / "sample.epub"
    build(src)
    book = read_epub(src.read_bytes())
    picked = select_blocks(book, Selection("pages", page_start=1, page_end=1))
    assert picked and all(b.page == 1 for _, blocks in picked for b in blocks)
    assert select_blocks(book, Selection("pages", page_start=50, page_end=60)) == []
