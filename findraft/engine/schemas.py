"""Core data structures. Pure dataclasses — no DB, no HTTP. (Cursor rules §3)"""
from dataclasses import dataclass
from decimal import Decimal

@dataclass(frozen=True)
class TBLine:
    nominal_code: str
    account_name: str
    debit: Decimal
    credit: Decimal

    def __post_init__(self) -> None:
        for f in ("debit", "credit"):
            v = getattr(self, f)
            if not isinstance(v, Decimal) or not v.is_finite():
                raise TypeError(f"TBLine.{f} must be a finite Decimal, got {v!r}")
            if v < 0:
                raise ValueError(f"TBLine.{f} must be non-negative, got {v}")

    @property
    def balance(self) -> Decimal:  # debit-positive convention
        return self.debit - self.credit
