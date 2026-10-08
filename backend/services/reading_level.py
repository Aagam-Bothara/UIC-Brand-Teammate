"""Readability metrics (Task 2.3).

Implements Flesch-Kincaid Grade Level and Flesch Reading Ease with a
heuristic syllable counter. No external dependencies so it runs in Lambda
without extra layers.

    FK grade   = 0.39 * (words / sentences) + 11.8 * (syllables / words) - 15.59
    Reading ease = 206.835 - 1.015 * (words / sentences) - 84.6 * (syllables / words)
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List, Tuple

# Target grade levels per audience (SPEC: Students Grade 8, Faculty/Staff Grade 10).
AUDIENCE_GRADE_TARGETS = {
    "students": 8.0,
    "faculty": 10.0,
    "staff": 10.0,
}
DEFAULT_GRADE_TARGET = 10.0

WORD_RE = re.compile(r"[A-Za-z]+(?:['’][A-Za-z]+)*")

# Abbreviations whose trailing period should not end a sentence.
_ABBREVIATIONS = [
    "Mr.", "Mrs.", "Ms.", "Dr.", "Prof.", "Sr.", "Jr.", "St.", "vs.", "etc.",
    "e.g.", "i.e.", "a.m.", "p.m.", "A.M.", "P.M.", "U.S.", "Ph.D.", "No.",
    "Jan.", "Feb.", "Aug.", "Sept.", "Oct.", "Nov.", "Dec.", "Univ.", "Dept.",
]
_ABBREV_RE = re.compile(
    r"(?<!\w)(" + "|".join(re.escape(a) for a in sorted(_ABBREVIATIONS, key=len, reverse=True)) + r")"
)
# A sentence ends at . ! ? (optionally followed by closing quotes/brackets)
# or at a line break (headings, bullet points, sign-offs).
_SENTENCE_END_RE = re.compile(r"[.!?]+[\"'’”)\]]*(?=\s|$)|\n+")

# Words the vowel-group heuristic gets wrong.
_SYLLABLE_OVERRIDES = {
    "the": 1, "every": 3, "people": 2, "business": 2, "area": 3, "idea": 3,
    "create": 2, "created": 3, "being": 2, "science": 2, "sciences": 3,
    "university": 5, "chicago": 3, "illinois": 3, "via": 2, "quiet": 2,
    "poem": 2, "real": 1, "really": 2, "toward": 2, "towards": 2,
    "naive": 2, "orientation": 5, "evaluate": 4, "academic": 4,
}


def count_syllables(word: str) -> int:
    """Estimate the number of syllables in a single English word."""
    w = re.sub(r"[^a-z]", "", word.lower())
    if not w:
        return 0
    if w in _SYLLABLE_OVERRIDES:
        return _SYLLABLE_OVERRIDES[w]
    if len(w) <= 3:
        return 1

    # Drop silent endings: -es, -ed (but not -ted/-ded), trailing silent -e (but not -le).
    if w.endswith("es") and not w.endswith(("ses", "zes", "ces", "ges", "xes", "ches", "shes")):
        w = w[:-2]
    elif w.endswith("ed") and not w.endswith(("ted", "ded")):
        w = w[:-2]
    elif w.endswith("e") and not w.endswith(("le", "ee", "ye")):
        w = w[:-1]

    count = len(re.findall(r"[aeiouy]+", w))
    # Vowel pairs that are usually two syllables: "ia" (media, but not social/partial),
    # "ua" (actual, but not quality/language), "eo" (video).
    count += len(re.findall(r"(?<![aeioucgst])ia|(?<![qg])ua|eo", w))
    return max(1, count)


# Abbreviations that often end a sentence ("...at 3 p.m. Join us").
_TERMINAL_ABBREVIATIONS = {"a.m.", "p.m.", "etc."}


def _mask_abbreviation(m: "re.Match") -> str:
    abbr = m.group(0)
    if abbr.lower() in _TERMINAL_ABBREVIATIONS and re.match(r"\s+[A-Z]", m.string[m.end():]):
        return abbr  # keep the final period: it ends the sentence
    return abbr.replace(".", "\x00")


def split_sentences(text: str) -> List[Tuple[int, int]]:
    """Return (start, end) character spans of sentences in `text`."""
    # Mask abbreviation periods so they don't terminate sentences; keep offsets intact.
    masked = _ABBREV_RE.sub(_mask_abbreviation, text)
    spans: List[Tuple[int, int]] = []
    pos = 0
    for m in _SENTENCE_END_RE.finditer(masked):
        end = m.end()
        span = _trim(text, pos, end)
        if span and WORD_RE.search(text[span[0]:span[1]]):
            spans.append(span)
        pos = end
    span = _trim(text, pos, len(text))
    if span and WORD_RE.search(text[span[0]:span[1]]):
        spans.append(span)
    return spans


def _trim(text: str, start: int, end: int):
    while start < end and text[start].isspace():
        start += 1
    while end > start and text[end - 1].isspace():
        end -= 1
    return (start, end) if end > start else None


def split_paragraphs(text: str) -> List[Tuple[int, int]]:
    """Return (start, end) spans of blank-line-separated paragraphs."""
    spans = []
    pos = 0
    for m in re.finditer(r"\n\s*\n", text):
        span = _trim(text, pos, m.start())
        if span:
            spans.append(span)
        pos = m.end()
    span = _trim(text, pos, len(text))
    if span:
        spans.append(span)
    return spans


def words(text: str) -> List[str]:
    return WORD_RE.findall(text)


@dataclass
class ReadabilityMetrics:
    word_count: int
    sentence_count: int
    syllable_count: int
    grade_level: float
    reading_ease: float

    @property
    def avg_words_per_sentence(self) -> float:
        return self.word_count / self.sentence_count if self.sentence_count else 0.0

    @property
    def avg_syllables_per_word(self) -> float:
        return self.syllable_count / self.word_count if self.word_count else 0.0


def compute_metrics(text: str) -> ReadabilityMetrics:
    """Compute Flesch-Kincaid grade level and reading ease for `text`."""
    ws = words(text)
    n_words = len(ws)
    n_sentences = max(1, len(split_sentences(text))) if n_words else 0
    n_syllables = sum(count_syllables(w) for w in ws)

    if n_words == 0:
        return ReadabilityMetrics(0, 0, 0, 0.0, 100.0)

    wps = n_words / n_sentences
    spw = n_syllables / n_words
    grade = 0.39 * wps + 11.8 * spw - 15.59
    ease = 206.835 - 1.015 * wps - 84.6 * spw
    return ReadabilityMetrics(
        word_count=n_words,
        sentence_count=n_sentences,
        syllable_count=n_syllables,
        grade_level=round(max(0.0, grade), 1),
        reading_ease=round(max(0.0, min(100.0, ease)), 1),
    )


def grade_target_for(audience: str) -> float:
    return AUDIENCE_GRADE_TARGETS.get((audience or "").lower(), DEFAULT_GRADE_TARGET)
