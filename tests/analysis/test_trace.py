import pytest

from pyreview.analysis.application.trace import thoughts


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Обычный текст.", ["Обычный текст."]),
        (
            "think: первая мысль. think: вторая.\n\nthink: третья.",
            ["первая мысль.", "вторая.", "третья."],
        ),
        ("think: суть.\nsummary: итог\nverdict: issues", ["суть."]),
        ("Итоговое ревью:\nreasoning: всё", []),
        ("", []),
    ],
)
def test_thoughts_are_split_and_tail_is_dropped(text: str, expected: list[str]) -> None:
    assert thoughts(text) == expected
