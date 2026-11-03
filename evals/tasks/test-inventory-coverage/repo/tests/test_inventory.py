from inventory import Inventory


def test_add():
    inv = Inventory()
    inv.add("A", 3)
    assert inv.quantity("A") == 3
