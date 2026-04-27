#!/usr/bin/env python3
"""Geocode a hand-curated SoCal stockist list (names only — no addresses)
via Nominatim and merge into stores.csv.

Usage:
  python3 import_named_list.py "Brand Name" path/to/list.txt

List format: one business name per line. Blank lines and # comments ignored.
Optional location hint after a "|" (e.g. "Cookbook Market | Highland Park, Los Angeles").
"""
import csv
import json
import os
import sys
import time
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
CSV_PATH = os.path.join(HERE, "stores.csv")
FIELDNAMES = ["brand", "store_name", "full_address", "city", "state", "zip", "latitude", "longitude"]
USER_AGENT = "spritz-map/1.0 (oliviagubel)"
LA_BBOX = (33.715, 34.439, -118.700, -117.830)


def in_la_bbox(lat, lon):
    return LA_BBOX[0] <= lat <= LA_BBOX[1] and LA_BBOX[2] <= lon <= LA_BBOX[3]


def geocode(query):
    params = urllib.parse.urlencode({
        "q": query, "format": "json", "addressdetails": "1",
        "limit": "3", "countrycodes": "us",
    })
    req = urllib.request.Request(
        f"https://nominatim.openstreetmap.org/search?{params}",
        headers={"User-Agent": USER_AGENT},
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            return json.load(resp)
    except Exception as e:
        print(f"  ! request failed: {e}")
        return []


def best_la_hit(hits):
    for h in hits:
        try:
            lat, lon = float(h["lat"]), float(h["lon"])
        except (ValueError, TypeError, KeyError):
            continue
        if in_la_bbox(lat, lon):
            return h
    return None


def parse_line(line):
    if "|" in line:
        name, hint = line.split("|", 1)
        return name.strip(), hint.strip()
    return line.strip(), ""


def lookup(name, hint):
    queries = []
    if hint:
        queries.append(f"{name}, {hint}, CA, USA")
    queries.append(f"{name}, Los Angeles, CA, USA")
    queries.append(f"{name}, Los Angeles County, CA, USA")
    queries.append(f"{name}, CA, USA")
    seen = set()
    for q in queries:
        if q in seen:
            continue
        seen.add(q)
        hits = geocode(q)
        time.sleep(1.1)
        h = best_la_hit(hits)
        if h:
            return h, q
    return None, None


def main():
    if len(sys.argv) != 3:
        print("Usage: import_named_list.py 'Brand Name' path/to/list.txt", file=sys.stderr)
        sys.exit(1)
    brand, list_path = sys.argv[1], sys.argv[2]
    if not os.path.isabs(list_path):
        list_path = os.path.join(HERE, list_path)

    with open(list_path) as f:
        lines = [l.strip() for l in f if l.strip() and not l.startswith("#")]

    # Cache existing rows for this brand so reruns don't re-query Nominatim.
    existing = {}
    other_rows = []
    if os.path.exists(CSV_PATH):
        with open(CSV_PATH, newline="") as f:
            for r in csv.DictReader(f):
                if r.get("brand") == brand:
                    if r.get("latitude"):
                        existing[r["store_name"]] = r
                else:
                    other_rows.append({k: r.get(k, "") for k in FIELDNAMES})

    new_rows = []
    misses = []
    for raw in lines:
        name, hint = parse_line(raw)
        display = name if not hint else f"{name} ({hint.split(',')[0]})"
        if display in existing:
            new_rows.append(existing[display])
            print(f"  cache hit: {display}")
            continue
        print(f"geocoding: {display}")
        h, q = lookup(name, hint)
        if h is None:
            print("  -> MISS")
            misses.append(display)
            continue
        addr = h.get("address", {})
        full_short = ", ".join(h.get("display_name", "").split(", ")[:5])
        new_rows.append({
            "brand": brand,
            "store_name": display,
            "full_address": full_short,
            "city": addr.get("city") or addr.get("town") or addr.get("village") or "",
            "state": "CA",
            "zip": addr.get("postcode", ""),
            "latitude": h["lat"],
            "longitude": h["lon"],
        })
        print(f"  -> {h['lat']}, {h['lon']}  ({full_short[:60]})")

    all_rows = other_rows + new_rows
    with open(CSV_PATH, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDNAMES)
        w.writeheader()
        for r in all_rows:
            w.writerow({k: r.get(k, "") for k in FIELDNAMES})
    print(f"\nWrote {len(all_rows)} total rows ({len(new_rows)} {brand})")
    if misses:
        print(f"\n{len(misses)} unmatched (need manual lat/lon):")
        for m in misses:
            print(f"  - {m}")


if __name__ == "__main__":
    main()
