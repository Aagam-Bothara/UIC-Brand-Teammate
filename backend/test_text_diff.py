"""Offline tests for Task 3.6 text diffing."""

import pytest

from backend.services.text_diff import TextDiffError, diff_text


def test_identical_text_has_no_annotations():
    result = diff_text("Welcome to UIC.", "Welcome to UIC.")

    assert result.annotations == []
    assert result.stats == {"total": 0, "insert": 0, "delete": 0, "replace": 0}
    assert result.similarity_ratio == 1.0
    assert result.original_html == "Welcome to UIC."


def test_generates_position_aware_annotations():
    result = diff_text(
        "UIC has old resources and forms.",
        "UIC now offers accessible resources.",
    )

    assert result.stats["total"] >= 2
    assert {item.operation for item in result.annotations} <= {"insert", "delete", "replace"}
    assert [item.change_id for item in result.annotations] == [
        f"change-{index}" for index in range(1, len(result.annotations) + 1)
    ]
    for item in result.annotations:
        assert result.original_text[item.original_start:item.original_end] == item.original_text
        assert result.revised_text[item.revised_start:item.revised_end] == item.revised_text


@pytest.mark.parametrize(
    ("original", "revised", "operation"),
    [
        ("Apply today.", "Please apply today.", "insert"),
        ("Please apply today.", "Apply today.", "delete"),
        ("Apply tomorrow.", "Apply today.", "replace"),
    ],
)
def test_operation_types(original, revised, operation):
    if operation == 'insert':
        revised = 'Please ' + original
    elif operation == 'delete':
        revised = original.removeprefix('Please ')
    result = diff_text(original, revised)

    assert operation in {item.operation for item in result.annotations}
    assert result.stats[operation] >= 1


def test_annotations_support_rulesets_and_json_serialization():
    result = diff_text(
        "UIC welcomes you.",
        "The University of Illinois Chicago welcomes you.",
        rulesets=["brand", "AUDIENCE_TONE", "brand"],
    )
    payload = result.to_dict()

    assert result.changes is result.annotations
    assert all(item.rulesets == ["BRAND", "AUDIENCE_TONE"] for item in result.annotations)
    assert payload["annotations"][0]["change_id"] == "change-1"
    assert payload["stats"] == result.stats


def test_html_is_escaped_and_links_both_sides_by_change_id():
    result = diff_text("Use <old> text.", "Use <strong>new</strong> text.")

    assert "<old>" not in result.original_html
    assert "&lt;" in result.original_html
    assert "<strong>" not in result.revised_html
    assert 'data-change-id="change-1"' in result.original_html
    assert 'data-change-id="change-1"' in result.revised_html
    assert 'data-operation="replace"' in result.revised_html


def test_empty_and_unicode_text_are_supported():
    empty = diff_text("", "")
    unicode_result = diff_text("UIC cafe", "UIC caf\u00e9 \U0001f525")

    assert empty.similarity_ratio == 1.0
    assert empty.annotations == []
    assert unicode_result.annotations
    assert unicode_result.revised_html.endswith("\U0001f525")


def test_invalid_inputs_and_rulesets_are_rejected():
    with pytest.raises(TextDiffError, match="must be strings"):
        diff_text(None, "text")  # type: ignore[arg-type]
    with pytest.raises(TextDiffError, match="Unknown ruleset"):
        diff_text("before", "after", rulesets=["UNKNOWN"])
    with pytest.raises(TextDiffError, match="at least one"):
        diff_text("before", "after", rulesets=[])
