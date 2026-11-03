import pytest

from pagination import paginate, total_pages


def test_pages():
    items = list(range(10))
    assert paginate(items, 1, 3) == [0, 1, 2]
    assert paginate(items, 2, 3) == [3, 4, 5]
    assert paginate(items, 4, 3) == [9]
    assert paginate(items, 5, 3) == []


@pytest.mark.parametrize(("n", "per", "expected"), [(10, 3, 4), (9, 3, 3), (0, 3, 0), (1, 5, 1)])
def test_total_pages(n, per, expected):
    assert total_pages(n, per) == expected


def test_invalid():
    with pytest.raises(ValueError):
        paginate([1], 0, 3)
