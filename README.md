[![Review Assignment Due Date](https://classroom.github.com/assets/deadline-readme-button-22041afd0340ce965d47ae6ef1cefeee28c7c493a6346c4f15d667ab976d596c.svg)](https://classroom.github.com/a/iR6i90R4)
# test-template

## Rules
- Language: {pick one or allow multiple; keep the right CI file}
- Time limit: ~90 minutes (honor system).
- Don’t use AI assistants for final code (discussion is fine). Note sources if used.

## How to submit
1. Click **Use this template** to create a **private** repo under your GitHub.
2. Add **@YOUR_GITHUB_USERNAME** as a collaborator.
3. Implement code in `src/`, keep tests in `tests/` unchanged.
4. Push to your repo; ensure **CI is green**.
5. Open a PR to `main` titled `Submission - YOUR NAME` (optional), or share repo link.

## Evaluation
- ✅ All tests pass
- ✅ Code clarity & structure
- ✅ Edge cases & performance
- ✅ Commit hygiene


# SDET Coding Test – JSON Validation & Extraction (Tests Only)

## Goal
Using the provided JSON dataset, write **unit tests only** (no production code) that validate data quality and extract insights via **JSONPath** (or equivalent selectors in your language).  
You may use any language and test framework (e.g., Java+JUnit, Python+pytest, JS+Jest).

---

## Dataset
The file `orders.json` is provided. Use it in your tests.

---

## What You Must Do

### A) Presence & Format Validation (via JSONPath)

Write tests that **fail on bad data**:

1. **Order identity**
   - Every order has a non-empty `id`.
   - `status` is one of `PAID | PENDING | CANCELLED`.

2. **Customer email**
   - If `customer.email` exists, it matches a basic email regex like:  
     `^[^@\s]+@[^@\s]+\.[^@\s]+$`
   - Flag orders with missing or invalid emails.

3. **Lines integrity**
   - `lines` array must be **non-empty** for `status` in `PAID | PENDING`.
   - Each line has `sku` (non-empty), `qty` > 0, `price` ≥ 0.

4. **Payment / Refund consistency**
   - If `status = PAID`, `payment.captured` should be `true`.
   - If `status = CANCELLED` and `lines` exist, `refund.amount` equals the **sum of line totals** (`qty × price`), allowing zero shipping fee to be excluded.

5. **Shipping**
   - `fee` ≥ 0 for all orders.

👉 Use JSONPath to locate what you validate (e.g., `$.orders[*].customer.email`, `$.orders[*].lines[*].qty`).  
You may combine JSONPath with small helper code to compute totals.

---

### B) Extraction & Aggregation (assert exact expected values)

From the provided dataset:

1. **List of all order IDs**  
   `["A-1001","A-1002","A-1003","A-1004","A-1005"]`

2. **Count of total line items across all orders**  
   `8`

3. **Top 2 SKUs by total quantity**
   - `PEN-RED` → 5 (2 from A-1001, 3 from A-1005)  
   - `USB-32GB` → 2 (from A-1005)  
   *(Note: `USB-32GB` in A-1003 has qty 0 and should not add to totals.)*

4. **Gross merchandise value (GMV) per order (Σ qty×price, before discounts/shipping)**
   - A-1001 → `70.0` (2×10 + 1×50)  
   - A-1002 → `0.0` (no lines)  
   - A-1003 → `-15.0` (0×12.5 + 1×-15.0 → invalid; should be flagged)  
   - A-1004 → `16.0` (2×8)  
   - A-1005 → `55.0` (3×10 + 2×12.5)

5. **Orders missing or invalid emails**  
   `["A-1002","A-1003"]`

6. **Paid orders with `payment.captured = false`**  
   `[]`

7. **Cancelled orders with correct refund amount**  
   `["A-1004"]`

Write tests that assert these exact results against your JSONPath-driven computations.

---

### C) Reporting (one test that prints a summary)

Create **one test** that assembles a short summary string (or JSON) with:
- total orders,
- total line items,
- number of invalid orders,
- list of problematic order IDs with reasons (e.g., empty lines, invalid email, non-positive qty/price).

👉 You can simply `assertTrue(summary.length() > 0)`; the point is to show you can aggregate findings cleanly.

---

## Rules & Constraints
- No production/source classes required — **tests only** that load `orders.json`, query with JSONPath, and assert.
- You may use any JSONPath library (Jayway for Java, `jsonpath-ng` for Python, etc.).
- Keep the tests deterministic (no network calls).
- Include instructions to run (e.g., `mvn test`, `pytest`, or `npm test`).

---

## What to Submit
A repo containing:
- `orders.json` (as provided),
- your test file(s),
- a short `README` with run instructions.

👉 Keep commit history (we care about how you work).

---

## Evaluation (what we look for)
- ✅ Correct use of JSONPath for selection/validation  
- ✅ Clear, minimal assertions with good messages  
- ✅ Edge-case coverage (invalid email, empty lines, non-positive qty/price)  
- ✅ Clean code & structure in tests (naming, small helpers OK)  
- ✅ Bonus: property-based tests, schema validation (e.g., JSON Schema), or parameterized tests
