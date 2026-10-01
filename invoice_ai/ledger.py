"""Step 3: post to the accounting system.

- FakeLedger: a local JSON file. Lets you run the whole pipeline with no accounts.
- quickbooks_payload(): builds the request body for the QuickBooks Online
  Accounting API (Deposit for money in, Purchase for money out). The demo only
  prints it (dry run). Sending it needs an OAuth 2.0 app, the realm id and your
  own chart-of-accounts ids; check the entity fields against Intuit's docs
  before going live.
"""
from __future__ import annotations

import json
from pathlib import Path

from .models import Transaction

# Map our categories to the ids of the accounts in YOUR chart of accounts.
DEFAULT_ACCOUNTS = {
    "sales": "1", "freight": "2", "software": "3", "utilities": "4", "rent": "5",
    "bank_fees": "6", "payroll": "7", "taxes": "8", "other": "9", "bank": "35",
}


def quickbooks_payload(t: Transaction, accounts: dict[str, str] = DEFAULT_ACCOUNTS) -> tuple[str, dict]:
    memo = f"{t.description} | inv {t.invoice_number or '-'} | src {t.source}"
    amount = float(abs(t.amount))
    if t.direction == "in":
        return "deposit", {
            "DepositToAccountRef": {"value": accounts["bank"]},
            "TxnDate": t.posted.isoformat(),
            "PrivateNote": memo,
            "Line": [{
                "Amount": amount,
                "DetailType": "DepositLineDetail",
                "DepositLineDetail": {"AccountRef": {"value": accounts[t.category]}},
                "Description": t.counterparty,
            }],
        }
    return "purchase", {
        "PaymentType": "Cash",
        "AccountRef": {"value": accounts["bank"]},
        "TxnDate": t.posted.isoformat(),
        "PrivateNote": memo,
        "Line": [{
            "Amount": amount,
            "DetailType": "AccountBasedExpenseLineDetail",
            "AccountBasedExpenseLineDetail": {"AccountRef": {"value": accounts[t.category]}},
            "Description": t.counterparty,
        }],
    }


class FakeLedger:
    """Idempotent local ledger: posting the same statement twice never duplicates entries."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.entries: dict[str, dict] = json.loads(self.path.read_text()) if self.path.exists() else {}

    @staticmethod
    def key(t: Transaction) -> str:
        return f"{t.posted.isoformat()}|{t.amount}|{t.description}"

    def post(self, t: Transaction) -> bool:
        k = self.key(t)
        if k in self.entries:
            return False
        kind, payload = quickbooks_payload(t)
        self.entries[k] = {"kind": kind, "transaction": t.to_dict(), "payload": payload}
        return True

    def save(self) -> None:
        self.path.write_text(json.dumps(self.entries, indent=2, ensure_ascii=False))
