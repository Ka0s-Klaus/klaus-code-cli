import pytest

from models import User
from serializers import from_dict, to_dict


def test_roundtrip():
    u = User(name="Ana", age=30, email="ana@example.com")
    assert from_dict(to_dict(u)) == u


def test_negative_age():
    with pytest.raises(ValueError):
        User(name="Ana", age=-1, email="ana@example.com").validate()
