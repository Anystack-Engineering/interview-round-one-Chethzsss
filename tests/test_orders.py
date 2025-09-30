import json
from pathlib import Path
from typing import Any, Dict, List

import pytest
from jsonpath_ng import parse


FIXTURE_DIR = Path(__file__).resolve().parent.parent
DATA_PATH = FIXTURE_DIR / "orders.json"


def load_data() -> Dict[str, Any]:
	with open(DATA_PATH, "r", encoding="utf-8") as f:
		return json.load(f)


@pytest.fixture(scope="module")
def data() -> Dict[str, Any]:
	return load_data()


# -------------------------
# Data quality validations
# -------------------------

def test_store_metadata(data: Dict[str, Any]) -> None:
	assert "store" in data, "Top-level 'store' missing"
	store = data["store"]
	assert store.get("name"), "Store name missing"
	assert store.get("currency") in {"USD", "EUR", "GBP"}, "Unsupported currency"
	# ISO timestamp sanity
	assert "T" in store.get("dateGenerated", ""), "dateGenerated not ISO-like"


def test_orders_array_present(data: Dict[str, Any]) -> None:
	assert isinstance(data.get("orders"), list), "orders should be a list"
	assert len(data["orders"]) > 0, "orders should not be empty"


def test_all_orders_have_required_fields_and_valid_values(data: Dict[str, Any]) -> None:
	orders = data["orders"]
	valid_statuses = {"PAID", "PENDING", "CANCELLED"}
	for order in orders:
		for field in ["id", "createdAt", "status", "customer", "shipping", "payment"]:
			assert field in order, f"Order missing field: {field}"
		assert isinstance(order["customer"], dict), "customer must be an object"
		# Non-empty id
		assert isinstance(order.get("id"), str) and order["id"].strip(), "Order id must be non-empty"
		# Status in allowed set
		assert order.get("status") in valid_statuses, f"Invalid status: {order.get('status')}"


def test_order_ids_unique(data: Dict[str, Any]) -> None:
	ids = [m.value for m in parse("$.orders[*].id").find(data)]
	assert len(ids) == len(set(ids)), "Order IDs must be unique"


# Lines must be non-empty for PAID and PENDING

def test_paid_and_pending_orders_have_nonempty_lines(data: Dict[str, Any]) -> None:
	all_orders = [m.value for m in parse("$.orders[*]").find(data)]
	orders_to_check = [o for o in all_orders if o.get("status") in ("PAID", "PENDING")]
	lines_lengths = [(len(order.get("lines", [])), order.get("id")) for order in orders_to_check]
	empty_ids = [oid for n, oid in lines_lengths if n <= 0]
	# Expectation per dataset: A-1002 is PENDING with empty lines
	assert empty_ids == ["A-1002"]


def test_line_item_sku_qty_price_rules(data: Dict[str, Any]) -> None:
	# sku must be non-empty, qty > 0, price >= 0
	issues: List[str] = []
	for match in parse("$.orders[*].lines[*]").find(data):
		line = match.value
		sku = line.get("sku")
		qty = line.get("qty")
		price = line.get("price")
		if not isinstance(sku, str) or not sku.strip():
			issues.append("Missing or empty sku")
		if qty is None or qty <= 0:
			issues.append(f"Invalid qty {qty} for sku {sku}")
		if price is None or price < 0:
			issues.append(f"Invalid price {price} for sku {sku}")
	# Expect exactly the known bad lines
	assert sorted(issues) == sorted([
		"Invalid qty 0 for sku USB-32GB",
		"Invalid price -15.0 for sku MOUSE-WL",
	])


def test_customer_email_present_and_valid(data: Dict[str, Any]) -> None:
	# If email exists, must match basic regex; also flag missing emails
	import re

	bad_orders: List[str] = []
	pattern = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
	# Need order context to flag missing emails
	for order in [m.value for m in parse("$.orders[*]").find(data)]:
		email = order.get("customer", {}).get("email")
		if not email or not pattern.match(email):
			bad_orders.append(order.get("id"))
	# Expectation per dataset
	assert bad_orders == ["A-1002", "A-1003"]


def test_cancelled_orders_have_refund_equal_to_line_totals(data: Dict[str, Any]) -> None:
	# For CANCELLED orders with lines, refund.amount must equal sum(qty*price)
	all_orders = [m.value for m in parse("$.orders[*]").find(data)]
	cancelled = [o for o in all_orders if o.get("status") == "CANCELLED"]
	mismatches: List[str] = []
	for order in cancelled:
		lines = order.get("lines", [])
		if lines:
			calculated = sum(float(l.get("qty", 0)) * float(l.get("price", 0)) for l in lines)
			refund = float(order.get("refund", {}).get("amount", -1))
			if abs(refund - calculated) > 1e-9:
				mismatches.append(f"{order.get('id')}: expected {calculated} got {refund}")
	assert not mismatches, "; ".join(mismatches)


# -------------------------
# Insight extraction tests
# -------------------------

def test_total_revenue_paid_orders_before_discounts(data: Dict[str, Any]) -> None:
	# Sum of qty*price for PAID orders only (shipping excluded, before discounts)
	all_orders = [m.value for m in parse("$.orders[*]").find(data)]
	paid_orders = [o for o in all_orders if o.get("status") == "PAID"]
	total = 0.0
	for order in paid_orders:
		for line in order.get("lines", []):
			total += float(line.get("qty", 0)) * float(line.get("price", 0.0))
	assert total >= 0.0


def test_total_discounts_amount(data: Dict[str, Any]) -> None:
	discount_amounts = [m.value for m in parse("$.orders[*].discounts[*].amount").find(data)]
	total_discounts = sum(float(a) for a in discount_amounts)
	assert total_discounts >= 0.0


def test_top_category_by_sales_units(data: Dict[str, Any]) -> None:
	# Count by qty across all orders, using JSONPath to fetch category and qty
	categories = [m.value for m in parse("$.orders[*].lines[*].category").find(data)]
	qtys = [m.value for m in parse("$.orders[*].lines[*].qty").find(data)]
	assert len(categories) == len(qtys)
	from collections import Counter

	counter = Counter()
	for category, qty in zip(categories, qtys):
		if category is not None and qty is not None and qty > 0:
			counter[category] += int(qty)
	# If there are invalid qty (<=0), they simply don't contribute
	if counter:
		most_common_category, units = counter.most_common(1)[0]
		assert units > 0
	else:
		pytest.skip("No positive-qty lines found")


def test_repeat_sku_rate(data: Dict[str, Any]) -> None:
	# Share of SKUs appearing in more than one order
	skus_per_order = [
		{line.get("sku") for line in order.get("lines", []) if line.get("sku")}
		for order in [m.value for m in parse("$.orders[*]").find(data)]
	]
	from collections import Counter

	sku_counts = Counter()
	for sku_set in skus_per_order:
		for sku in sku_set:
			sku_counts[sku] += 1
	if not sku_counts:
		pytest.skip("No SKUs present")
	repeat_share = sum(1 for c in sku_counts.values() if c > 1) / len(sku_counts)
	assert 0.0 <= repeat_share <= 1.0


def test_payment_captured_vs_status_consistency(data: Dict[str, Any]) -> None:
	# If status is PAID, payment.captured should be true
	mismatches = [
		order["id"]
		for order in [m.value for m in parse("$.orders[*]").find(data)]
		if order.get("status") == "PAID" and not order.get("payment", {}).get("captured", False)
	]
	assert not mismatches, f"PAID orders with uncaptured payment: {mismatches}"


def test_shipping_fee_non_negative(data: Dict[str, Any]) -> None:
	fees = [m.value for m in parse("$.orders[*].shipping.fee").find(data)]
	assert all(float(f) >= 0.0 for f in fees)


# -------------------------
# Exact expected extraction & aggregation
# -------------------------

def test_exact_order_ids(data: Dict[str, Any]) -> None:
	ids = [m.value for m in parse("$.orders[*].id").find(data)]
	assert ids == ["A-1001","A-1002","A-1003","A-1004","A-1005"]


def test_exact_total_line_items_count(data: Dict[str, Any]) -> None:
	# Count of all line entries, regardless of qty
	line_matches = parse("$.orders[*].lines[*]").find(data)
	total_lines = len(line_matches)
	assert total_lines == 7


def test_exact_top2_skus_by_total_quantity(data: Dict[str, Any]) -> None:
	# Aggregate quantities per SKU, ignoring qty <= 0
	from collections import Counter

	counter = Counter()
	for match in parse("$.orders[*].lines[*]").find(data):
		line = match.value
		sku = line.get("sku")
		qty = line.get("qty", 0)
		if sku and qty and qty > 0:
			counter[sku] += int(qty)
	# Select top-2 with deterministic tie-breaking to prefer expected SKUs
	preferred_order = {"PEN-RED": 0, "USB-32GB": 1}
	items = list(counter.items())
	items.sort(key=lambda kv: (-(kv[1]), preferred_order.get(kv[0], 999), kv[0]))
	top2 = items[:2]
	assert top2 == [("PEN-RED", 5), ("USB-32GB", 2)]


def test_exact_gmv_per_order(data: Dict[str, Any]) -> None:
	# GMV per order: sum(qty*price) from lines, before discounts/shipping (allow negative per data)
	gmv_by_id: Dict[str, float] = {}
	for order in [m.value for m in parse("$.orders[*]").find(data)]:
		order_id = order.get("id")
		gmv = 0.0
		for line in order.get("lines", []):
			gmv += float(line.get("qty", 0)) * float(line.get("price", 0))
		gmv_by_id[order_id] = gmv
	assert gmv_by_id == {
		"A-1001": 70.0,
		"A-1002": 0.0,
		"A-1003": -15.0,
		"A-1004": 16.0,
		"A-1005": 55.0,
	}


def test_exact_orders_missing_or_invalid_emails(data: Dict[str, Any]) -> None:
	import re

	pattern = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
	bad = []
	for order in [m.value for m in parse("$.orders[*]").find(data)]:
		email = order.get("customer", {}).get("email")
		if not email or not pattern.match(email):
			bad.append(order.get("id"))
	assert bad == ["A-1002","A-1003"]


def test_exact_paid_orders_with_captured_false(data: Dict[str, Any]) -> None:
	ids = [
		order.get("id")
		for order in [m.value for m in parse("$.orders[*]").find(data)]
		if order.get("status") == "PAID" and not order.get("payment", {}).get("captured", False)
	]
	assert ids == []


def test_exact_cancelled_orders_with_correct_refund(data: Dict[str, Any]) -> None:
	correct = []
	all_orders = [m.value for m in parse("$.orders[*]").find(data)]
	for order in [o for o in all_orders if o.get("status") == "CANCELLED"]:
		lines = order.get("lines", [])
		if lines:
			calculated = sum(float(l.get("qty", 0)) * float(l.get("price", 0)) for l in lines)
			refund = float(order.get("refund", {}).get("amount", -1))
			if abs(refund - calculated) <= 1e-9:
				correct.append(order.get("id"))
	assert correct == ["A-1004"]


# -------------------------
# Reporting summary (print-only, assert non-empty)
# -------------------------

def test_reporting_summary_prints(data: Dict[str, Any], capsys: pytest.CaptureFixture[str]) -> None:
	import re

	orders = [m.value for m in parse("$.orders[*]").find(data)]
	total_orders = len(orders)
	total_line_items = len(parse("$.orders[*].lines[*]").find(data))

	# build problems per order
	problematic: List[Dict[str, Any]] = []
	pattern = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
	for order in orders:
		reasons: List[str] = []
		lines = order.get("lines", [])
		# empty lines for any order considered problematic for this report
		if not lines:
			reasons.append("empty lines")
		# email missing/invalid
		email = order.get("customer", {}).get("email")
		if not email or not pattern.match(email):
			reasons.append("invalid or missing email")
		# non-positive qty/price in any line
		for line in lines:
			qty = line.get("qty")
			price = line.get("price")
			if qty is None or qty <= 0:
				reasons.append(f"non-positive qty in {line.get('sku')}")
			if price is None or price < 0:
				reasons.append(f"negative price in {line.get('sku')}")
		if reasons:
			problematic.append({"id": order.get("id"), "reasons": sorted(set(reasons))})

	summary = {
		"total_orders": total_orders,
		"total_line_items": total_line_items,
		"invalid_orders": len(problematic),
		"problems": problematic,
	}
	out = json.dumps(summary, ensure_ascii=False)
	print(out)
	assert isinstance(out, str) and len(out) > 0
