# DEGIRO Investment Dashboard

A local, self-hosted investment dashboard for DEGIRO brokerage accounts. Drop in your exported `Account.csv` and get a live multi-tab view of your portfolio — with real-time prices, dividend tracking, and total return calculations.

---

## Features

| Tab | What it shows |
|-----|---------------|
| **Portfolio** | Holdings, total CHF invested, dividends received, live prices, total return |
| **Purchases** | One clean row per buy trade — units, price, fees, total CHF paid |
| **Dividends** | Every dividend event converted to CHF using actual DEGIRO FX rates |
| **Dividend Summary** | Net dividend received per asset (after tax) |
| **Transactions** | Full raw CSV — sortable, filterable, paginated |

- Live prices fetched from Yahoo Finance via `yfinance`
- All foreign currencies (USD, EUR, GBX) converted to CHF
- Total Return = Capital Gain + Dividends Received
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
                   • parses and renders all 5 tabs in the browser
                   • calls /prices for live data
```

**Key design principle:** `Account.csv` is a pure data source. To update your dashboard, just download a new CSV from DEGIRO and replace the file — no code changes needed.

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Runtime | Python 3.x |
| HTTP server | `http.server` + `socketserver` (Python stdlib) |
| Live prices | [`yfinance`](https://github.com/ranaroussi/yfinance) |
| Frontend | Vanilla HTML + CSS + JavaScript (no frameworks) |
| Charting | None — pure HTML tables |
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
├── dashboard.html   # Full frontend (single file)
├── start.bat        # Windows launcher
├── Account.csv      # Your DEGIRO export (gitignored, never committed)
└── .gitignore
```

---

## How Prices Work

1. Browser sends `GET /prices?isins=US0378331005,CH0012221716,...`
2. `server.py` resolves each ISIN to a Yahoo Finance ticker via `yf.Search()`
3. Fetches `fast_info.last_price` and `fast_info.currency`
4. Converts to CHF using live USDCHF/EURCHF/GBPCHF rates
5. Returns JSON, cached for 5 minutes

**GBX (pence):** automatically divided by 100 before CHF conversion.

**ISIN overrides:** some ISINs (e.g. Alphabet `US02079K3059`) aren't found by Yahoo Search. Add them to `ISIN_OVERRIDES` in `server.py`:
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
| FX Debit | CHF debited from account ← this is the actual CHF cost |
| Fee | DEGIRO transaction fee in CHF |

The dashboard reads the **FX Debit** row for the true CHF cost. For CHF-denominated stocks (e.g. Novartis), there is no FX row — the Buy row itself carries the CHF amount.

**Total CHF Invested = FX Debit amount + Fee**

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
- Sold positions are not yet filtered out of the Portfolio tab
- No historical portfolio value chart
