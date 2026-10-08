# Prompt Template Usage Examples

This document shows how the prompt templates will be used in the LLM Service (Task 3.3).

## Example 1: Simple Email Rewrite

### Input Data

```python
user_input = {
    "text": "UIC has great programs. Come check us out!",
    "audience": "Students",
    "channel": "Email"
}

issues_detected = [
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

rag_guidelines = [
    {
        "text": "The official name is 'University of Illinois Chicago' on first reference...",
        "source_url": "https://brand.uic.edu/messaging/name-and-boilerplate/"
    }
]
```

### Formatted Rewrite Prompt

```
# Text Rewriting Task

You are rewriting a UIC communication to improve brand compliance, accessibility, and overall quality.

## Context

**Target Audience**: Students
**Communication Channel**: Email
**Reading Level Target**: Grade 8

## Original Text

UIC has great programs. Come check us out!

## Identified Issues

The following issues were detected by automated rule checking:

- [BRAND - High] Use full university name on first reference
  Location: "UIC has great programs"
  
- [ACCESSIBILITY - Medium] Too informal for official communication
  Location: "Come check us out!"

## Retrieved Brand Guidelines

These relevant excerpts from UIC brand guidelines should inform your rewrite:

- The official name is 'University of Illinois Chicago' on first reference. Subsequent references may use 'UIC'.
  Source: https://brand.uic.edu/messaging/name-and-boilerplate/

## Rewriting Instructions

[... full instructions from rewrite_prompt_template.txt ...]

Begin your rewrite now:
```

### Expected LLM Response

```
The [BRAND]University of Illinois Chicago[/BRAND] offers [ACCESSIBILITY]exceptional academic programs[/ACCESSIBILITY]. [AUDIENCE_TONE]We invite you to explore the opportunities available at UIC[/AUDIENCE_TONE]!
```

### Parsed Output

```python
{
    "rewritten_text": "The University of Illinois Chicago offers exceptional academic programs. We invite you to explore the opportunities available at UIC!",
    "changes": [
        {
            "tag": "BRAND",
            "original": "UIC",
            "rewritten": "University of Illinois Chicago",
            "start_index": 4,
            "end_index": 32
        },
        {
            "tag": "ACCESSIBILITY",
            "original": "great programs",
            "rewritten": "exceptional academic programs",
            "start_index": 41,
            "end_index": 70
        },
        {
            "tag": "AUDIENCE_TONE",
            "original": "Come check us out!",
            "rewritten": "We invite you to explore the opportunities available at UIC!",
            "start_index": 72,
            "end_index": 133
        }
    ]
}
```

---

## Example 2: Faculty Website Content

### Input Data

```python
user_input = {
    "text": "The Department of Computer Science offers cutting-edge research opportunities in artificial intelligence, machine learning, and data science. Students can work with world-renowned faculty on projects that push the boundaries of what's possible with computational systems.",
    "audience": "Faculty",
    "channel": "Website"
}

issues_detected = [
    {
        "type": "READING_LEVEL",
        "severity": "medium",
        "description": "Sentence too long (35 words)",
        "location": "Students can work with world-renowned faculty..."
    }
]

rag_guidelines = [
    {
        "text": "Use clear, direct language. Break complex ideas into digestible chunks.",
        "source_url": "https://brand.uic.edu/messaging/editorial-and-style-guide/"
    }
]
```

### Expected LLM Response

```
The Department of Computer Science offers cutting-edge research opportunities in artificial intelligence, machine learning, and data science. [READING_LEVEL]Students collaborate with world-renowned faculty on innovative projects. These projects push the boundaries of computational systems.[/READING_LEVEL]
```

---

## Example 3: Issue Detection Only

Sometimes you may want to just analyze text without rewriting. Use the detection template:

### Input Data

```python
user_input = {
    "text": "UIC's new building will open next Fall. The facility features state-of-the-art classrooms and labs.",
    "audience": "Staff",
    "channel": "Email"
}

rag_guidelines = [
    {
        "text": "Use 'fall' (lowercase) for seasons unless part of a proper noun.",
        "source_url": "https://brand.uic.edu/messaging/editorial-and-style-guide/"
    }
]
```

### Expected LLM Response (JSON)

```json
[
  {
    "issue_type": "BRAND",
    "severity": "high",
    "location": "UIC's new building",
    "description": "Use full university name on first reference",
    "suggestion": "The University of Illinois Chicago's new building",
    "guideline_reference": "https://brand.uic.edu/messaging/name-and-boilerplate/"
  },
  {
    "issue_type": "CONTENT",
    "severity": "low",
    "location": "next Fall",
    "description": "Seasons should be lowercase",
    "suggestion": "next fall",
    "guideline_reference": "https://brand.uic.edu/messaging/editorial-and-style-guide/"
  }
]
```

---

## Example 4: Progressive Reveal Use Case

User wants to see improvements one ruleset at a time:

### Step 1: User enables only BRAND ruleset

Frontend sends rewrite request with `enabled_rulesets: ["BRAND"]`

**LLM Output**:
```
The [BRAND]University of Illinois Chicago[/BRAND] has great programs. Come check us out!
```

### Step 2: User additionally enables ACCESSIBILITY

Frontend toggles visibility of `[ACCESSIBILITY]` tags from previous full rewrite:

**Full Rewritten Text** (pre-generated):
```
The [BRAND]University of Illinois Chicago[/BRAND] offers [ACCESSIBILITY]exceptional academic programs[/ACCESSIBILITY]. [AUDIENCE_TONE]We invite you to explore the opportunities available at UIC[/AUDIENCE_TONE]!
```

**Display with BRAND + ACCESSIBILITY**:
```
The University of Illinois Chicago offers exceptional academic programs. Come check us out!
```

### Step 3: User enables all rulesets

**Display with all tags**:
```
The University of Illinois Chicago offers exceptional academic programs. We invite you to explore the opportunities available at UIC!
```

---

## Code Integration Example (Task 3.3)

Here's how the LLM Service will use these templates:

```python
class LLMService:
    def __init__(self):
        # Load templates at initialization
        self.system_prompt = self._load_prompt("system_prompt.txt")
        self.rewrite_template = self._load_prompt("rewrite_prompt_template.txt")
        self.detection_template = self._load_prompt("detection_prompt_template.txt")
    
    def rewrite_text(
        self,
        original_text: str,
        issues: List[Dict],
        guidelines: List[Dict],
        audience: str,
        channel: str
    ) -> str:
        """Generate improved text with change tags."""
        
        # Determine reading level based on audience
        reading_level = self._get_reading_level(audience)
        
        # Format issues as text list
        issues_text = self._format_issues(issues)
        
        # Format guidelines as text
        guidelines_text = self._format_guidelines(guidelines)
        
        # Fill template
        prompt = self.rewrite_template.format(
            audience=audience,
            channel=channel,
            reading_level_target=reading_level,
            original_text=original_text,
            issues_list=issues_text,
            guidelines_context=guidelines_text
        )
        
        # Invoke Bedrock
        response = self._invoke_bedrock(
            system_prompt=self.system_prompt,
            user_prompt=prompt,
            model_id=self._select_model(original_text)
        )
        
        return response
    
    def _invoke_bedrock(self, system_prompt: str, user_prompt: str, model_id: str) -> str:
        """Send request to AWS Bedrock."""
        
        body = {
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 4000,
            "temperature": 0.5,
            "system": system_prompt,
            "messages": [
                {
                    "role": "user",
                    "content": user_prompt
                }
            ]
        }
        
        response = self.bedrock_client.invoke_model(
            modelId=model_id,
            body=json.dumps(body)
        )
        
        response_body = json.loads(response['body'].read())
        return response_body['content'][0]['text']
```

---

## Testing the Prompts

### Manual Test with Sample Data

1. **Set up environment** (requires Task 3.1):
   ```bash
   python backend/test_bedrock_setup.py
   ```

2. **Create test script**:
   ```python
   # test_prompts_with_bedrock.py
   import json
   from services.llm_service import LLMService
   
   service = LLMService()
   
   result = service.rewrite_text(
       original_text="UIC is great!",
       issues=[{"type": "BRAND", "description": "Use full name"}],
       guidelines=[{"text": "Use 'University of Illinois Chicago'"}],
       audience="Students",
       channel="Email"
   )
   
   print(result)
   ```

3. **Verify output**:
   - Contains change tags: `[BRAND]...[/BRAND]`
   - Addresses identified issues
   - Maintains natural flow
   - Appropriate for audience and channel

### Iterative Refinement

If output quality is poor:

1. **Check prompt clarity**: Are instructions clear?
2. **Check examples**: Add few-shot examples if needed
3. **Check constraints**: Are constraints too strict or too loose?
4. **Check guidelines**: Is RAG returning relevant context?
5. **Check model**: Try Sonnet instead of Haiku for complex cases

---

## Best Practices

### 1. Always Include System Prompt
The system prompt establishes crucial context. Never skip it.

### 2. Keep Placeholders Consistent
If you add new placeholders, update:
- Template file
- Validation scripts
- README documentation
- This examples file

### 3. Test with Real Data Early
Use examples from Team8Dataset.xlsx to validate prompt quality.

### 4. Monitor Token Usage
- System prompt: ~1,000 tokens
- Rewrite template + data: ~1,500-3,000 tokens
- Keep total under 8,000 for Haiku, 16,000 for Sonnet

### 5. Handle Edge Cases
- Empty text: Return original
- No issues: Still improve tone/style
- Malformed tags: Fall back to text diffing

---

**Document Version**: 1.0  
**Last Updated**: 2026-10-08  
**Task**: 3.2 - Prompt Engineering  
**Status**: Complete ✅
