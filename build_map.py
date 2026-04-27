#!/usr/bin/env python3
"""Multi-brand spritz retailer map.

Reads stores.csv (columns: brand, store_name, full_address, city, state, zip,
latitude, longitude). For any row missing lat/lon, geocodes via Nominatim.
Writes a self-contained Leaflet HTML map (spritz_map.html) with brand
filtering and color-coded markers.

Workflow to add stores manually:
  1. Append rows to stores.csv with at least: brand, store_name, full_address.
     Leave lat/lon blank to be auto-geocoded.
  2. python3 build_map.py
  3. Open spritz_map.html (or refresh).
"""
import csv
import json
import os
import time
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
CSV_PATH = os.path.join(HERE, "stores.csv")
HTML_PATH = os.path.join(HERE, "index.html")
USER_AGENT = "spritz-map/1.0 (oliviagubel)"
FIELDNAMES = ["brand", "store_name", "full_address", "city", "state", "zip", "latitude", "longitude"]

# Brand -> hex color for map markers + legend.
BRAND_COLORS = {
    "Nomadica":          "#C2185B",
    "Anytime Spritz":    "#F9A825",
    "Yes Way Rosé":      "#E91E63",
    "Hoxie":             "#7CB342",
    "Jumbo Time":        "#1976D2",
    "Ysidro":            "#00897B",
    "Djuce":             "#6D4C41",
    "Veranda":           "#9C27B0",
    "Little Sun":        "#FBC02D",
    "Other LA Spots":    "#455A64",
}
DEFAULT_COLOR = "#37474F"


def color_for(brand):
    return BRAND_COLORS.get(brand, DEFAULT_COLOR)


def strip_suite(street):
    for marker in [" Ste ", " Suite ", " Unit ", " #"]:
        i = street.lower().find(marker.lower())
        if i != -1:
            return street[:i]
    return street


def geocode(query):
    params = urllib.parse.urlencode({
        "q": query, "format": "json", "addressdetails": "1",
        "limit": "1", "countrycodes": "us",
    })
    url = f"https://nominatim.openstreetmap.org/search?{params}"
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            data = json.load(resp)
    except Exception as e:
        print(f"  ! request failed: {e}")
        return None
    if not data:
        return None
    hit = data[0]
    return {
        "lat": float(hit["lat"]),
        "lon": float(hit["lon"]),
        "postcode": hit.get("address", {}).get("postcode", ""),
    }


def fill_missing_geocodes(rows):
    changed = False
    for i, row in enumerate(rows, 1):
        if row.get("latitude") and row.get("longitude"):
            continue
        addr = (row.get("full_address") or "").strip()
        if not addr:
            print(f"[{i}] {row.get('store_name')}: no address — skipped")
            continue
        q = addr if "USA" in addr.upper() else addr + ", USA"
        print(f"[{i}] {row.get('brand')} / {row.get('store_name')} — geocoding: {q}")
        result = geocode(q)
        if result is None:
            stripped = strip_suite(addr)
            if stripped != addr:
                q2 = stripped + ", USA"
                print(f"     retry: {q2}")
                time.sleep(1.1)
                result = geocode(q2)
        if result is None:
            print("     -> NO MATCH (skipped on map)")
        else:
            row["latitude"] = f"{result['lat']:.7f}"
            row["longitude"] = f"{result['lon']:.7f}"
            if not row.get("zip") and result["postcode"]:
                row["zip"] = result["postcode"]
            print(f"     -> {row['latitude']}, {row['longitude']}  zip={row['zip'] or '?'}")
            changed = True
        time.sleep(1.1)
    return changed


def write_csv(rows):
    with open(CSV_PATH, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k, "") for k in FIELDNAMES})


HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Spritz Retailers — LA Area</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"
  integrity="sha256-p4NxAoJBhIIN+hmNHrzRCf9tD/miZyoHS5obTRR9BMY=" crossorigin=""/>
<style>
  html, body { margin: 0; padding: 0; height: 100%; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }
  #map { position: absolute; top: 0; bottom: 0; left: 0; right: 340px; }
  #sidebar { position: absolute; top: 0; bottom: 0; right: 0; width: 340px; overflow-y: auto;
             background: #fafafa; border-left: 1px solid #ddd; padding: 12px 16px; box-sizing: border-box; }
  #sidebar h1 { font-size: 16px; margin: 4px 0 4px; }
  #sidebar .scope { color: #888; font-size: 11px; margin-bottom: 12px; }
  .brand-toggle { display: flex; align-items: center; gap: 8px; padding: 4px 0; cursor: pointer; font-size: 13px; user-select: none; }
  .brand-toggle input { margin: 0; }
  .swatch { display: inline-block; width: 12px; height: 12px; border-radius: 50%; vertical-align: middle; }
  .brand-count { color: #888; font-size: 11px; margin-left: auto; }
  #brands { padding: 6px 0; border-top: 1px solid #eee; border-bottom: 1px solid #eee; margin-bottom: 8px; }
  #count { color: #666; font-size: 12px; margin: 8px 0 6px; }
  #filter { width: 100%; padding: 6px 8px; border: 1px solid #ccc; border-radius: 4px; font-size: 13px; box-sizing: border-box; margin-bottom: 8px; }
  .store { padding: 8px 0; border-bottom: 1px solid #eee; cursor: pointer; font-size: 13px; }
  .store:hover { background: #f0f0f0; }
  .store .name { font-weight: 600; }
  .store .meta { color: #555; font-size: 12px; }
  .store .brand-tag { display: inline-block; font-size: 10px; padding: 1px 6px; border-radius: 3px; color: white; margin-right: 4px; vertical-align: middle; }
  .leaflet-popup-content .name { font-weight: 600; margin-bottom: 4px; }
  .leaflet-popup-content .addr { color: #555; }
  .leaflet-popup-content .brand-tag { display: inline-block; font-size: 10px; padding: 1px 6px; border-radius: 3px; color: white; margin-bottom: 4px; }
  @media (max-width: 700px) {
    #map { right: 0; bottom: 50%; }
    #sidebar { left: 0; top: 50%; width: auto; border-left: none; border-top: 1px solid #ddd; }
  }
</style>
</head>
<body>
<div id="map"></div>
<div id="sidebar">
  <h1>Spritz retailers</h1>
  <div class="scope">LA area · regenerate via build_map.py</div>
  <div id="brands"></div>
  <input id="filter" placeholder="Filter by name, city, ZIP…" />
  <div id="count"></div>
  <div id="list"></div>
</div>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"
  integrity="sha256-20nQCchB9co0qIjJZRGuk2/Z9VM+kNiyxNV1lvTlZBo=" crossorigin=""></script>
<script>
const STORES = __STORES_JSON__;

const map = L.map('map');
L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
  attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
  maxZoom: 19,
}).addTo(map);

function makeIcon(color) {
  return L.divIcon({
    className: 'spritz-pin',
    html: `<div style="background:${color};width:16px;height:16px;border-radius:50%;border:2px solid white;box-shadow:0 1px 4px rgba(0,0,0,.4);"></div>`,
    iconSize: [16, 16], iconAnchor: [8, 8],
  });
}

const bounds = L.latLngBounds();
const enabledBrands = new Set();
const brandCounts = {};
STORES.forEach(s => {
  brandCounts[s.brand] = (brandCounts[s.brand] || 0) + 1;
  enabledBrands.add(s.brand);
  if (s.lat && s.lon) bounds.extend([s.lat, s.lon]);
});

const items = STORES.map(s => {
  if (!s.lat || !s.lon) return null;
  const m = L.marker([s.lat, s.lon], { icon: makeIcon(s.color) });
  m.bindPopup(`<div class="brand-tag" style="background:${s.color}">${s.brand}</div><div class="name">${s.name}</div><div class="addr">${s.addr}</div>`);
  return { marker: m, store: s };
}).filter(Boolean);

if (bounds.isValid()) map.fitBounds(bounds, { padding: [30, 30] });
else map.setView([34.05, -118.25], 10);

const brandsEl = document.getElementById('brands');
Object.keys(brandCounts).sort().forEach(brand => {
  const color = (items.find(it => it.store.brand === brand) || {}).store?.color || '#999';
  const label = document.createElement('label');
  label.className = 'brand-toggle';
  label.innerHTML = `<input type="checkbox" checked data-brand="${brand}"> <span class="swatch" style="background:${color}"></span> ${brand} <span class="brand-count">${brandCounts[brand]}</span>`;
  label.querySelector('input').addEventListener('change', e => {
    if (e.target.checked) enabledBrands.add(brand); else enabledBrands.delete(brand);
    render();
  });
  brandsEl.appendChild(label);
});

const list = document.getElementById('list');
const countEl = document.getElementById('count');
const filterEl = document.getElementById('filter');

function render() {
  const f = (filterEl.value || '').toLowerCase().trim();
  list.innerHTML = '';
  let shown = 0;
  items.forEach(({ marker, store }) => {
    const hay = `${store.name} ${store.addr} ${store.zip}`.toLowerCase();
    const show = enabledBrands.has(store.brand) && (!f || hay.includes(f));
    if (show) {
      shown++;
      const div = document.createElement('div');
      div.className = 'store';
      div.innerHTML = `<div class="name"><span class="brand-tag" style="background:${store.color}">${store.brand}</span>${store.name}</div><div class="meta">${store.addr}</div>`;
      div.onclick = () => { map.setView([store.lat, store.lon], 15); marker.openPopup(); };
      list.appendChild(div);
      marker.addTo(map);
    } else {
      map.removeLayer(marker);
    }
  });
  countEl.textContent = `${shown} of ${items.length} stores shown`;
}

filterEl.addEventListener('input', render);
render();
</script>
</body>
</html>
"""


def build_html(rows):
    stores = []
    for row in rows:
        if not row.get("latitude") or not row.get("longitude"):
            continue
        stores.append({
            "brand": row.get("brand", ""),
            "name": row["store_name"],
            "addr": row["full_address"],
            "zip": row.get("zip", ""),
            "lat": float(row["latitude"]),
            "lon": float(row["longitude"]),
            "color": color_for(row.get("brand", "")),
        })
    html = HTML_TEMPLATE.replace("__STORES_JSON__", json.dumps(stores))
    with open(HTML_PATH, "w") as f:
        f.write(html)
    return len(stores)


def main():
    with open(CSV_PATH, newline="") as f:
        rows = [dict(r) for r in csv.DictReader(f)]
    if fill_missing_geocodes(rows):
        write_csv(rows)
        print(f"\nUpdated CSV: {CSV_PATH}")
    n = build_html(rows)
    print(f"Wrote map with {n} stores: {HTML_PATH}")
    print(f"\nOpen with: open '{HTML_PATH}'")


if __name__ == "__main__":
    main()
