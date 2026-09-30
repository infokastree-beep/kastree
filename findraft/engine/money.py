"""Money handling. Decimal(15,2) everywhere, 0.01 tolerance.
v5.1: D() REJECTS floats outright — float imprecision must be fixed upstream
(at parse time), never silently carried into money values. (Review finding.)"""
from decimal import Decimal, ROUND_HALF_UP

CENT = Decimal("0.01")
ZERO = Decimal("0.00")
MAX_ABS = Decimal("1e13")  # NUMERIC(15,2) => 13 integer digits

def D(x) -> Decimal:
    if isinstance(x, Decimal): return x
    if isinstance(x, float):
        raise TypeError("float is not acceptable in money handling — pass str or Decimal (upstream float imprecision must not reach money code)")
    if isinstance(x, bool):
        raise TypeError("bool is not a money value")
    d = Decimal(str(x))
    if not d.is_finite():
        raise ValueError(f"non-finite money value: {x!r}")
    if abs(d) >= MAX_ABS:
        raise ValueError(f"money value exceeds NUMERIC(15,2): {x!r}")
    return d

def money(x) -> Decimal:
    return D(x).quantize(CENT, rounding=ROUND_HALF_UP)

def close(a, b, tol=CENT) -> bool:
    return abs(D(a) - D(b)) <= tol
