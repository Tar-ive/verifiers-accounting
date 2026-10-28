"""Synthetic quarterly sales & use tax ledgers with injected bookkeeping faults.

US analogue of `au-bas-reconciliation-v1`: the GST/BAS mechanics (G1, 1A, 1B,
ABN threshold, GST-free supplies) map onto a state Sales & Use Tax (SUT) return
(gross sales, sales tax due, vendor use tax, exemption-certificate threshold,
exempt sales). Everything here is pure and seeded, so a task's ground truth is
recomputed bit-for-bit from its seed.
"""

import random
from dataclasses import asdict, dataclass
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal

CENT = Decimal("0.01")

FAULT_CODES = (
    "tax_on_exempt_item",
    "tax_miscalculated",
    "duplicate_invoice",
    "outside_period",
    "missing_exemption_cert",
    "nexus_misallocation",
)

# Illustrative single-state rulebook. Rates are stylized, not current statutory
# rates; the prompt carries the full table so the task is closed-book safe.
STATE_NAME = "State of Lone Pine (illustrative)"
STATE_RATE = Decimal("0.0625")
LOCAL_RATES = {
    "78701": Decimal("0.0200"),
    "78130": Decimal("0.0150"),
    "77002": Decimal("0.0200"),
    "75201": Decimal("0.0175"),
    "79901": Decimal("0.0125"),
    "76102": Decimal("0.0100"),
    "78664": Decimal("0.0050"),
    "79401": Decimal("0.0000"),
}
CERT_THRESHOLD = Decimal("200.00")

EXEMPT_CATEGORIES = ("unprepared_grocery", "prescription_drug", "medical_device", "consulting_service")
TAXABLE_CATEGORIES = ("prepared_food", "apparel", "software_saas", "electronics", "furniture", "office_supplies")

QUARTERS = {1: (1, 3), 2: (4, 6), 3: (7, 9), 4: (10, 12)}


def money(x: Decimal) -> Decimal:
    return x.quantize(CENT, rounding=ROUND_HALF_UP)


def combined_rate(zip_code: str) -> Decimal:
    return STATE_RATE + LOCAL_RATES[zip_code]


def quarter_bounds(year: int, quarter: int) -> tuple[date, date]:
    first, last = QUARTERS[quarter]
    start = date(year, first, 1)
    end = (date(year + (last == 12), last % 12 + 1, 1)) - timedelta(days=1)
    return start, end


@dataclass
class Row:
    transaction_id: str
    invoice_number: str
    date: str
    type: str
    category: str
    gross_amount: str
    tax_collected_or_paid: str
    jurisdiction_zip: str
    tax_exempt_claimed: bool
    customer_or_vendor_cert_id: str


@dataclass
class Ledger:
    seed: int
    year: int
    quarter: int
    business_zip: str
    rows: list[Row]


def _cert_id(rng: random.Random) -> str:
    return f"RC-{rng.randint(10**7, 10**8 - 1)}"


def _gross(rng: random.Random, low: int, high: int) -> Decimal:
    return Decimal(rng.randint(low * 100, high * 100)) / 100


def _miscalc(rng: random.Random, gross: Decimal, dest: str, origin: str) -> Decimal:
    """A wrong tax figure that cannot be mistaken for a correct or origin-sourced one."""
    rate = combined_rate(dest)
    candidates = [
        money(gross * STATE_RATE),  # local/district rate omitted
        money(gross * rate / (1 + rate)),  # computed as an internal extraction
        money(gross * rate) + Decimal(rng.choice([-3, -1, 1, 2, 5])),  # keying error
    ]
    banned = {money(gross * rate), money(gross * combined_rate(origin)), Decimal("0.00")}
    for value in rng.sample(candidates, len(candidates)):
        if value not in banned and value > 0:
            return value
    return money(gross * rate) + Decimal("7.00")


def generate(seed: int, num_rows: int = 30, fault_rate: float = 0.25) -> Ledger:
    rng = random.Random(seed)
    year = rng.choice([2025, 2026])
    quarter = rng.randint(1, 4)
    start, end = quarter_bounds(year, quarter)
    zips = list(LOCAL_RATES)
    business_zip = rng.choice(zips)
    span = (end - start).days

    rows: list[Row] = []
    inv_no = rng.randint(1000, 8000)
    num_dups = 0
    for i in range(num_rows):
        kind = "sale" if rng.random() < 0.7 else "purchase"
        exempt_cat = rng.random() < 0.3
        category = rng.choice(EXEMPT_CATEGORIES if exempt_cat else TAXABLE_CATEGORIES)
        gross = _gross(rng, 20, 2500) if rng.random() < 0.85 else _gross(rng, 5, 199)
        day = start + timedelta(days=rng.randint(0, span))
        claimed, cert = False, ""
        fault = rng.choice(FAULT_CODES) if rng.random() < fault_rate else None

        if kind == "sale":
            dest = rng.choice(zips)
            if fault == "nexus_misallocation" and (exempt_cat or combined_rate(dest) == combined_rate(business_zip)):
                others = [z for z in zips if combined_rate(z) != combined_rate(business_zip)]
                dest, category, exempt_cat = rng.choice(others), rng.choice(TAXABLE_CATEGORIES), False
            if fault == "tax_on_exempt_item" and not exempt_cat:
                category, exempt_cat = rng.choice(EXEMPT_CATEGORIES), True
            if fault == "tax_miscalculated" and exempt_cat:
                category, exempt_cat = rng.choice(TAXABLE_CATEGORIES), False

            resale = not exempt_cat and fault is None and rng.random() < 0.2
            if fault == "missing_exemption_cert":
                category, exempt_cat = rng.choice(TAXABLE_CATEGORIES), False
                gross = max(gross, _gross(rng, 250, 2500))
                claimed, cert, tax = True, "", Decimal("0.00")
            elif resale:
                claimed, tax = True, Decimal("0.00")
                if gross > CERT_THRESHOLD:
                    cert = _cert_id(rng)
            elif exempt_cat:
                tax = money(gross * combined_rate(dest)) if fault == "tax_on_exempt_item" else Decimal("0.00")
            elif fault == "nexus_misallocation":
                tax = money(gross * combined_rate(business_zip))
            elif fault == "tax_miscalculated":
                tax = _miscalc(rng, gross, dest, business_zip)
            else:
                tax = money(gross * combined_rate(dest))
            zip_code = dest
        else:
            # Purchases: vendor-located ZIP; tax either charged by the vendor, or not (use tax accrues).
            if fault in ("tax_on_exempt_item", "tax_miscalculated", "nexus_misallocation"):
                fault = None
            zip_code = rng.choice(zips)
            if fault == "missing_exemption_cert":
                category, exempt_cat = rng.choice(TAXABLE_CATEGORIES), False
                gross = max(gross, _gross(rng, 250, 2500))
                claimed, cert, tax = True, "", Decimal("0.00")
            elif exempt_cat:
                tax = Decimal("0.00")
            else:
                mode = rng.random()
                if mode < 0.5:
                    tax = money(gross * combined_rate(zip_code))  # vendor charged tax
                elif mode < 0.75:
                    tax = Decimal("0.00")  # out-of-state / untaxed vendor -> use tax
                else:
                    claimed, tax = True, Decimal("0.00")  # bought for resale
                    if gross > CERT_THRESHOLD:
                        cert = _cert_id(rng)

        if fault == "outside_period":
            day = start - timedelta(days=rng.randint(1, 40)) if rng.random() < 0.5 else end + timedelta(days=rng.randint(1, 40))

        inv_no += rng.randint(1, 3)
        prefix = "INV" if kind == "sale" else "BILL"
        row = Row(
            transaction_id="",
            invoice_number=f"{prefix}-{inv_no}",
            date=day.isoformat(),
            type=kind,
            category=category,
            gross_amount=f"{gross:.2f}",
            tax_collected_or_paid=f"{tax:.2f}",
            jurisdiction_zip=zip_code,
            tax_exempt_claimed=claimed,
            customer_or_vendor_cert_id=cert,
        )
        rows.append(row)
        if fault == "duplicate_invoice" and num_dups < 3:
            num_dups += 1
            rows.append(Row(**{**asdict(row)}))

    # Stable sort by date keeps a duplicate after its original (same date, later position).
    rows.sort(key=lambda r: r.date)
    for n, row in enumerate(rows, start=1):
        row.transaction_id = f"txn_{n:03d}"
    return Ledger(seed=seed, year=year, quarter=quarter, business_zip=business_zip, rows=rows)


def reconcile(ledger: Ledger) -> dict:
    """The programmatic ground truth: return figures plus the fault map."""
    start, end = quarter_bounds(ledger.year, ledger.quarter)
    faults: dict[str, list[str]] = {}
    seen: set[str] = set()
    gross_sales = exempt_sales = sales_tax = use_tax = Decimal("0.00")

    for row in ledger.rows:
        tid = row.transaction_id
        if row.invoice_number in seen:
            faults[tid] = ["duplicate_invoice"]
            continue
        seen.add(row.invoice_number)
        if not (start <= date.fromisoformat(row.date) <= end):
            faults[tid] = ["outside_period"]
            continue

        gross = Decimal(row.gross_amount)
        recorded = Decimal(row.tax_collected_or_paid)
        exempt_cat = row.category in EXEMPT_CATEGORIES
        row_faults: list[str] = []
        certified = bool(row.customer_or_vendor_cert_id) or gross <= CERT_THRESHOLD
        if row.tax_exempt_claimed and not exempt_cat and not certified:
            row_faults.append("missing_exemption_cert")
        exempt = exempt_cat or (row.tax_exempt_claimed and certified)

        if row.type == "sale":
            gross_sales += gross
            if exempt:
                exempt_sales += gross
                if exempt_cat and recorded > 0:
                    row_faults.append("tax_on_exempt_item")
            else:
                due = money(gross * combined_rate(row.jurisdiction_zip))
                sales_tax += due
                if recorded != due and not row_faults:
                    origin = money(gross * combined_rate(ledger.business_zip))
                    row_faults.append("nexus_misallocation" if recorded == origin else "tax_miscalculated")
        elif not exempt and recorded == 0:
            use_tax += money(gross * combined_rate(ledger.business_zip))

        if row_faults:
            faults[tid] = row_faults

    return {
        "gross_sales": f"{gross_sales:.2f}",
        "exempt_sales": f"{exempt_sales:.2f}",
        "taxable_sales": f"{gross_sales - exempt_sales:.2f}",
        "sales_tax_due": f"{sales_tax:.2f}",
        "use_tax_due": f"{use_tax:.2f}",
        "net_remittance": f"{sales_tax + use_tax:.2f}",
        "faults": faults,
    }


def render_rulebook(ledger: Ledger) -> str:
    start, end = quarter_bounds(ledger.year, ledger.quarter)
    rate_lines = "\n".join(
        f"  {z}: local {LOCAL_RATES[z] * 100:.2f}% -> combined {combined_rate(z) * 100:.2f}%" for z in LOCAL_RATES
    )
    return f"""\
Jurisdiction: {STATE_NAME}. State rate {STATE_RATE * 100:.2f}% plus the local rate of the ZIP below.
{rate_lines}

Filing period: {ledger.year} Q{ledger.quarter} ({start.isoformat()} to {end.isoformat()}, inclusive).
Filer's business location (origin / place of use): ZIP {ledger.business_zip}.

Rules:
1. Exempt categories: {", ".join(EXEMPT_CATEGORIES)}. All other categories are taxable at retail.
2. Sales are destination-sourced: tax = gross_amount x combined rate of the sale's jurisdiction_zip
   (the buyer's delivery ZIP). gross_amount is the pre-tax line amount; tax is added on top.
3. Round tax per line to the cent (half-up), then sum.
4. A taxable-category transaction with tax_exempt_claimed=true is exempt (sale for resale) only if
   customer_or_vendor_cert_id is non-empty OR gross_amount <= ${CERT_THRESHOLD}. Otherwise it is a
   missing_exemption_cert fault and the transaction is treated as taxable.
5. Exclude from the return any row dated outside the filing period, and the second (later) occurrence of a
   repeated invoice_number (when dates tie, the later row in the ledger is the duplicate).
6. Purchases: when the vendor charged no tax on a taxable, non-exempt purchase, vendor use tax is due at the
   filer's business ZIP combined rate (per line, rounded). Purchases with vendor-charged tax, exempt categories,
   or a valid resale exemption owe no use tax.

Return figures (sales only for the sales lines):
  gross_sales    = sum of gross_amount of included sales
  exempt_sales   = included sales that are exempt (exempt category, or valid resale per rule 4)
  taxable_sales  = gross_sales - exempt_sales
  sales_tax_due  = tax that SHOULD be due on taxable sales per rules 2-3 (not the recorded tax)
  use_tax_due    = per rule 6
  net_remittance = sales_tax_due + use_tax_due

Fault codes (report every row that has one; one row may carry several):
  tax_on_exempt_item     - an exempt-category sale with tax recorded
  tax_miscalculated      - a taxable sale whose recorded tax != correct tax (not reported on rows that already
                           carry missing_exemption_cert, and not when nexus_misallocation explains the difference)
  duplicate_invoice      - the later occurrence of a repeated invoice_number (report only this code for that row)
  outside_period         - dated outside the filing period (report only this code for that row)
  missing_exemption_cert - per rule 4
  nexus_misallocation    - a taxable sale whose recorded tax equals gross x the ORIGIN (business ZIP) combined rate
                           instead of the destination rate"""


def render_ledger(ledger: Ledger) -> str:
    cols = list(Row.__dataclass_fields__)
    lines = [",".join(cols)]
    for row in ledger.rows:
        values = asdict(row)
        values["tax_exempt_claimed"] = "true" if row.tax_exempt_claimed else "false"
        lines.append(",".join(str(values[c]) for c in cols))
    return "\n".join(lines)
