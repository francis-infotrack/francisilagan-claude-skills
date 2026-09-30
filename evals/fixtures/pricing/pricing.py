"""Order pricing for the shop. All money is integer cents."""


def line_total(unit_price_cents, quantity):
    """Price of `quantity` units at `unit_price_cents` each."""
    if quantity < 0:
        raise ValueError("quantity must be non-negative")
    return unit_price_cents * quantity


def apply_discount(total_cents, percent):
    """Reduce `total_cents` by `percent` (0-100), rounding half up to the cent."""
    if not 0 <= percent <= 100:
        raise ValueError("percent must be between 0 and 100")
    return total_cents - (total_cents * percent + 50) // 100
