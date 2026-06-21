"""
Local data server for the DEGIRO dashboard.
Run: python server.py   OR double-click start.bat

Requires:  pip install yfinance
"""
import http.server
import socketserver
import webbrowser
import os
import json
import urllib.parse
import time

PORTS     = [8081, 8082, 8083, 9000, 9001]
DIR       = os.path.dirname(os.path.abspath(__file__))
CACHE_TTL = 300   # seconds — prices refreshed every 5 min

_price_cache = {}
_cache_ts    = {}
SKIP_ISINS   = {'NLFLATEXACNT'}

# ISINs that Yahoo Finance search cannot resolve — add more here as needed
ISIN_OVERRIDES = {
    'US02079K3059': 'GOOGL',   # Alphabet Inc Class A
}

# ── yfinance ─────────────────────────────────────────────
try:
    import yfinance as yf
    print('yfinance loaded OK')
except ImportError:
    yf = None
    print('WARNING: yfinance not installed — run:  pip install yfinance')


def isin_to_symbol(isin):
    """Resolve ISIN to Yahoo Finance ticker symbol."""
    # Use hardcoded override if Yahoo search can't find it
    if isin in ISIN_OVERRIDES:
        sym = ISIN_OVERRIDES[isin]
        print(f'  [search] {isin} → {sym} (override)')
        return sym
    try:
        results = yf.Search(isin, max_results=10).quotes
        print(f'  [search] {isin} → {[q.get("symbol") + "(" + q.get("quoteType","?") + ")" for q in results]}')
        for q in results:
            if q.get('quoteType', '').upper() in ('EQUITY', 'ETF', 'MUTUALFUND'):
                return q['symbol']
        if results:
            return results[0]['symbol']
    except Exception as e:
        print(f'  [search] {isin}: {e}')
    return None


def fetch_price(symbol):
    """Return (price, currency) for a Yahoo ticker symbol."""
    try:
        info = yf.Ticker(symbol).fast_info
        return info.last_price, info.currency
    except Exception as e:
        print(f'  [quote] {symbol}: {e}')
        return None, None


def fetch_fx():
    """Return CHF conversion rates: {USD: x, EUR: x, GBP: x}."""
    rates = {'CHF': 1.0}
    for pair, key in [('USDCHF=X', 'USD'), ('EURCHF=X', 'EUR'), ('GBPCHF=X', 'GBP')]:
        try:
            p, _ = fetch_price(pair)
            if p:
                rates[key] = p
        except Exception:
            pass
    rates.setdefault('USD', 0.89)
    rates.setdefault('EUR', 0.95)
    rates.setdefault('GBP', 1.12)
    return rates


def to_chf(price, currency, fx):
    if currency == 'CHF':
        return price
    if currency == 'GBX':           # pence → GBP → CHF
        return price / 100 * fx.get('GBP', 1.12)
    rate = fx.get(currency)
    return price * rate if rate else None


# ── HTTP handler ─────────────────────────────────────────
class Handler(http.server.SimpleHTTPRequestHandler):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=DIR, **kwargs)

    def log_message(self, fmt, *args):
        print(f'  [{self.command}] {self.path}')   # log every request

    def do_GET(self):
        if self.path.startswith('/prices'):
            self.handle_prices()
        else:
            super().do_GET()

    def handle_prices(self):
        if yf is None:
            self._json({'error': 'yfinance not installed — run: pip install yfinance'}, 503)
            return

        parsed = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(parsed.query)
        raw    = params.get('isins', [''])[0]
        isins  = [i.strip() for i in raw.split(',')
                  if i.strip() and i.strip() not in SKIP_ISINS]

        now      = time.time()
        result   = {}
        to_fetch = []

        for isin in isins:
            if isin in _price_cache and (now - _cache_ts.get(isin, 0)) < CACHE_TTL:
                result[isin] = _price_cache[isin]
            else:
                to_fetch.append(isin)

        if to_fetch:
            print(f'\n[prices] fetching {len(to_fetch)} ISINs…')
            try:
                fx = fetch_fx()
                print(f'  [fx] USD={fx.get("USD"):.4f}  EUR={fx.get("EUR"):.4f}')

                for isin in to_fetch:
                    sym = isin_to_symbol(isin)
                    if not sym:
                        entry = {'error': 'symbol not found'}
                        print(f'  {isin} → NOT FOUND')
                    else:
                        price, ccy = fetch_price(sym)
                        if price is None:
                            entry = {'error': f'no price returned for {sym}'}
                            print(f'  {isin} → {sym}: no price')
                        else:
                            p_chf = to_chf(price, ccy, fx)
                            entry = {
                                'symbol'  : sym,
                                'price'   : round(price, 4),
                                'currency': ccy,
                                'priceChf': round(p_chf, 4) if p_chf else None,
                            }
                            print(f'  {isin} → {sym}: {price:.2f} {ccy} = CHF {p_chf:.2f}')

                    result[isin]       = entry
                    _price_cache[isin] = entry
                    _cache_ts[isin]    = now

            except Exception as e:
                print(f'  [prices] ERROR: {e}')
                for isin in to_fetch:
                    if isin not in result:
                        result[isin] = {'error': str(e)}

        self._json(result, 200)

    def _json(self, data, status):
        body = json.dumps(data).encode()
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)


# ── Start ─────────────────────────────────────────────────
if __name__ == '__main__':
    os.chdir(DIR)
    for PORT in PORTS:
        try:
            httpd = socketserver.TCPServer(('', PORT), Handler)
            break
        except OSError:
            print(f'Port {PORT} busy, trying next…')
    else:
        print('ERROR: Could not bind to any port.')
        input('Press Enter to exit.')
        raise SystemExit(1)

    url = f'http://localhost:{PORT}/dashboard.html'
    print(f'DEGIRO Dashboard  →  {url}')
    print('Press Ctrl+C to stop.\n')
    webbrowser.open(url)
    with httpd:
        httpd.serve_forever()
