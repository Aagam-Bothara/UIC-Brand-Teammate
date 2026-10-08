# Services Module - Quick Start Guide

This directory contains service classes for the UIC Editorial Assistant backend.

## LLM Service (Task 3.3) ✅

The LLM Service handles all interactions with AWS Bedrock models for text rewriting and analysis.

### Quick Start

```python
from services.llm_service import create_llm_service

# Initialize service
service = create_llm_service()

# Rewrite text with change tags
response = service.rewrite_text(
    original_text="UIC has great programs!",
    issues=[{"type": "BRAND", "description": "Use full name"}],
    guidelines=[{"text": "Use 'University of Illinois Chicago'"}],
    audience="Students",
    channel="Email"
)

print(response.text)
# Output: "The [BRAND]University of Illinois Chicago[/BRAND] has..."
```

### Testing

Run the comprehensive test suite:

```bash
python backend/test_llm_service.py
```

**Prerequisites:**
- AWS credentials configured (environment variables or AWS CLI)
- Model access granted for Claude Haiku and Sonnet
- Task 3.1 completed (Bedrock setup)

### Documentation

Full documentation available at: `backend/docs/LLM_SERVICE.md`

Topics covered:
- Public API reference
- Error handling guide
- Integration examples
- Performance optimization
- Troubleshooting

### Features

- ✅ Adaptive model selection (Haiku/Sonnet)
- ✅ Exponential backoff retry logic
- ✅ Comprehensive error handling
- ✅ CloudWatch logging
- ✅ Token usage tracking
- ✅ Three public methods:
  - `rewrite_text()` - Generate improvements with tags
  - `detect_issues()` - Analyze for compliance issues
  - `refine_text()` - Apply chat-based refinements

### Next Steps

With LLM Service complete (Task 3.3), proceed to:

1. **Task 3.4**: Implement change tag parsing and HTML generation
2. **Task 3.5**: Add complexity scoring for model selection
3. **Task 3.6**: Text diffing fallback implemented in `text_diff.py`
4. **Task 3.7**: Structured refinement handling implemented in `refinement.py`
5. **Next**: Task 3.8 LLM API routes

### Support

For issues or questions:
- Check `backend/docs/LLM_SERVICE.md` for detailed documentation
- Review `backend/prompts/EXAMPLE_USAGE.md` for integration patterns
- Run `python backend/test_llm_service.py` to validate setup

---

**Last Updated**: 2026-10-08  
**Status**: Task 3.3 Complete ✅
