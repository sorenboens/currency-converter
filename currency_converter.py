#!/usr/bin/env python3
"""
Currency Converter — Danmarks Nationalbank daily exchange rates (DNVALD)
========================================================================

Fetches official daily exchange rates from the Nationalbanken Statistikbank
and converts a foreign currency amount into DKK.

USAGE
-----
    python currency_converter.py <date> <amount> <currency>

FORMAT
------
    Date:      DD.MM.YYYY   (leading zeros optional, e.g. 3.4.2025)
    Amount:    number        (e.g. 145 or 1234.56 — use dot for decimals)
    Currency:  ISO 4217 code (e.g. CHF, USD, EUR, GBP, SEK, NOK, JPY …)

EXAMPLES
--------
    python currency_converter.py 3.4.2025 145 CHF
    python currency_converter.py 15.01.2024 1000 USD
    python currency_converter.py 28.02.2025 500 EUR

LIST CURRENCIES
---------------
    python currency_converter.py --list

NOTE
----
    Rates are only published on Danish banking days (Mon–Fri, excl. holidays).
    If you request a weekend or holiday, the script will tell you and suggest
    the nearest Friday.

Source: Danmarks Nationalbank — https://nationalbanken.statistikbank.dk/DNVALD
"""

import sys
import json
import urllib.request
import urllib.error
from datetime import datetime, timedelta

# ── API Configuration ──────────────────────────────────────────────────────────
# The Nationalbanken Statbank uses the same PxWeb / Statbank API as DST.
# Base URL pattern: <domain>/statbank5a/api/v1/<function>

API_BASE = "https://api.statbank.dk/v1"
TABLE = "DNVALD"


# ── Helpers ────────────────────────────────────────────────────────────────────

def api_post(endpoint: str, payload: dict, timeout: int = 30) -> bytes:
    """POST JSON to the Statbank API and return raw response bytes."""
    url = f"{API_BASE}/{endpoint}"
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url, data=data, headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read()
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"API HTTP {e.code}: {body}")
    except urllib.error.URLError as e:
        raise RuntimeError(
            f"Cannot reach the Nationalbanken API ({url}).\n"
            f"Check your internet connection.\nDetails: {e.reason}"
        )


def fetch_table_info() -> dict:
    """Return DNVALD table metadata (variables and their value codes)."""
    raw = api_post("tableinfo", {"table": TABLE, "lang": "en"})
    return json.loads(raw.decode("utf-8"))


def fetch_data_csv(variables: list[dict]) -> str:
    """Fetch data from DNVALD in semicolon-separated CSV format."""
    payload = {
        "table": TABLE,
        "format": "CSV",
        "lang": "en",
        "variables": variables,
    }
    raw = api_post("data", payload)
    return raw.decode("utf-8")


# ── Variable discovery ─────────────────────────────────────────────────────────

def discover_variables() -> dict:
    """
    Fetch table metadata and identify the three DNVALD variables:
      - currency  (VALUTA / valuta / …)
      - type      (KURTYP / kurtyp / …)  → we want the "exchange rate" value
      - time      (Tid / tid / …)
    Returns a dict with keys: currency_var, type_var, time_var,
    rate_type_id, and currency_map {code: description}.
    """
    info = fetch_table_info()
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
            # Pick the "Exchange rates (DKK per 100 …)" value
            for v in values:
                t = v["text"].lower()
                if "exchange rate" in t or "kurs" in t or "dkk per 100" in t:
                    result["rate_type_id"] = v["id"]
                    break
            # Fallback: first value
            if "rate_type_id" not in result and values:
                result["rate_type_id"] = values[0]["id"]

    # Sanity check
    for key in ("currency_var", "type_var", "time_var", "rate_type_id"):
        if key not in result:
            raise RuntimeError(
                f"Could not find '{key}' in table metadata. "
                f"The API structure may have changed."
            )
    return result


# ── Input parsing ──────────────────────────────────────────────────────────────

def parse_date(s: str) -> datetime:
    """Parse DD.MM.YYYY (leading zeros optional)."""
    parts = s.strip().split(".")
    if len(parts) != 3:
        raise ValueError(f"Bad date '{s}'. Use DD.MM.YYYY, e.g. 3.4.2025")
    return datetime(int(parts[2]), int(parts[1]), int(parts[0]))


def date_to_code(dt: datetime) -> str:
    """Convert datetime → Statbank daily code like '2025M04D03'."""
    return f"{dt.year}M{dt.month:02d}D{dt.day:02d}"


def resolve_currency(user_input: str, currency_map: dict) -> str:
    """Match the user's ISO code to a Statbank currency value ID."""
    key = user_input.upper().strip()

    # Exact match on value ID
    if key in currency_map:
        return key

    # Search inside the description texts
    for vid, desc in currency_map.items():
        if key in vid.upper() or key in desc.upper():
            return vid

    available = ", ".join(sorted(currency_map.keys()))
    raise ValueError(
        f"Unknown currency '{user_input}'.\nAvailable codes: {available}"
    )


# ── CSV parsing ────────────────────────────────────────────────────────────────

def extract_rate(csv_text: str) -> float:
    """Pull the numeric exchange rate from the API's CSV response."""
    lines = [l for l in csv_text.strip().splitlines() if l.strip()]
    if len(lines) < 2:
        raise RuntimeError(f"No data rows in API response:\n{csv_text}")

    # Last column of the data row is the value
    value_str = lines[1].split(";")[-1].strip().strip('"')
    if value_str in ("", "..", "-"):
        raise RuntimeError(
            "No rate published for this date. "
            "The Nationalbank doesn't publish rates on weekends or holidays."
        )
    try:
        return float(value_str.replace(",", "."))
    except ValueError:
        raise RuntimeError(f"Cannot parse rate '{value_str}' from:\n{csv_text}")


# ── Main ───────────────────────────────────────────────────────────────────────

def cmd_list():
    """Print all available currencies."""
    print("Fetching currency list from Danmarks Nationalbank…")
    meta = discover_variables()
    print(f"\nAvailable currencies ({len(meta['currency_map'])}):")
    print("-" * 60)
    for code, desc in sorted(meta["currency_map"].items()):
        print(f"  {code:6s}  {desc}")


def cmd_convert(date_str: str, amount_str: str, currency_str: str):
    """Fetch the rate and convert."""
    # ── Parse inputs ───────────────────────────────────────────────────────
    try:
        dt = parse_date(date_str)
    except ValueError as e:
        print(f"Error: {e}")
        sys.exit(1)

    try:
        amount = float(amount_str.replace(",", "."))
    except ValueError:
        print(f"Error: '{amount_str}' is not a valid number.")
        sys.exit(1)

    currency_input = currency_str.upper().strip()

    print(f"Fetching exchange rate from Danmarks Nationalbank…")
    print(f"  Date:     {dt.strftime('%d %B %Y')}")
    print(f"  Currency: {currency_input}")
    print(f"  Amount:   {amount:,.2f}")
    print()

    # ── Discover table structure ───────────────────────────────────────────
    try:
        meta = discover_variables()
    except RuntimeError as e:
        print(f"Error: {e}")
        sys.exit(1)

    # ── Resolve currency ───────────────────────────────────────────────────
    try:
        currency_code = resolve_currency(currency_input, meta["currency_map"])
    except ValueError as e:
        print(f"Error: {e}")
        sys.exit(1)

    currency_name = meta["currency_map"].get(currency_code, currency_code)

    # ── Fetch rate ─────────────────────────────────────────────────────────
    date_code = date_to_code(dt)
    variables = [
        {"code": meta["currency_var"], "values": [currency_code]},
        {"code": meta["type_var"],     "values": [meta["rate_type_id"]]},
        {"code": meta["time_var"],     "values": [date_code]},
    ]

    try:
        csv_text = fetch_data_csv(variables)
        rate = extract_rate(csv_text)
    except RuntimeError as e:
        hint = ""
        wd = dt.weekday()
        if wd == 5:
            hint = f"\n  Try Friday {(dt - timedelta(1)).strftime('%d.%m.%Y')} instead."
        elif wd == 6:
            hint = f"\n  Try Friday {(dt - timedelta(2)).strftime('%d.%m.%Y')} instead."
        else:
            hint = "\n  This may be a Danish public holiday."
        print(f"Error: {e}{hint}")
        sys.exit(1)

    # ── Result ─────────────────────────────────────────────────────────────
    unit_rate = rate / 100.0
    dkk = amount * unit_rate

    print(f"  Exchange rate: {rate:.4f} DKK per 100 {currency_code}")
    print(f"  (1 {currency_code} = {unit_rate:.4f} DKK)")
    print()
    print(f"  ╔══════════════════════════════════════════════════════╗")
    print(f"  ║  {amount:>12,.2f} {currency_code:<5s} = {dkk:>14,.2f} DKK       ║")
    print(f"  ╚══════════════════════════════════════════════════════╝")
    print()
    print(f"  Source: Danmarks Nationalbank (DNVALD)")
    print(f"  Date:   {dt.strftime('%d %B %Y')} — {currency_name}")


def main():
    if len(sys.argv) == 2 and sys.argv[1] in ("--list", "-l"):
        cmd_list()
    elif len(sys.argv) == 4:
        cmd_convert(sys.argv[1], sys.argv[2], sys.argv[3])
    else:
        print(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    main()
