import pytest

from inventory import Inventory


@pytest.fixture
def inv():
    i = Inventory()
    i.add("A", 5)
    return i


def test_add(inv):
    assert inv.quantity("A") == 5


def test_remove_partial(inv):
    inv.remove("A", 2)
    assert inv.quantity("A") == 3


def test_remove_all(inv):
    inv.remove("A", 5)
    assert inv.quantity("A") == 0


def test_remove_insufficient(inv):
    with pytest.raises(ValueError):
        inv.remove("A", 6)
    assert inv.quantity("A") == 5


@pytest.mark.parametrize("qty", [0, -1])
def test_remove_non_positive(inv, qty):
    with pytest.raises(ValueError):
        inv.remove("A", qty)


def test_remove_unknown_sku(inv):
    with pytest.raises(ValueError):
        inv.remove("B", 1)
