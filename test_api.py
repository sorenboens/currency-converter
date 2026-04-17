#!/usr/bin/env python3
"""Quick test to find the working API endpoint for DNVALD."""

import json
import urllib.request

ENDPOINTS = [
    "https://api.statbank.dk/v1",
    "https://nationalbanken.statistikbank.dk/statbank5a/api/v1",
    "https://nationalbanken.statbank.dk/statbank5a/api/v1",
]

for base in ENDPOINTS:
    url = f"{base}/tableinfo"
    payload = json.dumps({"table": "DNVALD", "lang": "en"}).encode("utf-8")
    req = urllib.request.Request(
        url, data=payload, headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            print(f"SUCCESS: {base}")
            print(f"  Table: {data.get('id')} — {data.get('text')}")
            for v in data.get("variables", []):
                vals = v.get("values", [])
                print(f"  Variable: {v['id']} ({v.get('text')}) — {len(vals)} values")
                if len(vals) <= 5:
                    for val in vals:
                        print(f"    {val['id']}: {val['text']}")
            print()
    except Exception as e:
        print(f"FAILED:  {base}")
        print(f"  Error: {e}")
        print()
