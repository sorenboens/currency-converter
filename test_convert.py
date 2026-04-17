#!/usr/bin/env python3
"""Test the actual data fetch to see what fails."""
import json, urllib.request

API = "https://api.statbank.dk/v1"

# First get metadata
req = urllib.request.Request(
    f"{API}/tableinfo",
    data=json.dumps({"table": "DNVALD", "lang": "en"}).encode("utf-8"),
    headers={"Content-Type": "application/json"},
)
with urllib.request.urlopen(req, timeout=15) as resp:
    info = json.loads(resp.read().decode("utf-8"))

# Show variable IDs
for v in info["variables"]:
    print(f"Variable: {v['id']}")

# Build a data request for EUR on 2026-04-16 (last known date)
payload = {
    "table": "DNVALD",
    "format": "CSV",
    "lang": "en",
    "variables": [
        {"code": "VALUTA", "values": ["EUR"]},
        {"code": "KURTYP", "values": ["KBH"]},
        {"code": "Tid", "values": ["2026M04D16"]},
    ],
}

print(f"\nPayload: {json.dumps(payload, indent=2)}")

req = urllib.request.Request(
    f"{API}/data",
    data=json.dumps(payload).encode("utf-8"),
    headers={"Content-Type": "application/json"},
)
try:
    with urllib.request.urlopen(req, timeout=15) as resp:
        print(f"\nSUCCESS:\n{resp.read().decode('utf-8')}")
except urllib.error.HTTPError as e:
    body = e.read().decode("utf-8", errors="replace")
    print(f"\nFAILED: HTTP {e.code}")
    print(f"Response body: {body}")
