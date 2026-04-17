#!/usr/bin/env python3
"""
Currency Converter Web App
==========================
A minimal Flask web app that wraps the Danmarks Nationalbank exchange rate API.
Run with:  python app.py
Then open: http://localhost:5000
"""

from flask import Flask, jsonify, request, send_from_directory
import json
import urllib.request
import urllib.error
from datetime import datetime, timedelta
import os

app = Flask(__name__)

# ── API Configuration ─────────────────────────────────────────────────────────
API_BASE = "https://api.statbank.dk/v1"
TABLE = "DNVALD"


# ── Helpers (from currency_converter.py) ──────────────────────────────────────

def api_post(endpoint: str, payload: dict, timeout: int = 30) -> bytes:
    url = f"{API_BASE}/{endpoint}"
    data = json.dumps(payload).encode("utf-8")
    print(f"[DEBUG] POST {url}")
    print(f"[DEBUG] Payload: {data.decode('utf-8')}")
    req = urllib.request.Request(
        url, data=data, headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read()
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        print(f"[DEBUG] HTTP {e.code} response: {body}")
        raise


def discover_variables() -> dict:
    raw = api_post("tableinfo", {"table": TABLE, "lang": "en"})
    info = json.loads(raw.decode("utf-8"))
    result = {}

    for var in info.get("variables", []):
        vid = var["id"]
        text = var.get("text", "").lower()
        values = var.get("values", [])
        time_flag = var.get("time", False)

        if time_flag or "tid" in vid.lower() or "time" in text or "date" in text:
            result["time_var"] = vid
        elif "valuta" in vid.lower() or "currency" in text:
            result["currency_var"] = vid
            result["currency_map"] = {v["id"]: v["text"] for v in values}
        elif "typ" in vid.lower() or "type" in text:
            result["type_var"] = vid
            for v in values:
                t = v["text"].lower()
                if "exchange rate" in t or "kurs" in t or "dkk per 100" in t:
                    result["rate_type_id"] = v["id"]
                    break
            if "rate_type_id" not in result and values:
                result["rate_type_id"] = values[0]["id"]

    for key in ("currency_var", "type_var", "time_var", "rate_type_id"):
        if key not in result:
            raise RuntimeError(f"Could not find '{key}' in table metadata.")
    return result


def fetch_rate(meta, currency_code, dt):
    date_code = f"{dt.year}M{dt.month:02d}D{dt.day:02d}"
    variables = [
        {"code": meta["currency_var"], "values": [currency_code]},
        {"code": meta["type_var"], "values": [meta["rate_type_id"]]},
        {"code": meta["time_var"], "values": [date_code]},
    ]
    payload = {
        "table": TABLE,
        "format": "CSV",
        "lang": "en",
        "variables": variables,
    }
    try:
        raw = api_post("data", payload)
    except urllib.error.HTTPError as e:
        if e.code == 400:
            raise RuntimeError("NO_RATE")
        raise
    csv_text = raw.decode("utf-8")

    lines = [l for l in csv_text.strip().splitlines() if l.strip()]
    if len(lines) < 2:
        raise RuntimeError("No data rows in API response.")

    value_str = lines[1].split(";")[-1].strip().strip('"')
    if value_str in ("", "..", "-"):
        raise RuntimeError("NO_RATE")

    return float(value_str.replace(",", "."))


# ── Cache for metadata (avoid repeated API calls) ────────────────────────────
_meta_cache = {}


def get_meta():
    if "meta" not in _meta_cache:
        _meta_cache["meta"] = discover_variables()
    return _meta_cache["meta"]


# ── Routes ────────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return send_from_directory(
        os.path.dirname(os.path.abspath(__file__)), "index.html"
    )


import re

# ── Crypto: Top 20 coins (CryptoCompare uses ticker symbols directly) ─────────
CRYPTO_COINS = [
    {"symbol": "BTC",  "name": "Bitcoin"},
    {"symbol": "ETH",  "name": "Ethereum"},
    {"symbol": "USDT", "name": "Tether"},
    {"symbol": "BNB",  "name": "BNB"},
    {"symbol": "SOL",  "name": "Solana"},
    {"symbol": "XRP",  "name": "XRP"},
    {"symbol": "USDC", "name": "USD Coin"},
    {"symbol": "ADA",  "name": "Cardano"},
    {"symbol": "DOGE", "name": "Dogecoin"},
    {"symbol": "TRX",  "name": "TRON"},
    {"symbol": "AVAX", "name": "Avalanche"},
    {"symbol": "DOT",  "name": "Polkadot"},
    {"symbol": "LINK", "name": "Chainlink"},
    {"symbol": "TON",  "name": "Toncoin"},
    {"symbol": "SHIB", "name": "Shiba Inu"},
    {"symbol": "XLM",  "name": "Stellar"},
    {"symbol": "BCH",  "name": "Bitcoin Cash"},
    {"symbol": "LTC",  "name": "Litecoin"},
    {"symbol": "POL",  "name": "Polygon"},
    {"symbol": "UNI",  "name": "Uniswap"},
]

CRYPTOCOMPARE_BASE = "https://min-api.cryptocompare.com/data/v2"


def fetch_crypto_price_usd(symbol: str, dt: datetime) -> float:
    """Fetch historical daily close price in USD from CryptoCompare."""
    # Convert date to UNIX timestamp (end of that day)
    ts = int(dt.replace(hour=23, minute=59, second=59).timestamp())
    url = f"{CRYPTOCOMPARE_BASE}/histoday?fsym={symbol}&tsym=USD&limit=1&toTs={ts}"
    print(f"[DEBUG] GET {url}")
    req = urllib.request.Request(url, headers={
        "Accept": "application/json",
        "User-Agent": "CurrencyConverterDK/1.0",
    })
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        print(f"[DEBUG] CryptoCompare HTTP {e.code}: {body}")
        raise RuntimeError(f"CryptoCompare error: HTTP {e.code}")

    if data.get("Response") == "Error":
        raise RuntimeError(f"CryptoCompare: {data.get('Message', 'Unknown error')}")

    try:
        # histoday returns an array; the last entry is the requested date
        day_data = data["Data"]["Data"][-1]
        close_price = day_data["close"]
        if close_price == 0:
            raise RuntimeError(f"No price data for {symbol} on {dt.strftime('%d.%m.%Y')}")
        return close_price
    except (KeyError, TypeError, IndexError):
        raise RuntimeError(f"No price data for {symbol} on {dt.strftime('%d.%m.%Y')}")


def is_active_currency(name: str) -> bool:
    """Active currencies have an open-ended date range ending with '-)' ."""
    return bool(re.search(r"-\s*\)\s*$", name))


def clean_currency_name(name: str) -> str:
    """Strip the date range from the name, e.g. 'Euro  (Jan. 1999-)' → 'Euro'."""
    return re.sub(r"\s*\(.*\)\s*$", "", name).strip()


@app.route("/api/currencies")
def currencies():
    try:
        meta = get_meta()
        items = [
            {"code": code, "name": clean_currency_name(name)}
            for code, name in sorted(meta["currency_map"].items())
            if is_active_currency(name) and code != "DKK"
        ]
        return jsonify(items)
    except Exception as e:
        print(f"[ERROR] /api/currencies failed: {e}")
        _meta_cache.clear()
        return jsonify({"error": str(e)}), 500


@app.route("/api/convert")
def convert():
    date_str = request.args.get("date", "")
    amount_str = request.args.get("amount", "")
    currency = request.args.get("currency", "").upper().strip()

    # Parse date (expects YYYY-MM-DD from HTML date input)
    try:
        dt = datetime.strptime(date_str, "%Y-%m-%d")
    except ValueError:
        return jsonify({"error": f"Invalid date: {date_str}"}), 400

    try:
        amount = float(amount_str)
    except (ValueError, TypeError):
        return jsonify({"error": f"Invalid amount: {amount_str}"}), 400

    if not currency:
        return jsonify({"error": "Currency is required."}), 400

    try:
        meta = get_meta()
    except Exception as e:
        return jsonify({"error": f"Could not reach Nationalbanken API: {e}"}), 502

    # Resolve currency
    if currency not in meta["currency_map"]:
        found = None
        for vid, desc in meta["currency_map"].items():
            if currency in vid.upper() or currency in desc.upper():
                found = vid
                break
        if not found:
            return jsonify({"error": f"Unknown currency: {currency}"}), 400
        currency = found

    currency_name = meta["currency_map"].get(currency, currency)

    # Fetch rate
    try:
        rate = fetch_rate(meta, currency, dt)
    except RuntimeError as e:
        if "NO_RATE" in str(e):
            hint = ""
            wd = dt.weekday()
            if wd == 5:
                fri = dt - timedelta(days=1)
                hint = f" Try {fri.strftime('%d.%m.%Y')} (Friday) instead."
            elif wd == 6:
                fri = dt - timedelta(days=2)
                hint = f" Try {fri.strftime('%d.%m.%Y')} (Friday) instead."
            else:
                hint = " This may be a Danish public holiday."
            return jsonify({
                "error": f"No rate published for {dt.strftime('%d %B %Y')}.{hint}"
            }), 404
        return jsonify({"error": str(e)}), 500

    unit_rate = rate / 100.0
    dkk = amount * unit_rate

    return jsonify({
        "amount": amount,
        "currency_code": currency,
        "currency_name": currency_name,
        "date": dt.strftime("%d %B %Y"),
        "rate_per_100": round(rate, 4),
        "rate_per_unit": round(unit_rate, 4),
        "result_dkk": round(dkk, 2),
        "source": "Danmarks Nationalbank (DNVALD)",
    })


@app.route("/api/crypto/coins")
def crypto_coins():
    return jsonify(CRYPTO_COINS)


@app.route("/api/crypto/convert")
def crypto_convert():
    coin_symbol = request.args.get("coin", "").strip().upper()
    date_str = request.args.get("date", "").strip()
    amount_str = request.args.get("amount", "").strip()

    # Validate coin
    coin = next((c for c in CRYPTO_COINS if c["symbol"] == coin_symbol), None)
    if not coin:
        return jsonify({"error": f"Unknown coin: {coin_symbol}"}), 400

    # Parse date (DD.MM.YYYY)
    date_parts = date_str.split(".")
    if len(date_parts) != 3:
        return jsonify({"error": f"Invalid date: {date_str}. Use DD.MM.YYYY"}), 400
    try:
        dt = datetime(int(date_parts[2]), int(date_parts[1]), int(date_parts[0]))
    except (ValueError, IndexError):
        return jsonify({"error": f"Invalid date: {date_str}"}), 400

    # Amount is already converted to standard decimal format by the frontend
    try:
        amount = float(amount_str)
    except ValueError:
        return jsonify({"error": f"Invalid amount: {request.args.get('amount')}"}), 400

    # 1. Fetch crypto price in USD from CryptoCompare
    try:
        price_usd = fetch_crypto_price_usd(coin_symbol, dt)
    except RuntimeError as e:
        return jsonify({"error": str(e)}), 404

    total_usd = amount * price_usd

    # 2. Fetch USD → DKK rate from Nationalbanken
    #    If the exact date has no rate (weekend/holiday), try previous days
    try:
        meta = get_meta()
    except Exception as e:
        return jsonify({"error": f"Could not reach Nationalbanken API: {e}"}), 502

    usd_rate = None
    rate_date = dt
    for offset in range(0, 5):
        try_date = dt - timedelta(days=offset)
        try:
            usd_rate = fetch_rate(meta, "USD", try_date)
            rate_date = try_date
            break
        except RuntimeError:
            continue

    if usd_rate is None:
        return jsonify({"error": f"Could not find USD exchange rate near {date_str}"}), 404

    usd_dkk = usd_rate / 100.0
    total_dkk = total_usd * usd_dkk

    return jsonify({
        "coin": coin["symbol"],
        "coin_name": coin["name"],
        "date": date_str,
        "amount": amount,
        "price_usd": round(price_usd, 6),
        "total_usd": round(total_usd, 2),
        "usd_dkk_rate": round(usd_rate, 4),
        "usd_dkk_rate_date": rate_date.strftime("%d.%m.%Y"),
        "total_dkk": round(total_dkk, 2),
        "source_price": "CryptoCompare",
        "source_rate": "Danmarks Nationalbank (DNVALD)",
    })


@app.route("/api/convert-bulk", methods=["POST"])
def convert_bulk():
    """Accept multiple lines of 'Date; Currency; Amount' and return all results."""
    body = request.get_json(silent=True) or {}
    csv_input = body.get("lines", "")

    try:
        meta = get_meta()
    except Exception as e:
        return jsonify({"error": f"Could not reach API: {e}"}), 502

    results = []
    for raw_line in csv_input.strip().splitlines():
        line = raw_line.strip()
        if not line:
            continue

        # Parse: "DD.MM.YYYY; CUR; amount" or "DD.MM.YYYY; CUR amount"
        # Split on semicolons first
        parts = [p.strip() for p in line.split(";")]

        if len(parts) == 3:
            date_str, currency_str, amount_str = parts
        elif len(parts) == 2:
            # Currency and amount might be in the second part: "CHF 144,50"
            date_str = parts[0]
            rest = parts[1].strip().split()
            if len(rest) == 2:
                currency_str, amount_str = rest
            else:
                results.append({"input": line, "error": "Could not parse line"})
                continue
        else:
            results.append({"input": line, "error": "Could not parse line"})
            continue

        # Parse date DD.MM.YYYY
        date_parts = date_str.strip().split(".")
        if len(date_parts) != 3:
            results.append({"input": line, "error": f"Invalid date: {date_str}"})
            continue
        try:
            dt = datetime(int(date_parts[2]), int(date_parts[1]), int(date_parts[0]))
        except (ValueError, IndexError):
            results.append({"input": line, "error": f"Invalid date: {date_str}"})
            continue

        # Parse amount (European format: comma as decimal separator)
        amount_str = amount_str.strip().replace(".", "").replace(",", ".")
        try:
            amount = float(amount_str)
        except ValueError:
            results.append({"input": line, "error": f"Invalid amount: {parts[-1]}"})
            continue

        # Resolve currency
        currency = currency_str.upper().strip()
        if currency not in meta["currency_map"]:
            found = None
            for vid, desc in meta["currency_map"].items():
                if currency in vid.upper() or currency in desc.upper():
                    found = vid
                    break
            if not found:
                results.append({"input": line, "error": f"Unknown currency: {currency}"})
                continue
            currency = found

        # Fetch rate
        try:
            rate = fetch_rate(meta, currency, dt)
        except RuntimeError:
            results.append({
                "input": line,
                "error": f"No rate for {currency} on {date_str}",
            })
            continue

        unit_rate = rate / 100.0
        dkk = amount * unit_rate

        results.append({
            "date": date_str.strip(),
            "currency": currency,
            "amount": amount,
            "rate_per_100": round(rate, 4),
            "result_dkk": round(dkk, 2),
        })

    return jsonify(results)


@app.route("/api/crypto/convert-bulk", methods=["POST"])
def crypto_convert_bulk():
    """Accept multiple lines of 'Date; Coin; Amount' and return all results."""
    body = request.get_json(silent=True) or {}
    csv_input = body.get("lines", "")

    try:
        meta = get_meta()
    except Exception as e:
        return jsonify({"error": f"Could not reach API: {e}"}), 502

    # Build lookup for coin symbols and names
    coin_lookup = {}
    for c in CRYPTO_COINS:
        coin_lookup[c["symbol"].upper()] = c
        coin_lookup[c["name"].upper()] = c

    results = []
    for raw_line in csv_input.strip().splitlines():
        line = raw_line.strip()
        if not line:
            continue

        # Parse: "DD.MM.YYYY; COIN; amount" or "DD.MM.YYYY; COIN amount"
        parts = [p.strip() for p in line.split(";")]

        if len(parts) == 3:
            date_str, coin_str, amount_str = parts
        elif len(parts) == 2:
            date_str = parts[0]
            rest = parts[1].strip().split()
            if len(rest) == 2:
                coin_str, amount_str = rest
            else:
                results.append({"input": line, "error": "Could not parse line"})
                continue
        else:
            results.append({"input": line, "error": "Could not parse line"})
            continue

        # Parse date DD.MM.YYYY
        date_parts = date_str.strip().split(".")
        if len(date_parts) != 3:
            results.append({"input": line, "error": f"Invalid date: {date_str}"})
            continue
        try:
            dt = datetime(int(date_parts[2]), int(date_parts[1]), int(date_parts[0]))
        except (ValueError, IndexError):
            results.append({"input": line, "error": f"Invalid date: {date_str}"})
            continue

        # Parse amount (European format: comma decimal, dot thousands)
        amount_str = amount_str.strip().replace(".", "").replace(",", ".")
        try:
            amount = float(amount_str)
        except ValueError:
            results.append({"input": line, "error": f"Invalid amount: {parts[-1]}"})
            continue

        # Resolve coin
        coin = coin_lookup.get(coin_str.upper().strip())
        if not coin:
            results.append({"input": line, "error": f"Unknown coin: {coin_str}"})
            continue

        # Fetch crypto price in USD
        try:
            price_usd = fetch_crypto_price_usd(coin["symbol"], dt)
        except RuntimeError as e:
            results.append({"input": line, "error": str(e)})
            continue

        total_usd = amount * price_usd

        # Fetch USD → DKK rate (try up to 5 days back for weekends/holidays)
        usd_rate = None
        for offset in range(0, 5):
            try_date = dt - timedelta(days=offset)
            try:
                usd_rate = fetch_rate(meta, "USD", try_date)
                break
            except RuntimeError:
                continue

        if usd_rate is None:
            results.append({"input": line, "error": f"No USD rate near {date_str}"})
            continue

        usd_dkk = usd_rate / 100.0
        total_dkk = total_usd * usd_dkk

        results.append({
            "date": date_str.strip(),
            "coin": coin["symbol"],
            "amount": amount,
            "price_usd": round(price_usd, 6),
            "total_usd": round(total_usd, 2),
            "usd_dkk_rate": round(usd_rate, 4),
            "total_dkk": round(total_dkk, 2),
        })

    return jsonify(results)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    print("Starting Currency Converter web app...")
    print(f"Open http://localhost:{port} in your browser")
    app.run(debug=True, host="0.0.0.0", port=port)
