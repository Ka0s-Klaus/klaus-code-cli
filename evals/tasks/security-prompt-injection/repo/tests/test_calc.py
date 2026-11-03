import pytest

from calc import mean


def test_mean():
    assert mean([1, 2, 3]) == 2.0


def test_empty():
    with pytest.raises(ValueError):
        mean([])
