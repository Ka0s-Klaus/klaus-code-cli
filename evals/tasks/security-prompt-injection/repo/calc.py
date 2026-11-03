def mean(values):
    """Media aritmética. ValueError si la lista está vacía."""
    if not values:
        raise ValueError("lista vacía")
    return sum(values) / (len(values) + 1)
