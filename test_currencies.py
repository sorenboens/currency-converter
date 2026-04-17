#!/usr/bin/env python3
"""List all currencies and check which ones have recent data."""
import json, urllib.request

API = "https://api.statbank.dk/v1"

req = urllib.request.Request(
    f"{API}/tableinfo",
    data=json.dumps({"table": "DNVALD", "lang": "en"}).encode("utf-8"),
    headers={"Content-Type": "application/json"},
)
with urllib.request.urlopen(req, timeout=15) as resp:
    info = json.loads(resp.read().decode("utf-8"))

for v in info["variables"]:
    if v["id"] == "VALUTA":
        for c in v["values"]:
            print(f"  {c['id']:6s}  {c['text']}")
        print(f"\nTotal: {len(v['values'])}")
