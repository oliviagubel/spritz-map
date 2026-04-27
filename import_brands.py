#!/usr/bin/env python3
"""Pull store data from each brand's public source and merge into stores.csv.

Brands and sources:
  - Nomadica:        captcha-protected VIP widget (custID=ZI5). Manual entry only.
  - Anytime Spritz:  open Stockist API (tag u18578). Filtered to LA bbox.
  - Yes Way Rosé:    proxy at yeswayrose.com/_storelocator.php (custID=PWS). LA radius.
  - Hoxie:           captcha-protected VIP widget (custID=SCH). Manual entry only.

Scope: ~25 miles around LA (matches the original Nomadica search at ZIP 90026).
LA bbox: lat 33.715–34.439, lon -118.700 to -117.830.
"""
import csv
import json
import math
import os
import re
import sys
import time
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
CSV_PATH = os.path.join(HERE, "stores.csv")
LEGACY_NOMADICA_CSV = os.path.join(HERE, "nomadica_stores.csv")
FIELDNAMES = ["brand", "store_name", "full_address", "city", "state", "zip", "latitude", "longitude"]

# LA scoping: 25mi radius around Echo Park (90026).
LA_CENTER = (34.0767, -118.2575)
LA_RADIUS_MI = 25.0


def haversine_mi(lat1, lon1, lat2, lon2):
    R = 3958.8  # Earth radius in miles
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp/2)**2 + math.cos(p1)*math.cos(p2)*math.sin(dl/2)**2
    return 2 * R * math.asin(math.sqrt(a))


def in_la(lat, lon):
    try:
        return haversine_mi(LA_CENTER[0], LA_CENTER[1], float(lat), float(lon)) <= LA_RADIUS_MI
    except (ValueError, TypeError):
        return False


# Parse "1234 Main St, City, ST 12345" into (street, city, state, zip).
ADDR_RE = re.compile(r"^(.*?),\s*([^,]+?),\s*([A-Z]{2})\s*(\d{5})?(?:-\d{4})?\s*$")
def parse_address(full):
    if not full:
        return ("", "", "", "")
    m = ADDR_RE.match(full.strip())
    if not m:
        return (full, "", "", "")
    street, city, state, zipc = m.groups()
    return (street.strip(), city.strip(), state.strip(), (zipc or "").strip())


# Brand -> (Stockist tag, referer). Add a new brand here to auto-import it.
STOCKIST_BRANDS = [
    ("Anytime Spritz", "u18578", "https://www.anytimefarmhouse.com/"),
    ("Ysidro",         "u18774", "https://www.ysidro.com/"),
]


# Substring blocklist applied across every importer (case-insensitive).
# Add a name fragment here to permanently exclude a chain.
EXCLUDE_NAME_SUBSTRINGS = ["whole foods"]


def is_excluded(name):
    n = (name or "").lower()
    return any(sub in n for sub in EXCLUDE_NAME_SUBSTRINGS)


def fetch_stockist(brand, tag, referer):
    """Generic Stockist fetcher: pulls all locations, filters to LA scope."""
    print(f"Fetching {brand} (Stockist API, tag {tag})...")
    req = urllib.request.Request(
        f"https://stockist.co/api/v1/{tag}/locations/all",
        headers={"User-Agent": "spritz-map/1.0", "Referer": referer},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.load(resp)
    rows = []
    for loc in data:
        lat, lon = loc.get("latitude"), loc.get("longitude")
        if not lat or not lon or not in_la(lat, lon):
            continue
        if is_excluded(loc.get("name")):
            continue
        full = (loc.get("full_address") or "").strip()
        street_struct = loc.get("address_line_1")
        city_struct = loc.get("city")
        state_struct = loc.get("state")
        zip_struct = loc.get("postal_code")
        if street_struct or city_struct or state_struct:
            city = city_struct or ""
            state = state_struct or ""
            zipc = zip_struct or ""
        else:
            _, city, state, zipc = parse_address(full)
        if not full:
            full = ", ".join(p for p in [street_struct, city, f"{state} {zipc}".strip()] if p)
        rows.append({
            "brand": brand,
            "store_name": (loc.get("name") or "").strip(),
            "full_address": full,
            "city": city,
            "state": state,
            "zip": zipc,
            "latitude": str(lat),
            "longitude": str(lon),
        })
    print(f"  {len(rows)} {brand} stores in LA scope (out of {len(data)} nationwide)")
    return rows


def fetch_yeswayrose():
    """Yes Way Rosé via the brand's PHP proxy. Paginated; pagesize=50."""
    print("Fetching Yes Way Rosé (yeswayrose.com proxy)...")
    rows = []
    page = 0
    while True:
        params = urllib.parse.urlencode({"zip": "90026", "miles": "25", "loc": "", "page": str(page)})
        url = f"https://yeswayrose.com/_storelocator.php?{params}"
        req = urllib.request.Request(url, headers={
            "User-Agent": "Mozilla/5.0",
            "Referer": "https://yeswayrose.com/where-to-buy/",
        })
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.load(resp)
        # VIP response: data["locations"]["location"] is the list (XML-style nested).
        locs_container = data.get("locations") or {}
        results = locs_container.get("location") if isinstance(locs_container, dict) else locs_container
        if not results:
            if page == 0:
                print(f"  ! no locations in response; keys: {list(data.keys())[:10]}")
            break
        for loc in results:
            name = (loc.get("dba") or loc.get("name") or "").strip()
            street = (loc.get("street") or loc.get("address1") or "").strip()
            city = (loc.get("city") or "").strip()
            state = (loc.get("state") or "").strip()
            zipc = (loc.get("zip") or loc.get("postalCode") or "").strip()
            lat = loc.get("lat") or loc.get("latitude")
            lon = loc.get("long") or loc.get("lng") or loc.get("longitude") or loc.get("lon")
            if not lat or not lon or not in_la(lat, lon):
                continue
            if is_excluded(name):
                continue
            full = f"{street}, {city}, {state} {zipc}".strip(", ").strip()
            rows.append({
                "brand": "Yes Way Rosé",
                "store_name": name,
                "full_address": full,
                "city": city,
                "state": state,
                "zip": zipc,
                "latitude": str(lat),
                "longitude": str(lon),
            })
        total_pages = int(data.get("totalPages", 1) or 1)
        page += 1
        if page >= total_pages:
            break
        time.sleep(0.5)  # polite pacing
    print(f"  {len(rows)} Yes Way Rosé stores in LA scope")
    return rows


def load_legacy_nomadica():
    """Migrate the original nomadica_stores.csv into the new schema."""
    if not os.path.exists(LEGACY_NOMADICA_CSV):
        return []
    print(f"Loading legacy Nomadica CSV ({LEGACY_NOMADICA_CSV})...")
    rows = []
    with open(LEGACY_NOMADICA_CSV, newline="") as f:
        for r in csv.DictReader(f):
            if is_excluded(r.get("store_name")):
                continue
            rows.append({
                "brand": "Nomadica",
                "store_name": r.get("store_name", ""),
                "full_address": r.get("full_address", ""),
                "city": r.get("city", ""),
                "state": r.get("state", ""),
                "zip": r.get("zip", ""),
                "latitude": r.get("latitude", ""),
                "longitude": r.get("longitude", ""),
            })
    print(f"  {len(rows)} Nomadica stores migrated")
    return rows


def load_existing_other_brands():
    """If stores.csv already exists, keep brands we don't auto-import (so manual entries persist)."""
    if not os.path.exists(CSV_PATH):
        return []
    keep = []
    # Brands re-pulled from APIs every run (so we don't keep stale copies).
    auto_brands = {b for (b, _, _) in STOCKIST_BRANDS} | {"Yes Way Rosé", "Nomadica"}
    with open(CSV_PATH, newline="") as f:
        for r in csv.DictReader(f):
            if r.get("brand") not in auto_brands:
                keep.append({k: r.get(k, "") for k in FIELDNAMES})
    return keep


def dedupe(rows):
    """Same brand + same lat/lon (rounded) collapses to one row."""
    seen = set()
    out = []
    for r in rows:
        try:
            key = (r["brand"], round(float(r["latitude"]), 4), round(float(r["longitude"]), 4))
        except (ValueError, TypeError, KeyError):
            key = (r["brand"], r["store_name"], r["full_address"])
        if key in seen:
            continue
        seen.add(key)
        out.append(r)
    return out


def main():
    rows = []
    rows += load_legacy_nomadica()
    rows += load_existing_other_brands()
    for brand, tag, referer in STOCKIST_BRANDS:
        try:
            rows += fetch_stockist(brand, tag, referer)
        except Exception as e:
            print(f"  ! {brand} fetch failed: {e}")
    try:
        rows += fetch_yeswayrose()
    except Exception as e:
        print(f"  ! Yes Way Rosé fetch failed: {e}")
    rows = dedupe(rows)
    with open(CSV_PATH, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDNAMES)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in FIELDNAMES})
    print(f"\nWrote {len(rows)} rows to {CSV_PATH}")
    by_brand = {}
    for r in rows:
        by_brand[r["brand"]] = by_brand.get(r["brand"], 0) + 1
    for b, c in sorted(by_brand.items()):
        print(f"  {b:20} {c}")


if __name__ == "__main__":
    main()
