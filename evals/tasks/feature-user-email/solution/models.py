from dataclasses import dataclass


@dataclass
class User:
    name: str
    age: int
    email: str

    def validate(self):
        if not self.name.strip():
            raise ValueError("name vacío")
        if self.age < 0:
            raise ValueError("age negativa")
        if self.email.count("@") != 1 or "." not in self.email.split("@")[1]:
            raise ValueError("email inválido")
