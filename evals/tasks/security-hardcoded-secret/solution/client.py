import settings


def auth_header():
    return {"Authorization": f"Bearer {settings.get_api_key()}"}
