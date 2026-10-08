"""
Test Suite for Change Parser
Task 3.4: Change Tagging Implementation

Tests:
1. Basic tag parsing
2. Multiple tags
3. Nested tags
4. Malformed tags (unclosed, unmatched)
5. HTML generation
6. Plain text extraction
7. Statistics calculation
8. CSS style generation
"""

import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from services.change_parser import ChangeParser, parse_changes, get_ruleset_colors


def test_basic_parsing():
    """Test 1: Basic tag parsing with single change."""
    print("\n" + "="*80)
    print("TEST 1: Basic Tag Parsing")
    print("="*80)
    
    tagged_text = "The [BRAND]University of Illinois Chicago[/BRAND] offers many programs."
    
    parser = ChangeParser()
    result = parser.parse(tagged_text)
    
    print(f"âœ“ Input: {tagged_text}")
    print(f"âœ“ Plain text: {result.plain_text}")
    print(f"âœ“ Changes found: {len(result.changes)}")
    print(f"âœ“ Stats: {result.stats}")
    print(f"âœ“ Warnings: {result.warnings if result.warnings else 'None'}")
    
    # Assertions
    assert result.plain_text == "The University of Illinois Chicago offers many programs."
    assert len(result.changes) == 1
    assert result.changes[0].text == "University of Illinois Chicago"
    assert result.changes[0].rulesets == ['BRAND']
    assert result.stats['BRAND'] == 1
    assert len(result.warnings) == 0
    
    print("âœ… TEST 1 PASSED")
    return True


def test_multiple_tags():
    """Test 2: Multiple changes with different rulesets."""
    print("\n" + "="*80)
    print("TEST 2: Multiple Tags")
    print("="*80)
    
    tagged_text = (
        "The [BRAND]University of Illinois Chicago[/BRAND] provides "
        "[ACCESSIBILITY]excellent educational opportunities[/ACCESSIBILITY] for "
        "[AUDIENCE_TONE]students like you[/AUDIENCE_TONE]."
    )
    
    result = parse_changes(tagged_text)
    
    print(f"âœ“ Input: {tagged_text[:100]}...")
    print(f"âœ“ Plain text: {result.plain_text}")
    print(f"âœ“ Changes found: {len(result.changes)}")
    print(f"âœ“ Stats: {result.stats}")
    
    # Assertions
    assert len(result.changes) == 3
    assert result.stats['BRAND'] == 1
    assert result.stats['ACCESSIBILITY'] == 1
    assert result.stats['AUDIENCE_TONE'] == 1
    assert "University of Illinois Chicago" in result.plain_text
    assert "[BRAND]" not in result.plain_text
    
    print("âœ… TEST 2 PASSED")
    return True


def test_html_generation():
    """Test 3: HTML generation with proper styling."""
    print("\n" + "="*80)
    print("TEST 3: HTML Generation")
    print("="*80)
    
    tagged_text = "Visit [BRAND]UIC[/BRAND] today!"
    
    result = parse_changes(tagged_text)
    
    print(f"âœ“ Tagged text: {tagged_text}")
    print(f"âœ“ Generated HTML: {result.html}")
    
    # Assertions
    assert '<span' in result.html
    assert 'data-rulesets="BRAND"' in result.html
    assert 'change-brand' in result.html
    assert '</span>' in result.html
    
    print("âœ… TEST 3 PASSED")
    return True


def test_reading_level_tags():
    """Test 4: Reading level simplifications."""
    print("\n" + "="*80)
    print("TEST 4: Reading Level Tags")
    print("="*80)
    
    tagged_text = (
        "Students can [READING_LEVEL]use[/READING_LEVEL] the library resources."
    )
    
    result = parse_changes(tagged_text)
    
    print(f"âœ“ Tagged text: {tagged_text}")
    print(f"âœ“ Plain text: {result.plain_text}")
    print(f"âœ“ Stats: {result.stats}")
    
    # Assertions
    assert result.stats['READING_LEVEL'] == 1
    assert result.plain_text == "Students can use the library resources."
    
    print("âœ… TEST 4 PASSED")
    return True


def test_content_quality_tags():
    """Test 5: Content quality improvements."""
    print("\n" + "="*80)
    print("TEST 5: Content Quality Tags")
    print("="*80)
    
    tagged_text = (
        "The department [CONTENT]offers comprehensive programs[/CONTENT] in engineering."
    )
    
    result = parse_changes(tagged_text)
    
    print(f"âœ“ Tagged text: {tagged_text}")
    print(f"âœ“ Changes: {len(result.changes)}")
    print(f"âœ“ Stats: {result.stats}")
    
    # Assertions
    assert result.stats['CONTENT'] == 1
    assert result.changes[0].rulesets == ['CONTENT']
    
    print("âœ… TEST 5 PASSED")
    return True


def test_malformed_unclosed_tag():
    """Test 6: Malformed tag - unclosed opening tag."""
    print("\n" + "="*80)
    print("TEST 6: Malformed Tag - Unclosed")
    print("="*80)
    
    tagged_text = "The [BRAND]University of Illinois Chicago offers programs."
    
    result = parse_changes(tagged_text)
    
    print(f"âœ“ Tagged text: {tagged_text}")
    print(f"âœ“ Warnings: {result.warnings}")
    print(f"âœ“ Plain text still generated: {result.plain_text}")
    
    # Assertions
    assert len(result.warnings) > 0
    assert any('Unclosed' in w for w in result.warnings)
    # Plain text should still be generated
    assert "University of Illinois Chicago" in result.plain_text
    
    print("âœ… TEST 6 PASSED (graceful fallback)")
    return True


def test_malformed_unmatched_closing():
    """Test 7: Malformed tag - unmatched closing tag."""
    print("\n" + "="*80)
    print("TEST 7: Malformed Tag - Unmatched Closing")
    print("="*80)
    
    tagged_text = "The University of Illinois Chicago[/BRAND] offers programs."
    
    result = parse_changes(tagged_text)
    
    print(f"âœ“ Tagged text: {tagged_text}")
    print(f"âœ“ Warnings: {result.warnings}")
    print(f"âœ“ Plain text: {result.plain_text}")
    
    # Assertions
    assert len(result.warnings) > 0
    assert any('Unmatched' in w for w in result.warnings)
    
    print("âœ… TEST 7 PASSED (graceful fallback)")
    return True


def test_unknown_tag():
    """Test 8: Unknown tag type."""
    print("\n" + "="*80)
    print("TEST 8: Unknown Tag Type")
    print("="*80)
    
    tagged_text = "The [UNKNOWN]University of Illinois Chicago[/UNKNOWN] offers programs."
    
    result = parse_changes(tagged_text)
    
    print(f"âœ“ Tagged text: {tagged_text}")
    print(f"âœ“ Warnings: {result.warnings}")
    print(f"âœ“ Plain text: {result.plain_text}")
    
    # Assertions
    assert len(result.warnings) > 0
    assert any('Unknown tag' in w for w in result.warnings)
    # Should still extract text
    assert "University of Illinois Chicago" in result.plain_text
    
    print("âœ… TEST 8 PASSED (warning generated)")
    return True


def test_css_generation():
    """Test 9: CSS style generation."""
    print("\n" + "="*80)
    print("TEST 9: CSS Style Generation")
    print("="*80)
    
    parser = ChangeParser()
    css = parser.get_css_styles()
    
    print(f"âœ“ CSS length: {len(css)} chars")
    print("âœ“ Sample CSS:")
    print(css[:500] + "...")
    
    # Assertions
    assert '.text-change' in css
    assert '.change-brand' in css
    assert '.change-accessibility' in css
    assert '.change-content' in css
    assert '.change-reading_level' in css
    assert '.change-audience_tone' in css
    assert 'background-color' in css
    assert 'border-bottom' in css
    
    print("âœ… TEST 9 PASSED")
    return True


def test_ruleset_colors():
    """Test 10: Ruleset color mapping."""
    print("\n" + "="*80)
    print("TEST 10: Ruleset Colors")
    print("="*80)
    
    colors = get_ruleset_colors()
    
    print(f"âœ“ Color scheme:")
    for ruleset, color in colors.items():
        print(f"  - {ruleset}: {color}")
    
    # Assertions
    assert len(colors) == 5
    assert 'BRAND' in colors
    assert 'ACCESSIBILITY' in colors
    assert 'CONTENT' in colors
    assert 'READING_LEVEL' in colors
    assert 'AUDIENCE_TONE' in colors
    # All should be valid hex colors
    for color in colors.values():
        assert color.startswith('#')
        assert len(color) == 7
    
    print("âœ… TEST 10 PASSED")
    return True


def test_complex_example():
    """Test 11: Complex real-world example."""
    print("\n" + "="*80)
    print("TEST 11: Complex Real-World Example")
    print("="*80)
    
    tagged_text = """Dear [AUDIENCE_TONE]students[/AUDIENCE_TONE],

The [BRAND]University of Illinois Chicago[/BRAND] [CONTENT]invites you to attend[/CONTENT] our upcoming [ACCESSIBILITY]open house event[/ACCESSIBILITY].

During this event, you will [READING_LEVEL]learn about[/READING_LEVEL] our [ACCESSIBILITY]diverse academic programs[/ACCESSIBILITY] and meet [CONTENT]our faculty members[/CONTENT].

[BRAND]UIC[/BRAND] is committed to [ACCESSIBILITY]providing an excellent education[/ACCESSIBILITY] for all students.

We look forward to [AUDIENCE_TONE]seeing you there[/AUDIENCE_TONE]!"""
    
    result = parse_changes(tagged_text)
    
    print(f"âœ“ Input length: {len(tagged_text)} chars")
    print(f"âœ“ Changes found: {len(result.changes)}")
    print(f"âœ“ Stats:")
    for ruleset, count in result.stats.items():
        if count > 0:
            print(f"  - {ruleset}: {count}")
    print(f"âœ“ Warnings: {len(result.warnings)}")
    print(f"\nâœ“ Plain text preview:")
    print(result.plain_text[:200] + "...")
    
    # Assertions
    assert len(result.changes) > 5
    assert result.stats['BRAND'] >= 2
    assert result.stats['ACCESSIBILITY'] >= 2
    assert result.stats['AUDIENCE_TONE'] >= 2
    assert "University of Illinois Chicago" in result.plain_text
    assert "[BRAND]" not in result.plain_text
    
    print("âœ… TEST 11 PASSED")
    return True


def test_change_object_structure():
    """Test 12: Change object data structure."""
    print("\n" + "="*80)
    print("TEST 12: Change Object Structure")
    print("="*80)
    
    tagged_text = "Visit [BRAND]UIC[/BRAND] today!"
    result = parse_changes(tagged_text)
    
    change = result.changes[0]
    change_dict = change.to_dict()
    
    print(f"âœ“ Change object attributes:")
    print(f"  - text: {change.text}")
    print(f"  - rulesets: {change.rulesets}")
    print(f"  - start_pos: {change.start_pos}")
    print(f"  - end_pos: {change.end_pos}")
    print(f"  - html: {change.html[:50]}...")
    
    print(f"\nâœ“ Change dictionary: {change_dict}")
    
    # Assertions
    assert hasattr(change, 'text')
    assert hasattr(change, 'rulesets')
    assert hasattr(change, 'start_pos')
    assert hasattr(change, 'end_pos')
    assert hasattr(change, 'html')
    assert isinstance(change_dict, dict)
    assert all(key in change_dict for key in ['text', 'rulesets', 'start_pos', 'end_pos', 'html'])
    
    print("âœ… TEST 12 PASSED")
    return True


def test_parse_result_to_dict():
    """Test 13: ParseResult serialization for API."""
    print("\n" + "="*80)
    print("TEST 13: ParseResult to Dictionary")
    print("="*80)
    
    tagged_text = "The [BRAND]University of Illinois Chicago[/BRAND] offers [ACCESSIBILITY]great programs[/ACCESSIBILITY]."
    result = parse_changes(tagged_text)
    
    result_dict = result.to_dict()
    
    print(f"âœ“ Result dictionary keys: {list(result_dict.keys())}")
    print(f"âœ“ Changes count: {len(result_dict['changes'])}")
    print(f"âœ“ Stats: {result_dict['stats']}")
    
    # Assertions
    assert isinstance(result_dict, dict)
    assert 'plain_text' in result_dict
    assert 'html' in result_dict
    assert 'changes' in result_dict
    assert 'stats' in result_dict
    assert 'warnings' in result_dict
    assert isinstance(result_dict['changes'], list)
    assert isinstance(result_dict['stats'], dict)
    
    print("âœ… TEST 13 PASSED")
    return True


def test_html_escaping_and_balancing():
    """LLM text is escaped and only matched tags produce balanced spans."""
    result = parse_changes(
        '<script>alert("x")</script> [CONTENT]<b>clear</b>[/CONTENT]'
    )

    assert '<script>' not in result.html
    assert '<b>' not in result.html
    assert '&lt;script&gt;' in result.html
    assert '&lt;b&gt;clear&lt;/b&gt;' in result.html
    assert result.html.count('<span') == result.html.count('</span>') == 1
    return True


def test_nested_and_crossed_tags():
    """Nested tags work; crossed tags fall back to balanced HTML."""
    nested = parse_changes(
        '[BRAND]University of [CONTENT]Illinois Chicago[/CONTENT][/BRAND]'
    )
    assert [change.rulesets for change in nested.changes] == [
        ['BRAND'],
        ['CONTENT'],
    ]
    assert nested.html.count('<span') == nested.html.count('</span>') == 2

    crossed = parse_changes('[BRAND]UIC [CONTENT]news[/BRAND] today')
    assert crossed.plain_text == 'UIC news today'
    assert any('Unclosed' in warning for warning in crossed.warnings)
    assert crossed.html.count('<span') == crossed.html.count('</span>') == 1
    return True


def test_lowercase_tags_are_normalized():
    """Benign casing differences in LLM output remain parseable."""
    result = parse_changes('[brand]UIC[/brand]')

    assert result.plain_text == 'UIC'
    assert result.changes[0].rulesets == ['BRAND']
    assert 'change-brand' in result.html
    assert not result.warnings
    return True

def run_all_tests():
    """Run all test cases."""
    print("\n" + "="*80)
    print("CHANGE PARSER TEST SUITE")
    print("Task 3.4: Change Tagging Implementation")
    print("="*80)
    
    tests = [
        ("Basic Parsing", test_basic_parsing),
        ("Multiple Tags", test_multiple_tags),
        ("HTML Generation", test_html_generation),
        ("Reading Level Tags", test_reading_level_tags),
        ("Content Quality Tags", test_content_quality_tags),
        ("Malformed - Unclosed", test_malformed_unclosed_tag),
        ("Malformed - Unmatched", test_malformed_unmatched_closing),
        ("Unknown Tag", test_unknown_tag),
        ("CSS Generation", test_css_generation),
        ("Ruleset Colors", test_ruleset_colors),
        ("Complex Example", test_complex_example),
        ("Change Object Structure", test_change_object_structure),
        ("ParseResult Serialization", test_parse_result_to_dict),
        ("HTML Escaping and Balancing", test_html_escaping_and_balancing),
        ("Nested and Crossed Tags", test_nested_and_crossed_tags),
        ("Lowercase Tag Normalization", test_lowercase_tags_are_normalized),
    ]
    
    passed = 0
    failed = 0
    
    for name, test_func in tests:
        try:
            test_func()
            passed += 1
        except AssertionError as e:
            print(f"âŒ TEST FAILED: {name}")
            print(f"   Error: {e}")
            failed += 1
        except Exception as e:
            print(f"âŒ TEST ERROR: {name}")
            print(f"   Exception: {e}")
            failed += 1
    
    # Summary
    print("\n" + "="*80)
    print("TEST SUMMARY")
    print("="*80)
    print(f"âœ… Passed: {passed}/{len(tests)}")
    print(f"âŒ Failed: {failed}/{len(tests)}")
    
    if failed == 0:
        print("\nðŸŽ‰ ALL TESTS PASSED!")
        print("\nTask 3.4 Implementation Complete:")
        print("âœ“ Change tag parsing")
        print("âœ“ Change object structure")
        print("âœ“ HTML generation with styling")
        print("âœ“ Malformed tag fallback")
        print("âœ“ Statistics calculation")
        print("âœ“ CSS generation")
        return True
    else:
        print(f"\nâš ï¸  {failed} test(s) failed. Please review.")
        return False


if __name__ == "__main__":
    import sys
    success = run_all_tests()
    sys.exit(0 if success else 1)
