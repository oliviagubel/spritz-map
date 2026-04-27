# Spritz Retailers Map (LA Area)

Interactive map of where you can buy small-batch spritzers, canned wines, and
other spritz-adjacent drinks across the LA area. Roughly 25 miles around Echo
Park, but with some outliers (Long Beach, Agoura Hills) thrown in by hand.

**Live map:** https://oliviagubel.github.io/spritz-map/

## Brands tracked

| Brand | Source |
|---|---|
| Anytime Spritz | Stockist API (open) |
| Djuce | Hand-curated list, geocoded |
| Jumbo Time Wines | Hand-curated list, geocoded |
| Little Sun | Manual entries with addresses |
| Nomadica | Original screenshot import, geocoded |
| Veranda Cocktails | Manual entries with addresses |
| Yes Way Rosé | yeswayrose.com proxy (VIP/vtinfo backend) |
| Ysidro | Stockist API (open) |

Whole Foods locations are filtered out by default (see `EXCLUDE_NAME_SUBSTRINGS`
in `import_brands.py`).

## Files

- `index.html` — the map. Self-contained Leaflet + OSM. Open in any browser.
- `stores.csv` — single source of truth. Columns: `brand, store_name, full_address, city, state, zip, latitude, longitude`.
- `build_map.py` — reads `stores.csv`, geocodes any rows missing lat/lon via
  Nominatim, writes `index.html`.
- `import_brands.py` — refreshes auto-importable brands (Anytime, Ysidro, Yes Way Rosé)
  from their public APIs and merges into `stores.csv`.
- `import_named_list.py` — generic geocoder for hand-curated lists like
  `djuce_socal.txt`, `jumbo_socal.txt`, `veranda_socal.txt`. Usage:
  `python3 import_named_list.py "Brand Name" path/to/list.txt`

## Updating the map

```bash
# Pull fresh data from Anytime/Ysidro/YWR APIs (skip if you only added manual rows)
python3 import_brands.py

# Geocode any new rows + regenerate the HTML
python3 build_map.py

# Publish
git add -A && git commit -m "update stores" && git push
```

GitHub Pages picks up the new `index.html` automatically (~1 minute).

## Adding a new brand

**If they use Stockist** (most common): find their tag (search the locator page
HTML for `data-stockist-widget-tag="u…"`), then add it to `STOCKIST_BRANDS` in
`import_brands.py` and re-run.

**If they have a hand-curated list**: drop names into a `<brand>_socal.txt` file
(one per line, optional `| Hint` for disambiguation) and run
`python3 import_named_list.py "Brand Name" <brand>_socal.txt`.

**If they have addresses already**: append rows directly to `stores.csv` with
lat/lon left blank — `build_map.py` will geocode them.

Also add the brand to the `BRAND_COLORS` dict in `build_map.py` so it gets a
distinct marker color.

## License

CC0 / public domain. Map tiles © OpenStreetMap contributors.
