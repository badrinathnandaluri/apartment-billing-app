from billing.config import FLAT_NUMBERS
from billing.domain import clean_expenses, compute_bills, compute_close
from billing.pdf.render import bills_pdf, full_pdf, slips_pdf


def sample():
    rd = {f: (1000, 1000 + 8 + i) for i, f in enumerate(FLAT_NUMBERS)}
    bills = compute_bills(10_000, 3, 510, rd)
    close = compute_close(4_200, clean_expenses([{"name": "Watchman Salary", "amount": 8000},
                                                 {"name": "Garbage", "amount": 600}]),
                          bills.total_water_bill, bills.total_collection)
    return bills, close


def test_documents_render_with_expected_page_counts():
    bills, close = sample()
    b = bills_pdf("2026-10", bills)
    f = full_pdf("2026-10", bills, close)
    s = slips_pdf("2026-10", bills)
    for doc in (b, f, s):
        assert doc.startswith(b"%PDF")
    assert b.count(b"/Type /Page") - b.count(b"/Type /Pages") == 1
    assert f.count(b"/Type /Page") - f.count(b"/Type /Pages") == 2
    assert s.count(b"/Type /Page") - s.count(b"/Type /Pages") == 1
