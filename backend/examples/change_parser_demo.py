"""
Change Parser Demo
Demonstrates Task 3.4 functionality without requiring AWS credentials.

This shows how the change parser processes LLM output with inline tags
and generates HTML for the progressive reveal feature.
"""

import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from services.change_parser import ChangeParser, parse_changes, get_ruleset_colors


def demo_basic_parsing():
    """Demo 1: Basic change tag parsing."""
    print("\n" + "="*80)
    print("DEMO 1: Basic Change Tag Parsing")
    print("="*80)
    
    # Simulate LLM output with inline tags
    llm_output = """Dear Students,

The [BRAND]University of Illinois Chicago[/BRAND] is pleased to announce our new [ACCESSIBILITY]tutoring program[/ACCESSIBILITY].

This program will [READING_LEVEL]help[/READING_LEVEL] you [CONTENT]succeed in your courses[/CONTENT] and [AUDIENCE_TONE]reach your academic goals[/AUDIENCE_TONE].

Please visit [BRAND]uic.edu/tutoring[/BRAND] for more information."""
    
    print("\n📝 SIMULATED LLM OUTPUT:")
    print(llm_output)
    
    # Parse the tagged text
    result = parse_changes(llm_output)
    
    print("\n✨ PARSED RESULTS:")
    print(f"\n1. Plain Text (tags removed):")
    print(result.plain_text)
    
    print(f"\n2. Changes Found: {len(result.changes)}")
    for i, change in enumerate(result.changes, 1):
        print(f"\n   Change {i}:")
        print(f"   - Text: \"{change.text}\"")
        print(f"   - Rulesets: {', '.join(change.rulesets)}")
        print(f"   - Position: {change.start_pos}-{change.end_pos}")
    
    print(f"\n3. Statistics by Ruleset:")
    for ruleset, count in result.stats.items():
        if count > 0:
            print(f"   - {ruleset}: {count} changes")
    
    print(f"\n4. Warnings: {len(result.warnings)}")
    if result.warnings:
        for warning in result.warnings:
            print(f"   - {warning}")
    else:
        print("   (none)")


def demo_html_generation():
    """Demo 2: HTML generation with styling."""
    print("\n" + "="*80)
    print("DEMO 2: HTML Generation for Progressive Reveal")
    print("="*80)
    
    llm_output = "Visit [BRAND]UIC[/BRAND] for [ACCESSIBILITY]excellent education[/ACCESSIBILITY]!"
    
    print("\n📝 INPUT:")
    print(llm_output)
    
    result = parse_changes(llm_output)
    
    print("\n🎨 GENERATED HTML:")
    print(result.html)
    
    print("\n📊 STRUCTURE BREAKDOWN:")
    print("- Each change wrapped in <span> with CSS classes")
    print("- data-rulesets attribute for JavaScript toggling")
    print("- data-primary attribute for color coding")
    
    print("\n💡 FRONTEND USAGE:")
    print("JavaScript can toggle visibility:")
    print("  document.querySelectorAll('.change-brand').forEach(el => {")
    print("    el.classList.toggle('hidden');")
    print("  });")


def demo_css_styles():
    """Demo 3: CSS stylesheet generation."""
    print("\n" + "="*80)
    print("DEMO 3: CSS Stylesheet Generation")
    print("="*80)
    
    parser = ChangeParser()
    css = parser.get_css_styles()
    
    print("\n🎨 GENERATED CSS STYLES:")
    print(css[:500] + "...")
    
    print(f"\n📏 Total CSS Size: {len(css)} characters")
    
    print("\n🎨 RULESET COLOR SCHEME:")
    colors = get_ruleset_colors()
    for ruleset, color in colors.items():
        print(f"   {ruleset:20} {color}")


def demo_malformed_tags():
    """Demo 4: Handling malformed tags."""
    print("\n" + "="*80)
    print("DEMO 4: Graceful Handling of Malformed Tags")
    print("="*80)
    
    test_cases = [
        ("Unclosed tag", "The [BRAND]University of Illinois Chicago offers programs."),
        ("Unmatched closing", "The University[/BRAND] offers programs."),
        ("Unknown tag type", "The [UNKNOWN]text[/UNKNOWN] here."),
        ("Multiple issues", "[BRAND]Text1 [ACCESSIBILITY]Text2 with issues.")
    ]
    
    for name, text in test_cases:
        print(f"\n📝 TEST: {name}")
        print(f"Input: {text}")
        
        result = parse_changes(text)
        
        print(f"Plain text: {result.plain_text}")
        print(f"Warnings: {len(result.warnings)}")
        for warning in result.warnings:
            print(f"  ⚠️  {warning}")


def demo_complex_email():
    """Demo 5: Complete email rewrite example."""
    print("\n" + "="*80)
    print("DEMO 5: Complete Email Rewrite with Multiple Changes")
    print("="*80)
    
    # Simulate a complete LLM rewrite with all tag types
    original = """Dear Students,

UIC offers tutoring services. Utilize these resources to do better in your classes and achieve your goals.

Visit our website for more info."""
    
    rewritten = """Dear [AUDIENCE_TONE]students[/AUDIENCE_TONE],

The [BRAND]University of Illinois Chicago[/BRAND] offers [ACCESSIBILITY]comprehensive tutoring services[/ACCESSIBILITY]. [READING_LEVEL]Use[/READING_LEVEL] these resources to [CONTENT]excel in your courses[/CONTENT] and [AUDIENCE_TONE]reach your academic goals[/AUDIENCE_TONE].

Visit [BRAND]uic.edu/tutoring[/BRAND] for [ACCESSIBILITY]more information[/ACCESSIBILITY]."""
    
    print("\n📄 ORIGINAL:")
    print(original)
    
    print("\n📄 LLM REWRITTEN (with tags):")
    print(rewritten)
    
    result = parse_changes(rewritten)
    
    print("\n📄 FINAL PLAIN TEXT:")
    print(result.plain_text)
    
    print(f"\n📊 IMPROVEMENT BREAKDOWN:")
    print(f"Total changes: {len(result.changes)}")
    for ruleset, count in sorted(result.stats.items(), key=lambda x: x[1], reverse=True):
        if count > 0:
            print(f"  {ruleset:20} {count} changes")
    
    print(f"\n🎨 HTML FOR PROGRESSIVE REVEAL:")
    print(result.html[:300] + "...")


def demo_api_response():
    """Demo 6: API response format."""
    print("\n" + "="*80)
    print("DEMO 6: API Response Format")
    print("="*80)
    
    llm_output = "The [BRAND]University of Illinois Chicago[/BRAND] offers [ACCESSIBILITY]excellent programs[/ACCESSIBILITY]."
    
    result = parse_changes(llm_output)
    result_dict = result.to_dict()
    
    print("\n📡 API RESPONSE STRUCTURE:")
    print("{")
    print(f"  'plain_text': '{result_dict['plain_text'][:50]}...',")
    print(f"  'html': '{result_dict['html'][:50]}...',")
    print(f"  'changes': [")
    for change in result_dict['changes'][:2]:
        print(f"    {{")
        print(f"      'text': '{change['text']}',")
        print(f"      'rulesets': {change['rulesets']},")
        print(f"      'start_pos': {change['start_pos']},")
        print(f"      'end_pos': {change['end_pos']},")
        print(f"      'html': '{change['html'][:40]}...'")
        print(f"    }},")
    print(f"  ],")
    print(f"  'stats': {result_dict['stats']},")
    print(f"  'warnings': {result_dict['warnings']}")
    print("}")


def main():
    """Run all demos."""
    print("\n" + "="*80)
    print("CHANGE PARSER DEMO")
    print("Task 3.4: Change Tagging Implementation")
    print("="*80)
    print("\nThis demo shows how the change parser processes LLM output")
    print("with inline tags and generates HTML for progressive reveal.")
    
    demos = [
        demo_basic_parsing,
        demo_html_generation,
        demo_css_styles,
        demo_malformed_tags,
        demo_complex_email,
        demo_api_response
    ]
    
    for demo in demos:
        try:
            demo()
        except Exception as e:
            print(f"\n❌ Error in demo: {e}")
    
    print("\n" + "="*80)
    print("✅ DEMO COMPLETE")
    print("="*80)
    print("\nKey Takeaways:")
    print("✓ Parse inline tags from LLM output")
    print("✓ Generate HTML with CSS classes for styling")
    print("✓ Extract plain text by removing tags")
    print("✓ Calculate statistics by ruleset")
    print("✓ Handle malformed tags gracefully")
    print("✓ Ready for API integration")
    print("\nNext Steps:")
    print("→ Integrate with Task 3.3 (LLM Service)")
    print("→ Expose in Task 3.8 (API Routes)")
    print("→ Use in Workstream 4 (Frontend)")


if __name__ == "__main__":
    main()
