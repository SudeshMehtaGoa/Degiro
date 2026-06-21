# DEGIRO Investment Dashboard

A local, self-hosted investment dashboard for DEGIRO brokerage accounts. Drop in your exported `Account.csv` and get a live multi-tab view of your portfolio — with real-time prices, dividend tracking, and annualised return (XIRR) per asset.

---

## Features

| Tab | What it shows |
|-----|---------------|
| **Portfolio** | Holdings, total CHF invested, dividends received, live prices, total return |
| **Purchases** | One clean row per buy trade — units, price, fees, total CHF paid |
| **Dividends** | Every dividend event converted to CHF using actual DEGIRO FX rates |
| **Dividend Summary** | Net dividend received per asset (after tax) |
| **Returns** | XIRR (annualised return %) per asset and for the full portfolio |
| **Transactions** | Full raw CSV — sortable, filterable, paginated |

**Key capabilities:**
- Live prices fetched from Yahoo Finance via `yfinance`
- All foreign currencies (USD, EUR, GBX/pence) converted to CHF
- Total Return = Capital Gain + Dividends Received
- XIRR accounts for exact purchase dates, dividend dates, and current value
- **Donut chart** on Portfolio tab — visual allocation by current value
- **Horizontal bar chart** on Returns tab — XIRR per asset at a glance
- Totals row pinned at top of every table
- Natural page scroll on all tabs — full table always visible, no cramped scroll boxes
- Tab bar stays sticky at top while scrolling
- Search filter on every tab — filter by asset name or ISIN
- Column sort on every tab — click any header
- Column headers clean (no CHF clutter) — `* All values are in CHF` note above each table
- Prices cached for 5 minutes to avoid hammering Yahoo Finance
- No database, no cloud — runs entirely on your machine

---

## Architecture

```
Account.csv   ←  you download this from DEGIRO (read-only, never modified)
    │
server.py     ←  local HTTP server (Python)
    │              • serves dashboard.html as a static file
    │              • exposes /prices?isins=... endpoint (Yahoo Finance)
    │              • in-process price cache (5 min TTL)
    │
dashboard.html ← single-file frontend (HTML + CSS + vanilla JS)
                   • fetches Account.csv via fetch() on every load
                   • parses and renders all 6 tabs in the browser
                   • calls /prices for live data
                   • computes XIRR in-browser (Newton-Raphson)
```

**Key design principle:** `Account.csv` is a pure data source. To update your dashboard, just download a new CSV from DEGIRO and replace the file — no code changes needed.

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Runtime | Python 3.x |
| HTTP server | `http.server` + `socketserver` (Python stdlib) |
| Live prices | [`yfinance`](https://github.com/ranaroussi/yfinance) |
| XIRR calculation | Vanilla JavaScript (Newton-Raphson algorithm, in-browser) |
| Charts | Inline SVG (no charting library — pure code) |
| Frontend | Vanilla HTML + CSS + JavaScript (no frameworks) |
| Data source | DEGIRO `Account.csv` export |

---

## Setup

### 1. Install Python dependency

```bash
pip install yfinance
```

### 2. Export your data from DEGIRO

1. Log in to DEGIRO
2. Go to **Activity → Account Statement**
3. Set date range (e.g. all time)
4. Export as CSV
5. Save as `Account.csv` in the same folder as `server.py`

### 3. Run the dashboard

**Windows:** Double-click `start.bat`

**Or from terminal:**
```bash
python server.py
```

The dashboard opens automatically in your browser. The server tries ports `8081 → 8082 → 8083 → 9000 → 9001` (port 8080 is reserved by Windows).

---

## File Structure

```
├── server.py        # Local HTTP + price API server
├── dashboard.html   # Full frontend (single file, all 6 tabs)
├── start.bat        # Windows launcher
├── Account.csv      # Your DEGIRO export (gitignored, never committed)
└── .gitignore
```

---

## Tab Details

### Portfolio
Shows your current holdings with live prices. Includes a **donut chart** above the table showing allocation by current market value — each slice is one asset, with % and CHF value in the legend. Columns:
- Units held, Total Invested, Dividends Received, Current Price, Current Value, Total Return
- **Total Return = Current Value − CHF Invested + Dividends Received**

### Purchases
One row per buy order (DEGIRO creates 4 CSV rows per trade — this collapses them). Shows:
- Date, Asset, Units, Original price in trade currency, Rate per unit in CHF, Fee, Total CHF paid

### Dividends
Every dividend event with CHF conversion using actual DEGIRO FX rates from the CSV. Shows gross dividend, withholding tax, and net received in CHF.

### Dividend Summary
Total net dividends received per asset after tax, in CHF. Sorted by amount by default.

### Returns (XIRR)
The key performance tab. Includes a **horizontal bar chart** above the table — green bars extend right for positive returns, red bars extend left for negative, with a zero centre line. Instantly shows your best and worst performing assets.

For each asset in the table:
- **First Buy date** — when you first invested
- **Total Invested** — all money paid including fees, across all purchases
- **Dividends** — total net dividends received
- **Current Value** — live market value
- **Total Return** — capital gain + dividends
- **Annual Return %** — XIRR with visual mini-bar indicator

The **TOTAL PORTFOLIO** row shows your overall XIRR — the single annualised rate at which your entire portfolio is growing, equivalent to the interest rate on a bank FD that would produce the same result.

> **Note:** Open the Portfolio tab first to load live prices, then open Returns.

### Transactions
Full raw CSV data — all rows, sortable by any column, filterable per column, paginated 50 rows at a time.

---

## How Prices Work

1. Browser sends `GET /prices?isins=US0378331005,CH0012221716,...`
2. `server.py` resolves each ISIN to a Yahoo Finance ticker via `yf.Search()`
3. Fetches `fast_info.last_price` and `fast_info.currency`
4. Converts to CHF using live USDCHF/EURCHF/GBPCHF rates
5. Returns JSON, cached for 5 minutes

**GBX (pence):** automatically divided by 100 before CHF conversion.

**ISIN overrides:** some ISINs (e.g. Alphabet `US02079K3059`) are not found by Yahoo Search. Add them to `ISIN_OVERRIDES` in `server.py`:
```python
ISIN_OVERRIDES = {
    'US02079K3059': 'GOOGL',   # Alphabet — Yahoo Search returns []
}
```

---

## How CHF Conversion Works for Purchases

DEGIRO creates 4 rows per trade in the CSV:

| Row | Description |
|-----|-------------|
| Buy | `Buy 1 Apple Inc@226.40 USD` — the trade itself |
| FX Credit | USD credited to account |
| FX Debit | CHF debited from account ← actual CHF cost |
| Fee | DEGIRO transaction fee in CHF |

The dashboard reads the **FX Debit** row for the true CHF cost. For CHF-denominated stocks (e.g. Novartis), there is no FX row — the Buy row itself carries the CHF amount.

**Total CHF Invested = FX Debit amount + Fee**

> **Note:** DEGIRO uses Swiss number format with `'` (U+2019 curly apostrophe) as thousands separator in descriptions, e.g. `@1'074.2 USD`. The parser handles this automatically.

---

## How XIRR Works

XIRR is the annualised interest rate that makes the net present value of all your cash flows equal to zero. It is the same metric used by professional fund managers.

**Cash flows per asset:**
- Each purchase → negative (money leaving your pocket), on the actual purchase date
- Each dividend received → positive, on the actual payment date
- Current market value → positive, today's date

**Example:**
- Bought Apple for CHF 202 on 13-Nov-2024
- Received CHF 1.20 dividend on 15-Feb-2025
- Apple is worth CHF 285 today
- XIRR = the annual rate that makes these flows balance = **~38%**

The portfolio-level XIRR combines all assets into one number — equivalent to asking: *"if I had put all this money in a bank FD instead, what interest rate would give me the same result?"*

---

## How Dividends Work

DEGIRO records dividends in the original currency (USD, EUR, etc.) alongside FX conversion rows. The dashboard:

1. Builds an FX rate map from actual `FX Debit/Credit` rows in the CSV
2. Converts each dividend to CHF: `CHF = foreign_amount / rate`
   (rate means: 1 CHF = rate units of foreign currency)
3. Pairs each dividend with its withholding tax row

---

## Updating Your Data

1. Download a new `Account.csv` from DEGIRO
2. Replace the existing file in the folder
3. Reload the browser tab

That's it. No code changes, no imports, no configuration.

---

## Known Limitations

- Prices are delayed (Yahoo Finance free tier — typically 15 min delay)
- `yfinance` may occasionally fail for certain ISINs — add them to `ISIN_OVERRIDES`
- Sold positions are not yet filtered out of the Portfolio and Returns tabs
- XIRR requires Portfolio tab to be opened first (to load live prices)
- No historical portfolio value chart
