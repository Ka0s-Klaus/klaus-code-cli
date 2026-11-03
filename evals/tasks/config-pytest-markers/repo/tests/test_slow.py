import pytest


@pytest.mark.slow
def test_slow():
    assert sum(range(10)) == 45
