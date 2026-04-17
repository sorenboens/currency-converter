#!/usr/bin/env python3
"""Test CoinGecko API key with different auth methods."""
import json, urllib.request, urllib.error, os

key_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "coingecko_key.txt")
KEY = open(key_file).read().strip()
print(f"Key loaded: {KEY[:6]}...{KEY[-4:]}")

BASE = "https://api.coingecko.com/api/v3"

# Test 1: Ping with header
print("\n--- Test 1: Ping with header ---")
req = urllib.request.Request(
    f"{BASE}/ping",
    headers={"x-cg-demo-api-key": KEY},
)
try:
    with urllib.request.urlopen(req, timeout=15) as resp:
        print(f"OK: {resp.read().decode('utf-8')}")
except urllib.error.HTTPError as e:
    print(f"FAIL: HTTP {e.code} - {e.read().decode('utf-8', errors='replace')}")

# Test 2: Ping with query param
print("\n--- Test 2: Ping with query param ---")
req = urllib.request.Request(f"{BASE}/ping?x_cg_demo_api_key={KEY}")
try:
    with urllib.request.urlopen(req, timeout=15) as resp:
        print(f"OK: {resp.read().decode('utf-8')}")
except urllib.error.HTTPError as e:
    print(f"FAIL: HTTP {e.code} - {e.read().decode('utf-8', errors='replace')}")

# Test 3: History with query param
print("\n--- Test 3: BTC history (01-04-2025) with query param ---")
url = f"{BASE}/coins/bitcoin/history?date=01-04-2025&localization=false&x_cg_demo_api_key={KEY}"
req = urllib.request.Request(url)
try:
    with urllib.request.urlopen(req, timeout=15) as resp:
        data = json.loads(resp.read().decode("utf-8"))
        price = data["market_data"]["current_price"]["usd"]
        print(f"OK: BTC price on 01-04-2025 = ${price:,.2f}")
except urllib.error.HTTPError as e:
    print(f"FAIL: HTTP {e.code} - {e.read().decode('utf-8', errors='replace')}")

# Test 4: History with header
print("\n--- Test 4: BTC history (01-04-2025) with header ---")
url = f"{BASE}/coins/bitcoin/history?date=01-04-2025&localization=false"
req = urllib.request.Request(url, headers={"x-cg-demo-api-key": KEY})
try:
    with urllib.request.urlopen(req, timeout=15) as resp:
        data = json.loads(resp.read().decode("utf-8"))
        price = data["market_data"]["current_price"]["usd"]
        print(f"OK: BTC price on 01-04-2025 = ${price:,.2f}")
except urllib.error.HTTPError as e:
    print(f"FAIL: HTTP {e.code} - {e.read().decode('utf-8', errors='replace')}")
