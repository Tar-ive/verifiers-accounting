import json

from us_sut_reconciliation_v1.ledger import FAULT_CODES, generate, reconcile
from us_sut_reconciliation_v1.taskset import fault_pairs, parse_answer, to_cents


def test_deterministic():
    assert reconcile(generate(7)) == reconcile(generate(7))


def test_every_fault_code_occurs():
    seen = {code for s in range(50) for codes in reconcile(generate(s))["faults"].values() for code in codes}
    assert seen == set(FAULT_CODES)


def test_return_identities():
    for s in range(50):
        e = reconcile(generate(s))
        assert to_cents(e["gross_sales"]) - to_cents(e["exempt_sales"]) == to_cents(e["taxable_sales"])
        assert to_cents(e["sales_tax_due"]) + to_cents(e["use_tax_due"]) == to_cents(e["net_remittance"])


def test_parse_oracle_roundtrip():
    e = reconcile(generate(3))
    text = f"work...\n<answer>\n```json\n{json.dumps(e)}\n```\n</answer>"
    parsed = parse_answer(text)
    assert fault_pairs(parsed["faults"]) == fault_pairs(e["faults"])
    assert to_cents(parsed["net_remittance"]) == to_cents(e["net_remittance"])
    assert parse_answer("no answer") is None
