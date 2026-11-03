from report import invoice_line, total_line


def test_lines():
    assert invoice_line("Licencia", 1234.5) == "Licencia: 1.234,50 EUR"
    assert total_line(99) == "TOTAL: 99,00 EUR"
