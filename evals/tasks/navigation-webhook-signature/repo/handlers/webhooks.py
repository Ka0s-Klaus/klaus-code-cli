import json

from security import hmac_utils


def handle_webhook(headers, body: bytes, secret: bytes):
    if not hmac_utils.verify_signature(body, headers.get("X-Signature", ""), secret):
        return 401, "firma inválida"
    event = json.loads(body)
    return 200, event["type"]
