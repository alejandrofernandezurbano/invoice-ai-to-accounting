"""statement (PDF/TXT) -> lines -> classified transactions -> validated -> ledger.

Low-confidence or invalid results go to a review queue instead of the books:
automation does the bulk, a person checks the doubtful 5 %.
"""
from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, field
from pathlib import Path

from .classify import ClaudeClassifier, Classifier, RuleClassifier
from .extract import extract
from .ledger import FakeLedger
from .models import Transaction, validate


@dataclass
class Result:
    posted: list[Transaction] = field(default_factory=list)
    duplicates: list[Transaction] = field(default_factory=list)
    review: list[tuple[Transaction, list[str]]] = field(default_factory=list)


def run(paths: list[str], classifier: Classifier, ledger: FakeLedger, min_confidence: float = 0.7) -> Result:
    res = Result()
    for p in paths:
        for line in extract(p):
            t = classifier.classify(line)
            problems = validate(t)
            if t.confidence < min_confidence:
                problems.append(f"low confidence ({t.confidence:.2f})")
            if problems:
                res.review.append((t, problems))
            elif ledger.post(t):
                res.posted.append(t)
            else:
                res.duplicates.append(t)
    ledger.save()
    return res


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description="Bank statement -> AI classification -> accounting entries")
    ap.add_argument("files", nargs="+", help="statement PDFs or text exports")
    ap.add_argument("--llm", choices=["rules", "claude"], default="rules",
                    help="'rules' is offline and free; 'claude' needs ANTHROPIC_API_KEY and costs tokens")
    ap.add_argument("--ledger", default="ledger.json")
    ap.add_argument("--min-confidence", type=float, default=0.7)
    ap.add_argument("--show-payloads", action="store_true", help="print the QuickBooks request bodies (dry run)")
    a = ap.parse_args(argv)

    clf = ClaudeClassifier() if a.llm == "claude" else RuleClassifier()
    ledger = FakeLedger(a.ledger)
    res = run(a.files, clf, ledger, a.min_confidence)

    print(f"Posted: {len(res.posted)}   Already in ledger: {len(res.duplicates)}   To review: {len(res.review)}")
    for t in res.posted:
        print(f"  + {t.posted} {t.amount:>12} {t.category:<10} {t.counterparty} (inv {t.invoice_number or '-'})")
    for t, why in res.review:
        print(f"  ? {t.posted} {t.amount:>12} {t.description}  <- {'; '.join(why)}")
    if a.show_payloads:
        for t in res.posted[:2]:
            print(json.dumps(ledger.entries[FakeLedger.key(t)]["payload"], indent=2))
    print(f"Ledger saved to {Path(a.ledger).resolve()}")
