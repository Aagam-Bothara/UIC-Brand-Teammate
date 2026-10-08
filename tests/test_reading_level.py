import pytest

from backend.services import reading_level as rl


@pytest.mark.parametrize("word,expected", [
    ("cat", 1), ("the", 1), ("table", 2), ("make", 1), ("walked", 1),
    ("wanted", 2), ("happy", 2), ("university", 5), ("communication", 5),
    ("beautiful", 3), ("education", 4), ("students", 2), ("orientation", 5),
    ("video", 3), ("media", 3), ("social", 2), ("nation", 2), ("actual", 3),
    ("language", 2), ("quality", 3), ("Chicago", 3),
])
def test_count_syllables(word, expected):
    assert rl.count_syllables(word) == expected


def test_split_sentences_handles_abbreviations():
    text = "Meet Dr. Smith at 3 p.m. on Oct. 8. Bring your ID! Questions? Email us"
    spans = rl.split_sentences(text)
    sentences = [text[s:e] for s, e in spans]
    assert sentences == [
        "Meet Dr. Smith at 3 p.m. on Oct. 8.",
        "Bring your ID!",
        "Questions?",
        "Email us",
    ]


def test_time_abbreviation_can_end_a_sentence():
    text = "Doors open at 3 p.m. Join us early."
    assert [text[s:e] for s, e in rl.split_sentences(text)] == ["Doors open at 3 p.m.", "Join us early."]


def test_line_breaks_split_sentences():
    assert len(rl.split_sentences("Subject: Orientation\nHello students\n- Item one")) == 3


def test_split_paragraphs():
    assert len(rl.split_paragraphs("A b.\n\nC d.\n   \nE f.")) == 3


def test_empty_text():
    m = rl.compute_metrics("")
    assert m.word_count == 0 and m.grade_level == 0.0


def test_simple_text_is_low_grade():
    m = rl.compute_metrics("The cat sat on the mat. The dog ran to the park. We had fun.")
    assert m.grade_level < 3


def test_known_grade_level_text():
    # Classic FK reference sentence pair; published FK grade is ~ 8-9.
    text = (
        "The Australian platypus is seemingly a hybrid of a mammal and reptilian creature. "
        "It is one of the few mammals that lay eggs."
    )
    m = rl.compute_metrics(text)
    assert 6 <= m.grade_level <= 11


def test_complex_text_is_high_grade():
    text = (
        "The institutional administration subsequently determined that comprehensive "
        "interdisciplinary collaboration necessitates considerable organizational restructuring."
    )
    assert rl.compute_metrics(text).grade_level > 16


def test_grade_targets():
    assert rl.grade_target_for("students") == 8
    assert rl.grade_target_for("faculty") == 10
    assert rl.grade_target_for("staff") == 10
    assert rl.grade_target_for("unknown") == rl.DEFAULT_GRADE_TARGET
