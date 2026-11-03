import os

API_URL = "https://payments.example.com/v1"


def get_api_key() -> str:
    key = os.environ.get("PAYMENTS_API_KEY")
    if not key:
        raise RuntimeError("Falta la variable de entorno PAYMENTS_API_KEY")
    return key
