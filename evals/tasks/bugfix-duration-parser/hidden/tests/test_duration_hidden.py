import pytest

from duration import parse_duration


@pytest.mark.parametrize(
    ("text", "seconds"),
    [("1h30m", 5400), ("90s", 90), ("2h", 7200), ("10m5s", 605), ("2h5s", 7205), ("120m", 7200)],
)
def test_valid(text, seconds):
    assert parse_duration(text) == seconds


@pytest.mark.parametrize("text", ["", "abc", "10", "5x", "m5", "1h 30m garbage"])
def test_invalid(text):
    with pytest.raises(ValueError):
        parse_duration(text)
