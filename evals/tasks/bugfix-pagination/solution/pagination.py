def paginate(items, page, per_page):
    """Devuelve los elementos de la página `page` (la primera página es la 1)."""
    if page < 1 or per_page < 1:
        raise ValueError("page y per_page deben ser >= 1")
    start = (page - 1) * per_page
    return items[start:start + per_page]


def total_pages(n_items, per_page):
    """Número de páginas necesarias para mostrar `n_items` elementos."""
    if per_page < 1:
        raise ValueError("per_page debe ser >= 1")
    return -(-n_items // per_page)
