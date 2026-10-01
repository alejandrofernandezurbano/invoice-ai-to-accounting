from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date
from decimal import Decimal


@dataclass(frozen=True)
class RawLine:
    """One movement exactly as it appears on the bank statement."""
    posted: date
    description: str
    amount: Decimal          # positive = money in, negative = money out
    source: str              # file it came from, for traceability


@dataclass(frozen=True)
class Transaction:
    """The structured result the accounting system needs."""
    posted: date
    amount: Decimal
    direction: str            # "in" | "out"
    counterparty: str         # who we paid or who paid us
    counterparty_type: str    # "customer" | "vendor" | "bank" | "internal"
    invoice_number: str | None
    category: str             # e.g. "sales", "freight", "software", "bank_fees", "payroll"
    payer: str
    payee: str
    confidence: float         # 0-1, from the classifier
    description: str
    source: str

    def to_dict(self) -> dict:
        d = asdict(self)
        d["posted"] = self.posted.isoformat()
        d["amount"] = str(self.amount)
        return d


VALID_TYPES = {"customer", "vendor", "bank", "internal"}
VALID_CATEGORIES = {"sales", "freight", "software", "utilities", "rent", "bank_fees", "payroll", "taxes", "other"}


def validate(t: Transaction) -> list[str]:
    """Checks a classifier must pass before anything reaches the books."""
    problems = []
    if t.direction not in ("in", "out"):
        problems.append("direction must be 'in' or 'out'")
    if (t.direction == "in") != (t.amount > 0):
        problems.append("direction does not match the sign of the amount")
    if t.counterparty_type not in VALID_TYPES:
        problems.append(f"unknown counterparty_type {t.counterparty_type!r}")
    if t.category not in VALID_CATEGORIES:
        problems.append(f"unknown category {t.category!r}")
    if not t.counterparty.strip():
        problems.append("counterparty is empty")
    if not 0 <= t.confidence <= 1:
        problems.append("confidence must be between 0 and 1")
    return problems
