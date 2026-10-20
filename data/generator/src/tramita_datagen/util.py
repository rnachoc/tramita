"""Small helpers shared by the generator modules."""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

CENT = Decimal("0.01")
TAX_RATE = Decimal(21)
TAX_FACTOR = Decimal("1.21")


def money(value: Decimal | float) -> Decimal:
    """Rounds to cents, half up, as invoices do."""
    return Decimal(str(value)).quantize(CENT, rounding=ROUND_HALF_UP)


def require[T](value: T | None, what: str) -> T:
    """Returns ``value`` or fails loudly; used for invariants of the generated data."""
    if value is None:
        raise ValueError(f"generator invariant broken: missing {what}")
    return value
