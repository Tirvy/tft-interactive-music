from __future__ import annotations

from tft_recognition.ocr.paddle import _bbox_from_box, _parse_paddle_result


def test_parse_v2_result() -> None:
    result = [
        [
            [
                [[10, 10], [90, 10], [90, 30], [10, 30]],
                ("Инферно", 0.97),
            ],
            [
                [[10, 40], [50, 40], [50, 60], [10, 60]],
                ("4", 0.93),
            ],
        ]
    ]
    lines = _parse_paddle_result(result)
    assert [line.text for line in lines] == ["Инферно", "4"]
    assert lines[0].box == (10.0, 10.0, 90.0, 30.0)
    assert lines[0].confidence == 0.97


def test_parse_v3_mapping_result() -> None:
    result = [
        {
            "rec_texts": ["4", "Инферно"],
            "rec_scores": [0.99, 0.95],
            "rec_boxes": [[0, 10, 20, 30], [30, 10, 130, 30]],
        }
    ]
    lines = _parse_paddle_result(result)
    assert [line.text for line in lines] == ["4", "Инферно"]
    assert lines[1].box == (30.0, 10.0, 130.0, 30.0)


def test_parse_nested_v3_result() -> None:
    result = [
        {
            "res": {
                "rec_texts": ["Фея"],
                "rec_scores": [0.91],
                "rec_polys": [
                    [[10, 20], [80, 20], [80, 40], [10, 40]]
                ],
            }
        }
    ]
    lines = _parse_paddle_result(result)
    assert len(lines) == 1
    assert lines[0].text == "Фея"
    assert lines[0].box == (10.0, 20.0, 80.0, 40.0)


def test_parse_object_with_json_attribute() -> None:
    class Result:
        json = {
            "rec_texts": ["Адаптация"],
            "rec_scores": [0.9],
            "rec_boxes": [[0, 0, 100, 20]],
        }

    lines = _parse_paddle_result([Result()])
    assert len(lines) == 1
    assert lines[0].text == "Адаптация"


def test_parse_empty_result() -> None:
    assert _parse_paddle_result(None) == []
    assert _parse_paddle_result([None]) == []


def test_bbox_from_eight_numbers() -> None:
    assert _bbox_from_box([10, 20, 90, 20, 90, 50, 10, 50]) == (
        10.0,
        20.0,
        90.0,
        50.0,
    )
