# LLM Service Documentation

**Task**: 3.3 - LLM Service Implementation  
**Status**: Complete ✅  
**Version**: 1.0  
**Last Updated**: 2026-10-08

---

## Table of Contents

1. [Overview](#overview)
2. [Architecture](#architecture)
3. [Public Interface](#public-interface)
4. [Configuration](#configuration)
5. [Error Handling](#error-handling)
6. [Usage Examples](#usage-examples)
7. [Testing](#testing)
8. [Integration Guide](#integration-guide)
9. [Performance Considerations](#performance-considerations)
10. [Troubleshooting](#troubleshooting)

---

## Overview

The LLM Service is the core component for interacting with AWS Bedrock models (Claude Haiku and Sonnet) to provide intelligent text rewriting, issue detection, and refinement capabilities for the UIC Editorial Assistant.

### Key Features

- **Prompt Template Management**: Loads and formats prompt templates from `backend/prompts/`
- **Adaptive Model Selection**: Automatically chooses Haiku (fast) or Sonnet (quality) based on text complexity
- **Retry Logic**: Exponential backoff retry for transient failures
- **Error Handling**: Comprehensive error handling for all failure modes
- **CloudWatch Logging**: Structured logging for observability
- **Token Tracking**: Monitors input/output token usage for cost optimization

### Design Principles

1. **Separation of Concerns**: Prompt templates are external files, not hardcoded
2. **Fail-Safe Defaults**: Graceful degradation when errors occur
3. **Observable**: All operations logged with context
4. **Testable**: Accepts pre-configured Bedrock client for testing
5. **Maintainable**: Clear code structure with comprehensive documentation

---

## Architecture

### Component Structure

```
LLMService
├── Initialization
│   ├── Load prompt templates (system_prompt.txt, rewrite_prompt_template.txt, detection_prompt_template.txt)
│   ├── Initialize Bedrock client (boto3 bedrock-runtime)
│   └── Setup CloudWatch logging
│
├── Public Methods
│   ├── rewrite_text() - Generate improved text with inline change tags
│   ├── detect_issues() - Analyze text for compliance issues (JSON output)
│   └── refine_text() - Apply user-requested refinements
│
├── Model Selection
│   ├── Word count analysis
│   └── Route to Haiku (<500 words) or Sonnet (>500 words)
│
├── Prompt Formatting
│   ├── Fill template placeholders
│   ├── Format issues as text
│   └── Format guidelines as text
│
├── Retry Logic
│   ├── Detect retryable errors (throttling, network)
│   ├── Exponential backoff (1s, 2s, 4s)
│   └── Log retry attempts
│
└── Error Handling
    ├── ModelInvocationError - Model call failures
    ├── PromptLoadError - Template loading failures
    └── Graceful fallbacks
```

### Data Flow

```
User Input (text, audience, channel)
         ↓
Load relevant prompt template
         ↓
Format issues & guidelines from other services
         ↓
Select model (Haiku or Sonnet)
         ↓
Invoke Bedrock with retry logic
         ↓
Parse response (text or JSON)
         ↓
Return LLMResponse with metadata
```

---

## Public Interface

### LLMService Class

```python
from services.llm_service import LLMService, create_llm_service

# Create service instance
service = create_llm_service()
```

### Method: `rewrite_text()`

Generate improved text with inline change tags for progressive reveal.

**Signature:**
```python
def rewrite_text(
    self,
    original_text: str,
    issues: List[Dict[str, Any]],
    guidelines: List[Dict[str, str]],
    audience: str,
    channel: str
) -> LLMResponse
```

**Parameters:**
- `original_text`: Original text to improve
- `issues`: List of detected issues from rule engine
  ```python
  [
      {
          "type": "BRAND",  # BRAND, ACCESSIBILITY, CONTENT, READING_LEVEL, AUDIENCE_TONE
          "severity": "high",  # high, medium, low
          "description": "Use full university name on first reference",
          "location": "UIC has great programs"
      }
  ]
  ```
- `guidelines`: Retrieved guidelines from RAG service
  ```python
  [
      {
          "text": "The official name is 'University of Illinois Chicago'...",
          "source_url": "https://brand.uic.edu/messaging/name-and-boilerplate/"
      }
  ]
  ```
- `audience`: Target audience - "Students", "Faculty", or "Staff"
- `channel`: Communication channel - "Email", "Website", or "Social Media"

**Returns:**
```python
LLMResponse(
    text="The [BRAND]University of Illinois Chicago[/BRAND] offers...",
    model_id="anthropic.claude-3-haiku-20240307-v1:0",
    latency_ms=2450.5,
    token_usage={"input_tokens": 1234, "output_tokens": 456}
)
```

**Change Tags in Output:**
- `[BRAND]...[/BRAND]` - Brand compliance fixes
- `[ACCESSIBILITY]...[/ACCESSIBILITY]` - Accessibility improvements
- `[CONTENT]...[/CONTENT]` - Content quality enhancements
- `[READING_LEVEL]...[/READING_LEVEL]` - Reading level simplifications
- `[AUDIENCE_TONE]...[/AUDIENCE_TONE]` - Audience-specific tone adjustments

**Raises:**
- `ModelInvocationError`: If model invocation fails after 3 retry attempts

---

### Method: `detect_issues()`

Analyze text to detect compliance issues (optional step, can complement rule engine).

**Signature:**
```python
def detect_issues(
    self,
    text_to_analyze: str,
    guidelines: List[Dict[str, str]],
    audience: str,
    channel: str
) -> List[Dict[str, Any]]
```

**Parameters:**
- `text_to_analyze`: Text to analyze
- `guidelines`: Retrieved guidelines from RAG service
- `audience`: Target audience
- `channel`: Communication channel

**Returns:**
```python
[
    {
        "issue_type": "BRAND",
        "severity": "high",
        "location": "UIC's new building",
        "description": "Use full university name on first reference",
        "suggestion": "The University of Illinois Chicago's new building",
        "guideline_reference": "https://brand.uic.edu/..."
    }
]
```

**Raises:**
- `ModelInvocationError`: If model invocation fails

**Notes:**
- Uses Haiku model for faster, cheaper analysis
- Returns empty list if JSON parsing fails (graceful degradation)

---

### Method: `refine_text()`

Apply user-requested refinements via chat interface.

**Signature:**
```python
def refine_text(
    self,
    current_text: str,
    refinement_request: str,
    audience: str,
    channel: str,
    context: Optional[str] = None
) -> LLMResponse
```

**Parameters:**
- `current_text`: Current version of the text
- `refinement_request`: User's refinement request (e.g., "Make it more formal")
- `audience`: Target audience
- `channel`: Communication channel
- `context`: Optional additional context

**Returns:**
- `LLMResponse` with refined text

**Example:**
```python
response = service.refine_text(
    current_text="The University of Illinois Chicago has great programs.",
    refinement_request="Make it sound more welcoming and enthusiastic.",
    audience="Students",
    channel="Website"
)
print(response.text)
# "The University of Illinois Chicago is excited to offer outstanding programs..."
```

---

## Configuration

### Environment Variables

The service uses configuration from environment variables or Parameter Store:

```bash
# AWS Configuration
AWS_REGION="us-east-1"
AWS_ACCESS_KEY_ID="your-access-key"
AWS_SECRET_ACCESS_KEY="your-secret-key"
AWS_SESSION_TOKEN="your-session-token"  # if using temporary credentials

# Optional: Override model IDs (defaults are in code)
BEDROCK_HAIKU_MODEL_ID="anthropic.claude-3-haiku-20240307-v1:0"
BEDROCK_SONNET_MODEL_ID="anthropic.claude-3-5-sonnet-20241022-v2:0"
```

### Service Configuration

Constants defined in `LLMService` class:

```python
# Model IDs
HAIKU_MODEL_ID = "anthropic.claude-3-haiku-20240307-v1:0"
SONNET_MODEL_ID = "anthropic.claude-3-5-sonnet-20241022-v2:0"

# AWS Configuration
REGION = "us-east-1"
CONNECTION_TIMEOUT = 30  # seconds
READ_TIMEOUT = 120  # seconds
MAX_RETRIES = 3

# Retry Configuration
BASE_DELAY = 1.0  # seconds for exponential backoff (1s, 2s, 4s)

# Model Selection
WORD_COUNT_THRESHOLD = 500  # Use Sonnet if > 500 words
```

### Reading Level Mapping

From SPEC.md requirements:

| Audience | Reading Level |
|----------|---------------|
| Students | Grade 8       |
| Faculty  | Grade 10      |
| Staff    | Grade 10      |

---

## Error Handling

### Exception Hierarchy

```python
LLMServiceError (base)
├── PromptLoadError - Template file not found or unreadable
└── ModelInvocationError - Model invocation failed after retries
```

### Retryable Errors

The service automatically retries these AWS errors with exponential backoff:

- `ThrottlingException` - API rate limit exceeded
- `ProvisionedThroughputExceededException` - Throughput limit exceeded
- `TooManyRequestsException` - Too many concurrent requests
- `ServiceUnavailableException` - AWS service temporarily unavailable

**Retry Schedule:**
- Attempt 1: Immediate
- Attempt 2: 1 second delay
- Attempt 3: 2 seconds delay
- Attempt 4: 4 seconds delay (final)

### Non-Retryable Errors

These errors fail immediately:

- `AccessDeniedException` - IAM permissions issue
- `ResourceNotFoundException` - Model not accessible
- `ValidationException` - Invalid request format

### Error Response Format

```python
try:
    response = service.rewrite_text(...)
except ModelInvocationError as e:
    # Error message includes:
    # - Model ID
    # - Number of attempts
    # - Error code from AWS
    # - Error message from AWS
    print(f"Error: {e}")
```

---

## Usage Examples

### Example 1: Simple Email Rewrite

```python
from services.llm_service import create_llm_service

# Initialize service
service = create_llm_service()

# Sample data
original_text = "UIC has great programs. Come check us out!"

issues = [
    {
        "type": "BRAND",
        "severity": "high",
        "description": "Use full university name on first reference",
        "location": "UIC has great programs"
    }
]

guidelines = [
    {
        "text": "The official name is 'University of Illinois Chicago' on first reference.",
        "source_url": "https://brand.uic.edu/messaging/name-and-boilerplate/"
    }
]

# Rewrite
response = service.rewrite_text(
    original_text=original_text,
    issues=issues,
    guidelines=guidelines,
    audience="Students",
    channel="Email"
)

print(f"Rewritten: {response.text}")
print(f"Model: {response.model_id}")
print(f"Latency: {response.latency_ms:.0f}ms")
```

### Example 2: Issue Detection

```python
# Analyze text for issues
text = "UIC's new building will open next Fall."

issues = service.detect_issues(
    text_to_analyze=text,
    guidelines=[
        {
            "text": "Use 'fall' (lowercase) for seasons.",
            "source_url": "https://brand.uic.edu/..."
        }
    ],
    audience="Staff",
    channel="Email"
)

for issue in issues:
    print(f"Issue: {issue['description']}")
    print(f"  Location: {issue['location']}")
    print(f"  Suggestion: {issue['suggestion']}")
```

### Example 3: Chat-based Refinement

```python
# User asks for a change
current_text = "The University of Illinois Chicago offers exceptional academic programs."

response = service.refine_text(
    current_text=current_text,
    refinement_request="Make it sound more welcoming and enthusiastic.",
    audience="Students",
    channel="Website"
)

print(f"Refined: {response.text}")
```

### Example 4: Integration with Backend Orchestrator

```python
# In FastAPI endpoint
from services.llm_service import create_llm_service

# Initialize once at startup
llm_service = create_llm_service()

@app.post("/api/analyze")
async def analyze_text(request: AnalyzeRequest):
    # Get issues from rule engine
    issues = rule_engine.check_text(request.text)
    
    # Get guidelines from RAG service
    guidelines = rag_service.retrieve_guidelines(request.text, request.audience)
    
    # Rewrite with LLM
    response = llm_service.rewrite_text(
        original_text=request.text,
        issues=issues,
        guidelines=guidelines,
        audience=request.audience,
        channel=request.channel
    )
    
    # Parse change tags (Task 3.4)
    changes = parse_change_tags(response.text)
    
    return {
        "original": request.text,
        "rewritten": response.text,
        "changes": changes,
        "model_used": response.model_id,
        "latency_ms": response.latency_ms
    }
```

---

## Testing

### Unit Tests

Run unit tests (requires AWS credentials):

```bash
python backend/test_llm_service.py
```

**Test Coverage:**
1. ✓ Initialization - Template loading, client setup
2. ✓ Model Selection - Word count threshold logic
3. ✓ Reading Level Mapping - Audience to grade level
4. ✓ Formatting Helpers - Issue and guideline formatting
5. ✓ Text Rewriting - End-to-end rewrite with change tags
6. ✓ Issue Detection - JSON parsing and validation
7. ✓ Text Refinement - Chat-based refinement

### Manual Testing

Quick test with real Bedrock:

```python
from services.llm_service import create_llm_service

service = create_llm_service()

response = service.rewrite_text(
    original_text="UIC is great!",
    issues=[{"type": "BRAND", "description": "Use full name"}],
    guidelines=[{"text": "Use 'University of Illinois Chicago'"}],
    audience="Students",
    channel="Email"
)

print(response.text)
```

---

## Integration Guide

### Step 1: Import Service

```python
from services.llm_service import create_llm_service
```

### Step 2: Initialize at Startup

```python
# In FastAPI app startup
@app.on_event("startup")
async def startup_event():
    app.state.llm_service = create_llm_service()
```

### Step 3: Use in Endpoints

```python
@app.post("/api/analyze")
async def analyze_text(request: AnalyzeRequest):
    llm_service = request.app.state.llm_service
    
    # Use service methods
    response = llm_service.rewrite_text(...)
    return response
```

### Integration Points

**With Workstream 1 (RAG)**:
```python
# RAG service provides guidelines
guidelines = rag_service.retrieve_guidelines(text, audience)

# LLM service uses guidelines in rewrite
response = llm_service.rewrite_text(..., guidelines=guidelines)
```

**With Workstream 2 (Rule Engine)**:
```python
# Rule engine provides issues
issues = rule_engine.analyze_text(text, rulesets, audience)

# LLM service uses issues in rewrite
response = llm_service.rewrite_text(..., issues=issues)
```

**With Task 3.4 (Change Tagging)**:
```python
# LLM service returns tagged text
response = llm_service.rewrite_text(...)

# Task 3.4 parses tags
changes = parse_change_tags(response.text)
html = generate_html_with_highlights(response.text, changes)
```

---

## Performance Considerations

### Model Selection Strategy

| Text Length | Model | Latency | Cost | Use Case |
|-------------|-------|---------|------|----------|
| < 500 words | Haiku | 2-3s | Low | Simple emails, short announcements |
| > 500 words | Sonnet | 4-6s | Medium | Long articles, complex documents |

### Optimization Tips

1. **Batch Processing**: Process multiple texts in parallel when possible
2. **Caching**: Cache results for identical inputs (not implemented in Phase 1)
3. **Progressive Loading**: Show partial results while waiting for LLM
4. **Model Warm-up**: First Lambda invocation is slower (cold start)

### Cost Tracking

Monitor token usage to optimize costs:

```python
response = service.rewrite_text(...)

if response.token_usage:
    input_tokens = response.token_usage['input_tokens']
    output_tokens = response.token_usage['output_tokens']
    
    # Log for cost analysis
    logger.info(f"Token usage: {input_tokens} in, {output_tokens} out")
```

### Lambda Optimization

For Lambda deployment:
- Keep service instance warm (singleton pattern)
- Reuse Bedrock client across invocations
- Set appropriate Lambda timeout (60-120 seconds)
- Allocate sufficient memory (512-1024 MB)

---

## Troubleshooting

### Issue: PromptLoadError

**Symptom**: "Template file not found"

**Solution**:
1. Verify `backend/prompts/` directory exists
2. Check all 3 template files are present:
   - `system_prompt.txt`
   - `rewrite_prompt_template.txt`
   - `detection_prompt_template.txt`
3. Ensure file encoding is UTF-8

---

### Issue: ModelInvocationError - AccessDeniedException

**Symptom**: "IAM role lacks permission"

**Solution**:
1. Check AWS credentials are configured
2. Verify IAM role has `bedrock:InvokeModel` permission
3. Request model access in AWS Console (Bedrock > Model access)

---

### Issue: ModelInvocationError - ResourceNotFoundException

**Symptom**: "Model not accessible"

**Solution**:
1. Go to AWS Console > Bedrock > Model access
2. Request access for Claude Haiku and Claude Sonnet
3. Wait for approval (usually instant)
4. Retry test

---

### Issue: ThrottlingException

**Symptom**: Frequent throttling errors

**Solution**:
- Service automatically retries with backoff
- If persistent, request higher throughput quotas
- Consider using Haiku more (lower rate limits)

---

### Issue: Malformed Change Tags

**Symptom**: Output missing `[BRAND]` or other tags

**Possible Causes**:
1. Model didn't follow instructions (rare)
2. Text too complex for model
3. Prompt template issue

**Solution**:
- Task 3.6 implements text diffing as fallback
- Check prompt templates for clarity
- Try Sonnet instead of Haiku for complex text

---

### Issue: High Latency

**Symptom**: Responses take >10 seconds

**Solution**:
1. Check network connectivity to AWS
2. Verify region is us-east-1 (closest to most users)
3. Consider using Haiku for simpler texts
4. Monitor CloudWatch logs for retry attempts

---

## Next Steps

With Task 3.3 complete, proceed to:

1. **Task 3.4**: Implement change tag parsing and HTML generation
2. **Task 3.5**: Add complexity scoring for model selection
3. **Task 3.6**: Implement text diffing as fallback for malformed tags
4. **Task 3.7**: Expand refinement handling for common patterns
5. **Task 3.8**: Create FastAPI routes for LLM endpoints
6. **Task 3.9**: Complete API documentation and mock data

---

## References

- **SPEC.md**: Overall system specification
- **project-plans/workstream-3-llm.md**: Task breakdown
- **backend/prompts/README.md**: Prompt template documentation
- **backend/prompts/EXAMPLE_USAGE.md**: Integration examples
- **.kiro/specs/bedrock-setup/design.md**: Technical design details

---

**Document Version**: 1.0  
**Task**: 3.3 - LLM Service Implementation  
**Status**: Complete ✅  
**Last Updated**: 2026-10-08

---

## Adaptive Model Selection (Task 3.5)

`select_model()` returns a `ModelSelectionDecision` with the selected model, a 0-100 complexity score, the routing reason, and component metrics. The score is computed locally from document length, average sentence length, long-word ratio, rule issue severity, and refinement-request complexity. Documents over 500 words always use Sonnet; shorter documents use Sonnet at a score of 50 or higher and Haiku otherwise.

All rewrite, detection, and refinement calls use this selector. Each decision is emitted as a structured `model_selection` log entry suitable for CloudWatch. The legacy `_select_model(text)` helper still returns a model ID for compatibility.

When Bedrock returns token usage, each `LLMResponse` includes `estimated_cost_usd` and `estimated_savings_usd`. `get_cost_metrics()` returns service-instance totals against an all-Sonnet baseline. Rates are USD per one million tokens and can be overridden with:

- `BEDROCK_HAIKU_INPUT_COST_PER_MILLION`
- `BEDROCK_HAIKU_OUTPUT_COST_PER_MILLION`
- `BEDROCK_SONNET_INPUT_COST_PER_MILLION`
- `BEDROCK_SONNET_OUTPUT_COST_PER_MILLION`

These values are estimates for observability, not billing records. Configure them to current contracted AWS rates before using the totals for financial reporting.

---

## Refinement Handling (Task 3.7)

The refine_text method normalizes chat requests before invoking Bedrock.
Recognized patterns include shorten, expand, formal, casual, simplify,
welcoming, engaging, and active voice. Multiple patterns can be combined, while
requests that do not match a preset remain supported as custom refinements.

Pass selection_start and selection_end as zero-based, half-open character
offsets to refine only part of a document. Both offsets are required together,
must describe a non-empty in-range selection, and cause the model to return only
replacement text for that span. The service then reconstructs the document
locally, so unselected text is preserved exactly.

The generated prompt preserves facts and existing change tags, forbids invented
details, applies the audience reading-level target, and requests tags for new
changes. LLMResponse.refinement contains JSON-ready pattern, ruleset, and
selection metadata for API consumers.

Offline validation:

    pytest backend/test_refinement.py
