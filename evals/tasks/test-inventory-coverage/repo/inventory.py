class Inventory:
    def __init__(self):
        self._stock = {}

    def add(self, sku, qty):
        if qty <= 0:
            raise ValueError("qty debe ser > 0")
        self._stock[sku] = self._stock.get(sku, 0) + qty

    def remove(self, sku, qty):
        if qty <= 0:
            raise ValueError("qty debe ser > 0")
        current = self._stock.get(sku, 0)
        if qty > current:
            raise ValueError("stock insuficiente")
        if qty == current:
            del self._stock[sku]
        else:
            self._stock[sku] = current - qty

    def quantity(self, sku):
        return self._stock.get(sku, 0)
