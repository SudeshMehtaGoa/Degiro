"""
Local data server for the DEGIRO dashboard.
Run: python server.py   OR double-click start.bat

Requires:  pip install yfinance
"""
import sys
import os

sys.stdout.reconfigure(encoding='utf-8')   # Windows cp1252 fix — allow → ✓ … in print()

# On Windows, Python / curl_cffi don't use the Windows certificate store by default.
# Export Windows trusted root CAs to a PEM file next to this script, then point
# both the standard ssl module and curl_cffi (used by yfinance 1.4+) at it.
_WIN_CERTS = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'win_certs.pem')
if os.path.exists(_WIN_CERTS):
    os.environ.setdefault('SSL_CERT_FILE',   _WIN_CERTS)
    os.environ.setdefault('CURL_CA_BUNDLE',  _WIN_CERTS)
    os.environ.setdefault('REQUESTS_CA_BUNDLE', _WIN_CERTS)

import http.server
import socketserver
import webbrowser
import json
import urllib.parse
import time

PORTS     = [8081, 8082, 8083, 9000, 9001]
DIR       = os.path.dirname(os.path.abspath(__file__))
CACHE_TTL = 300   # seconds — prices refreshed every 5 min

_price_cache = {}
_cache_ts    = {}
SKIP_ISINS   = {'NLFLATEXACNT'}

_history_cache    = None
_history_cache_ts = 0
HISTORY_CACHE_TTL = 3600   # 1 hour — weekly history data changes slowly

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
        print(f'  [search] {isin} →{sym} (override)')
        return sym
    try:
        results = yf.Search(isin, max_results=10).quotes
        print(f'  [search] {isin} →{[q.get("symbol") + "(" + q.get("quoteType","?") + ")" for q in results]}')
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
    if currency == 'GBX':           # pence →GBP →CHF
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
        elif self.path.startswith('/benchmark'):
            self.handle_benchmark()
        elif self.path.startswith('/history'):
            self.handle_history()
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
                        print(f'  {isin} →NOT FOUND')
                    else:
                        price, ccy = fetch_price(sym)
                        if price is None:
                            entry = {'error': f'no price returned for {sym}'}
                            print(f'  {isin} →{sym}: no price')
                        else:
                            p_chf = to_chf(price, ccy, fx)
                            entry = {
                                'symbol'  : sym,
                                'price'   : round(price, 4),
                                'currency': ccy,
                                'priceChf': round(p_chf, 4) if p_chf else None,
                            }
                            print(f'  {isin} →{sym}: {price:.2f} {ccy} = CHF {p_chf:.2f}')

                    result[isin]       = entry
                    _price_cache[isin] = entry
                    _cache_ts[isin]    = now

            except Exception as e:
                print(f'  [prices] ERROR: {e}')
                for isin in to_fetch:
                    if isin not in result:
                        result[isin] = {'error': str(e)}

        self._json(result, 200)

    def handle_benchmark(self):
        if yf is None:
            self._json({'error': 'yfinance not installed'}, 503)
            return

        parsed    = urllib.parse.urlparse(self.path)
        params    = urllib.parse.parse_qs(parsed.query)
        from_date = params.get('from', [''])[0]   # YYYY-MM-DD
        if not from_date:
            self._json({'error': 'missing from= parameter'}, 400)
            return

        BENCHMARKS = {
            'SPY'  : 'S&P 500',
            '^SSMI': 'SMI (Swiss)',
            'URTH' : 'MSCI World',
        }

        import datetime
        result = {}
        print(f'\n[benchmark] from={from_date}')
        for symbol, name in BENCHMARKS.items():
            try:
                hist = yf.Ticker(symbol).history(start=from_date)
                if hist.empty:
                    result[symbol] = {'name': name, 'error': 'no data'}
                    continue
                start_price = float(hist['Close'].iloc[0])
                end_price   = float(hist['Close'].iloc[-1])
                start_dt    = hist.index[0].to_pydatetime()
                end_dt      = hist.index[-1].to_pydatetime()
                years       = max((end_dt - start_dt).days / 365.25, 1/365)
                cagr        = (end_price / start_price) ** (1 / years) - 1
                total_ret   = (end_price / start_price) - 1
                result[symbol] = {
                    'name'       : name,
                    'cagr'       : round(cagr, 6),
                    'totalReturn': round(total_ret, 6),
                    'startPrice' : round(start_price, 4),
                    'endPrice'   : round(end_price, 4),
                    'startDate'  : start_dt.strftime('%Y-%m-%d'),
                    'endDate'    : end_dt.strftime('%Y-%m-%d'),
                }
                print(f'  {symbol}: {start_price:.2f} →{end_price:.2f}  CAGR={cagr*100:.2f}%')
            except Exception as e:
                result[symbol] = {'name': name, 'error': str(e)}
                print(f'  {symbol}: ERROR {e}')

        self._json(result, 200)

    def handle_history(self):
        global _history_cache, _history_cache_ts
        if yf is None:
            self._json({'error': 'yfinance not installed'}, 503)
            return

        parsed    = urllib.parse.urlparse(self.path)
        params    = urllib.parse.parse_qs(parsed.query)
        raw       = params.get('isins', [''])[0]
        from_date = params.get('from', [''])[0]

        isins = [i.strip() for i in raw.split(',')
                 if i.strip() and i.strip() not in SKIP_ISINS]
        if not from_date or not isins:
            self._json({'error': 'missing isins= or from= parameter'}, 400)
            return

        # Serve from cache if key matches and still fresh
        now       = time.time()
        cache_key = f'{from_date}:{",".join(sorted(isins))}'
        if (_history_cache and
                _history_cache.get('_key') == cache_key and
                (now - _history_cache_ts) < HISTORY_CACHE_TTL):
            print('[history] serving from cache')
            self._json(_history_cache, 200)
            return

        print(f'\n[history] from={from_date}, {len(isins)} ISINs')
        result = {'stocks': {}, 'fx': {}, '_key': cache_key}

        # Weekly FX history (USDCHF, EURCHF, GBPCHF)
        for pair, ccy in [('USDCHF=X', 'USD'), ('EURCHF=X', 'EUR'), ('GBPCHF=X', 'GBP')]:
            try:
                hist = yf.Ticker(pair).history(start=from_date, interval='1wk')
                if not hist.empty:
                    result['fx'][ccy] = {
                        'dates': [d.strftime('%Y-%m-%d') for d in hist.index],
                        'rates': [round(float(p), 6) for p in hist['Close']],
                    }
                    print(f'  [fx] {ccy}: {len(hist)} weeks')
            except Exception as e:
                print(f'  [history] FX {pair}: {e}')

        # Weekly stock history for each ISIN
        for isin in isins:
            sym = isin_to_symbol(isin)
            if not sym:
                result['stocks'][isin] = {'error': 'symbol not found'}
                continue
            try:
                ticker = yf.Ticker(sym)
                hist   = ticker.history(start=from_date, interval='1wk')
                try:
                    ccy = ticker.fast_info.currency or 'USD'
                except Exception:
                    ccy = 'USD'
                if hist.empty:
                    result['stocks'][isin] = {'error': 'no data', 'symbol': sym}
                else:
                    result['stocks'][isin] = {
                        'symbol'  : sym,
                        'currency': ccy,
                        'dates'   : [d.strftime('%Y-%m-%d') for d in hist.index],
                        'prices'  : [round(float(p), 4) for p in hist['Close']],
                    }
                    print(f'  {isin} →{sym} ({ccy}): {len(hist)} weeks')
            except Exception as e:
                result['stocks'][isin] = {'error': str(e), 'symbol': sym}
                print(f'  {isin} →{sym}: ERROR {e}')

        _history_cache    = result
        _history_cache_ts = now
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
