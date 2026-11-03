def invoice_line(item, amount):
    return f"{item}: {amount:,.2f} EUR".replace(",", "X").replace(".", ",").replace("X", ".")


def total_line(total):
    return f"TOTAL: {total:,.2f} EUR".replace(",", "X").replace(".", ",").replace("X", ".")
