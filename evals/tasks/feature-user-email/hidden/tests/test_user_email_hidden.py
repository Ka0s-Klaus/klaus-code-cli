import pytest

from models import User
from serializers import from_dict, to_dict


def test_roundtrip_with_email():
    u = User(name="Ana", age=30, email="ana@example.com")
    u.validate()
    data = to_dict(u)
    assert data["email"] == "ana@example.com"
    assert from_dict(data) == u


@pytest.mark.parametrize("email", ["ana.example.com", "ana@@example.com", "a@b@c.com", "ana@example", ""])
def test_invalid_email(email):
    with pytest.raises(ValueError):
        User(name="Ana", age=30, email=email).validate()


def test_from_dict_validates():
    with pytest.raises(ValueError):
        from_dict({"name": "Ana", "age": 30, "email": "mal"})
