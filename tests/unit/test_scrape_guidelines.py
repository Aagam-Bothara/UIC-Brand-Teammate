"""Offline tests for scripts/scrape_guidelines.py (no network access)."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone

import pytest

from scripts import scrape_guidelines as sg
from scripts.scrape_guidelines import (
    CATEGORIES,
    SOURCES,
    build_manifest,
    chunk_markdown,
    chunk_records,
    html_to_markdown,
    metadata_sidecar,
    source_record,
    split_sentences,
)

PAGE_URL = "https://brand.uic.edu/messaging/editorial-and-style-guide/"

# Shaped like brand.uic.edu (WordPress): header/menus, breadcrumbs, <article id="article">
# with components, a sidebar, footer, cookie banner and scripts.
SAMPLE_HTML = f"""<!doctype html>
<html><head><title>Editorial and style guide | Brand guidelines</title>
<script>window.dataLayer = [];</script><style>.x{{color:red}}</style></head>
<body>
<div class="cookie-consent-banner">We use cookies to improve your experience. Accept</div>
<header class="site-header"><div class="site-title-main">University of Illinois Chicago</div>
  <nav class="menu-main"><ul><li><a href="/messaging/">Messaging menu item</a></li></ul></nav>
</header>
<main id="red-main" class="l-content-wrapper"><div class="l-full"><div class="l-content">
 <nav class="breadcrumbs"><ol class="menu"><li>Brand guidelines crumb</li></ol></nav>
 <article id="article" class="post-type-page">
  <div class="intro-text">
   <h1 class="_title post-title">Editorial and style guide</h1>
   <h2 class="_subtitle invisible">Introduction</h2>
   <p>Campus units at UIC each have diverse audiences. The message is most effective when it is clear.</p>
  </div>
  <div class="components">
   <section class="component"><div class="at-a-glance-tiles">
     <div class="component-description"><div class="anchor-link-container">
       <h2 class="__title visible" id="table-of-contents">Table of contents</h2>
       <button class="submit tooltip"><svg><path d="M0"/></svg><span>Copy link</span></button>
     </div></div>
     <ul class="at-a-glance-tiles__list"><li class="at-a-glance-tiles__item">
       <p class="at-a-glance-tiles__header">Terminology guides</p>
       <div class="at-a-glance-tiles__text"><p><a href="{PAGE_URL}#uic">TOC link</a></p></div>
     </li></ul>
   </div></section>
   <section class="component"><div class="component-text-block">
     <div class="component-description"><div class="anchor-link-container">
       <h2 class="__title visible" id="uic">UIC specific terminology</h2>
       <button class="submit tooltip"><span>Copy link</span></button>
     </div></div>
     <p><strong>i-card:</strong> Use i-card for UIC&#8217;s identification card.</p>
     <p><strong>WHEN TO USE IT:<br/></strong>To build on the creative hook.</p>
     <p>See <a href="#uic">this section</a> and <a href="https://greatcities.uic.edu/">greatcities.uic.edu</a>.</p>
   </div></section>
   <section class="component"><div class="component-tab-group">
     <div class="component-description"><h2 class="__title invisible" id="terms">Terms</h2></div>
     <div class="tab-group">
      <div class="tab-group__tablist" role="tablist">
        <button role="tab" aria-controls="p1">A</button><button role="tab" aria-controls="p2">B</button>
      </div>
      <div class="tab-group__tabpanels">
       <div class="tab-group__tabpanel" id="p1" role="tabpanel">
         <h3 class="invisible">A</h3><p><strong>ableism:</strong> Visible tab content.</p></div>
       <div class="tab-group__tabpanel" id="p2" role="tabpanel" hidden style="display:none">
         <h3 class="invisible">B</h3><p><strong>blind:</strong> Hidden tab content must be kept.</p></div>
      </div>
     </div>
   </div></section>
   <section class="component">
     <div class="component-description"><h2 id="q">Have a question or suggestion?</h2>
       <p>We would love to hear from you.</p></div>
     <div class="gform_wrapper"><form><label>Name</label><input type="text"/></form></div>
   </section>
   <p style="display: none !important;">honeypot field do not fill</p>
  </div>
 </article>
</div>
<div class="l-sidebar"><nav class="menu-secondary"><ul><li>Sidebar link</li></ul></nav></div>
</div></main>
<footer class="site-footer"><p>Copyright footer text</p></footer>
<script>console.log("tracking")</script>
</body></html>
"""


# --------------------------------------------------------------------------- html_to_markdown


@pytest.fixture(scope="module")
def converted():
    return html_to_markdown(SAMPLE_HTML, PAGE_URL)


def test_html_to_markdown_extracts_title(converted):
    _, title = converted
    assert title == "Editorial and style guide"


def test_html_to_markdown_keeps_guideline_content(converted):
    md, _ = converted
    assert md.startswith("# Editorial and style guide")
    assert "## Introduction" in md
    assert "## UIC specific terminology" in md
    assert "**i-card:** Use i-card for UIC’s identification card." in md
    # external links survive, in-page anchors become plain text
    assert "[greatcities.uic.edu](https://greatcities.uic.edu/)" in md
    assert "this section" in md and "(#uic)" not in md


@pytest.mark.parametrize("boilerplate", [
    "cookies", "Messaging menu item", "Brand guidelines crumb", "Sidebar link",
    "Copyright footer", "tracking", "dataLayer", "Copy link", "Table of contents",
    "TOC link", "Terminology guides", "honeypot", "Have a question", "Name\n", "<",
    "University of Illinois Chicago\n",
])
def test_html_to_markdown_strips_boilerplate(converted, boilerplate):
    md, _ = converted
    assert boilerplate not in md


def test_html_to_markdown_keeps_hidden_tab_panels(converted):
    md, _ = converted
    assert "Visible tab content." in md
    assert "Hidden tab content must be kept." in md
    assert "### B" in md


def test_html_to_markdown_keeps_line_break_after_bold_label(converted):
    md, _ = converted
    assert "**WHEN TO USE IT:**To build" not in md
    assert re.search(r"\*\*WHEN TO USE IT:\*\*\s+To build", md)


def test_html_to_markdown_demotes_same_level_headings_inside_tiles():
    html = """<article id="article"><h1>Brand strategy</h1><div class="components">
      <section class="component"><div class="component-text-block">
        <div class="component-description"><h3 class="invisible">Prospective students</h3></div>
        <h3>Who they are</h3><ul><li>Transfer students</li></ul>
        <h3>Goal</h3><ul><li>Boost enrollment</li></ul>
      </div></section></div></article>"""
    md, _ = html_to_markdown(html)
    assert "### Prospective students" in md
    assert "#### Who they are" in md and "#### Goal" in md


def test_html_to_markdown_dedupes_numbered_duplicate_headings():
    html = """<article id="article"><h1>T</h1>
      <h2>Disability</h2><p>Guiding principles text.</p>
      <h2>Disability 2</h2><p><strong>Resources</strong></p><ul><li>Item</li></ul></article>"""
    md, _ = html_to_markdown(html)
    assert "Disability 2" not in md
    assert md.count("## Disability") == 2


def test_html_to_markdown_falls_back_to_body_without_article():
    md, title = html_to_markdown("<html><body><nav>Menu</nav><h1>T</h1><p>Body text.</p></body></html>")
    assert title == "T"
    assert "Body text." in md and "Menu" not in md


# --------------------------------------------------------------------------- split_sentences


def test_split_sentences_respects_abbreviations():
    text = ("Use St., Ave. and Blvd. in numbered addresses. Spell out e.g. Road. "
            "The U.S. Department said so! Is it true? “Yes,” she said.")
    assert split_sentences(text) == [
        "Use St., Ave. and Blvd. in numbered addresses.",
        "Spell out e.g. Road.",
        "The U.S. Department said so!",
        "Is it true?",
        "“Yes,” she said.",
    ]


# --------------------------------------------------------------------------- chunk_markdown

LONG_MD = "# Style guide\n\n## Introduction\n\nShort intro paragraph for the guide.\n\n## Capitalization\n\n" + "\n\n".join(
    f"**term {i}:** " + " ".join(
        f"Sentence {i}.{j} explains how to capitalize the word number {j} in running copy." for j in range(4)
    )
    for i in range(12)
) + "\n\n## Punctuation\n\n" + " ".join(
    f"Rule {k} says commas and periods go inside quotation marks in American English." for k in range(30)
) + "\n\n- list item one\n- list item two\n"


@pytest.fixture(scope="module")
def chunks():
    return chunk_markdown(LONG_MD, "Style guide", max_chars=500, overlap=100)


def _body(chunk):
    header, _, body = chunk.text.partition("\n\n")
    return header, body


def _all_sentences(md: str) -> set[str]:
    out = set()
    for block in re.split(r"\n\s*\n", md):
        for line in block.split("\n"):
            if line.startswith("#"):
                continue
            out.update(split_sentences(line))
    return out


def test_chunks_respect_max_size(chunks):
    assert len(chunks) > 5
    assert all(c.char_count <= 500 for c in chunks)
    assert all(c.char_count == len(c.text) for c in chunks)


def test_chunks_start_with_title_and_section(chunks):
    for c in chunks:
        header, body = _body(c)
        assert header == f"# Style guide — {c.section}"
        assert body.strip()
    assert {c.section for c in chunks} == {"Introduction", "Capitalization", "Punctuation"}


def test_chunks_never_split_mid_sentence(chunks):
    sentences = _all_sentences(LONG_MD)
    for c in chunks:
        _, body = _body(c)
        for block in body.split("\n\n"):
            for line in block.split("\n"):
                for sent in split_sentences(line):
                    assert sent in sentences, f"fragment not a whole sentence: {sent!r}"


def test_all_content_is_covered(chunks):
    joined = "\n".join(c.text for c in chunks)
    for sent in _all_sentences(LONG_MD):
        assert sent in joined


def test_consecutive_chunks_in_section_overlap(chunks):
    pairs = [(a, b) for a, b in zip(chunks, chunks[1:]) if a.section == b.section]
    assert pairs
    for a, b in pairs:
        _, prev_body = _body(a)
        _, next_body = _body(b)
        first_sentence = split_sentences(next_body.split("\n\n")[0].split("\n")[0])[0]
        assert first_sentence in prev_body, "next chunk should start with text from the previous one"
        # overlap is roughly the requested size, not a copy of the whole chunk
        assert len(first_sentence) < len(prev_body)


def test_no_overlap_across_sections(chunks):
    intro = [c for c in chunks if c.section == "Introduction"]
    assert len(intro) == 1
    cap_first = next(c for c in chunks if c.section == "Capitalization")
    assert "Short intro paragraph" not in cap_first.text


def test_zero_overlap_disables_overlap():
    chunks = chunk_markdown(LONG_MD, "Style guide", max_chars=500, overlap=0)
    bodies = [_body(c)[1] for c in chunks if c.section == "Punctuation"]
    for a, b in zip(bodies, bodies[1:]):
        assert split_sentences(b)[0] not in a


def test_nested_sections_and_lead_in_carry():
    md = ("# Brand strategy\n\n## Audiences\n\n**Audiences: who they are**\n\n"
          "### Prospective students\n\n#### Who they are\n\n" + "\n".join(f"- Group {i} of prospective students" for i in range(8)) +
          "\n\n#### Goal\n\n" + "\n".join(f"- Goal number {i} for prospective students and families" for i in range(4)) +
          "\n\n### Industry\n\n#### Who they are\n\n" + "\n".join(f"- Employer type {i}" for i in range(8)))
    chunks = chunk_markdown(md, "Brand strategy", max_chars=1000, overlap=100)
    sections = [c.section for c in chunks]
    assert "Audiences > Prospective students > Who they are" in sections
    assert "Audiences > Prospective students > Goal" in sections
    assert "Audiences > Industry > Who they are" in sections
    # the short "Audiences" lead-in is carried into the first sub-section, not a tiny chunk
    assert "Audiences" not in sections
    assert "**Audiences: who they are**" in chunks[0].text


def test_short_sibling_section_keeps_its_label():
    md = "# G\n\n## Principle\n\n### Don't say:\n\n“We offer education.”\n\n### Instead say:\n\n“You’ll receive an education.”\n"
    chunks = chunk_markdown(md, "G", max_chars=1000, overlap=100)
    assert len(chunks) == 1
    assert "**Don't say:**" in chunks[0].text and "**Instead say:**" in chunks[0].text
    assert chunks[0].section == "Principle"


def test_fill_in_the_blank_headings_kept_as_is():
    md = "# Voice\n\n## Headline frameworks\n\n### Make ___ known. Make ___(verb).\n\n" + "Use it to build on the hook. " * 6
    chunks = chunk_markdown(md, "Voice", max_chars=1000, overlap=100)
    assert chunks[0].section == "Headline frameworks > Make ___ known. Make ___(verb)."


def test_overlong_sentence_is_hard_split_within_limit():
    md = "# T\n\n## S\n\n" + " ".join(["word"] * 400) + "."
    chunks = chunk_markdown(md, "T", max_chars=300, overlap=50)
    assert all(c.char_count <= 300 for c in chunks)


@pytest.mark.parametrize("kwargs", [{"max_chars": 100}, {"overlap": -1}, {"max_chars": 400, "overlap": 300}])
def test_chunk_markdown_rejects_bad_params(kwargs):
    with pytest.raises(ValueError):
        chunk_markdown("# T\n\ntext", "T", **kwargs)


# --------------------------------------------------------------------------- manifest


def test_sources_match_contract():
    assert set(CATEGORIES) == {"name", "tone", "audience", "editorial"}
    assert [s.source_id for s in SOURCES] == ["name-boilerplate", "voice-tone", "brand-strategy", "editorial-style"]
    for s in SOURCES:
        assert s.category in CATEGORIES
        assert s.url.startswith("https://brand.uic.edu/")


def _manifest():
    src = SOURCES[3]
    raw = "# Editorial and style guide\n\n## Capitalization\n\nLowercase campus regions.\n"
    chunks = chunk_markdown(raw, "Editorial and style guide")
    s_rec = source_record(src, "Editorial and style guide", raw, len(chunks))
    c_recs = chunk_records(src, "Editorial and style guide", chunks)
    when = datetime(2026, 10, 8, 12, 0, 0, tzinfo=timezone.utc)
    return build_manifest([s_rec], c_recs, generated_at=when), raw


def test_manifest_schema():
    manifest, raw = _manifest()
    assert set(manifest) == {"generated_at", "sources", "chunks"}
    assert manifest["generated_at"] == "2026-10-08T12:00:00Z"
    (src,) = manifest["sources"]
    assert set(src) == {"source_id", "title", "url", "category", "raw_path", "chunk_count", "sha256"}
    assert src["source_id"] == "editorial-style"
    assert src["category"] == "editorial"
    assert src["raw_path"] == "raw/editorial-style.md"
    assert src["chunk_count"] == len(manifest["chunks"]) == 1
    assert re.fullmatch(r"[0-9a-f]{64}", src["sha256"])
    assert src["sha256"] == sg.sha256_text(raw)
    (ch,) = manifest["chunks"]
    assert set(ch) == {"chunk_id", "source_id", "category", "title", "url", "section",
                       "path", "text", "char_count"}
    assert ch["chunk_id"] == "editorial-style-001"
    assert ch["path"] == "chunks/editorial-style-001.md"
    assert ch["section"] == "Capitalization"
    assert ch["text"].startswith("# Editorial and style guide — Capitalization")
    assert ch["char_count"] == len(ch["text"])
    json.dumps(manifest)  # serialisable


def test_build_manifest_converts_naive_and_orders_sources():
    recs = [source_record(s, s.default_title, "x", 0) for s in reversed(SOURCES)]
    m = build_manifest(recs, [], generated_at=datetime(2026, 1, 2, 3, 4, 5))
    assert m["generated_at"] == "2026-01-02T03:04:05Z"
    assert [s["source_id"] for s in m["sources"]] == [s.source_id for s in SOURCES]


def test_metadata_sidecar_format():
    manifest, _ = _manifest()
    side = metadata_sidecar(manifest["chunks"][0])
    assert side == {"metadataAttributes": {
        "source_id": "editorial-style", "category": "editorial",
        "title": "Editorial and style guide", "url": SOURCES[3].url, "section": "Capitalization",
    }}


# --------------------------------------------------------------------------- I/O (network mocked)


class _FakeResponse:
    def __init__(self, text, status=200, url=None):
        self.text, self.status_code, self.url = text, status, url
        self.headers = {"Content-Type": "text/html; charset=UTF-8"}
        self.encoding = "utf-8"
        self.apparent_encoding = "utf-8"


class _FakeSession:
    def __init__(self, pages):
        self.pages, self.calls = pages, []

    def get(self, url, headers=None, timeout=None):
        self.calls.append((url, headers))
        return _FakeResponse(self.pages[url], url=url)


def test_process_source_writes_layout_and_is_idempotent(tmp_path, monkeypatch):
    src = SOURCES[3]
    session = _FakeSession({src.url: SAMPLE_HTML})
    chunk_dir = tmp_path / "chunks"
    chunk_dir.mkdir()
    (chunk_dir / f"{src.source_id}-999.md").write_text("stale")
    (chunk_dir / f"{src.source_id}-999.md.metadata.json").write_text("{}")
    (chunk_dir / "voice-tone-001.md").write_text("other source untouched")

    s_rec, c_recs = sg.process_source(src, tmp_path, 1000, 100, session=session)

    assert "UIC-Editorial-Assistant" in session.calls[0][1]["User-Agent"]
    assert (tmp_path / "raw" / "editorial-style.md").read_text() .startswith("# Editorial and style guide")
    assert not (chunk_dir / f"{src.source_id}-999.md").exists()
    assert (chunk_dir / "voice-tone-001.md").exists()
    assert s_rec["chunk_count"] == len(c_recs) > 0
    for rec in c_recs:
        assert (tmp_path / rec["path"]).read_text() == rec["text"]
        side = json.loads((tmp_path / f"{rec['path']}.metadata.json").read_text())
        assert side["metadataAttributes"]["section"] == rec["section"]


def test_fetch_html_retries_then_fails(monkeypatch):
    import requests

    monkeypatch.setattr(sg.time, "sleep", lambda s: None)

    class Boom:
        calls = 0

        def get(self, *a, **k):
            Boom.calls += 1
            raise requests.ConnectionError("down")

    with pytest.raises(sg.FetchError):
        sg.fetch_html("https://brand.uic.edu/x/", Boom())
    assert Boom.calls == sg.MAX_RETRIES


# --------------------------------------------------------------------------- regressions (QA)


def test_fetch_html_sniffs_encoding_when_content_type_has_no_charset():
    import requests

    body = "<p>UIC’s café</p>".encode("utf-8")

    class Resp:
        status_code, url = 200, "https://brand.uic.edu/x/"
        headers = {"Content-Type": "text/html"}
        # what requests picks for text/* without a charset
        encoding = requests.utils.get_encoding_from_headers({"content-type": "text/html"})
        apparent_encoding = "utf-8"

        @property
        def text(self):
            return body.decode(self.encoding)

    class Session:
        def get(self, *a, **k):
            return Resp()

    html, _ = sg.fetch_html("https://brand.uic.edu/x/", Session())
    assert html == "<p>UIC’s café</p>"


def test_run_dedupes_repeated_source_ids(tmp_path, monkeypatch):
    src = SOURCES[1]
    monkeypatch.setattr(sg.requests, "Session", lambda: _FakeSession({src.url: SAMPLE_HTML}))
    assert sg.run(tmp_path, 1000, 100, [src.source_id, src.source_id]) == 0
    manifest = json.loads((tmp_path / sg.MANIFEST_NAME).read_text())
    assert [s["source_id"] for s in manifest["sources"]] == [src.source_id]
    ids = [c["chunk_id"] for c in manifest["chunks"]]
    assert len(ids) == len(set(ids)) == manifest["sources"][0]["chunk_count"]


@pytest.mark.parametrize("argv", [["--max-chars", "100"], ["--overlap", "-1"],
                                  ["--max-chars", "400", "--overlap", "200"]])
def test_cli_rejects_bad_chunk_params_before_fetching(argv, monkeypatch, capsys):
    monkeypatch.setattr(sg, "fetch_html", lambda *a, **k: pytest.fail("must not fetch"))
    with pytest.raises(SystemExit) as exc:
        sg.main(argv)
    assert exc.value.code == 2
    assert "must be" in capsys.readouterr().err


def test_html_to_markdown_keeps_nested_list_indentation():
    html = """<article id="article"><h1>T</h1><h2>S</h2><ul><li>Parent rule
      <ul><li>Sub rule a</li><li>Sub rule b</li></ul></li><li>Next rule</li></ul></article>"""
    md, _ = html_to_markdown(html)
    assert "- Parent rule\n  - Sub rule a\n  - Sub rule b\n- Next rule" in md


def test_overlong_token_is_hard_split_within_limit():
    url = "https://example.com/" + "a" * 1200
    md = f"# T\n\n## S\n\nSee {url} for details. More text here."
    chunks = chunk_markdown(md, "T", max_chars=1000, overlap=100)
    assert all(c.char_count <= 1000 for c in chunks)
    assert "a" * 900 in "".join(c.text for c in chunks)


def test_link_markup_stripped_from_section_names():
    md = "# T\n\n## [Linked heading](https://x.com/)\n\n" + "Body sentence here. " * 10
    (chunk,) = chunk_markdown(md, "T")
    assert chunk.section == "Linked heading"


def test_later_level_one_heading_is_a_section_not_dropped():
    md = ("# T\n\n## First\n\n" + "First body sentence. " * 10 +
          "\n\n# Resources\n\n" + "Resource body sentence. " * 10)
    chunks = chunk_markdown(md, "T")
    assert [c.section for c in chunks] == ["First", "Resources"]
