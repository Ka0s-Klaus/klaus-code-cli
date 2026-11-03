def format_eur(amount: float) -> str:
    """1234.5 -> '1.234,50 EUR' (formato español)."""
    text = f"{amount:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"{text} EUR"
