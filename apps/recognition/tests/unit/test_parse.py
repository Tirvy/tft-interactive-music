from __future__ import annotations

from tft_recognition.ocr.base import OcrLine
from tft_recognition.parse import parse_ocr_lines


def line(
    text: str,
    left: float,
    top: float,
    width: float = 120,
    height: float = 20,
    confidence: float = 0.95,
) -> OcrLine:
    return OcrLine(
        text=text,
        confidence=confidence,
        box=(left, top, left + width, top + height),
    )


def test_merged_count_label_and_breakpoints() -> None:
    parsed = parse_ocr_lines(
        [line("4 Инферно 2 > 3 > 5 > 7", left=40, top=10, width=260)]
    )
    assert len(parsed.rows) == 1
    row = parsed.rows[0]
    assert row.count_text == "4"
    assert row.label_text == "Инферно"
    assert row.breakpoint_text == "2 > 3 > 5 > 7"


def test_split_count_and_label_boxes() -> None:
    parsed = parse_ocr_lines(
        [
            line("4", left=10, top=10, width=20),
            line("Инферно", left=45, top=10, width=150),
        ]
    )
    assert len(parsed.rows) == 1
    assert parsed.rows[0].count_text == "4"
    assert parsed.rows[0].label_text == "Инферно"


def test_breakpoint_subline_is_not_used_as_count() -> None:
    parsed = parse_ocr_lines(
        [
            line("Инферно", left=45, top=10, width=150),
            line("2 > 3 > 5 > 7", left=45, top=33, width=140, height=14),
        ]
    )
    assert len(parsed.rows) == 1
    row = parsed.rows[0]
    assert row.count_text is None
    assert row.label_text == "Инферно"
    assert "missing_count" in row.warnings
    assert row.breakpoint_text == "2 > 3 > 5 > 7"


def test_two_digit_count() -> None:
    parsed = parse_ocr_lines(
        [
            line("10", left=10, top=10, width=28),
            line("Инферно", left=45, top=10, width=150),
        ]
    )
    assert parsed.rows[0].count_text == "10"


def test_missing_count_is_preserved() -> None:
    parsed = parse_ocr_lines([line("Фея", left=45, top=10, width=80)])
    assert len(parsed.rows) == 1
    assert parsed.rows[0].label_text == "Фея"
    assert parsed.rows[0].count_text is None


def test_ui_noise_is_ignored() -> None:
    parsed = parse_ocr_lines([line("5+", left=100, top=200, width=40)])
    assert parsed.rows == ()
    assert parsed.ignored_lines[0].reason == "non_trait_noise"


def test_multiple_rows_are_kept_separate() -> None:
    parsed = parse_ocr_lines(
        [
            line("2", left=10, top=10, width=20),
            line("Инферно", left=45, top=10, width=150),
            line("1", left=10, top=60, width=20),
            line("Фея", left=45, top=60, width=80),
        ]
    )
    assert len(parsed.rows) == 2
    assert [(row.count_text, row.label_text) for row in parsed.rows] == [
        ("2", "Инферно"),
        ("1", "Фея"),
    ]


def test_split_label_parts_are_joined() -> None:
    parsed = parse_ocr_lines(
        [
            line("1", left=10, top=10, width=20),
            line("Коварная", left=45, top=10, width=100),
            line("флора", left=150, top=10, width=70),
        ]
    )
    assert len(parsed.rows) == 1
    assert parsed.rows[0].label_text == "Коварная флора"


def test_breakpoint_only_line_is_not_a_row() -> None:
    parsed = parse_ocr_lines([line("1/2", left=45, top=10, width=40, height=14)])
    assert parsed.rows == ()
    assert parsed.ignored_lines[0].reason == "unassigned_breakpoint"


def test_leading_count_without_space() -> None:
    parsed = parse_ocr_lines([line("1Древний лес", left=10, top=10, width=180)])
    assert parsed.rows[0].count_text == "1"
    assert parsed.rows[0].label_text == "Древний лес"


def test_trailing_slash_breakpoints_are_stripped() -> None:
    parsed = parse_ocr_lines([line("Адаптация 1/2", left=45, top=10, width=150)])
    assert parsed.rows[0].label_text == "Адаптация"
    assert parsed.rows[0].breakpoint_text == "1/2"
    assert parsed.rows[0].count_text is None


def test_nearest_count_wins_over_icon_noise() -> None:
    parsed = parse_ocr_lines(
        [
            line("4", left=5, top=10, width=20),
            line("2", left=30, top=10, width=20),
            line("Заклинатель", left=55, top=10, width=160),
        ]
    )
    assert parsed.rows[0].count_text == "2"
    assert any(
        ignored.reason == "unassigned_count" and ignored.text == "4"
        for ignored in parsed.ignored_lines
    )


def test_compact_breakpoint_run_is_attached_to_its_row() -> None:
    parsed = parse_ocr_lines(
        [
            line("2", left=10, top=10, width=20),
            line("Инферно", left=45, top=10, width=150),
            line("246", left=45, top=33, width=90, height=14),
        ]
    )
    assert parsed.rows[0].count_text == "2"
    assert parsed.rows[0].label_text == "Инферно"
    assert parsed.rows[0].breakpoint_text == "246"


def test_numeric_text_to_the_right_is_not_a_count() -> None:
    parsed = parse_ocr_lines(
        [
            line("Инферно", left=45, top=10, width=120),
            line("46", left=150, top=10, width=50),
        ]
    )
    assert parsed.rows[0].count_text is None
    assert parsed.rows[0].breakpoint_text is None
    assert any(ignored.reason == "unassigned_count" for ignored in parsed.ignored_lines)
