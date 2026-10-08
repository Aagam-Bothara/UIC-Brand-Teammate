#!/usr/bin/env python3
"""Scrape the UIC brand guideline pages and turn them into RAG-ready chunks.

Implements Task 1.2 (Guideline Processing) of Workstream 1. The on-disk layout,
manifest schema, metadata sidecar format and chunking rules are defined in
``docs/API_CONTRACT.md``::

    data/guidelines/
    ├── raw/<source_id>.md
    ├── chunks/<source_id>-<NNN>.md
    ├── chunks/<source_id>-<NNN>.md.metadata.json
    └── guidelines_manifest.json

Usage::

    python -m scripts.scrape_guidelines [--out-dir data/guidelines]
        [--max-chars 1000] [--overlap 100] [--sources editorial-style voice-tone]

The pure functions (:func:`html_to_markdown`, :func:`chunk_markdown`,
:func:`build_manifest`) do no I/O so they can be unit-tested offline.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import re
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Sequence
from urllib.parse import urldefrag

import requests
from bs4 import BeautifulSoup, Comment, Tag
from markdownify import markdownify

logger = logging.getLogger("scrape_guidelines")

# --------------------------------------------------------------------------------------
# Configuration
# --------------------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUT_DIR = REPO_ROOT / "data" / "guidelines"
MANIFEST_NAME = "guidelines_manifest.json"

USER_AGENT = (
    "UIC-Editorial-Assistant/0.1 (hackathon project; RAG guideline indexer; "
    "+https://brand.uic.edu/) python-requests"
)
REQUEST_TIMEOUT = 20  # seconds
MAX_RETRIES = 3
BACKOFF_BASE = 1.5  # seconds; delays are 1.5, 3.0, ...

CATEGORIES = ("name", "tone", "audience", "editorial")


@dataclass(frozen=True)
class Source:
    source_id: str
    category: str
    url: str
    default_title: str  # used only if the page has no <h1>


SOURCES: tuple[Source, ...] = (
    Source("name-boilerplate", "name",
           "https://brand.uic.edu/messaging/name-and-boilerplate/",
           "Name and boilerplate"),
    Source("voice-tone", "tone",
           "https://brand.uic.edu/messaging/voice-and-tone/",
           "Voice and tone"),
    Source("brand-strategy", "audience",
           "https://brand.uic.edu/messaging/brand-strategy/",
           "Brand strategy and messaging"),
    Source("editorial-style", "editorial",
           "https://brand.uic.edu/messaging/editorial-and-style-guide/",
           "Editorial and style guide"),
)
SOURCES_BY_ID = {s.source_id: s for s in SOURCES}

# --------------------------------------------------------------------------------------
# HTML -> Markdown (pure)
# --------------------------------------------------------------------------------------

# Candidate main-content containers, most specific first. brand.uic.edu (WordPress)
# renders the page body in <article id="article" class="post-type-page"> inside
# <main id="red-main">; breadcrumbs and the section sidebar are siblings of it.
CONTENT_SELECTORS = (
    "article#article",
    "article.post-type-page",
    "main article",
    "article",
    "main",
    "[role=main]",
    "#content",
    ".entry-content",
)

# Elements that are never guideline content.
STRIP_TAGS = (
    "script", "style", "noscript", "template", "svg", "iframe", "form", "button",
    "input", "select", "textarea", "label", "fieldset", "nav", "header", "footer",
    "aside", "img", "picture", "video", "audio", "source", "object", "embed", "canvas",
    "link", "meta",
)

# Class / id fragments that mark boilerplate (cookie banners, sidebars, menus, ...).
BOILERPLATE_PATTERNS = re.compile(
    r"(cookie|consent|gdpr|onetrust|banner-notice|sidebar|l-sidebar|menu|breadcrumb|"
    r"site-header|site-footer|skip-link|share|social|search-input|gform|"
    r"tab-group__tablist|anchor-link-container__button|tooltip|back-to-top)",
    re.I,
)

# Containers that hide content behind JS (tabs / accordions) — never drop these just
# because they carry `hidden` / display:none in the static HTML.
REVEALABLE_PATTERNS = re.compile(r"(tabpanel|accordion|collapse|panel|disclosure|details)", re.I)

# Section headings whose content is navigation, not guidance.
NAV_HEADINGS = {"table of contents", "top of page", "back to top", "on this page", "in this section",
                "have a question or suggestion?", "have a question or suggestion"}

_HEADING_TAG_RE = re.compile(r"^h[1-6]$")
_WS_RE = re.compile(r"[ \t   ]+")


def _classes(tag: Tag) -> str:
    cls = tag.get("class") or []
    if isinstance(cls, str):
        cls = [cls]
    return " ".join(cls) + " " + (tag.get("id") or "")


def _is_hidden(tag: Tag) -> bool:
    style = (tag.get("style") or "").replace(" ", "").lower()
    return (
        tag.has_attr("hidden")
        or tag.get("aria-hidden") == "true"
        or "display:none" in style
        or "visibility:hidden" in style
    )


def find_main_content(soup: BeautifulSoup) -> Tag:
    """Return the element holding the page's main content (falls back to <body>)."""
    for selector in CONTENT_SELECTORS:
        found = soup.select_one(selector)
        if found is not None and found.get_text(strip=True):
            return found
    return soup.body or soup


def _same_page_link(href: str, page_url: str | None) -> bool:
    if href.startswith("#"):
        return True
    if page_url and "#" in href:
        return urldefrag(href)[0].rstrip("/") == urldefrag(page_url)[0].rstrip("/")
    return False


def clean_html(html: str, page_url: str | None = None) -> tuple[Tag, str | None]:
    """Parse ``html`` and return (cleaned main-content element, page <h1> text)."""
    soup = BeautifulSoup(html, "html.parser")

    for c in soup.find_all(string=lambda s: isinstance(s, Comment)):
        c.extract()

    main = find_main_content(soup)

    # 1. Drop non-content tags outright.
    for tag in main.find_all(STRIP_TAGS):
        tag.decompose()

    # 2. Drop boilerplate containers (menus, cookie banners, share widgets, ...).
    for tag in list(main.find_all(True)):
        if tag.decomposed:
            continue
        if tag.get("role") in {"navigation", "banner", "contentinfo", "search", "tablist"}:
            tag.decompose()
            continue
        if BOILERPLATE_PATTERNS.search(_classes(tag)):
            tag.decompose()

    # 3. Drop hidden elements, but keep JS-revealed tab panels / accordion bodies.
    for tag in list(main.find_all(True)):
        if tag.decomposed:
            continue
        if _is_hidden(tag) and not (
            tag.get("role") == "tabpanel" or REVEALABLE_PATTERNS.search(_classes(tag))
        ):
            tag.decompose()

    # 4. Drop navigation-only sections ("Table of contents", "Top of page" links).
    for heading in list(main.find_all(re.compile(r"^h[1-6]$"))):
        if heading.decomposed:
            continue
        if heading.get_text(" ", strip=True).lower().rstrip(":").strip() in NAV_HEADINGS:
            section = heading.find_parent("section")
            column = heading.find_parent(class_=re.compile(r"column", re.I))
            target = column or section or heading
            # Only remove the wrapper if it is genuinely just navigation.
            if target is not heading and len(target.get_text(" ", strip=True)) > 600:
                target = heading
            target.decompose()
    for a in list(main.find_all("a")):
        if a.decomposed:
            continue
        if a.get_text(" ", strip=True).lower() in NAV_HEADINGS:
            parent = a.parent
            a.decompose()
            if parent is not None and parent.name == "p" and not parent.get_text(strip=True):
                parent.decompose()

    # 5. In-page anchor links become plain text; keep real outbound links.
    for a in main.find_all("a"):
        href = a.get("href") or ""
        if not href or _same_page_link(href, page_url) or href.startswith("javascript:"):
            a.unwrap()

    # 6. Tile components put their title in an (often visually hidden) heading and
    #    then use headings of the *same* level inside the tile ("Prospective
    #    students" h3 -> "Who they are" h3, "Goal" h3). Demote those inner headings
    #    so the heading hierarchy (and thus chunk section paths) stays unambiguous.
    for section in main.find_all("section"):
        own = [h for h in section.find_all(_HEADING_TAG_RE) if h.find_parent("section") is section]
        titles = [h for h in own if h.find_parent(class_="component-description") is not None]
        if not titles:
            continue
        title_level = int(titles[0].name[1])
        for h in own:
            if h in titles:
                continue
            if int(h.name[1]) <= title_level:
                h.name = f"h{min(6, title_level + 1)}"

    # 7. <strong>Label<br/></strong>Text: move the trailing <br> out of the inline
    #    element, otherwise markdownify drops it and glues "**Label**Text" together.
    for br in list(main.find_all("br")):
        parent = br.parent
        while (
            parent is not None
            and parent.name in {"strong", "b", "em", "i", "span"}
            and not "".join(
                str(s) for s in br.next_siblings if not (isinstance(s, str) and not s.strip())
            )
        ):
            parent.insert_after(br.extract())
            parent = br.parent

    # 8. "At a glance" tiles -> "**Header:** text" paragraphs.
    for ul in main.select("ul.at-a-glance-tiles__list"):
        for li in ul.find_all("li", recursive=False):
            header = li.select_one(".at-a-glance-tiles__header")
            body = li.select_one(".at-a-glance-tiles__text")
            para = soup.new_tag("p")
            if header is not None:
                strong = soup.new_tag("strong")
                strong.string = header.get_text(" ", strip=True).rstrip(":") + ":"
                para.append(strong)
                para.append(" ")
            if body is not None:
                para.append(_WS_RE.sub(" ", body.get_text(" ", strip=True)))
            ul.insert_before(para)
        ul.decompose()

    h1 = main.find("h1") or soup.find("h1")
    title = _WS_RE.sub(" ", h1.get_text(" ", strip=True)).strip() if h1 else None
    return main, title


def _tidy_markdown(md: str) -> str:
    lines: list[str] = []
    for line in md.splitlines():
        # keep leading indentation: it is what makes "  - sub item" a nested list item
        indent = re.match(r"[ \t]*", line).group(0)
        line = (indent + _WS_RE.sub(" ", line[len(indent):])).rstrip()
        # markdownify leaves "**term** :" when <strong> has trailing whitespace
        line = re.sub(r"\*\*\s+([:;,.])", r"**\1", line)
        line = re.sub(r"\*\*([^*\n]+?)\s+\*\*", r"**\1**", line)
        # drop empty emphasis / headings
        if re.fullmatch(r"\s*(\*\*|__|\*|_)\s*(\*\*|__|\*|_)?\s*", line):
            line = ""
        if re.fullmatch(r"#{1,6}\s*", line):
            line = ""
        lines.append(line)
    text = "\n".join(lines)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip() + "\n"


def _norm_heading(text: str) -> str:
    return re.sub(r"[*_`]", "", text).strip().rstrip(":.").strip().lower()


def _dedupe_headings(md: str) -> str:
    """Clean up WordPress block artefacts around headings.

    * ``## Disability 2`` (auto-numbered duplicate of an earlier ``## Disability``)
      becomes ``## Disability``;
    * a heading immediately followed by an identical heading is dropped;
    * a fully-bold paragraph repeating the heading right below it is dropped.
    """
    lines = md.split("\n")
    seen: dict[str, str] = {}
    out: list[str] = []
    for line in lines:
        m = HEADING_RE.match(line)
        if m:
            hashes, text = m.group(1), m.group(2).strip()
            base = re.match(r"^(.*\S)\s+\d+$", text)
            if base and _norm_heading(base.group(1)) in seen:
                text = seen[_norm_heading(base.group(1))]
            seen.setdefault(_norm_heading(text), text)
            line = f"{hashes} {text}"
            # previous non-blank line is the same heading (nothing in between) -> drop it
            j = len(out) - 1
            while j >= 0 and not out[j].strip():
                j -= 1
            if j >= 0:
                pm = HEADING_RE.match(out[j])
                if pm and _norm_heading(pm.group(2)) == _norm_heading(text) and len(pm.group(1)) == len(hashes):
                    del out[j:]
        else:
            j = len(out) - 1
            while j >= 0 and not out[j].strip():
                j -= 1
            stripped = line.strip()
            if (
                j >= 0
                and re.fullmatch(r"\*\*[^*]+\*\*:?", stripped)
                and (pm := HEADING_RE.match(out[j]))
                and _norm_heading(pm.group(2)) == _norm_heading(stripped)
            ):
                continue
        out.append(line)
    return re.sub(r"\n{3,}", "\n\n", "\n".join(out))


def html_to_markdown(html: str, page_url: str | None = None) -> tuple[str, str | None]:
    """Convert a guideline page to clean markdown containing only its main content.

    Returns ``(markdown, title)`` where ``title`` is the page's ``<h1>`` text (or
    ``None``). Navigation, headers, footers, sidebars, cookie banners, forms, scripts
    and "copy link" widgets are removed; tab panels and accordion bodies (hidden until
    clicked in the browser) are kept.
    """
    main, title = clean_html(html, page_url)
    md = markdownify(
        str(main),
        heading_style="ATX",
        bullets="-",
        escape_underscores=False,
        escape_asterisks=False,
    )
    return _tidy_markdown(_dedupe_headings(_tidy_markdown(md))), title


# --------------------------------------------------------------------------------------
# Chunking (pure)
# --------------------------------------------------------------------------------------

HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*#*\s*$")
LIST_ITEM_RE = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+")

_ABBREVIATIONS = {
    "e.g", "i.e", "etc", "vs", "cf", "dr", "mr", "mrs", "ms", "mx", "prof", "st", "jr",
    "sr", "inc", "ltd", "co", "corp", "u.s", "u.k", "a.m", "p.m", "ph.d", "no", "nos",
    "dept", "approx", "fig", "jan", "feb", "mar", "apr", "aug", "sept", "sep", "oct",
    "nov", "dec", "ave", "blvd", "rev", "gov", "sen", "rep", "gen", "lt", "col", "sgt",
    "b.a", "b.s", "m.a", "m.s", "m.d", "d.d.s", "pharm.d", "ed.d", "j.d", "est",
}
# sentence end: . ! or ? (+ optional closing quotes/brackets/emphasis) followed by space
_SENT_END_RE = re.compile(r"[.!?][\"'”’)\]*_]*\s+")


@dataclass
class Chunk:
    section: str
    text: str  # full chunk text, starting with "# <title> — <section>"

    @property
    def char_count(self) -> int:
        return len(self.text)


def split_sentences(text: str) -> list[str]:
    """Split prose into sentences without breaking on common abbreviations."""
    text = text.strip()
    if not text:
        return []
    out: list[str] = []
    start = 0
    for m in _SENT_END_RE.finditer(text):
        end = m.end()
        nxt = text[end:end + 1]
        if not nxt or not (nxt.isupper() or nxt.isdigit() or nxt in "\"'“‘(*[_"):
            continue
        # word right before the terminal punctuation
        before = text[start:m.start() + 1]
        last_word = re.split(r"\s+", before.strip())[-1].strip("*_\"'(“‘").lower()
        last_word = last_word.rstrip(".!?")
        if last_word in _ABBREVIATIONS or (len(last_word) == 1 and last_word.isalpha()):
            continue
        out.append(text[start:end].strip())
        start = end
    tail = text[start:].strip()
    if tail:
        out.append(tail)
    return out


def _hard_split(text: str, limit: int) -> list[str]:
    """Last resort for a single 'sentence' longer than the budget: split on spaces."""
    words, parts, cur = [], [], ""
    for w in text.split(" "):
        # a single token (e.g. a long URL) longer than the budget is cut into slices
        words += [w[i:i + limit] for i in range(0, len(w), limit)] or [w]
    for w in words:
        cand = f"{cur} {w}" if cur else w
        if len(cand) > limit and cur:
            parts.append(cur)
            cur = w
        else:
            cur = cand
    if cur:
        parts.append(cur)
    return parts


def _fine_pieces(block: str, budget: int) -> list[tuple[str, str]]:
    """Split a paragraph/list block into ``(piece, joiner)`` pairs that each fit ``budget``.

    Pieces are lines / list items, and sentences for lines that are still too long.
    ``joiner`` is what separates the piece from the previous one when they end up in
    the same chunk (``"\n\n"`` for the first piece of the block).
    """
    lines = [ln for ln in block.split("\n") if ln.strip()]
    items: list[str] = []
    for ln in lines:
        # list-item continuation lines stay with their item
        if items and LIST_ITEM_RE.match(items[-1]) and not LIST_ITEM_RE.match(ln) and ln[:1].isspace():
            items[-1] += "\n" + ln
        else:
            items.append(ln)
    out: list[tuple[str, str]] = []
    for item in items:
        sents = [item] if len(item) <= budget else split_sentences(item)
        for k, sent in enumerate(sents):
            parts = [sent]
            if len(sent) > budget:
                logger.warning("sentence longer than %d chars; splitting on spaces", budget)
                parts = _hard_split(sent, budget)
            for m, part in enumerate(parts):
                if not out:
                    joiner = "\n\n"
                elif k == 0 and m == 0:
                    joiner = "\n"
                else:
                    joiner = " "
                out.append((part, joiner))
    return out


def _overlap_tail(text: str, overlap: int, cap: int) -> str:
    """Trailing whole sentences of ``text`` totalling >= ``overlap`` chars (<= ``cap``)."""
    if overlap <= 0:
        return ""
    last_block = text.split("\n\n")[-1]
    if LIST_ITEM_RE.match(last_block.split("\n")[-1]):
        sents = [ln for ln in last_block.split("\n") if ln.strip()]
        joiner = "\n"
    else:
        sents = split_sentences(last_block)
        joiner = " "
    picked: list[str] = []
    total = 0
    for s in reversed(sents):
        new_total = total + len(s) + (len(joiner) if picked else 0)
        if new_total > cap:
            break
        picked.insert(0, s)
        total = new_total
        if total >= overlap:
            break
    return joiner.join(picked)


@dataclass
class _Section:
    path: list[str]
    level: int
    body: str


def split_sections(markdown: str, default_section: str = "Introduction") -> list[_Section]:
    """Split markdown on headings. The first level-1 heading (the page title) is not a section."""
    sections: list[_Section] = []
    stack: list[tuple[int, str]] = []
    buf: list[str] = []
    cur_level = 1
    seen_title = False

    def flush() -> None:
        body = "\n".join(buf).strip()
        path: list[str] = []
        for _, h in stack:  # collapse "Messaging map > Messaging map"
            if not path or _norm_heading(path[-1]) != _norm_heading(h):
                path.append(h)
        path = path or [default_section]
        sections.append(_Section(path=path, level=cur_level, body=body))
        buf.clear()

    for line in markdown.splitlines():
        m = HEADING_RE.match(line)
        if not m:
            buf.append(line)
            continue
        flush()
        level = len(m.group(1))
        name = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", m.group(2))  # "[text](url)" -> "text"
        name = re.sub(r"\*\*|`", "", name).strip().rstrip(":").strip()
        if level == 1 and not seen_title:
            # the first level-1 heading is the page title; any later one is a section
            seen_title = True
            stack.clear()
            cur_level = 1
            continue
        while stack and stack[-1][0] >= level:
            stack.pop()
        stack.append((level, name))
        cur_level = level
    flush()
    return [s for s in sections if s.body or s.path]


def _common_prefix(a: Sequence[str], b: Sequence[str]) -> list[str]:
    out: list[str] = []
    for x, y in zip(a, b):
        if x != y:
            break
        out.append(x)
    return out


def chunk_markdown(
    markdown: str,
    title: str,
    max_chars: int = 1000,
    overlap: int = 100,
    min_section_chars: int = 150,
) -> list[Chunk]:
    """Chunk guideline markdown per the API contract.

    * split on markdown headings (section = heading path below the page title,
      e.g. ``"Disability > A"``);
    * pack paragraphs/sentences into chunks of at most ``max_chars`` characters
      (including the header line), never splitting mid-sentence;
    * consecutive chunks of the same section share ~``overlap`` characters
      (whole trailing sentences of the previous chunk);
    * every chunk's text starts with ``# <title> — <section>``.

    A very short section body (< ``min_section_chars``, e.g. a one-line lead-in such
    as ``**General terminology**``) is carried into the next section of the same
    top-level section instead of becoming a tiny chunk of its own. When that next
    section is a sibling rather than a sub-section, the short section's heading is
    kept as a bold label and the merged chunk is named after the shared parent.
    """
    if max_chars < 200:
        raise ValueError("max_chars must be >= 200")
    if overlap < 0 or overlap >= max_chars // 2:
        raise ValueError("overlap must be >= 0 and < max_chars / 2")

    sections = split_sections(markdown)
    chunks: list[Chunk] = []
    carry = ""
    carry_path: list[str] | None = None
    for i, sec in enumerate(sections):
        body, path = sec.body, sec.path
        if carry:
            if carry_path is not None:
                leaf = path[-1]
                if body and path != carry_path and _norm_heading(leaf) not in _norm_heading(body[:200]):
                    body = f"**{leaf}:**\n\n{body}"
                path = carry_path
            body = f"{carry}\n\n{body}".strip() if body else carry
            carry, carry_path = "", None
        if not body:
            continue
        nxt = sections[i + 1] if i + 1 < len(sections) else None
        if len(body) < min_section_chars and nxt is not None and nxt.path[0] == path[0]:
            if nxt.path[: len(path)] != path:
                # merging into a sibling: keep our heading as a label (so "Don't say"
                # stays distinguishable from "Instead say") and name the merged
                # chunk after the shared parent section
                leaf = path[-1]
                if _norm_heading(leaf) not in _norm_heading(body):
                    body = f"**{leaf}:**\n\n{body}"
                carry_path = _common_prefix(path, nxt.path)
            carry = body
            continue

        section_name = " > ".join(path)
        header = f"# {title} — {section_name}"
        budget = max_chars - len(header) - 2  # "\n\n" between header and body
        if budget < 100:
            # absurdly long heading path: fall back to the leaf heading only
            section_name = path[-1]
            header = f"# {title} — {section_name}"[: max_chars // 2]
            budget = max_chars - len(header) - 2

        blocks = [blk.strip() for blk in re.split(r"\n\s*\n", body) if blk.strip()]
        cur = ""
        prev = ""

        def flush() -> None:
            nonlocal prev
            if cur:
                chunks.append(Chunk(section=section_name, text=f"{header}\n\n{cur}"))
                prev = cur

        def start_new(piece: str, joiner: str) -> str:
            room = budget - len(joiner) - len(piece)
            tail = _overlap_tail(prev, overlap, cap=min(budget // 3, overlap * 4, room))
            if tail and tail != prev and len(tail) + len(joiner) + len(piece) <= budget:
                return f"{tail}{joiner}{piece}"
            return piece

        for block in blocks:
            sep = "\n\n" if cur else ""
            if len(cur) + len(sep) + len(block) <= budget:
                cur += sep + block
                continue
            if cur and len(block) <= budget and len(cur) >= budget // 2:
                # current chunk is reasonably full: start the block in a fresh chunk
                flush()
                cur = start_new(block, "\n\n")
                continue
            # fill the current chunk line-by-line / sentence-by-sentence
            for piece, joiner in _fine_pieces(block, budget):
                j = joiner if cur else ""
                if len(cur) + len(j) + len(piece) <= budget:
                    cur += j + piece
                else:
                    flush()
                    cur = start_new(piece, joiner)
        flush()

    if carry:  # trailing short lead-in with nothing after it
        section_name = " > ".join(carry_path or sections[-1].path)
        chunks.append(Chunk(section=section_name, text=f"# {title} — {section_name}\n\n{carry}"))
    return chunks


# --------------------------------------------------------------------------------------
# Manifest (pure)
# --------------------------------------------------------------------------------------


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def chunk_id_for(source_id: str, index: int) -> str:
    """1-based, zero-padded chunk id: ``editorial-style-001``."""
    return f"{source_id}-{index:03d}"


def chunk_records(source: Source, title: str, chunks: Sequence[Chunk]) -> list[dict]:
    """Manifest ``chunks`` entries for one source."""
    records = []
    for i, ch in enumerate(chunks, start=1):
        cid = chunk_id_for(source.source_id, i)
        records.append({
            "chunk_id": cid,
            "source_id": source.source_id,
            "category": source.category,
            "title": title,
            "url": source.url,
            "section": ch.section,
            "path": f"chunks/{cid}.md",
            "text": ch.text,
            "char_count": ch.char_count,
        })
    return records


def source_record(source: Source, title: str, raw_markdown: str, chunk_count: int) -> dict:
    """Manifest ``sources`` entry for one source."""
    return {
        "source_id": source.source_id,
        "title": title,
        "url": source.url,
        "category": source.category,
        "raw_path": f"raw/{source.source_id}.md",
        "chunk_count": chunk_count,
        "sha256": sha256_text(raw_markdown),
    }


def metadata_sidecar(record: dict) -> dict:
    """Bedrock Knowledge Base ``.metadata.json`` sidecar for a manifest chunk record."""
    return {
        "metadataAttributes": {
            "source_id": record["source_id"],
            "category": record["category"],
            "title": record["title"],
            "url": record["url"],
            "section": record["section"],
        }
    }


def build_manifest(
    source_records: Iterable[dict],
    chunk_records_: Iterable[dict],
    generated_at: datetime | None = None,
) -> dict:
    """Assemble ``guidelines_manifest.json``. Sources/chunks are ordered per SOURCES."""
    generated_at = generated_at or datetime.now(timezone.utc)
    if generated_at.tzinfo is None:
        generated_at = generated_at.replace(tzinfo=timezone.utc)
    order = {s.source_id: i for i, s in enumerate(SOURCES)}
    srcs = sorted(source_records, key=lambda r: order.get(r["source_id"], len(order)))
    chs = sorted(
        chunk_records_,
        key=lambda r: (order.get(r["source_id"], len(order)), r["source_id"], r["chunk_id"]),
    )
    return {
        "generated_at": generated_at.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "sources": srcs,
        "chunks": chs,
    }


# --------------------------------------------------------------------------------------
# I/O
# --------------------------------------------------------------------------------------


class FetchError(RuntimeError):
    pass


def fetch_html(url: str, session: requests.Session | None = None) -> tuple[str, str]:
    """GET ``url`` with retries/backoff. Returns ``(html, final_url)``."""
    session = session or requests.Session()
    headers = {"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml"}
    last_err: Exception | None = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = session.get(url, headers=headers, timeout=REQUEST_TIMEOUT)
            if resp.status_code >= 500 or resp.status_code == 429:
                raise FetchError(f"HTTP {resp.status_code}")
            if resp.status_code != 200:
                raise FetchError(f"HTTP {resp.status_code} for {url}")  # not retryable
            # requests falls back to ISO-8859-1 for text/* without a charset, which turns
            # UTF-8 pages into mojibake (garbled curly quotes); sniff the encoding instead
            if "charset" not in (resp.headers.get("Content-Type") or "").lower():
                resp.encoding = resp.apparent_encoding
            return resp.text, resp.url
        except FetchError as exc:
            last_err = exc
            if "for" in str(exc):
                break
        except requests.RequestException as exc:
            last_err = exc
        if attempt < MAX_RETRIES:
            delay = BACKOFF_BASE * (2 ** (attempt - 1))
            logger.warning("fetch %s failed (%s); retry %d/%d in %.1fs",
                           url, last_err, attempt, MAX_RETRIES - 1, delay)
            time.sleep(delay)
    raise FetchError(f"could not fetch {url}: {last_err}")


def _write_json(path: Path, data: object) -> None:
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def process_source(
    source: Source,
    out_dir: Path,
    max_chars: int,
    overlap: int,
    session: requests.Session | None = None,
) -> tuple[dict, list[dict]]:
    """Fetch, convert, chunk and write one source. Returns (source record, chunk records)."""
    html, final_url = fetch_html(source.url, session)
    if final_url.rstrip("/") != source.url.rstrip("/"):
        logger.warning("%s redirected to %s", source.url, final_url)
    markdown, page_title = html_to_markdown(html, final_url)
    title = page_title or source.default_title
    if len(markdown) < 1500:
        logger.warning("%s: extracted only %d chars of content", source.source_id, len(markdown))

    chunks = chunk_markdown(markdown, title, max_chars=max_chars, overlap=overlap)
    raw_dir, chunk_dir = out_dir / "raw", out_dir / "chunks"
    raw_dir.mkdir(parents=True, exist_ok=True)
    chunk_dir.mkdir(parents=True, exist_ok=True)
    (raw_dir / f"{source.source_id}.md").write_text(markdown, encoding="utf-8")

    # idempotent reruns: remove this source's old chunks first
    for old in chunk_dir.glob(f"{source.source_id}-[0-9][0-9][0-9]*.md*"):
        old.unlink()

    records = chunk_records(source, title, chunks)
    for rec in records:
        (out_dir / rec["path"]).write_text(rec["text"], encoding="utf-8")
        _write_json(out_dir / f"{rec['path']}.metadata.json", metadata_sidecar(rec))
    src_rec = source_record(source, title, markdown, len(records))
    logger.info("%s: %d chars markdown -> %d chunks", source.source_id, len(markdown), len(records))
    return src_rec, records


def load_manifest(out_dir: Path) -> dict | None:
    path = out_dir / MANIFEST_NAME
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        logger.warning("ignoring unreadable existing manifest %s", path)
        return None


def run(out_dir: Path, max_chars: int, overlap: int, source_ids: Sequence[str] | None) -> int:
    # dict.fromkeys: "--sources a a" must not process (and record) a source twice
    selected = [SOURCES_BY_ID[s] for s in dict.fromkeys(source_ids)] if source_ids else list(SOURCES)
    out_dir.mkdir(parents=True, exist_ok=True)

    # keep entries for sources we are not (re)processing this run
    existing = load_manifest(out_dir) or {"sources": [], "chunks": []}
    selected_ids = {s.source_id for s in selected}
    src_records = [r for r in existing.get("sources", []) if r.get("source_id") not in selected_ids]
    ch_records = [r for r in existing.get("chunks", []) if r.get("source_id") not in selected_ids]

    failures: list[str] = []
    session = requests.Session()
    for src in selected:
        try:
            s_rec, c_recs = process_source(src, out_dir, max_chars, overlap, session)
        except FetchError as exc:
            logger.error("%s: %s", src.source_id, exc)
            failures.append(src.source_id)
            # keep the previous successful output for this source, if any
            src_records += [r for r in existing.get("sources", []) if r.get("source_id") == src.source_id]
            ch_records += [r for r in existing.get("chunks", []) if r.get("source_id") == src.source_id]
            continue
        src_records.append(s_rec)
        ch_records.extend(c_recs)

    manifest = build_manifest(src_records, ch_records)
    _write_json(out_dir / MANIFEST_NAME, manifest)
    logger.info("wrote %s: %d sources, %d chunks",
                out_dir / MANIFEST_NAME, len(manifest["sources"]), len(manifest["chunks"]))
    if failures:
        logger.error("failed sources: %s", ", ".join(failures))
        return 1
    return 0


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR,
                   help="output directory (default: data/guidelines)")
    p.add_argument("--max-chars", type=int, default=1000, help="max characters per chunk")
    p.add_argument("--overlap", type=int, default=100, help="target overlap between chunks")
    p.add_argument("--sources", nargs="+", choices=sorted(SOURCES_BY_ID), metavar="SOURCE_ID",
                   help=f"subset of sources to process ({', '.join(SOURCES_BY_ID)})")
    p.add_argument("-v", "--verbose", action="store_true")
    args = p.parse_args(argv)
    # same limits as chunk_markdown, checked up front (before any network I/O)
    if args.max_chars < 200:
        p.error("--max-chars must be >= 200")
    if args.overlap < 0 or args.overlap >= args.max_chars // 2:
        p.error("--overlap must be >= 0 and < max-chars / 2")
    return args


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(levelname)s %(name)s: %(message)s")
    return run(args.out_dir, args.max_chars, args.overlap, args.sources)


if __name__ == "__main__":
    sys.exit(main())
