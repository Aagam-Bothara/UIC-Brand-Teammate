# Backend Integration Guide

This guide shows how to integrate the LLM Service (Task 3.3) with the Change Parser (Task 3.4) for the complete text rewriting workflow.

## Quick Start

### Complete Rewrite Workflow

```python
from services.llm_service import create_llm_service
from services.change_parser import parse_changes

# Initialize LLM service
llm_service = create_llm_service()

# Input parameters
original_text = """UIC offers tutoring services. Use them to do better in classes."""

issues = [
    {
        'type': 'BRAND',
        'severity': 'high',
        'description': 'Use full university name',
        'location': 'UIC'
    }
]

guidelines = [
    {
        'text': 'Always use "University of Illinois Chicago" on first reference.',
        'source_url': 'https://brand.uic.edu/messaging/name-and-boilerplate/'
    }
]

# Step 1: Get rewritten text from LLM (with inline tags)
llm_response = llm_service.rewrite_text(
    original_text=original_text,
    issues=issues,
    guidelines=guidelines,
    audience="Students",
    channel="Email"
)

print("Tagged output from LLM:")
print(llm_response.text)
# Output: "The [BRAND]University of Illinois Chicago[/BRAND] offers..."

# Step 2: Parse tags and generate HTML
parse_result = parse_changes(llm_response.text)

# Step 3: Use the results
print("\nPlain text:")
print(parse_result.plain_text)

print("\nHTML for frontend:")
print(parse_result.html)

print("\nStatistics:")
print(parse_result.stats)
# {'BRAND': 1, 'ACCESSIBILITY': 0, ...}
```

## API Endpoint Integration

### Example FastAPI Endpoint

```python
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List, Dict, Any
from services.llm_service import create_llm_service
from services.change_parser import parse_changes

app = FastAPI()

# Initialize service once
llm_service = create_llm_service()

class RewriteRequest(BaseModel):
    text: str
    audience: str
    channel: str
    issues: List[Dict[str, Any]]
    guidelines: List[Dict[str, str]]

class RewriteResponse(BaseModel):
    original_text: str
    plain_text: str
    html: str
    changes: List[Dict[str, Any]]
    stats: Dict[str, int]
    model_id: str
    latency_ms: float
    warnings: List[str]

@app.post("/api/rewrite", response_model=RewriteResponse)
async def rewrite_text(request: RewriteRequest):
    """
    Rewrite text with brand compliance and accessibility improvements.
    
    Returns:
    - original_text: Input text
    - plain_text: Improved text without tags
    - html: HTML with styled change highlights
    - changes: List of changes with metadata
    - stats: Count of changes by ruleset
    - model_id: Which LLM was used
    - latency_ms: Processing time
    - warnings: Any parsing warnings
    """
    try:
        # Step 1: Get LLM rewrite with tags
        llm_response = llm_service.rewrite_text(
            original_text=request.text,
            issues=request.issues,
            guidelines=request.guidelines,
            audience=request.audience,
            channel=request.channel
        )
        
        # Step 2: Parse tags
        parse_result = parse_changes(llm_response.text)
        
        # Step 3: Build response
        return RewriteResponse(
            original_text=request.text,
            plain_text=parse_result.plain_text,
            html=parse_result.html,
            changes=parse_result.to_dict()['changes'],
            stats=parse_result.stats,
            model_id=llm_response.model_id,
            latency_ms=llm_response.latency_ms,
            warnings=parse_result.warnings
        )
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/css-styles")
async def get_css_styles():
    """Get CSS stylesheet for change highlighting."""
    from services.change_parser import ChangeParser
    
    parser = ChangeParser()
    return {"css": parser.get_css_styles()}
```

## Frontend Integration

### React Component Example

```typescript
// TypeScript interfaces
interface Change {
  text: string;
  rulesets: string[];
  start_pos: number;
  end_pos: number;
  html: string;
}

interface RewriteResult {
  original_text: string;
  plain_text: string;
  html: string;
  changes: Change[];
  stats: Record<string, number>;
  warnings: string[];
}

// React component
import React, { useState } from 'react';

const TextRewriter: React.FC = () => {
  const [result, setResult] = useState<RewriteResult | null>(null);
  const [visibleRulesets, setVisibleRulesets] = useState<Set<string>>(
    new Set(['BRAND', 'ACCESSIBILITY', 'CONTENT', 'READING_LEVEL', 'AUDIENCE_TONE'])
  );

  const toggleRuleset = (ruleset: string) => {
    setVisibleRulesets(prev => {
      const next = new Set(prev);
      if (next.has(ruleset)) {
        next.delete(ruleset);
      } else {
        next.add(ruleset);
      }
      return next;
    });
  };

  const getFilteredHTML = () => {
    if (!result) return '';
    
    // Client-side filtering based on visible rulesets
    const div = document.createElement('div');
    div.innerHTML = result.html;
    
    div.querySelectorAll('.text-change').forEach((span: any) => {
      const rulesets = span.dataset.rulesets.split(',');
      const isVisible = rulesets.some((r: string) => visibleRulesets.has(r));
      
      if (!isVisible) {
        span.classList.add('hidden');
      } else {
        span.classList.remove('hidden');
      }
    });
    
    return div.innerHTML;
  };

  return (
    <div className="rewriter-container">
      {/* Ruleset toggles */}
      <div className="ruleset-controls">
        {Object.entries(result?.stats || {}).map(([ruleset, count]) => (
          <button
            key={ruleset}
            onClick={() => toggleRuleset(ruleset)}
            className={visibleRulesets.has(ruleset) ? 'active' : 'inactive'}
          >
            {ruleset} ({count})
          </button>
        ))}
      </div>

      {/* Rewritten text with highlights */}
      <div 
        className="rewritten-content"
        dangerouslySetInnerHTML={{ __html: getFilteredHTML() }}
      />
    </div>
  );
};
```

### JavaScript Progressive Reveal

```javascript
// Toggle specific ruleset visibility
function toggleRuleset(rulesetName, isVisible) {
  const selector = `.change-${rulesetName.toLowerCase()}`;
  document.querySelectorAll(selector).forEach(span => {
    if (isVisible) {
      span.classList.remove('hidden');
    } else {
      span.classList.add('hidden');
    }
  });
}

// Toggle all rulesets
function showAllChanges(show) {
  document.querySelectorAll('.text-change').forEach(span => {
    if (show) {
      span.classList.remove('hidden');
    } else {
      span.classList.add('hidden');
    }
  });
}

// Highlight change on hover
document.querySelectorAll('.text-change').forEach(span => {
  span.addEventListener('mouseenter', () => {
    span.classList.add('active');
  });
  
  span.addEventListener('mouseleave', () => {
    span.classList.remove('active');
  });
  
  // Show explanation on click
  span.addEventListener('click', () => {
    const rulesets = span.dataset.rulesets.split(',');
    const text = span.textContent;
    showExplanation(text, rulesets);
  });
});

function showExplanation(text, rulesets) {
  // Show popup or sidebar with explanation
  console.log(`Explaining change: "${text}" (${rulesets.join(', ')})`);
}
```

## Complete Workflow Example

### Full Pipeline

```python
"""
Complete text rewriting pipeline.
Integrates: RAG → Rule Engine → LLM Service → Change Parser
"""

from services.llm_service import create_llm_service
from services.change_parser import parse_changes

def complete_rewrite_pipeline(
    text: str,
    audience: str,
    channel: str,
    rag_service,      # From Workstream 1
    rule_engine       # From Workstream 2
):
    """
    Execute complete rewrite pipeline.
    
    Returns:
        dict with all results
    """
    
    # Step 1: Retrieve guidelines (Workstream 1 - RAG)
    guidelines = rag_service.retrieve_guidelines(
        query=text[:200],  # Use first 200 chars for query
        audience=audience
    )
    
    # Step 2: Detect issues (Workstream 2 - Rule Engine)
    rule_results = rule_engine.analyze_text(
        text=text,
        rulesets=['brand', 'accessibility', 'content', 'reading_level', 'audience_tone'],
        audience=audience,
        channel=channel
    )
    issues = rule_results.issues
    
    # Step 3: Rewrite with LLM (Task 3.3)
    llm_service = create_llm_service()
    llm_response = llm_service.rewrite_text(
        original_text=text,
        issues=issues,
        guidelines=guidelines,
        audience=audience,
        channel=channel
    )
    
    # Step 4: Parse tags (Task 3.4)
    parse_result = parse_changes(llm_response.text)
    
    # Step 5: Assemble response
    return {
        # Original
        'original_text': text,
        'original_issues': issues,
        'original_scores': {
            'brand_score': rule_results.brand_score,
            'accessibility_score': rule_results.accessibility_score
        },
        
        # Rewritten
        'rewritten_plain': parse_result.plain_text,
        'rewritten_html': parse_result.html,
        'changes': parse_result.to_dict()['changes'],
        'change_stats': parse_result.stats,
        
        # Guidelines used
        'guidelines_retrieved': len(guidelines),
        
        # Metadata
        'model_used': llm_response.model_id,
        'processing_time_ms': llm_response.latency_ms,
        'tokens_used': llm_response.token_usage,
        'warnings': parse_result.warnings,
        
        # Context
        'audience': audience,
        'channel': channel
    }
```

## Error Handling

### Comprehensive Error Handling

```python
from services.llm_service import (
    LLMService,
    ModelInvocationError,
    PromptLoadError
)
from services.change_parser import ChangeParser, ChangeParserError

def safe_rewrite(text, audience, channel, issues, guidelines):
    """
    Rewrite with comprehensive error handling.
    """
    try:
        # Initialize services
        llm_service = create_llm_service()
        parser = ChangeParser()
        
        # LLM rewrite
        try:
            llm_response = llm_service.rewrite_text(
                original_text=text,
                issues=issues,
                guidelines=guidelines,
                audience=audience,
                channel=channel
            )
        except ModelInvocationError as e:
            return {
                'error': 'model_invocation_failed',
                'message': str(e),
                'fallback': 'original_text',
                'original_text': text
            }
        
        # Parse tags
        try:
            parse_result = parser.parse(llm_response.text)
            
            # Check for serious parsing issues
            if len(parse_result.warnings) > 5:
                # Too many warnings, might be malformed output
                return {
                    'warning': 'parsing_issues',
                    'plain_text': parse_result.plain_text,
                    'html': None,
                    'warnings': parse_result.warnings,
                    'fallback_to_plain': True
                }
            
            return {
                'success': True,
                'plain_text': parse_result.plain_text,
                'html': parse_result.html,
                'changes': parse_result.to_dict()['changes'],
                'stats': parse_result.stats,
                'warnings': parse_result.warnings
            }
            
        except Exception as e:
            # Parsing completely failed, return plain LLM output
            return {
                'error': 'parsing_failed',
                'message': str(e),
                'plain_text': llm_response.text,  # Raw LLM output
                'html': None,
                'fallback': 'plain_llm_output'
            }
    
    except Exception as e:
        # Catastrophic failure
        return {
            'error': 'critical_failure',
            'message': str(e),
            'original_text': text,
            'fallback': 'original_text'
        }
```

## Performance Optimization

### Caching Results

```python
from functools import lru_cache
import hashlib

class OptimizedRewriter:
    """Rewriter with caching for repeated requests."""
    
    def __init__(self):
        self.llm_service = create_llm_service()
        self.parser = ChangeParser()
        
        # Cache CSS (never changes)
        self._css_cache = self.parser.get_css_styles()
    
    def get_css(self):
        """Return cached CSS."""
        return self._css_cache
    
    @lru_cache(maxsize=128)
    def rewrite_cached(self, text_hash: str, audience: str, channel: str):
        """
        Cached rewrite for identical requests.
        Note: In production, use Redis or similar instead of lru_cache.
        """
        # This is a placeholder - actual implementation would look up by hash
        pass
    
    def rewrite(self, text: str, audience: str, channel: str, issues, guidelines):
        """Rewrite with optional caching."""
        
        # Generate cache key
        cache_key = self._generate_cache_key(text, audience, channel, issues)
        
        # Check cache (implement actual cache lookup)
        # cached = self.rewrite_cached(cache_key, audience, channel)
        # if cached:
        #     return cached
        
        # Perform actual rewrite
        llm_response = self.llm_service.rewrite_text(
            original_text=text,
            issues=issues,
            guidelines=guidelines,
            audience=audience,
            channel=channel
        )
        
        parse_result = self.parser.parse(llm_response.text)
        
        return {
            'plain_text': parse_result.plain_text,
            'html': parse_result.html,
            'changes': parse_result.to_dict()['changes'],
            'stats': parse_result.stats
        }
    
    def _generate_cache_key(self, text, audience, channel, issues):
        """Generate cache key for request."""
        key_parts = [
            text,
            audience,
            channel,
            str(sorted([(i.get('type'), i.get('severity')) for i in issues]))
        ]
        key_string = '|'.join(key_parts)
        return hashlib.md5(key_string.encode()).hexdigest()
```

## Testing Integration

### Integration Tests

```python
import pytest
from services.llm_service import create_llm_service
from services.change_parser import parse_changes

@pytest.fixture
def llm_service():
    return create_llm_service()

def test_llm_to_parser_integration(llm_service):
    """Test that LLM output can be parsed successfully."""
    
    # Mock LLM response with tags
    mock_output = "The [BRAND]University of Illinois Chicago[/BRAND] offers programs."
    
    # Parse
    result = parse_changes(mock_output)
    
    # Verify
    assert "University of Illinois Chicago" in result.plain_text
    assert result.stats['BRAND'] == 1
    assert len(result.changes) == 1
    assert '<span' in result.html

def test_end_to_end_workflow():
    """Test complete workflow (requires AWS credentials)."""
    
    # This test requires actual AWS credentials
    # Skip in CI/CD, run manually for validation
    
    pass  # Implementation when AWS is available
```

## Summary

### Integration Checklist

- [x] LLM Service generates tagged output
- [x] Change Parser processes tags
- [x] API endpoint combines both
- [ ] Frontend receives and displays HTML
- [ ] Progressive reveal works
- [ ] Error handling complete
- [ ] Performance optimization implemented
- [ ] Integration tests passing

### Next Steps

1. Implement API endpoints (Task 3.8)
2. Integrate with RAG Service (Workstream 1)
3. Integrate with Rule Engine (Workstream 2)
4. Build frontend components (Workstream 4)
5. Add comprehensive logging
6. Deploy to AWS Lambda

---

For more information:
- LLM Service: `backend/docs/LLM_SERVICE.md`
- Change Parser: `backend/docs/CHANGE_PARSER.md`
- API Documentation: `backend/docs/API.md` (Task 3.8)
