"""Text diffing and change annotations for the UIC Editorial Assistant.

Task 3.6 provides a deterministic fallback for LLM rewrites that omit or
malform the inline tags consumed by :mod:`services.change_parser`. Diffs are
calculated locally with ``difflib.SequenceMatcher`` and require no AWS access.
"""

from __future__ import annotations

import difflib
import logging
import re
from dataclasses import asdict, dataclass, field
from html import escape
from typing import Dict, List, Sequence, Tuple


VALID_RULESETS = {
    "BRAND",
    "ACCESSIBILITY",
    "CONTENT",
    "READING_LEVEL",
    "AUDIENCE_TONE",
}


class TextDiffError(ValueError):
    """Raised when text diff input or annotation metadata is invalid."""


@dataclass(frozen=True)
class _Token:
    """A diff token and its character offsets in the source string."""

    value: str
    start: int
    end: int


@dataclass
class DiffAnnotation:
    """One insert, delete, or replace operation between two texts."""

    change_id: str
    operation: str
    original_text: str
    revised_text: str
    original_start: int
    original_end: int
    revised_start: int
    revised_end: int
    rulesets: List[str]
    explanation: str

    def to_dict(self) -> Dict[str, object]:
        """Return a JSON-serializable annotation."""
        return asdict(self)


@dataclass
class DiffResult:
    """Complete comparison result for API and side-by-side UI consumers."""

    original_text: str
    revised_text: str
    annotations: List[DiffAnnotation]
    original_html: str
    revised_html: str
    stats: Dict[str, int]
    similarity_ratio: float
    warnings: List[str] = field(default_factory=list)

    @property
    def changes(self) -> List[DiffAnnotation]:
        """Alias used by existing frontend/API change-list conventions."""
        return self.annotations

    def to_dict(self) -> Dict[str, object]:
        """Return a JSON-serializable diff result."""
        return {
            "original_text": self.original_text,
            "revised_text": self.revised_text,
            "annotations": [item.to_dict() for item in self.annotations],
            "original_html": self.original_html,
            "revised_html": self.revised_html,
            "stats": dict(self.stats),
            "similarity_ratio": self.similarity_ratio,
            "warnings": list(self.warnings),
        }


class TextDiffer:
    """Generate word/whitespace-aware change annotations with ``difflib``."""

    TOKEN_PATTERN = re.compile(r"\s+|[\w]+(?:[\u2019'-][\w]+)*|[^\w\s]", re.UNICODE)

    def __init__(self) -> None:
        self.logger = logging.getLogger(__name__)

    def compare(
        self,
        original_text: str,
        revised_text: str,
        rulesets: Sequence[str] | None = None,
    ) -> DiffResult:
        """Compare two strings and return position-aware change annotations.

        A mechanical diff cannot know why an LLM made a change, so inferred
        annotations default to ``CONTENT``. Callers may provide issue-derived
        categories when that context is known.
        """
        if not isinstance(original_text, str) or not isinstance(revised_text, str):
            raise TextDiffError("original_text and revised_text must be strings")

        normalized_rulesets = self._normalize_rulesets(rulesets)
        original_tokens = self._tokenize(original_text)
        revised_tokens = self._tokenize(revised_text)
        matcher = difflib.SequenceMatcher(
            None,
            [token.value for token in original_tokens],
            [token.value for token in revised_tokens],
            autojunk=False,
        )

        annotations: List[DiffAnnotation] = []
        for tag, old_start, old_end, new_start, new_end in matcher.get_opcodes():
            if tag == "equal":
                continue
            old_span = self._span(original_tokens, old_start, old_end, len(original_text))
            new_span = self._span(revised_tokens, new_start, new_end, len(revised_text))
            before = original_text[old_span[0]:old_span[1]]
            after = revised_text[new_span[0]:new_span[1]]
            annotations.append(
                DiffAnnotation(
                    change_id=f"change-{len(annotations) + 1}",
                    operation=tag,
                    original_text=before,
                    revised_text=after,
                    original_start=old_span[0],
                    original_end=old_span[1],
                    revised_start=new_span[0],
                    revised_end=new_span[1],
                    rulesets=list(normalized_rulesets),
                    explanation=self._explain(tag, before, after),
                )
            )

        stats = {"total": len(annotations), "insert": 0, "delete": 0, "replace": 0}
        for annotation in annotations:
            stats[annotation.operation] += 1

        result = DiffResult(
            original_text=original_text,
            revised_text=revised_text,
            annotations=annotations,
            original_html=self._render_html(original_text, annotations, use_original=True),
            revised_html=self._render_html(revised_text, annotations, use_original=False),
            stats=stats,
            similarity_ratio=round(matcher.ratio(), 4),
        )
        self.logger.info(
            "Text diff complete: %d annotations (similarity %.4f)",
            len(annotations),
            result.similarity_ratio,
        )
        return result

    @classmethod
    def _tokenize(cls, text: str) -> List[_Token]:
        return [
            _Token(match.group(0), match.start(), match.end())
            for match in cls.TOKEN_PATTERN.finditer(text)
        ]

    @staticmethod
    def _span(tokens: List[_Token], start: int, end: int, text_length: int) -> Tuple[int, int]:
        """Translate a half-open token range into a character range."""
        if start < end:
            return tokens[start].start, tokens[end - 1].end
        anchor = tokens[start].start if start < len(tokens) else text_length
        return anchor, anchor

    @staticmethod
    def _normalize_rulesets(rulesets: Sequence[str] | None) -> Tuple[str, ...]:
        requested = rulesets if rulesets is not None else ("CONTENT",)
        if isinstance(requested, str):
            requested = (requested,)
        normalized: List[str] = []
        for ruleset in requested:
            if not isinstance(ruleset, str):
                raise TextDiffError("rulesets must contain strings")
            name = ruleset.strip().upper()
            if name not in VALID_RULESETS:
                raise TextDiffError(f"Unknown ruleset: {ruleset}")
            if name not in normalized:
                normalized.append(name)
        if not normalized:
            raise TextDiffError("at least one ruleset is required")
        return tuple(normalized)

    @staticmethod
    def _preview(value: str, limit: int = 80) -> str:
        compact = " ".join(value.split())
        return compact if len(compact) <= limit else f"{compact[:limit - 1]}\u2026"

    @classmethod
    def _explain(cls, operation: str, before: str, after: str) -> str:
        if operation == "insert":
            return f'Added "{cls._preview(after)}".'
        if operation == "delete":
            return f'Removed "{cls._preview(before)}".'
        return f'Changed "{cls._preview(before)}" to "{cls._preview(after)}".'

    @staticmethod
    def _render_html(
        text: str,
        annotations: List[DiffAnnotation],
        *,
        use_original: bool,
    ) -> str:
        """Render one side with escaped, non-overlapping annotated spans."""
        parts: List[str] = []
        cursor = 0
        for item in annotations:
            start = item.original_start if use_original else item.revised_start
            end = item.original_end if use_original else item.revised_end
            parts.append(escape(text[cursor:start]))
            element = "del" if use_original else "ins"
            ruleset_classes = " ".join(
                f"change-{ruleset.lower()}" for ruleset in item.rulesets
            )
            ruleset_data = ",".join(item.rulesets)
            parts.append(
                f'<{element} class="text-change diff-change diff-{item.operation} '
                f'{ruleset_classes}" data-change-id="{item.change_id}" '
                f'data-operation="{item.operation}" data-rulesets="{ruleset_data}">'
                f'{escape(text[start:end])}</{element}>'
            )
            cursor = end
        parts.append(escape(text[cursor:]))
        return "".join(parts)


def diff_text(
    original_text: str,
    revised_text: str,
    rulesets: Sequence[str] | None = None,
) -> DiffResult:
    """Convenience wrapper around :class:`TextDiffer`."""
    return TextDiffer().compare(original_text, revised_text, rulesets=rulesets)
