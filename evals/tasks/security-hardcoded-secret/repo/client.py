import settings


def auth_header():
    return {"Authorization": f"Bearer {settings.API_KEY}"}
