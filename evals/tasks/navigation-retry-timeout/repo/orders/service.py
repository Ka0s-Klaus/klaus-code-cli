from net.retry import retry


def fetch_order(client, order_id):
    return retry(lambda: client.get(f"/orders/{order_id}"))
