# Millbook

Order-to-audit prototype for a fictional Tamil Nadu snack factory. Follow the same 200 g murukku packets from flour receipt and batch production through invoice, dispatch, collection and monthly audit.

## Run the app

With Docker and Docker Compose installed, from this folder run:

```sh
docker compose up --build -d
```

Open http://localhost:8000. On first launch the app creates the schema, six demo users, price list, customers, supplier, recipe and opening stock. Every new database starts **before** the first flour purchase. The named volume preserves postings across restarts. Use a new Compose project and an unused host port (or stop the original project) for a separate clean demo. Use `docker compose stop` to stop without removing records.

For Python 3.12, use a virtual environment and then:

```sh
python -m pip install -r requirements.txt
python app.py
```

Run the regression suite with `python -m unittest -v`. The tests use isolated temporary databases. Configuration: PORT (default 8000), MILL_DB (default data/mill.sqlite), DEMO_PASSWORD (first launch only), COOKIE_SECURE=1 behind HTTPS. The Compose default binds to loopback. For a hosted evaluator demo, run the container behind an HTTPS reverse proxy with a persistent volume mounted at /app/data, one app replica, and your chosen initial password. Demo accounts have shared credentials for assessment. Real production use requires account provisioning, unique passwords, access monitoring and a backup policy.

| Role | Login | Workspace |
|---|---|---|
| Production supervisor | floor | Receipts, recipe, runs, actuals, overheads and inventory |
| Field sales | sales-a, sales-b | Mobile order entry, own order status and own customer sales |
| Factory admin | admin | Verification, invoice PDF, dispatch, credit notes and payments |
| Accountant | audit | Read-only reports, stock and CSV/PDF export |
| Owner | owner | Daily orders, inventory, alerts, cost, dues and reports |

The default password for all six demo users is **MillDemo2026!**.

## Why this stack

Python handles the posting rules and Decimal arithmetic. SQLite supports real transactional writes and makes the one-factory prototype portable. A small JavaScript frontend works at phone and desktop widths, and ReportLab creates downloadable PDFs on the server.

## Replay the internship benchmark

1. Sign in as **floor**. In Purchases receive 60 kg of flour at ₹45 per kg.
2. In Production use one batch. Enter 188 good packets, 6 damaged pouches, 40 kg flour, 10.5 L oil, 1.2 kg spice mix and 9 cartons. Confirm 194 issued pouches. Post once.
3. Check Stock and the run variance tables. The order of saving output and issuing inputs is atomic, so no half-complete run affects available stock.
4. On a mobile-width screen sign in as **sales-a** and submit 150 packets for Retailer A. As **admin**, approve, raise GST invoice, download its PDF and record dispatch.
5. As **sales-b** submit 120 packets for Distributor B. As **admin** open the order and attempt approval with the original quantity. The shortage blocks approval while preserving the order for later fulfilment.
6. Under SO-1 as **admin**, record ₹4,000. As **floor**, allocate ₹1,200 labour and ₹600 gas/power to RUN-1. These fields are the run's total allocations. Entering new amounts replaces the prior allocation and logs the revision.
7. As **audit** select the current month and export each register. Ageing shows open invoices grouped by customer identity and labelled with their age bucket. The date range includes both endpoints; ageing is an as-of-end-date report including older unpaid invoices.

| Benchmark measure | Result |
|---|---:|
| Flour / oil / spice closing | 120 kg / 19.5 L / 3.8 kg |
| Pouches / cartons closing | 306 / 21 |
| Finished stock after production / dispatch | 238 / 88 packets |
| Yield / oil / carton variance | −6% / +5% / −10%, all flagged |
| Retailer A invoice | ₹7,500 + ₹187.50 CGST + ₹187.50 SGST = ₹7,875 |
| Distributor B | 32 packets short; 5% IGST if supplied |
| Retailer A outstanding | ₹3,875 |
| Run inputs / overheads | ₹4,055 / ₹1,800 |
| Cost / pre-tax margin per packet | ₹31.14 / ₹18.86 |

Flour's moving average is (100 × ₹42 + 60 × ₹45) / 160 = ₹43.125/kg. The run consumes flour ₹1,725, oil ₹1,470, spice ₹240, pouches ₹485 and cartons ₹135. ₹5,855 / 188 = ₹31.14 rounded. Good output can include loose packets, so nine cartons need not hold all 188. The yield gap of 12 is tracked separately from six damaged empty pouches.

## Scope and interview guide

**Minimum:** role authentication and access checks, seeded masters, mobile sales, editable order verification, stock reservations, financial-year invoice numbers, GST invoice PDF, atomic recipe postings, consumption/yield variance and exportable stock and sales registers.

**Additional:** supplier receipts, weighted-average costing, run overheads, owner dashboard, payments and ageing, date-filtered sales/customer/product/GST/purchase/stock/production/collections registers, journalled credit notes and audit events. Sales quantities can be entered in cartons or packets. Receipts accept kg/g and L/mL. Exercise tax rates and fictional GST identifiers are supplied for this prototype. GST reports are outward-supply working papers for an accountant.

**Limits:** online order submission, fixed seed masters, full dispatch per order, full cancellation only before dispatch/payment. No returns, FEFO, opening finished-stock valuation, GST filing or Tally integration. The seed HSN and GSTINs are illustrative. The invoice email action opens a draft for manual PDF attachment. The production material named 200 g pouch has a one-pouch-per-good-packet reconciliation rule.

**Code map:** db.py and schema.sql define units and seed masters. operations.py handles postings and role permissions, reports.py builds the registers, documents.py renders PDFs, app.py checks sessions and serves JSON, and static/ui.js renders workspaces. DESIGN.md explains the model and transactions. Start a live change by tracing test_benchmark.py into the relevant posting rule.
