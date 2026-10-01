# Invoice & bank statement AI → accounting

> **ES:** Demo reescrita desde cero (datos 100 % inventados) del flujo que construí para una firma de
> auditoría internacional: extractos bancarios en PDF → OCR → IA que entiende cada movimiento →
> JSON validado → contabilidad (QuickBooks). En el proyecto real procesó más de 40.000
> transacciones y eliminó de 3 a 5 días de digitación manual cada mes.

Accounting teams still type bank movements into their books by hand. This pipeline reads the
statement, works out **who paid whom, for what and against which invoice**, validates the
result and posts it — sending only the doubtful lines to a person.

```
statement.pdf ──► text layer / OCR ──► movements ──► classifier (rules or LLM) ──► validation
                                                                                   │
                                     review queue ◄── low confidence / invalid ◄──┤
                                                                                   ▼
                                                      ledger (idempotent) ──► QuickBooks payload
```

## The real project behind it

I built the production version for an international financial-audit firm (Power Automate + OCR
+ OpenAI + QuickBooks API): **40,000+ transactions processed and 3–5 days of manual data entry
removed every month.** That code belongs to the client; this repository is an independent
re-implementation of the same idea in plain Python, with fictitious data, so it can be read and run.

## What it shows

- **Extraction:** text layer of digital PDFs with PyMuPDF; OCR with Tesseract for scanned pages
  (optional); plain exports read directly. Handles signed amounts and CR/DR columns.
- **Understanding each movement:** counterparty, customer/vendor/bank/internal, invoice number,
  category, payer and payee.
  - `RuleClassifier`: offline and free, used by the tests and the demo.
  - `ClaudeClassifier`: LLM with a strict JSON contract over plain HTTPS. **Off by default**:
    it only runs with `--llm claude` and your own `ANTHROPIC_API_KEY`.
- **Guardrails:** every result is validated (sign vs. direction, allowed categories,
  confidence range). An LLM answer that breaks the contract never reaches the books: it falls
  back to the rules and goes to review.
- **Human in the loop:** below a confidence threshold, the line goes to a review queue.
- **Idempotent posting:** running the same statement twice (even as PDF and as TXT) never
  duplicates entries.
- **QuickBooks Online payloads:** `Deposit` for money in, `Purchase` for money out, mapped to
  your chart of accounts. The demo prints them (dry run); going live needs an Intuit OAuth 2.0
  app, the company id and your account ids — check the fields against Intuit's docs first.

## Run it

```bash
pip install -r requirements.txt            # only needed for PDFs
python -m unittest discover -s tests -t .  # 11 tests, offline
python samples/make_pdf.py                 # builds samples/statement_2026-09.pdf
python -m invoice_ai samples/statement_2026-09.pdf --show-payloads
```

```
Posted: 11   Already in ledger: 0   To review: 1
  + 2026-09-01      1250.00 sales      Acme Logistics Sas (inv 1043)
  + 2026-09-02      -320.00 software   Globex Software Inc (inv 88123)
  + 2026-09-03       -12.50 bank_fees  Bank (inv -)
  ...
  ? 2026-09-18       -18.90 POS DEBIT CAFE CENTRAL  <- low confidence (0.55)
```

With an LLM (costs tokens on your account):

```bash
ANTHROPIC_API_KEY=... python -m invoice_ai samples/statement_2026-09.pdf --llm claude
```

## Layout

```
invoice_ai/extract.py    PDF / OCR / text -> movements
invoice_ai/classify.py   rules or LLM -> structured transaction
invoice_ai/models.py     data model + validation
invoice_ai/ledger.py     idempotent ledger + QuickBooks payloads
invoice_ai/pipeline.py   CLI and review queue
samples/                 fictitious statement
```

## Author

Alejandro Fernández Urbano — Power Platform & AI automation.
Available for this kind of project as **Calidá S.A.S.** (Colombia).
[LinkedIn](https://www.linkedin.com/in/alejandro-fernandez-urbano) · alejandrofernandezurbano@gmail.com
