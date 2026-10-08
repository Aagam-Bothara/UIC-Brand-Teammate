# UIC Editorial Assistant - Prompt Templates

This directory contains prompt templates for the LLM Service (Task 3.3). These prompts guide Claude Haiku and Sonnet models to generate brand-compliant, accessible text rewrites.

## Files

### 1. `system_prompt.txt`

**Purpose**: System-level instructions that define the AI assistant's role, responsibilities, and context.

**Usage**: Sent as the system message to establish the model's persona and guidelines before any user interaction.

**Key Sections**:
- Role definition as UIC editorial assistant
- Core responsibilities (brand compliance, accessibility, audience awareness)
- UIC brand guidelines summary
- Audience definitions (Students, Faculty, Staff)
- Communication channels (Email, Website, Social Media)
- Output requirements and approach

**Integration**: Used in every LLM invocation as the base context.

---

### 2. `detection_prompt_template.txt`

**Purpose**: Analyzes text to identify potential issues before rewriting.

**Usage**: Optional pre-processing step that can complement or validate rule engine output.

**Placeholders**:
- `{audience}` - Target audience (Students, Faculty, Staff)
- `{channel}` - Communication channel (Email, Website, Social Media)
- `{reading_level_target}` - Expected reading level (e.g., "Grade 8")
- `{text_to_analyze}` - Original text to analyze
- `{guidelines_context}` - Retrieved guidelines from RAG service

**Output Format**: JSON array of detected issues with type, severity, location, description, suggestion, and guideline reference.

**Example**:
```json
[
  {
    "issue_type": "BRAND",
    "severity": "high",
    "location": "UIC offers many programs",
    "description": "First reference should use full university name",
    "suggestion": "University of Illinois Chicago offers many programs",
    "guideline_reference": "https://brand.uic.edu/messaging/name-and-boilerplate/"
  }
]
```

---

### 3. `rewrite_prompt_template.txt`

**Purpose**: Main template for generating improved, tagged text rewrites.

**Usage**: Primary LLM task that produces the final rewritten text with change tags.

**Placeholders**:
- `{audience}` - Target audience
- `{channel}` - Communication channel
- `{reading_level_target}` - Target reading level
- `{original_text}` - Original text to rewrite
- `{issues_list}` - Issues detected by rule engine (formatted as text)
- `{guidelines_context}` - Retrieved guidelines from RAG service

**Output Format**: Plain text with inline change tags marking each modification:
- `[BRAND]...[/BRAND]` - Brand compliance fixes
- `[ACCESSIBILITY]...[/ACCESSIBILITY]` - Accessibility improvements
- `[CONTENT]...[/CONTENT]` - Content quality enhancements
- `[READING_LEVEL]...[/READING_LEVEL]` - Reading level simplifications
- `[AUDIENCE_TONE]...[/AUDIENCE_TONE]` - Tone adjustments

**Example**:
```
The [BRAND]University of Illinois Chicago[/BRAND] [ACCESSIBILITY]provides numerous academic programs[/ACCESSIBILITY] for [AUDIENCE_TONE]students seeking to advance their education[/AUDIENCE_TONE].
```

---

## Integration with LLM Service

### Typical Workflow

1. **Initialize**: Load `system_prompt.txt` as system context
2. **Retrieve Guidelines**: RAG service fetches relevant UIC guidelines
3. **Detect Issues**: Rule engine identifies specific violations
4. **Format Prompt**: Fill `rewrite_prompt_template.txt` with:
   - User's original text
   - Detected issues from rule engine
   - Retrieved guidelines from RAG
   - Audience, channel, reading level from user input
5. **Invoke Model**: Send to Claude (Haiku for simple, Sonnet for complex)
6. **Parse Response**: Extract rewritten text and parse change tags
7. **Return**: Send tagged text to frontend for progressive reveal

### Model Selection

- **Claude Haiku**: Short texts (<500 words), simple issues, faster response
- **Claude Sonnet**: Long texts (>500 words), complex issues, higher quality

### Error Handling

If the LLM response:
- **Missing tags**: Fall back to text diffing (see Task 3.6)
- **Malformed tags**: Attempt to parse and correct, log warning
- **Wrong format**: Retry once with clarified instructions
- **Empty response**: Use original text, log error

### Testing

Run validation tests with:
```bash
python backend/test_prompts.py
```

Tests verify:
- All files exist and are readable
- Required placeholders present in templates
- Templates format correctly with sample data
- Consistent terminology across prompts
- All 5 rulesets mentioned

### Prompt Refinement

As you iterate on prompt quality:
1. Update template files directly
2. Run `test_prompts.py` to verify structure
3. Test with actual Bedrock models (requires Task 3.1 setup)
4. Evaluate output quality on sample dataset
5. Adjust instructions, examples, or constraints as needed

## Design Rationale

### Why Separate Templates?

- **Modularity**: Detection and rewriting are distinct concerns
- **Flexibility**: Can use detection alone for analysis, or skip if rule engine sufficient
- **Testing**: Easier to test and refine each template independently

### Why Inline Tags?

- **Progressive Reveal**: Frontend can toggle visibility by tag type
- **Transparency**: Users see exactly which rulesets influenced each change
- **Diffing Fallback**: If tags fail, can fall back to text diffing (Task 3.6)

### Why Plain Text Output?

- **Simplicity**: Easier for model to generate reliably than complex formats
- **Natural**: Preserves flow and readability of the rewritten text
- **Frontend Control**: Parsing and rendering handled by frontend components

## Next Steps

With prompts created (Task 3.2 ✅), you can now:

1. **Task 3.3**: Implement `LLMService` class that uses these templates
2. **Task 3.4**: Parse change tags and generate HTML
3. **Task 3.5**: Add model selection logic (Haiku vs Sonnet)

## References

- **SPEC.md**: Overall system specification
- **project-plans/workstream-3-llm.md**: Task breakdown for Workstream 3
- **.kiro/specs/bedrock-setup/**: Detailed technical design documents
- **UIC Brand Guidelines**: https://brand.uic.edu/

---

**Task**: 3.2 - Prompt Engineering  
**Status**: Complete ✅  
**Last Updated**: 2026-10-08
