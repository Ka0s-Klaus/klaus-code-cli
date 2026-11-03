import pytest

from money import format_eur
from report import invoice_line, total_line


@pytest.mark.parametrize(
    ("amount", "text"),
    [(1234.5, "1.234,50 EUR"), (0, "0,00 EUR"), (1000000, "1.000.000,00 EUR"), (3.456, "3,46 EUR")],
)
def test_format_eur(amount, text):
    assert format_eur(amount) == text


def test_report_unchanged():
    assert invoice_line("Licencia", 1234.5) == "Licencia: 1.234,50 EUR"
    assert total_line(1000000) == "TOTAL: 1.000.000,00 EUR"
