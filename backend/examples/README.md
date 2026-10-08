# Backend Examples

This directory contains demonstration scripts for backend components.

## Available Examples

### Change Parser Demo

**File**: `change_parser_demo.py`  
**Task**: 3.4 - Change Tagging Implementation  
**Requirements**: Python 3.8+ (no AWS credentials needed)

Demonstrates how the change parser processes LLM output with inline tags and generates HTML for progressive reveal.

**Run**:
```powershell
python backend/examples/change_parser_demo.py
```

**Demos Include**:
1. Basic change tag parsing
2. HTML generation with styling
3. CSS stylesheet generation
4. Graceful handling of malformed tags
5. Complete email rewrite example
6. API response format

**Features Demonstrated**:
- Parse inline tags (`[BRAND]`, `[ACCESSIBILITY]`, etc.)
- Generate styled HTML for frontend
- Extract plain text by removing tags
- Calculate statistics by ruleset
- Handle errors gracefully
- Serialize for JSON API responses

## Future Examples

Additional examples will be added for:
- LLM Service integration (Task 3.3)
- Rule Engine usage (Workstream 2)
- RAG Service queries (Workstream 1)
- Complete end-to-end workflow

## Notes

- Examples are self-contained and use only standard library dependencies
- No AWS credentials required for demos
- See individual file headers for specific requirements
- Use these examples to understand component integration
