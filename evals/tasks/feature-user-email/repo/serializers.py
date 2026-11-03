from models import User


def to_dict(user: User) -> dict:
    return {"name": user.name, "age": user.age}


def from_dict(data: dict) -> User:
    user = User(name=data["name"], age=int(data["age"]))
    user.validate()
    return user
