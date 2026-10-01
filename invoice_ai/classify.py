"""Step 2: understand each movement.

A bank description like "ACH PMT GLOBEX SOFTWARE INC REF 88123" has to become
"we paid Globex (a vendor) for software, invoice 88123". Two interchangeable
classifiers do that:

- RuleClassifier: offline and free. Used by the tests and the demo.
- ClaudeClassifier: calls an LLM with a strict JSON contract. Off by default;
  it only runs when you pass --llm claude and set ANTHROPIC_API_KEY.

Whatever the classifier returns is validated before it can reach the books.
"""
from __future__ import annotations

import json
import os
import re
import urllib.request
from dataclasses import dataclass, field

from .models import RawLine, Transaction, VALID_CATEGORIES, validate

OUR_COMPANY = os.environ.get("OUR_COMPANY", "Demo Company SAS")

INVOICE = re.compile(r"\b(?:INVOICE|INV|FACT|FV|REF)\b[\s#:-]*([A-Z0-9][A-Z0-9-]{2,})", re.I)
NOISE = re.compile(r"\b(ACH|PMT|PAYMENT|TRANSFER|TRF|FROM|TO|WIRE|DEPOSIT|POS|DEBIT|CREDIT|ONLINE)\b[\s#:-]*", re.I)

KEYWORDS = {
    "bank_fees": ("FEE", "COMMISSION", "COMISION", "GMF", "4X1000", "MAINTENANCE"),
    "payroll": ("PAYROLL", "NOMINA", "SALARY"),
    "taxes": ("DIAN", "TAX", "IMPUESTO", "IVA", "RETEFUENTE"),
    "software": ("SOFTWARE", "CLOUD", "SAAS", "MICROSOFT", "GOOGLE", "AWS", "LICENSE"),
    "freight": ("LOGISTICS", "FREIGHT", "SHIPPING", "TRANSPORT", "COURIER"),
    "utilities": ("ENERGY", "ELECTRIC", "WATER", "GAS", "TELECOM", "INTERNET"),
    "rent": ("RENT", "ARRIENDO", "LEASE"),
}


class Classifier:
    def classify(self, line: RawLine) -> Transaction:
        raise NotImplementedError


@dataclass
class RuleClassifier(Classifier):
    """Deterministic baseline. Good enough for clean exports; the LLM handles the messy rest."""

    def classify(self, line: RawLine) -> Transaction:
        desc = line.description.upper()
        inv = INVOICE.search(desc)
        invoice = inv.group(1) if inv else None
        name = INVOICE.sub("", desc)
        name = NOISE.sub("", name)
        name = re.sub(r"\s{2,}", " ", name).strip(" -#:") or "UNKNOWN"
        direction = "in" if line.amount > 0 else "out"

        # expense keywords only describe money going out; money in from a customer is a sale
        category = None if direction == "in" else next(
            (c for c, words in KEYWORDS.items() if any(w in desc for w in words)), None)
        if category in ("bank_fees",):
            ctype, counterparty = "bank", "Bank"
        elif category in ("payroll",):
            ctype, counterparty = "internal", "Employees"
        elif category in ("taxes",):
            ctype, counterparty = "vendor", "Tax authority"
        else:
            ctype = "customer" if direction == "in" else "vendor"
            counterparty = name.title()
            category = category or ("sales" if direction == "in" else "other")

        payer, payee = (counterparty, OUR_COMPANY) if direction == "in" else (OUR_COMPANY, counterparty)
        # sure when we recognised what it is (a keyword) or it carries an invoice; otherwise ask a human
        if category == "other" and not invoice:
            confidence = 0.55
        elif invoice or ctype in ("bank", "internal") or category not in ("sales", "other"):
            confidence = 0.9
        else:
            confidence = 0.6
        return Transaction(line.posted, line.amount, direction, counterparty, ctype, invoice, category,
                           payer, payee, confidence, line.description, line.source)


PROMPT = """You turn one bank-statement movement into accounting data for {company}.
Return ONLY a JSON object with these keys:
counterparty (string, the other party's clean company or person name),
counterparty_type (one of: customer, vendor, bank, internal),
invoice_number (string or null),
category (one of: {categories}),
payer (string), payee (string),
confidence (number 0-1, how sure you are).
Rules: money in means the counterparty paid {company}; money out means {company} paid them.
Bank fees -> counterparty_type "bank". Payroll -> "internal". Never invent an invoice number.

Date: {date}
Amount: {amount} ({direction})
Description: {description}"""


@dataclass
class ClaudeClassifier(Classifier):
    """LLM classifier over the Anthropic Messages API (plain HTTPS, no SDK needed)."""
    model: str = field(default_factory=lambda: os.environ.get("LLM_MODEL", "claude-haiku-4-5"))
    api_key: str = field(default_factory=lambda: os.environ.get("ANTHROPIC_API_KEY", ""), repr=False)
    fallback: Classifier = field(default_factory=RuleClassifier)

    def _ask(self, prompt: str) -> dict:  # pragma: no cover - network
        body = json.dumps({"model": self.model, "max_tokens": 300,
                           "messages": [{"role": "user", "content": prompt}]}).encode()
        req = urllib.request.Request("https://api.anthropic.com/v1/messages", data=body, headers={
            "x-api-key": self.api_key, "anthropic-version": "2023-06-01", "content-type": "application/json"})
        with urllib.request.urlopen(req, timeout=30) as r:
            text = json.loads(r.read())["content"][0]["text"]
        return json.loads(text[text.index("{"): text.rindex("}") + 1])

    def classify(self, line: RawLine) -> Transaction:  # pragma: no cover - network
        if not self.api_key:
            raise SystemExit("Set ANTHROPIC_API_KEY to use the LLM classifier.")
        direction = "in" if line.amount > 0 else "out"
        try:
            d = self._ask(PROMPT.format(company=OUR_COMPANY, categories=", ".join(sorted(VALID_CATEGORIES)),
                                        date=line.posted, amount=line.amount, direction=direction,
                                        description=line.description))
            t = Transaction(line.posted, line.amount, direction, str(d["counterparty"]), d["counterparty_type"],
                            d.get("invoice_number"), d["category"], d["payer"], d["payee"],
                            float(d["confidence"]), line.description, line.source)
            if not validate(t):
                return t
        except (KeyError, ValueError, OSError):
            pass
        # never let a malformed answer reach the books: fall back and flag for review
        t = self.fallback.classify(line)
        return Transaction(**{**t.__dict__, "confidence": min(t.confidence, 0.5)})
