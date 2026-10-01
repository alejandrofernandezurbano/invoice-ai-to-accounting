import tempfile
import unittest
from datetime import date
from decimal import Decimal
from pathlib import Path

from invoice_ai.classify import RuleClassifier
from invoice_ai.extract import extract, parse_lines
from invoice_ai.ledger import FakeLedger, quickbooks_payload
from invoice_ai.models import RawLine, Transaction, validate
from invoice_ai.pipeline import run

SAMPLE = Path(__file__).parent.parent / "samples" / "statement_2026-09.txt"


class ExtractTest(unittest.TestCase):
    def test_reads_every_movement_and_sign(self):
        lines = extract(SAMPLE)
        self.assertEqual(len(lines), 12)
        self.assertEqual(lines[0].amount, Decimal("1250.00"))
        self.assertEqual(lines[1].amount, Decimal("-320.00"))

    def test_ignores_headers_and_junk(self):
        self.assertEqual(parse_lines("DATE DESCRIPTION AMOUNT\nhello\n", "x"), [])


class ClassifyTest(unittest.TestCase):
    def setUp(self):
        self.c = RuleClassifier()

    def cls(self, desc, amount):
        return self.c.classify(RawLine(date(2026, 9, 1), desc, Decimal(amount), "t"))

    def test_customer_payment(self):
        t = self.cls("TRANSFER FROM ACME LOGISTICS SAS INV-1043", "1250.00")
        self.assertEqual((t.direction, t.counterparty_type, t.invoice_number), ("in", "customer", "1043"))
        self.assertEqual(t.counterparty, "Acme Logistics Sas")
        self.assertEqual(t.payee, "Demo Company SAS")

    def test_vendor_software(self):
        t = self.cls("ACH PMT GLOBEX SOFTWARE INC REF 88123", "-320.00")
        self.assertEqual((t.counterparty_type, t.category, t.invoice_number), ("vendor", "software", "88123"))
        self.assertEqual(t.payer, "Demo Company SAS")

    def test_bank_fee_and_payroll(self):
        self.assertEqual(self.cls("MONTHLY MAINTENANCE FEE", "-12.50").counterparty_type, "bank")
        self.assertEqual(self.cls("PAYROLL SEPTEMBER", "-3900").category, "payroll")

    def test_money_in_is_a_sale_even_with_expense_words(self):
        t = self.cls("TRANSFER FROM ACME LOGISTICS SAS INV-1043", "1250.00")
        self.assertEqual(t.category, "sales")

    def test_invoice_word_is_not_taken_as_the_number(self):
        self.assertEqual(self.cls("DEPOSIT UMBRELLA HEALTH IPS INVOICE 1051", "2175").invoice_number, "1051")

    def test_unclear_movement_gets_low_confidence(self):
        self.assertLess(self.cls("POS DEBIT CAFE CENTRAL", "-18.90").confidence, 0.7)


class GuardsTest(unittest.TestCase):
    def test_validate_catches_inconsistent_llm_output(self):
        t = Transaction(date(2026, 9, 1), Decimal("-10"), "in", "", "friend", None, "magic", "a", "b", 1.5, "d", "s")
        self.assertGreaterEqual(len(validate(t)), 5)

    def test_quickbooks_payload_shape(self):
        t = RuleClassifier().classify(RawLine(date(2026, 9, 2), "ACH PMT GLOBEX SOFTWARE INC REF 88123",
                                              Decimal("-320.00"), "s"))
        kind, body = quickbooks_payload(t)
        self.assertEqual(kind, "purchase")
        self.assertEqual(body["Line"][0]["Amount"], 320.0)
        self.assertEqual(body["Line"][0]["DetailType"], "AccountBasedExpenseLineDetail")


class PipelineTest(unittest.TestCase):
    def test_end_to_end_is_idempotent(self):
        with tempfile.TemporaryDirectory() as d:
            ledger_path = Path(d) / "ledger.json"
            first = run([str(SAMPLE)], RuleClassifier(), FakeLedger(ledger_path))
            self.assertGreaterEqual(len(first.posted), 9)
            self.assertTrue(first.review)  # the café purchase is sent to a human
            second = run([str(SAMPLE)], RuleClassifier(), FakeLedger(ledger_path))
            self.assertEqual(second.posted, [])
            self.assertEqual(len(second.duplicates), len(first.posted))


if __name__ == "__main__":
    unittest.main()
