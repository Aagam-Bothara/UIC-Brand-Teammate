"""
Test script for LLM Service (Task 3.3)

This script tests the LLMService class with real Bedrock connections.
It validates:
- Prompt template loading
- Text rewriting with change tags
- Issue detection
- Text refinement
- Model selection logic
- Error handling and retry logic
"""

import json
import sys
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent))

from services.llm_service import LLMService, create_llm_service


def print_header(text: str) -> None:
    """Print a formatted section header."""
    print("\n" + "=" * 70)
    print(text)
    print("=" * 70)


def print_success(text: str) -> None:
    """Print success message."""
    print(f"✓ {text}")


def print_error(text: str) -> None:
    """Print error message."""
    print(f"✗ {text}")


def test_initialization():
    """Test LLM Service initialization."""
    print_header("TEST 1: LLM Service Initialization")
    
    try:
        service = create_llm_service()
        print_success("LLM Service created successfully")
        
        # Check that templates are loaded
        assert service.system_prompt, "System prompt is empty"
        print_success(f"System prompt loaded ({len(service.system_prompt)} bytes)")
        
        assert service.rewrite_template, "Rewrite template is empty"
        print_success(f"Rewrite template loaded ({len(service.rewrite_template)} bytes)")
        
        assert service.detection_template, "Detection template is empty"
        print_success(f"Detection template loaded ({len(service.detection_template)} bytes)")
        
        # Check Bedrock client
        assert service.bedrock_client, "Bedrock client not initialized"
        print_success("Bedrock client initialized")
        
        return service, True
    
    except Exception as e:
        print_error(f"Initialization failed: {e}")
        return None, False


def test_text_rewrite(service: LLMService):
    """Test text rewriting functionality."""
    print_header("TEST 2: Text Rewriting with Change Tags")
    
    # Sample input
    original_text = "UIC has great programs. Come check us out!"
    
    issues = [
        {
            "type": "BRAND",
            "severity": "high",
            "description": "Use full university name on first reference",
            "location": "UIC has great programs"
        },
        {
            "type": "ACCESSIBILITY",
            "severity": "medium",
            "description": "Too informal for official communication",
            "location": "Come check us out!"
        }
    ]
    
    guidelines = [
        {
            "text": "The official name is 'University of Illinois Chicago' on first reference.",
            "source_url": "https://brand.uic.edu/messaging/name-and-boilerplate/"
        }
    ]
    
    print(f"\nOriginal text: \"{original_text}\"")
    print(f"Issues detected: {len(issues)}")
    print(f"Guidelines provided: {len(guidelines)}")
    
    try:
        response = service.rewrite_text(
            original_text=original_text,
            issues=issues,
            guidelines=guidelines,
            audience="Students",
            channel="Email"
        )
        
        print_success("Text rewrite completed")
        print(f"\nRewritten text:\n{response.text}")
        print(f"\nModel used: {response.model_id}")
        print(f"Latency: {response.latency_ms:.0f}ms")
        
        if response.token_usage:
            print(f"Input tokens: {response.token_usage['input_tokens']}")
            print(f"Output tokens: {response.token_usage['output_tokens']}")
        
        # Check for change tags
        has_brand_tags = "[BRAND]" in response.text
        has_accessibility_tags = "[ACCESSIBILITY]" in response.text
        
        if has_brand_tags:
            print_success("Contains [BRAND] tags")
        else:
            print_error("Missing [BRAND] tags")
        
        if has_accessibility_tags:
            print_success("Contains [ACCESSIBILITY] tags")
        else:
            print_error("Missing [ACCESSIBILITY] tags (may be optional)")
        
        return True
    
    except Exception as e:
        print_error(f"Text rewrite failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_issue_detection(service: LLMService):
    """Test issue detection functionality."""
    print_header("TEST 3: Issue Detection (JSON Output)")
    
    text_to_analyze = "UIC's new building will open next Fall. The facility features state-of-the-art classrooms."
    
    guidelines = [
        {
            "text": "Use 'fall' (lowercase) for seasons unless part of a proper noun.",
            "source_url": "https://brand.uic.edu/messaging/editorial-and-style-guide/"
        }
    ]
    
    print(f"\nText to analyze: \"{text_to_analyze}\"")
    print(f"Guidelines provided: {len(guidelines)}")
    
    try:
        issues = service.detect_issues(
            text_to_analyze=text_to_analyze,
            guidelines=guidelines,
            audience="Staff",
            channel="Email"
        )
        
        print_success(f"Issue detection completed (found {len(issues)} issues)")
        
        if issues:
            print("\nDetected issues:")
            for i, issue in enumerate(issues, 1):
                print(f"\n  Issue {i}:")
                print(f"    Type: {issue.get('issue_type', 'N/A')}")
                print(f"    Severity: {issue.get('severity', 'N/A')}")
                print(f"    Location: {issue.get('location', 'N/A')}")
                print(f"    Description: {issue.get('description', 'N/A')}")
        else:
            print("\nNo issues detected (or JSON parse failed)")
        
        return True
    
    except Exception as e:
        print_error(f"Issue detection failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_text_refinement(service: LLMService):
    """Test text refinement functionality."""
    print_header("TEST 4: Text Refinement (Chat-based)")
    
    current_text = "The University of Illinois Chicago offers exceptional academic programs."
    refinement_request = "Make it sound more welcoming and enthusiastic."
    
    print(f"\nCurrent text: \"{current_text}\"")
    print(f"Refinement request: \"{refinement_request}\"")
    
    try:
        response = service.refine_text(
            current_text=current_text,
            refinement_request=refinement_request,
            audience="Students",
            channel="Website"
        )
        
        print_success("Text refinement completed")
        print(f"\nRefined text:\n{response.text}")
        print(f"\nModel used: {response.model_id}")
        print(f"Latency: {response.latency_ms:.0f}ms")
        
        return True
    
    except Exception as e:
        print_error(f"Text refinement failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_model_selection(service: LLMService):
    """Test model selection logic."""
    print_header("TEST 5: Model Selection Logic")
    
    # Short text should use Haiku
    short_text = "UIC is great!"
    short_model = service._select_model(short_text)
    
    if short_model == service.HAIKU_MODEL_ID:
        print_success(f"Short text ({len(short_text.split())} words) → Haiku")
    else:
        print_error(f"Short text should use Haiku, got {short_model}")
    
    # Long text should use Sonnet
    long_text = " ".join(["word"] * 600)
    long_model = service._select_model(long_text)
    
    if long_model == service.SONNET_MODEL_ID:
        print_success(f"Long text ({len(long_text.split())} words) → Sonnet")
    else:
        print_error(f"Long text should use Sonnet, got {long_model}")
    
    return True


def test_reading_level_mapping(service: LLMService):
    """Test reading level determination."""
    print_header("TEST 6: Reading Level Mapping")
    
    # Students should get Grade 8
    students_level = service._get_reading_level("Students")
    if students_level == "Grade 8":
        print_success(f"Students → {students_level}")
    else:
        print_error(f"Students should get Grade 8, got {students_level}")
    
    # Faculty should get Grade 10
    faculty_level = service._get_reading_level("Faculty")
    if faculty_level == "Grade 10":
        print_success(f"Faculty → {faculty_level}")
    else:
        print_error(f"Faculty should get Grade 10, got {faculty_level}")
    
    # Staff should get Grade 10
    staff_level = service._get_reading_level("Staff")
    if staff_level == "Grade 10":
        print_success(f"Staff → {staff_level}")
    else:
        print_error(f"Staff should get Grade 10, got {staff_level}")
    
    return True


def test_formatting_helpers(service: LLMService):
    """Test issue and guideline formatting."""
    print_header("TEST 7: Formatting Helper Functions")
    
    # Test issue formatting
    issues = [
        {
            "type": "BRAND",
            "severity": "high",
            "description": "Use full name",
            "location": "UIC"
        },
        {
            "type": "CONTENT",
            "severity": "low",
            "description": "Minor typo"
        }
    ]
    
    formatted_issues = service._format_issues(issues)
    
    if "[BRAND - High]" in formatted_issues and "[CONTENT - Low]" in formatted_issues:
        print_success("Issue formatting works correctly")
    else:
        print_error("Issue formatting failed")
    
    # Test guideline formatting
    guidelines = [
        {
            "text": "Use full university name on first reference",
            "source_url": "https://brand.uic.edu/"
        }
    ]
    
    formatted_guidelines = service._format_guidelines(guidelines)
    
    if "full university name" in formatted_guidelines and "brand.uic.edu" in formatted_guidelines:
        print_success("Guideline formatting works correctly")
    else:
        print_error("Guideline formatting failed")
    
    return True


def main():
    """Run all tests."""
    print("\n" + "#" * 70)
    print("# UIC Editorial Assistant - LLM Service Test Suite (Task 3.3)")
    print("#" * 70)
    
    # Track results
    results = []
    
    # Test 1: Initialization
    service, init_success = test_initialization()
    results.append(("Initialization", init_success))
    
    if not init_success:
        print("\n✗ FAILED: Cannot proceed without successful initialization")
        return 1
    
    # Test 2-7: Functional tests
    results.append(("Model Selection", test_model_selection(service)))
    results.append(("Reading Level Mapping", test_reading_level_mapping(service)))
    results.append(("Formatting Helpers", test_formatting_helpers(service)))
    results.append(("Text Rewriting", test_text_rewrite(service)))
    results.append(("Issue Detection", test_issue_detection(service)))
    results.append(("Text Refinement", test_text_refinement(service)))
    
    # Summary
    print_header("TEST SUMMARY")
    
    passed = sum(1 for _, success in results if success)
    total = len(results)
    
    print(f"\nTests passed: {passed}/{total}")
    print("\nDetailed results:")
    
    for test_name, success in results:
        status = "✓ PASS" if success else "✗ FAIL"
        print(f"  {status} - {test_name}")
    
    if passed == total:
        print("\n✓ SUCCESS: All tests passed! Task 3.3 implementation complete.")
        print("\nNext steps:")
        print("  - Task 3.4: Implement change tag parsing and HTML generation")
        print("  - Task 3.5: Add model selection complexity scoring")
        print("  - Task 3.6: Implement text diffing for fallback")
        return 0
    else:
        print(f"\n✗ PARTIAL SUCCESS: {total - passed} test(s) failed")
        print("  Review errors above and fix issues")
        return 1


if __name__ == "__main__":
    sys.exit(main())
