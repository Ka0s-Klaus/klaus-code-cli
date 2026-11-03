from handlers.webhooks import handle_webhook

ROUTES = {"/webhooks/payments": handle_webhook}
