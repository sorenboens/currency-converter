#!/usr/bin/env python3
"""Check what date format the DNVALD time variable uses."""
import json, urllib.request

url = "https://api.statbank.dk/v1/tableinfo"
payload = json.dumps({"table": "DNVALD", "lang": "en"}).encode("utf-8")
req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
with urllib.request.urlopen(req, timeout=15) as resp:
    data = json.loads(resp.read().decode("utf-8"))

for v in data["variables"]:
    if v["id"] == "Tid":
        vals = v["values"]
        print(f"Total time values: {len(vals)}")
        print(f"First 5: {[x['id'] for x in vals[:5]]}")
        print(f"Last 5:  {[x['id'] for x in vals[-5:]]}")
        break
