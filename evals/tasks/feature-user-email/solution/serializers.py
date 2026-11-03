from models import User


def to_dict(user: User) -> dict:
    return {"name": user.name, "age": user.age, "email": user.email}


def from_dict(data: dict) -> User:
    user = User(name=data["name"], age=int(data["age"]), email=data["email"])
    user.validate()
    return user
