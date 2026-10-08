# Text Diff Service (Task 3.6)

`backend/services/text_diff.py` provides the deterministic fallback used when
an LLM rewrite omits inline change tags or returns malformed tags. It uses
Python's standard-library `difflib.SequenceMatcher`, so it runs offline and in
Lambda without another dependency or model invocation.

## Usage

```python
from backend.services.text_diff import diff_text

result = diff_text(
    "UIC has resources.",
    "The University of Illinois Chicago offers accessible resources.",
    rulesets=["BRAND", "ACCESSIBILITY"],
)

for change in result.annotations:
    print(change.change_id, change.operation, change.explanation)

payload = result.to_dict()
```

Each annotation contains a stable request-local ID, an `insert`, `delete`, or
`replace` operation, the before/after text, character offsets into both input
strings, ruleset metadata, and a concise explanation. `DiffResult` also
provides escaped `original_html` and `revised_html`, operation counts, and a
similarity ratio. Both HTML strings carry matching `data-change-id` attributes
for side-by-side selection and individual acceptance controls.

Mechanical diffing cannot infer why the LLM changed text. The default ruleset
is therefore `CONTENT`; callers should pass issue-derived rulesets when they
have reliable classification context.

## Change-parser fallback

Use tagged output when parsing is clean, and compare the original with the
parser's plain text when tags are missing or malformed:

```python
from backend.services.change_parser import parse_changes
from backend.services.text_diff import diff_text

parsed = parse_changes(llm_response.text)
if parsed.warnings or not parsed.changes:
    comparison = diff_text(original_text, parsed.plain_text)
    changes = comparison.to_dict()["annotations"]
else:
    changes = parsed.to_dict()["changes"]
```

An unchanged rewrite correctly returns zero annotations. Consumers should not
treat that case as a parsing failure.

## Verification

Run the offline test suite with:

```powershell
pytest backend/test_text_diff.py
```
