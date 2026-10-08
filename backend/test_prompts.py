"""
Test script for validating prompt templates.

This script tests that:
1. All prompt files exist and are readable
2. Template placeholders are valid
3. Prompts can be formatted with sample data
4. Output follows expected structure

Run this after creating prompts to verify they're ready for LLM service integration.
"""

import os
import sys
from pathlib import Path

def test_prompt_files_exist():
    """Verify all required prompt files exist."""
    print("=" * 60)
    print("TEST 1: Checking prompt files exist")
    print("=" * 60)
    
    prompts_dir = Path(__file__).parent / "prompts"
    required_files = [
        "system_prompt.txt",
        "rewrite_prompt_template.txt",
        "detection_prompt_template.txt"
    ]
    
    all_exist = True
    for filename in required_files:
        filepath = prompts_dir / filename
        if filepath.exists():
            print(f"✅ {filename} exists")
            size = filepath.stat().st_size
            print(f"   Size: {size} bytes")
        else:
            print(f"❌ {filename} NOT FOUND")
            all_exist = False
    
    return all_exist


def test_system_prompt():
    """Test system prompt loads correctly."""
    print("\n" + "=" * 60)
    print("TEST 2: Validating system_prompt.txt")
    print("=" * 60)
    
    try:
        prompts_dir = Path(__file__).parent / "prompts"
        with open(prompts_dir / "system_prompt.txt", 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Check key sections exist
        required_sections = [
            "Your Responsibilities",
            "UIC Brand Guidelines",
            "Key Audiences",
            "Communication Channels",
            "Your Approach",
            "Output Requirements"
        ]
        
        missing_sections = []
        for section in required_sections:
            if section not in content:
                missing_sections.append(section)
        
        if missing_sections:
            print(f"❌ Missing sections: {', '.join(missing_sections)}")
            return False
        else:
            print("✅ All required sections present")
        
        # Check mentions key concepts
        key_concepts = [
            "brand compliance",
            "accessibility",
            "audience",
            "University of Illinois Chicago",
            "reading level"
        ]
        
        missing_concepts = []
        for concept in key_concepts:
            if concept.lower() not in content.lower():
                missing_concepts.append(concept)
        
        if missing_concepts:
            print(f"⚠️  Missing key concepts: {', '.join(missing_concepts)}")
        else:
            print("✅ All key concepts mentioned")
        
        print(f"✅ System prompt is {len(content)} characters")
        return True
        
    except Exception as e:
        print(f"❌ Error reading system prompt: {e}")
        return False


def test_detection_prompt_template():
    """Test detection prompt template with sample data."""
    print("\n" + "=" * 60)
    print("TEST 3: Validating detection_prompt_template.txt")
    print("=" * 60)
    
    try:
        prompts_dir = Path(__file__).parent / "prompts"
        with open(prompts_dir / "detection_prompt_template.txt", 'r', encoding='utf-8') as f:
            template = f.read()
        
        # Check for required placeholders
        required_placeholders = [
            "{audience}",
            "{channel}",
            "{reading_level_target}",
            "{text_to_analyze}",
            "{guidelines_context}"
        ]
        
        missing_placeholders = []
        for placeholder in required_placeholders:
            if placeholder not in template:
                missing_placeholders.append(placeholder)
        
        if missing_placeholders:
            print(f"❌ Missing placeholders: {', '.join(missing_placeholders)}")
            return False
        else:
            print("✅ All required placeholders present")
        
        # Try formatting with sample data
        sample_data = {
            "audience": "Students",
            "channel": "Email",
            "reading_level_target": "Grade 8",
            "text_to_analyze": "This is a sample text for testing.",
            "guidelines_context": "Sample guideline: Use clear language."
        }
        
        try:
            formatted = template.format(**sample_data)
            print("✅ Template formats successfully")
            
            # Verify placeholders were replaced
            for placeholder in required_placeholders:
                if placeholder in formatted:
                    print(f"❌ Placeholder {placeholder} not replaced")
                    return False
            
            print("✅ All placeholders replaced in formatted output")
            print(f"✅ Formatted prompt is {len(formatted)} characters")
            
        except KeyError as e:
            print(f"❌ Template formatting error: missing key {e}")
            return False
        
        # Check for output format specification
        if "JSON" in template or "json" in template:
            print("✅ Specifies JSON output format")
        else:
            print("⚠️  Does not specify JSON output format")
        
        return True
        
    except Exception as e:
        print(f"❌ Error reading detection prompt template: {e}")
        return False


def test_rewrite_prompt_template():
    """Test rewrite prompt template with sample data."""
    print("\n" + "=" * 60)
    print("TEST 4: Validating rewrite_prompt_template.txt")
    print("=" * 60)
    
    try:
        prompts_dir = Path(__file__).parent / "prompts"
        with open(prompts_dir / "rewrite_prompt_template.txt", 'r', encoding='utf-8') as f:
            template = f.read()
        
        # Check for required placeholders
        required_placeholders = [
            "{audience}",
            "{channel}",
            "{reading_level_target}",
            "{original_text}",
            "{issues_list}",
            "{guidelines_context}"
        ]
        
        missing_placeholders = []
        for placeholder in required_placeholders:
            if placeholder not in template:
                missing_placeholders.append(placeholder)
        
        if missing_placeholders:
            print(f"❌ Missing placeholders: {', '.join(missing_placeholders)}")
            return False
        else:
            print("✅ All required placeholders present")
        
        # Try formatting with sample data
        sample_data = {
            "audience": "Faculty",
            "channel": "Website",
            "reading_level_target": "Grade 10",
            "original_text": "UIC is a great school.",
            "issues_list": "- Issue 1: Use full university name\n- Issue 2: Too casual",
            "guidelines_context": "Use 'University of Illinois Chicago' on first reference."
        }
        
        try:
            formatted = template.format(**sample_data)
            print("✅ Template formats successfully")
            
            # Verify placeholders were replaced
            for placeholder in required_placeholders:
                if placeholder in formatted:
                    print(f"❌ Placeholder {placeholder} not replaced")
                    return False
            
            print("✅ All placeholders replaced in formatted output")
            print(f"✅ Formatted prompt is {len(formatted)} characters")
            
        except KeyError as e:
            print(f"❌ Template formatting error: missing key {e}")
            return False
        
        # Check for tagging instructions
        tag_types = ["[BRAND]", "[ACCESSIBILITY]", "[CONTENT]", "[READING_LEVEL]", "[AUDIENCE_TONE]"]
        tags_mentioned = sum(1 for tag in tag_types if tag in template)
        
        if tags_mentioned >= 4:
            print(f"✅ Mentions {tags_mentioned}/5 tag types")
        else:
            print(f"⚠️  Only mentions {tags_mentioned}/5 tag types")
        
        return True
        
    except Exception as e:
        print(f"❌ Error reading rewrite prompt template: {e}")
        return False


def test_prompt_consistency():
    """Test that prompts use consistent terminology and structure."""
    print("\n" + "=" * 60)
    print("TEST 5: Checking consistency across prompts")
    print("=" * 60)
    
    try:
        prompts_dir = Path(__file__).parent / "prompts"
        
        # Load all prompts
        prompts = {}
        for filename in ["system_prompt.txt", "detection_prompt_template.txt", "rewrite_prompt_template.txt"]:
            with open(prompts_dir / filename, 'r', encoding='utf-8') as f:
                prompts[filename] = f.read()
        
        # Check for consistent terminology
        key_terms = {
            "University of Illinois Chicago": "Official university name",
            "Students": "Audience type",
            "Faculty": "Audience type",
            "Staff": "Audience type",
            "Email": "Channel type",
            "Website": "Channel type",
            "Social Media": "Channel type",
            "reading level": "Accessibility concept",
            "brand compliance": "Core requirement",
            "accessibility": "Core requirement"
        }
        
        consistency_issues = []
        for term, description in key_terms.items():
            # Count occurrences across all prompts
            total_mentions = sum(1 for content in prompts.values() if term in content)
            if total_mentions < 2:
                consistency_issues.append(f"{description} ('{term}') mentioned in <2 prompts")
        
        if consistency_issues:
            print("⚠️  Potential consistency issues:")
            for issue in consistency_issues:
                print(f"   - {issue}")
        else:
            print("✅ Key terminology used consistently")
        
        # Check that all prompts mention the 5 rulesets
        rulesets = ["BRAND", "ACCESSIBILITY", "CONTENT", "READING_LEVEL", "AUDIENCE_TONE"]
        for filename, content in prompts.items():
            mentioned = [rs for rs in rulesets if rs in content]
            if len(mentioned) >= 4:
                print(f"✅ {filename}: mentions {len(mentioned)}/5 rulesets")
            else:
                print(f"⚠️  {filename}: only mentions {len(mentioned)}/5 rulesets")
        
        return True
        
    except Exception as e:
        print(f"❌ Error checking consistency: {e}")
        return False


def print_summary(results):
    """Print test summary."""
    print("\n" + "=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)
    
    total = len(results)
    passed = sum(results.values())
    failed = total - passed
    
    print(f"\nTotal Tests: {total}")
    print(f"✅ Passed: {passed}")
    print(f"❌ Failed: {failed}")
    
    if failed == 0:
        print("\n🎉 All tests passed! Prompts are ready for integration.")
        print("\nNext steps:")
        print("1. Review prompts for content accuracy")
        print("2. Test with actual Bedrock models (requires Task 3.1)")
        print("3. Proceed to Task 3.3: LLM Service Implementation")
        return True
    else:
        print("\n⚠️  Some tests failed. Please review and fix the issues above.")
        return False


def main():
    """Run all prompt validation tests."""
    print("🧪 UIC Editorial Assistant - Prompt Validation Tests")
    print("Task 3.2: Prompt Engineering")
    print()
    
    # Run tests
    results = {
        "Files Exist": test_prompt_files_exist(),
        "System Prompt": test_system_prompt(),
        "Detection Template": test_detection_prompt_template(),
        "Rewrite Template": test_rewrite_prompt_template(),
        "Consistency": test_prompt_consistency()
    }
    
    # Print summary and exit
    success = print_summary(results)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
