# Millbook

Millbook follows a batch of 200 g murukku through a fictional Tamil Nadu snack factory. A production supervisor records flour receipts and packet output, salespeople take orders, and the billing desk issues invoices and records collections. An auditor can trace each stock movement back to the transaction that created it.

**[Watch the benchmark demo on YouTube (1 min 58 sec)](https://youtu.be/eF059R34RSQ)** · [Design note and data model](DESIGN.md)

## Run the app

From the repository root, with Docker and Docker Compose installed, run:

```sh
docker compose up --build -d
```

Open [Millbook on localhost](http://localhost:8000). Sign in as `floor` with password `MillDemo2026!` to begin the benchmark. First launch creates the schema and seeds six users, opening stock, the recipe, price list, customers and supplier. A fresh database starts before the first flour purchase.

The Compose volume preserves records across restarts. Run `docker compose stop` to stop the app. For a separate clean demo, use a new Compose project with a fresh volume and an available host port.

### Run with Python 3.12 on Windows

In PowerShell, from the repository root:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe app.py
```

Open the same localhost URL. To run the regression suite, use `.\.venv\Scripts\python.exe -m unittest -v`. The tests create isolated temporary databases.

### Demo accounts

All six demo users share the default password `MillDemo2026!`.

| Role | Username | Workspace |
|---|---|---|
| Production supervisor | `floor` | Purchases, recipe, production runs, overheads and stock |
| Field sales | `sales-a`, `sales-b` | Mobile order entry, own order status and customer-wise sales |
| Factory admin | `admin` | Order verification, invoice PDFs, dispatch, credit notes and payments |
| Accountant or auditor | `audit` | Read-only stock and reports with CSV and PDF export |
| Owner | `owner` | Today's orders, inventory, variance alerts, costs and dues |

## Replay the benchmark

Start with a fresh database so that the opening balance is 100 kg of flour and 50 finished packets.

1. **Receive flour.** As `floor`, open **Purchases** and receive 60 kg of flour at ₹45/kg.
2. **Post production.** In **Production**, select one batch. Enter 188 good packets, 6 damaged pouches, 40 kg flour, 10.5 L oil, 1.2 kg spice mix and 9 cartons. Confirm that 194 pouches were issued. Post the run once. Check the closing balances in **Stock** and the variance tables in **Production**.
3. **Invoice and dispatch.** As `sales-a`, use the mobile order form to submit 150 packets for Retailer A. As `admin`, approve the order, raise the GST invoice, download its PDF and record dispatch.
4. **Check insufficient stock.** As `sales-b`, submit 120 packets for Distributor B. As `admin`, attempt approval at the original quantity. The order stays submitted with a shortage of 32 packets.
5. **Collect payment.** As `admin`, record ₹4,000 against Retailer A’s invoice under SO-1.
6. **Allocate overheads.** As `floor`, assign ₹1,200 labour and ₹600 gas/power to RUN-1. Each amount represents the total allocation for that run. Revising an amount updates the cost and logs the change.
7. **Run the audit.** As `audit`, select the current month and export the registers. Date filters include both endpoints. Receivables ageing uses the end date and includes older invoices still outstanding on that date.

### Expected results

| Measure | Result |
|---|---|
| Closing flour, oil and spice mix | 120 kg, 19.5 L and 3.8 kg |
| Closing pouches and cartons | 306 pouches and 21 cartons |
| Finished stock | 238 packets after production, 88 after dispatch |
| Yield variance | 188 good vs 200 expected, −6% |
| Oil and carton consumption variance | +5% oil and −10% cartons. Both exceed the 3% tolerance |
| Retailer A invoice | ₹7,500 taxable + ₹187.50 CGST + ₹187.50 SGST = ₹7,875 |
| Distributor B | 120 requested, 88 available, 32 short. The exercise applies 5% IGST if supplied |
| Retailer A outstanding | ₹7,875 invoiced − ₹4,000 collected = ₹3,875 |
| Run cost | ₹4,055 materials and packaging + ₹1,800 overheads = ₹5,855 |
| Cost and pre-tax margin per packet | ₹31.14 cost and ₹18.86 margin at the ₹50 selling price |

Flour uses a moving weighted-average purchase rate. The opening 100 kg at ₹42/kg and the receipt of 60 kg at ₹45/kg give a rate of ₹43.125/kg. The run consumes ₹1,725 of flour, ₹1,470 of oil, ₹240 of spices, ₹485 of pouches and ₹135 of cartons. Dividing the total run cost of ₹5,855 by 188 good packets gives ₹31.14 per packet after rounding.

Good output includes loose packets, so nine cartons can be used even when the run produces 188 packets. The 12-packet yield shortfall and six damaged empty pouches measure different losses.

## Implementation and scope

Python handles posting rules and decimal arithmetic. SQLite commits a run, its material issues and its finished-stock receipt in one transaction. The JavaScript frontend supports phone and desktop widths. ReportLab generates PDFs on the server.

- **Core workflow.** Role-based access, seeded master data, mobile order entry, editable verification, stock reservations, financial-year invoice numbers, GST invoice PDFs, production postings, variance checks, stock ledger and sales registers.
- **Additional features.** Supplier receipts, weighted-average costing, run overheads, payments, ageing, owner dashboard, credit notes and audit events. Reports cover sales by customer and product, outward GST, purchases, stock, production and collections. Sales accept cartons or packets. Receipts support kg/g and L/mL.
- **Prototype limits.** Order submission requires connectivity. Masters are seeded. Dispatch covers the full order, and invoice cancellation is available before dispatch and payment. Returns, FEFO, opening finished-stock valuation, GST filing and Tally integration are outside the prototype. The tax rates, HSN and GSTINs are illustrative. The email action opens a draft for manual PDF attachment. The 200 g pouch rule reconciles one pouch per good packet plus damaged pouches.

## Code map

| File | Responsibility |
|---|---|
| [schema.sql](schema.sql), [db.py](db.py) | Tables, units, opening balances and seed masters |
| [operations.py](operations.py) | Posting rules, permissions and stock movements |
| [reports.py](reports.py), [documents.py](documents.py) | Registers, costing and PDF generation |
| [app.py](app.py), [static/ui.js](static/ui.js) | Sessions, HTTP endpoints and role-specific screens |
| [test_benchmark.py](test_benchmark.py), [test_http.py](test_http.py) | Benchmark arithmetic, transaction rollback, report downloads and access checks |

## Hosting configuration

| Variable | Purpose |
|---|---|
| `PORT` | Listening port. Defaults to `8000` |
| `MILL_DB` | SQLite file. Defaults to `data/mill.sqlite` |
| `DEMO_PASSWORD` | Initial password for seeded accounts on first launch |
| `COOKIE_SECURE` | Set to `1` behind HTTPS |

Compose binds to loopback by default. For a hosted assessment, use one app replica, an HTTPS reverse proxy and a persistent volume mounted at `/app/data`. Shared demo credentials are intended for the fictional dataset. A real factory deployment would also need individual account provisioning, access monitoring and backups.