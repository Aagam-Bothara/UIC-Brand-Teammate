"""
Change Tag Parser for UIC Editorial Assistant
Task 3.4: Change Tagging Implementation

This module parses inline change tags from LLM output and generates HTML
for progressive reveal functionality in the frontend.

Tag Types:
- [BRAND]...[/BRAND] - Brand compliance fixes
- [ACCESSIBILITY]...[/ACCESSIBILITY] - Accessibility improvements
- [CONTENT]...[/CONTENT] - Content quality enhancements
- [READING_LEVEL]...[/READING_LEVEL] - Reading level simplifications
- [AUDIENCE_TONE]...[/AUDIENCE_TONE] - Audience-specific tone adjustments
"""

import logging
import re
from dataclasses import dataclass, field
from typing import Dict, List, Tuple
from html import escape


@dataclass
class Change:
    """
    Represents a single tagged change in the rewritten text.
    
    Attributes:
        text: The changed text content
        rulesets: List of ruleset tags applied to this change (e.g., ['BRAND', 'ACCESSIBILITY'])
        start_pos: Character position where change starts in original tagged text
        end_pos: Character position where change ends in original tagged text
        html: HTML representation with styling (generated)
    """
    text: str
    rulesets: List[str]
    start_pos: int
    end_pos: int
    html: str = field(default="", init=False)
    
    def __post_init__(self):
        """Generate HTML after initialization."""
        self.html = self._generate_html()
    
    def _generate_html(self) -> str:
        """
        Generate HTML representation with proper styling.
        
        Returns:
            HTML string with span wrapper and data attributes
        """
        # Escape text for HTML
        escaped_text = escape(self.text)
        
        # Join rulesets for CSS classes and data attributes
        ruleset_classes = " ".join([f"change-{rs.lower()}" for rs in self.rulesets])
        ruleset_data = ",".join(self.rulesets)
        
        # Primary ruleset (first one) for color coding
        primary_ruleset = self.rulesets[0] if self.rulesets else "unknown"
        
        return (
            f'<span class="text-change {ruleset_classes}" '
            f'data-rulesets="{ruleset_data}" '
            f'data-primary="{primary_ruleset}">'
            f'{escaped_text}'
            f'</span>'
        )
    
    def to_dict(self) -> Dict:
        """Convert to dictionary for API responses."""
        return {
            'text': self.text,
            'rulesets': self.rulesets,
            'start_pos': self.start_pos,
            'end_pos': self.end_pos,
            'html': self.html
        }


@dataclass
class ParseResult:
    """
    Result of parsing tagged text.
    
    Attributes:
        plain_text: Text with all tags removed
        html: Full HTML with styled changes
        changes: List of Change objects
        stats: Statistics about changes by ruleset
        warnings: List of warnings about malformed tags
    """
    plain_text: str
    html: str
    changes: List[Change]
    stats: Dict[str, int]
    warnings: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict:
        """Convert to dictionary for API responses."""
        return {
            'plain_text': self.plain_text,
            'html': self.html,
            'changes': [c.to_dict() for c in self.changes],
            'stats': self.stats,
            'warnings': self.warnings
        }


class ChangeParserError(Exception):
    """Base exception for change parser errors."""
    pass


class ChangeParser:
    """
    Parser for inline change tags in LLM output.
    
    Handles:
    - Parsing nested and overlapping tags
    - Generating HTML with proper styling
    - Extracting plain text
    - Computing statistics
    - Handling malformed tags gracefully
    """
    
    # Valid ruleset tag names
    VALID_RULESETS = {
        'BRAND',
        'ACCESSIBILITY',
        'CONTENT',
        'READING_LEVEL',
        'AUDIENCE_TONE'
    }
    
    # Color scheme for each ruleset (for CSS styling)
    RULESET_COLORS = {
        'BRAND': '#3B82F6',           # Blue
        'ACCESSIBILITY': '#10B981',   # Green
        'CONTENT': '#F59E0B',         # Amber
        'READING_LEVEL': '#8B5CF6',   # Purple
        'AUDIENCE_TONE': '#EC4899'    # Pink
    }

    # Match tag-shaped tokens emitted by the LLM. Names are normalized to
    # uppercase so harmless casing differences do not leak into the output.
    TAG_PATTERN = re.compile(r'\[(/?)([A-Za-z_]+)\]')
    
    def __init__(self):
        """Initialize the change parser."""
        self.logger = self._setup_logging()
        

    def parse(self, tagged_text: str) -> ParseResult:
        """
        Parse tagged text and generate HTML with plain text.
        
        Args:
            tagged_text: Text with inline change tags
        
        Returns:
            ParseResult with plain text, HTML, changes, and stats
        
        Example:
            >>> parser = ChangeParser()
            >>> result = parser.parse("The [BRAND]University of Illinois Chicago[/BRAND] offers...")
            >>> print(result.plain_text)
            "The University of Illinois Chicago offers..."
            >>> print(result.stats)
            {'BRAND': 1, 'ACCESSIBILITY': 0, ...}
        """
        if not isinstance(tagged_text, str):
            raise ChangeParserError("tagged_text must be a string")
        self.logger.info(f"Parsing tagged text ({len(tagged_text)} chars)")
        
        # Track warnings
        warnings = []
        
        # Parse changes using stack-based approach
        changes, matched_tags, parse_warnings = self._parse_changes(tagged_text)
        warnings.extend(parse_warnings)
        
        # Generate plain text (remove all tags)
        plain_text = self._generate_plain_text(tagged_text)
        
        # Generate HTML with styled spans
        html = self._generate_html(tagged_text, matched_tags)
        
        # Compute statistics
        stats = self._compute_stats(changes)
        
        self.logger.info(
            f"Parsing complete: {len(changes)} changes, "
            f"{len(warnings)} warnings"
        )
        
        return ParseResult(
            plain_text=plain_text,
            html=html,
            changes=changes,
            stats=stats,
            warnings=warnings
        )
    
    def get_css_styles(self) -> str:
        """
        Generate CSS styles for change highlighting.
        
        Returns:
            CSS string with styles for all ruleset types
        
        This can be embedded in the frontend or served separately.
        """
        css_lines = [
            "/* UIC Editorial Assistant - Change Highlighting Styles */",
            "",
            "/* Base change style */",
            ".text-change {",
            "  padding: 2px 4px;",
            "  border-radius: 3px;",
            "  transition: all 0.2s ease;",
            "  cursor: pointer;",
            "}",
            "",
            ".text-change:hover {",
            "  opacity: 0.8;",
            "  box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);",
            "}",
            ""
        ]
        
        # Generate styles for each ruleset
        for ruleset, color in self.RULESET_COLORS.items():
            css_lines.extend([
                f"/* {ruleset.replace('_', ' ').title()} changes */",
                f".change-{ruleset.lower()} {{",
                f"  background-color: {color}20;",  # 20 = 12.5% opacity in hex
                f"  border-bottom: 2px solid {color};",
                "}",
                ""
            ])
        
        # Add toggle states
        css_lines.extend([
            "/* Hidden state when ruleset is toggled off */",
            ".text-change.hidden {",
            "  background-color: transparent;",
            "  border-bottom: none;",
            "  padding: 0;",
            "}",
            "",
            "/* Active/selected state */",
            ".text-change.active {",
            "  box-shadow: 0 0 0 2px rgba(59, 130, 246, 0.5);",
            "}"
        ])
        
        return "\n".join(css_lines)
    
    # Private methods
    
    def _setup_logging(self) -> logging.Logger:
        """Configure logging."""
        logger = logging.getLogger(__name__)
        
        if not logger.handlers:
            handler = logging.StreamHandler()
            formatter = logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
            )
            handler.setFormatter(formatter)
            logger.addHandler(handler)
            logger.setLevel(logging.INFO)
        
        return logger
    
    def _parse_changes(
        self, tagged_text: str
    ) -> Tuple[List[Change], Dict[int, int], List[str]]:
        """Parse changes and recover safely from malformed nesting."""
        tokens = list(self.TAG_PATTERN.finditer(tagged_text))
        warnings: List[str] = []
        stack: List[int] = []
        matched_tags: Dict[int, int] = {}

        for token_index, token in enumerate(tokens):
            is_closing = bool(token.group(1))
            tag_name = token.group(2).upper()

            if tag_name not in self.VALID_RULESETS:
                warnings.append(
                    f"Unknown tag '{token.group(2)}' at position {token.start()}"
                )
                continue

            if not is_closing:
                stack.append(token_index)
                continue

            matching_stack_index = next(
                (
                    index
                    for index in range(len(stack) - 1, -1, -1)
                    if tokens[stack[index]].group(2).upper() == tag_name
                ),
                None,
            )
            if matching_stack_index is None:
                warnings.append(
                    f"Unmatched closing tag '[/{tag_name}]' at position "
                    f"{token.start()}"
                )
                continue

            while len(stack) - 1 > matching_stack_index:
                discarded = tokens[stack.pop()]
                discarded_name = discarded.group(2).upper()
                warnings.append(
                    f"Unclosed tag '[{discarded_name}]' at position "
                    f"{discarded.start()} before closing '[/{tag_name}]'"
                )

            opening_index = stack.pop()
            matched_tags[opening_index] = token_index

        for opening_index in stack:
            opening = tokens[opening_index]
            tag_name = opening.group(2).upper()
            warnings.append(
                f"Unclosed tag '[{tag_name}]' at position {opening.start()}"
            )

        changes = []
        for opening_index, closing_index in sorted(
            matched_tags.items(), key=lambda item: tokens[item[0]].start()
        ):
            opening = tokens[opening_index]
            closing = tokens[closing_index]
            tag_name = opening.group(2).upper()
            changes.append(
                Change(
                    text=self._generate_plain_text(
                        tagged_text[opening.end():closing.start()]
                    ),
                    rulesets=[tag_name],
                    start_pos=opening.start(),
                    end_pos=closing.end(),
                )
            )

        return changes, matched_tags, warnings

    def _generate_plain_text(self, tagged_text: str) -> str:
        """
        Remove all tags to generate plain text.
        
        Args:
            tagged_text: Text with tags
        
        Returns:
            Plain text with tags removed
        """
        # Remove all tags (opening and closing)
        plain = self.TAG_PATTERN.sub('', tagged_text)
        return plain
    
    def _generate_html(
        self, tagged_text: str, matched_tags: Dict[int, int]
    ) -> str:
        """Generate balanced, escaped HTML for correctly matched tags."""
        tokens = list(self.TAG_PATTERN.finditer(tagged_text))
        closing_to_opening = {
            closing_index: opening_index
            for opening_index, closing_index in matched_tags.items()
        }
        html_parts: List[str] = []
        cursor = 0

        for token_index, token in enumerate(tokens):
            html_parts.append(escape(tagged_text[cursor:token.start()]))

            if token_index in matched_tags:
                ruleset = token.group(2).upper()
                html_parts.append(
                    f'<span class="text-change change-{ruleset.lower()}" '
                    f'data-rulesets="{ruleset}" '
                    f'data-primary="{ruleset}">'
                )
            elif token_index in closing_to_opening:
                html_parts.append('</span>')
            # Unknown or malformed tokens are omitted, retaining their content.
            cursor = token.end()

        html_parts.append(escape(tagged_text[cursor:]))
        return ''.join(html_parts)

    def _compute_stats(self, changes: List[Change]) -> Dict[str, int]:
        """
        Compute statistics about changes by ruleset.
        
        Args:
            changes: List of Change objects
        
        Returns:
            Dictionary mapping ruleset names to counts
        """
        stats = {ruleset: 0 for ruleset in self.VALID_RULESETS}
        
        for change in changes:
            for ruleset in change.rulesets:
                if ruleset in stats:
                    stats[ruleset] += 1
        
        return stats


# Convenience function for quick parsing
def parse_changes(tagged_text: str) -> ParseResult:
    """
    Parse tagged text and return results.
    
    Args:
        tagged_text: Text with inline change tags
    
    Returns:
        ParseResult with plain text, HTML, and statistics
    
    Example:
        >>> from services.change_parser import parse_changes
        >>> result = parse_changes("The [BRAND]University of Illinois Chicago[/BRAND] offers...")
        >>> print(result.plain_text)
    """
    parser = ChangeParser()
    return parser.parse(tagged_text)


def get_ruleset_colors() -> Dict[str, str]:
    """
    Get color scheme for rulesets.
    
    Returns:
        Dictionary mapping ruleset names to hex colors
    """
    return ChangeParser.RULESET_COLORS.copy()
