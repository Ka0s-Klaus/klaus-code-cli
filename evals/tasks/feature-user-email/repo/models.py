from dataclasses import dataclass


@dataclass
class User:
    name: str
    age: int

    def validate(self):
        if not self.name.strip():
            raise ValueError("name vacío")
        if self.age < 0:
            raise ValueError("age negativa")
