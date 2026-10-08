"""Function-based rules (pattern_type == "function").

Each function receives the full text and a RuleContext and returns a list of
RuleMatch spans. Register new checks with @rule_function("name") and reference
them from a ruleset JSON file via "pattern": "name". Rule-specific settings
come from the rule's "params" object.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from . import reading_level as rl


@dataclass
class RuleContext:
    audience: str
    channel: Optional[str]
    params: Dict[str, Any] = field(default_factory=dict)


@dataclass
class RuleMatch:
    start: int
    end: int
    message: Optional[str] = None      # overrides rule.message
    suggestion: Optional[str] = None   # overrides rule.suggestion
    severity: Optional[str] = None     # overrides rule.severity
    scope: str = "span"                # "span" (highlightable) or "document"


RuleFunction = Callable[[str, RuleContext], List[RuleMatch]]
RULE_FUNCTIONS: Dict[str, RuleFunction] = {}


def rule_function(name: str):
    def decorator(fn: RuleFunction) -> RuleFunction:
        RULE_FUNCTIONS[name] = fn
        return fn
    return decorator


def audience_param(ctx: RuleContext, name: str, default):
    """Read a param that is either a single value or a {audience: value} map."""
    value = ctx.params.get(name, default)
    if isinstance(value, dict):
        return value.get(ctx.audience, default)
    return value


def _doc_match(text: str, message: str, **kwargs) -> RuleMatch:
    return RuleMatch(start=0, end=len(text), message=message, scope="document", **kwargs)


# --------------------------------------------------------------------------
# Reading level
# --------------------------------------------------------------------------


@rule_function("reading_grade_level")
def reading_grade_level(text: str, ctx: RuleContext) -> List[RuleMatch]:
    """Flag the whole document when its FK grade exceeds the audience target."""
    metrics = rl.compute_metrics(text)
    if metrics.word_count < ctx.params.get("min_words", 30):
        return []  # FK is unreliable on very short texts
    target = rl.grade_target_for(ctx.audience)
    if metrics.grade_level <= target:
        return []
    over = metrics.grade_level - target
    severity = "high" if over >= ctx.params.get("high_severity_margin", 3) else "medium"
    return [_doc_match(
        text,
        f"Reading level is grade {metrics.grade_level:g}; the target for {ctx.audience} "
        f"is grade {target:g} or lower.",
        severity=severity,
    )]


@rule_function("complex_sentences")
def complex_sentences(text: str, ctx: RuleContext) -> List[RuleMatch]:
    """Flag individual sentences that read well above the audience target."""
    target = rl.grade_target_for(ctx.audience)
    margin = ctx.params.get("margin", 4)
    min_words = ctx.params.get("min_words", 12)
    # Sentences longer than this are already reported by long_sentences.
    max_words = audience_param(ctx, "skip_if_longer_than", 25)
    matches = []
    for start, end in rl.split_sentences(text):
        sentence = text[start:end]
        m = rl.compute_metrics(sentence)
        if min_words <= m.word_count <= max_words and m.grade_level > target + margin:
            matches.append(RuleMatch(
                start, end,
                message=f"This sentence reads at about grade {m.grade_level:g} "
                        f"(target {target:g}). Use shorter words or split it.",
            ))
    return matches


@rule_function("long_sentences")
def long_sentences(text: str, ctx: RuleContext) -> List[RuleMatch]:
    max_words = audience_param(ctx, "max_words", 25)
    matches = []
    for start, end in rl.split_sentences(text):
        n = len(rl.words(text[start:end]))
        if n > max_words:
            matches.append(RuleMatch(
                start, end,
                message=f"Sentence has {n} words (recommended maximum {max_words}).",
            ))
    return matches


@rule_function("long_paragraphs")
def long_paragraphs(text: str, ctx: RuleContext) -> List[RuleMatch]:
    max_words = ctx.params.get("max_words", 100)
    max_sentences = ctx.params.get("max_sentences", 5)
    matches = []
    for start, end in rl.split_paragraphs(text):
        para = text[start:end]
        n_words = len(rl.words(para))
        n_sent = len(rl.split_sentences(para))
        if n_words > max_words or n_sent > max_sentences:
            matches.append(RuleMatch(
                start, end,
                message=f"Paragraph has {n_words} words and {n_sent} sentences "
                        f"(recommended maximum {max_words} words / {max_sentences} sentences).",
            ))
    return matches


# --------------------------------------------------------------------------
# Brand
# --------------------------------------------------------------------------

_FULL_NAME_RE = re.compile(r"University of Illinois Chicago", re.IGNORECASE)
_UIC_RE = re.compile(r"\bUIC\b")


@rule_function("first_reference_full_name")
def first_reference_full_name(text: str, ctx: RuleContext) -> List[RuleMatch]:
    """'UIC' should not appear before the full name has been introduced."""
    first_uic = _UIC_RE.search(text)
    if not first_uic:
        return []
    full = _FULL_NAME_RE.search(text)
    if full and full.start() < first_uic.start():
        return []
    return [RuleMatch(first_uic.start(), first_uic.end())]


# --------------------------------------------------------------------------
# Accessibility
# --------------------------------------------------------------------------

_DEFAULT_ACRONYM_ALLOWLIST = {
    "UIC", "US", "USA", "AM", "PM", "FAQ", "ID", "PDF", "URL", "OK", "TV",
    "GPA", "CEO", "COVID", "ASAP", "RSVP", "PIN", "DIY", "AI", "IT", "HR",
    "PHD", "MBA", "MD", "BS", "BA", "MS", "MA", "CST", "CDT", "UI", "NCAA",
    # Approved by the UIC editorial guide
    "MC", "MPH", "DDS", "BSW", "EDD", "PSYD", "LGBTQ", "AY", "FY", "QA",
}
_ACRONYM_RE = re.compile(r"\b[A-Z][A-Z0-9&]{1,5}s?\b")
_CAPS_RUN_RE = re.compile(r"\b[A-Z]{2,}(?:[\s,'!?.-]+[A-Z]{2,})+\b")
# Same, but never crosses sentence punctuation or a line break.
_CAPS_PHRASE_RE = re.compile(r"\b[A-Z]{2,}(?:[ \t,'-]+[A-Z]{2,})+\b")


@rule_function("unexpanded_acronyms")
def unexpanded_acronyms(text: str, ctx: RuleContext) -> List[RuleMatch]:
    """Flag the first use of an acronym that is never spelled out as 'Full Name (ACR)'."""
    allow = _DEFAULT_ACRONYM_ALLOWLIST | {a.upper() for a in ctx.params.get("allowlist", [])}
    shouting = [(m.start(), m.end()) for m in _CAPS_RUN_RE.finditer(text)]
    seen = set()
    matches = []
    for m in _ACRONYM_RE.finditer(text):
        acr = m.group(0)
        base = acr[:-1] if acr.endswith("s") else acr
        if base.upper() in allow or base in seen:
            continue
        if any(s <= m.start() < e for s, e in shouting):
            continue  # all-caps prose is handled by all_caps_text
        seen.add(base)
        if re.search(r"\(\s*" + re.escape(base) + r"s?\s*\)", text):
            continue  # defined somewhere as "... (ACR)"
        matches.append(RuleMatch(
            m.start(), m.end(),
            message=f"'{base}' may be unfamiliar. UIC style avoids acronyms other than broadly "
                    "understood ones like UIC; use the full name.",
        ))
    return matches


@rule_function("all_caps_text")
def all_caps_text(text: str, ctx: RuleContext) -> List[RuleMatch]:
    """Runs of two or more ALL-CAPS words within a sentence.

    Known acronyms at either end of a run are trimmed off ("RSVP NOW" -> "NOW"),
    and runs made only of known acronyms ("UIC ID") are ignored.
    """
    allow = _DEFAULT_ACRONYM_ALLOWLIST | {a.upper() for a in ctx.params.get("allowlist", [])}
    matches = []
    for m in _CAPS_PHRASE_RE.finditer(text):
        tokens = [(t.start(), t.end(), t.group(0))
                  for t in re.finditer(r"[A-Z]{2,}", text[m.start():m.end()])]
        while tokens and tokens[0][2] in allow:
            tokens.pop(0)
        while tokens and tokens[-1][2] in allow:
            tokens.pop()
        if tokens:
            matches.append(RuleMatch(m.start() + tokens[0][0], m.start() + tokens[-1][1]))
    return matches


_EMOJI_RE = re.compile(
    "[\U0001F300-\U0001FAFF\U00002600-\U000027BF\U0001F1E6-\U0001F1FF]"
)


@rule_function("emoji_overuse")
def emoji_overuse(text: str, ctx: RuleContext) -> List[RuleMatch]:
    max_emojis = ctx.params.get("max_emojis", 3)
    found = list(_EMOJI_RE.finditer(text))
    if len(found) <= max_emojis:
        return []
    # Highlight the emojis beyond the limit.
    return [
        RuleMatch(m.start(), m.end(),
                  message=f"Text uses {len(found)} emojis (recommended maximum {max_emojis}). "
                          "Screen readers read each emoji aloud.")
        for m in found[max_emojis:]
    ]


@rule_function("non_camelcase_hashtags")
def non_camelcase_hashtags(text: str, ctx: RuleContext) -> List[RuleMatch]:
    """Long all-lowercase hashtags are read as one word by screen readers."""
    min_len = ctx.params.get("min_length", 10)
    matches = []
    for m in re.finditer(r"#([A-Za-z][A-Za-z0-9]*)", text):
        tag = m.group(1)
        if len(tag) >= min_len and (tag.islower() or tag.isupper()):
            matches.append(RuleMatch(m.start(), m.end()))
    return matches


# --------------------------------------------------------------------------
# Content / channel limits
# --------------------------------------------------------------------------


# The trailing period is only part of the match for the dotted form ("p.m."),
# so a sentence-ending period after "PM." is left alone.
_TIME_RE = re.compile(r"\b(\d{1,2})(?::(\d{2}))?\s*([AaPp])(?:\.\s?[Mm]\b\.?|\s?[Mm]\b)")


@rule_function("time_format")
def time_format(text: str, ctx: RuleContext) -> List[RuleMatch]:
    """AP style: '3 p.m.', '3:30 a.m.', 'noon', 'midnight' (no ':00', no 'PM')."""
    matches = []
    for m in _TIME_RE.finditer(text):
        hour, minutes, half = m.group(1), m.group(2), m.group(3).lower()
        if hour == "12" and minutes in (None, "00"):
            correct = "noon" if half == "p" else "midnight"
        else:
            mins = f":{minutes}" if minutes and minutes != "00" else ""
            correct = f"{hour}{mins} {half}.m."
        if m.group(0) != correct:
            matches.append(RuleMatch(m.start(), m.end(), suggestion=correct))
    return matches


_MONTH_ABBREVIATIONS = {
    "January": "Jan.", "February": "Feb.", "August": "Aug.", "September": "Sept.",
    "October": "Oct.", "November": "Nov.", "December": "Dec.",
}
_MONTH_FULL = {abbr: full for full, abbr in _MONTH_ABBREVIATIONS.items()}
_MONTH_NEVER_ABBREVIATED = {"Mar.": "March", "Apr.": "April", "Jun.": "June", "Jul.": "July"}
_LONG_MONTH_WITH_DAY_RE = re.compile(
    r"\b(January|February|August|September|October|November|December)(?=\s+\d{1,2}(?:st|nd|rd|th)?\b)"
)
_SHORT_MONTH_ABBR_RE = re.compile(r"\b(Mar|Apr|Jun|Jul)\.")
_SEP_RE = re.compile(r"\bSep\b\.?(?!t)")
_ABBR_MONTH_WITHOUT_DAY_RE = re.compile(r"\b(Jan|Feb|Aug|Sept|Oct|Nov|Dec)\.(?!\s*\d)")


@rule_function("month_format")
def month_format(text: str, ctx: RuleContext) -> List[RuleMatch]:
    """UIC/AP: abbreviate Jan., Feb., Aug., Sept., Oct., Nov., Dec. only with a specific
    date; always spell out March-July; spell out any month used without a date."""
    matches = []
    for m in _LONG_MONTH_WITH_DAY_RE.finditer(text):
        matches.append(RuleMatch(m.start(), m.end(), suggestion=_MONTH_ABBREVIATIONS[m.group(1)],
                                 message="Abbreviate this month when it is used with a specific date."))
    for m in _SHORT_MONTH_ABBR_RE.finditer(text):
        matches.append(RuleMatch(m.start(), m.end(), suggestion=_MONTH_NEVER_ABBREVIATED[m.group(0)],
                                 message="Always spell out March, April, May, June and July."))
    for m in _SEP_RE.finditer(text):
        matches.append(RuleMatch(m.start(), m.end(), suggestion="Sept.",
                                 message="The abbreviation for September is \"Sept.\""))
    for m in _ABBR_MONTH_WITHOUT_DAY_RE.finditer(text):
        matches.append(RuleMatch(m.start(), m.end(), suggestion=_MONTH_FULL[m.group(1) + "."],
                                 message="Spell out the month when it is used without a specific date."))
    return matches


_STREET_SUFFIX_RE = re.compile(r"\b([A-Z][a-z]+)\s+(St|Ave|Blvd|Rd|Pkwy)\.")
_STREET_SUFFIX_FULL = {"St": "Street", "Ave": "Avenue", "Blvd": "Boulevard", "Rd": "Road", "Pkwy": "Parkway"}
_NUMBERED_ADDRESS_TAIL_RE = re.compile(r"\d+\s+(?:[NSEW]\.?\s+)?$")


@rule_function("street_suffix")
def street_suffix(text: str, ctx: RuleContext) -> List[RuleMatch]:
    """Spell out street suffixes unless part of a numbered address (1200 W. Harrison St.)."""
    matches = []
    for m in _STREET_SUFFIX_RE.finditer(text):
        if _NUMBERED_ADDRESS_TAIL_RE.search(text[max(0, m.start() - 12):m.start()]):
            continue
        start = m.start(2)
        matches.append(RuleMatch(start, m.end(), suggestion=_STREET_SUFFIX_FULL[m.group(2)]))
    return matches


# ", item, and" / ", item, or": the second comma is the serial (Oxford) comma.
_SERIAL_COMMA_RE = re.compile(r",\s+[^,.;:!?\n]{1,40}(,)\s+(?:and|or)\s+\w")


@rule_function("serial_comma")
def serial_comma(text: str, ctx: RuleContext) -> List[RuleMatch]:
    return [RuleMatch(m.start(1), m.end(1)) for m in _SERIAL_COMMA_RE.finditer(text)]


_NUMBER_WORDS = ["", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine"]
_SINGLE_DIGIT_RE = re.compile(r"(?<![\w.,:/$#&+-])([1-9])(?![\w.,:%/-])")
# Contexts where a numeral is correct (AP): dates, addresses, rooms, ranks, ages, times,
# percentages, distances, list markers.
_NUMERAL_OK_BEFORE_RE = re.compile(
    r"(?:\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)[a-z]*\.?|\bNo\.|\b(?:Room|Suite|"
    r"MC|Floor|Level|Chapter|Page|Grade|Step|Phase|Section|Unit|Lot|Gate|Building|Title|Article|"
    r"Version|Week|Day|Year|Part|Track|Platform|Route|Bus|Line)|^\s*)\s*$",
    re.IGNORECASE,
)
_NUMERAL_OK_AFTER_RE = re.compile(
    r"^\s*(?:[ap]\.?m\b|o'clock|percent|%|-?year|years? old|-month-old|-week-old|"
    r"(?:miles?|feet|foot|ft|inch(?:es)?|km|meters?|mph)\b|[.)]\s)",
    re.IGNORECASE,
)


@rule_function("small_numerals")
def small_numerals(text: str, ctx: RuleContext) -> List[RuleMatch]:
    """Spell out one through nine (AP), except where numerals are standard."""
    matches = []
    for m in _SINGLE_DIGIT_RE.finditer(text):
        line_start = text.rfind("\n", 0, m.start()) + 1
        before = text[max(line_start, m.start() - 15):m.start()]
        after = text[m.end():m.end() + 15]
        if _NUMERAL_OK_BEFORE_RE.search(before) or _NUMERAL_OK_AFTER_RE.match(after):
            continue
        matches.append(RuleMatch(m.start(), m.end(), suggestion=_NUMBER_WORDS[int(m.group(1))]))
    return matches


@rule_function("lowercase_midsentence")
def lowercase_midsentence(text: str, ctx: RuleContext) -> List[RuleMatch]:
    """Flag listed terms capitalized in the middle of a sentence.

    params.terms: words that should be lowercase unless they start a sentence.
    Terms followed by "of" are treated as part of a formal name and skipped.
    """
    matches = []
    for term in ctx.params.get("terms", []):
        pattern = re.compile(r"(?<=[a-z0-9,;] )" + re.escape(term) + r"\b(?!\s+of\b)")
        for m in pattern.finditer(text):
            matches.append(RuleMatch(m.start(), m.end(), suggestion=term.lower()))
    return matches


_ALUMNI_RE = re.compile(r"\b(alumnus|alumna|alumnae|alumni)\b", re.IGNORECASE)
_ALUMNI_FIX = {"alumnus": "alum", "alumna": "alum", "alumnae": "alums", "alumni": "alums"}
# "University of Illinois Alumni Association", "Alumni Weekend": official names keep "Alumni".
_ALUMNI_PROPER_NAME_RE = re.compile(r"\s+[A-Z][a-z]+")


@rule_function("alumni_terms")
def alumni_terms(text: str, ctx: RuleContext) -> List[RuleMatch]:
    """Prefer gender-neutral alum/alums over alumnus/alumna/alumni/alumnae."""
    matches = []
    for m in _ALUMNI_RE.finditer(text):
        word = m.group(1)
        if word[0].isupper() and _ALUMNI_PROPER_NAME_RE.match(text, m.end()):
            continue  # part of a formal name
        fix = _ALUMNI_FIX[word.lower()]
        matches.append(RuleMatch(m.start(), m.end(), suggestion=fix.capitalize() if word[0].isupper() else fix))
    return matches


@rule_function("max_characters")
def max_characters(text: str, ctx: RuleContext) -> List[RuleMatch]:
    limit = ctx.params.get("max_chars", 280)
    if len(text) <= limit:
        return []
    return [RuleMatch(
        limit, len(text),
        message=f"Text is {len(text)} characters; the limit for this channel is {limit}. "
                "Highlighted text is past the limit.",
    )]


@rule_function("max_words")
def max_words(text: str, ctx: RuleContext) -> List[RuleMatch]:
    limit = ctx.params.get("max_words", 300)
    n = len(rl.words(text))
    if n <= limit:
        return []
    return [_doc_match(text, f"Text is {n} words; aim for {limit} or fewer for this channel.")]


# --------------------------------------------------------------------------
# Audience tone
# --------------------------------------------------------------------------


@rule_function("excessive_exclamations")
def excessive_exclamations(text: str, ctx: RuleContext) -> List[RuleMatch]:
    max_count = ctx.params.get("max_count", 2)
    found = list(re.finditer(r"!+", text))
    if len(found) <= max_count:
        return []
    return [
        RuleMatch(m.start(), m.end(),
                  message=f"Text has {len(found)} exclamation points. UIC style uses them "
                          f"rarely (at most {max_count}).")
        for m in found[max_count:]
    ]
