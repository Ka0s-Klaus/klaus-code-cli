from money import format_eur


def invoice_line(item, amount):
    return f"{item}: {format_eur(amount)}"


def total_line(total):
    return f"TOTAL: {format_eur(total)}"
