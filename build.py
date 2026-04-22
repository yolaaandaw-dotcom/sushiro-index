#!/usr/bin/env python3
"""
build.py — fetches all Sushiro locations from OpenStreetMap (Overpass API),
optionally merges a manual supplement file (china-stores.csv),
and writes a fully self-contained `index.html` with the data inlined.

Usage:
    python3 build.py

Output:
    index.html  (single file, deploy to GitHub Pages as-is)

Optional supplement file (same folder as build.py):
    china-stores.csv  — manually maintained stores missing from OSM
    CSV format (header row required):
        name,address,lat,lng
        寿司郎·北京西单大悦城店,北京市西城区西单北大街131号西单大悦城,39.9108,116.3746

No dependencies — standard library only.
"""

import urllib.request
import urllib.parse
import json
import sys
import time
import csv
from pathlib import Path

OVERPASS_QUERY = """
[out:json][timeout:180];
(
  nwr["brand"="スシロー"];
  nwr["brand"="Sushiro"];
  nwr["brand"="寿司郎"];
  nwr["brand"="壽司郎"];
  nwr["brand"="寿司朗"];
  nwr["brand:wikidata"="Q11303864"];
  nwr["name"~"^スシロー"];
  nwr["name"~"^寿司郎"];
  nwr["name"~"^壽司郎"];
);
out center;
""".strip()

OVERPASS_ENDPOINTS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://z.overpass-api.de/api/interpreter",
    "https://overpass.openstreetmap.ru/api/interpreter",
]


def fetch_overpass():
    body = urllib.parse.urlencode({"data": OVERPASS_QUERY}).encode()
    for url in OVERPASS_ENDPOINTS:
        try:
            print(f"→ Trying {url}", file=sys.stderr)
            req = urllib.request.Request(
                url,
                data=body,
                headers={
                    "Content-Type": "application/x-www-form-urlencoded",
                    "User-Agent": "sushiro-index-builder/1.0 (personal project)",
                },
            )
            with urllib.request.urlopen(req, timeout=200) as r:
                data = json.loads(r.read().decode())
                n = len(data.get("elements", []))
                print(f"  ✓ Got {n} raw elements", file=sys.stderr)
                return data
        except Exception as e:
            print(f"  ✗ Failed: {e}", file=sys.stderr)
            time.sleep(3)
    raise RuntimeError("All Overpass endpoints failed. Try again in a few minutes.")


def process(data):
    import re
    locs = []
    for el in data.get("elements", []):
        lat = el.get("lat") or (el.get("center") or {}).get("lat")
        lon = el.get("lon") or (el.get("center") or {}).get("lon")
        if lat is None or lon is None:
            continue
        tags = el.get("tags", {})
        raw_name = (
            tags.get("name:ja") or tags.get("name:zh") or tags.get("name:zh-Hant")
            or tags.get("name") or tags.get("name:en") or tags.get("brand") or "スシロー"
        )
        name = raw_name

        # Extract the "branch" part from names like "スシロー 新宿店" / "スシロー南池袋店"
        # This gives us a location hint even when addr:* is empty
        branch_hint = ""
        m = re.match(r"^(?:スシロー|Sushiro|寿司郎|壽司郎)[\s·・]*(.+?店?)$", raw_name)
        if m and m.group(1).strip():
            candidate = m.group(1).strip()
            # Only use if it's actually location-like (not just the brand repeated)
            if candidate and candidate not in ("スシロー", "Sushiro", "寿司郎", "壽司郎"):
                branch_hint = candidate

        # Build address from all plausible addr:* fields (Japan uses quarter / block_number / neighbourhood)
        parts = []
        if tags.get("addr:full"):
            parts.append(tags["addr:full"])
        else:
            for k in ("addr:country", "addr:state", "addr:province", "addr:city",
                      "addr:suburb", "addr:neighbourhood", "addr:quarter"):
                if tags.get(k):
                    parts.append(tags[k])
            # Street + house number (Western style)
            if tags.get("addr:street"):
                street = tags["addr:street"]
                if tags.get("addr:housenumber"):
                    street += " " + tags["addr:housenumber"]
                parts.append(street)
            # Japanese-style block-number / bare housenumber
            elif tags.get("addr:block_number") or tags.get("addr:housenumber"):
                block = tags.get("addr:block_number") or ""
                hn = tags.get("addr:housenumber") or ""
                combined = "-".join(x for x in (block, hn) if x)
                if combined:
                    parts.append(combined)

        address = " · ".join(parts) if parts else ""

        # If no structured address but we extracted a branch hint that isn't
        # already visible in the name, use it (avoid redundant display).
        if not address and branch_hint and branch_hint not in name:
            address = branch_hint

        # If still no address, infer region from coords as last resort
        if not address:
            if 24 < lat < 46 and 123 < lon < 146:     region = "日本"
            elif 21 < lat < 26 and 119 < lon < 123:   region = "台灣"
            elif 22.1 < lat < 22.5 and 113.8 < lon < 114.5: region = "香港"
            elif 1 < lat < 2 and 103 < lon < 104:     region = "Singapore"
            elif 33 < lat < 39 and 126 < lon < 130:   region = "대한민국"
            elif 13 < lat < 19 and 100 < lon < 105:   region = "ประเทศไทย"
            elif 18 < lat < 42 and 104 < lon < 122:   region = "中国大陆"
            elif -7 < lat < -6 and 106 < lon < 107:   region = "Indonesia"
            elif 1 < lat < 7 and 100 < lon < 120:     region = "Malaysia"
            else:                                     region = "—"
            address = region

        locs.append({
            "n": name,
            "a": address,
            "y": round(lat, 6),
            "x": round(lon, 6),
        })

    # Dedupe by rough coord
    seen = set()
    out = []
    for loc in locs:
        key = (round(loc["y"], 4), round(loc["x"], 4))
        if key in seen:
            continue
        seen.add(key)
        out.append(loc)
    return out


def load_supplement(here):
    """Load optional supplement CSVs (china-stores.csv, jp-stores.csv)
    and return combined list of location dicts."""
    supp = []
    for fname in ("china-stores.csv", "jp-stores.csv"):
        csv_path = here / fname
        if not csv_path.exists():
            continue

        with open(csv_path, encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f)
            file_count = 0
            for i, row in enumerate(reader, start=2):
                name = (row.get("name") or "").strip()
                if not name or name.startswith("#"):
                    continue
                try:
                    lat = float(row["lat"])
                    lng = float(row["lng"])
                except (KeyError, ValueError, TypeError):
                    print(f"  ⚠ {fname} row {i}: bad lat/lng → {row}", file=sys.stderr)
                    continue
                supp.append({
                    "n": name,
                    "a": (row.get("address") or "—").strip(),
                    "y": round(lat, 6),
                    "x": round(lng, 6),
                })
                file_count += 1
        print(f"  {fname}: {file_count} rows", file=sys.stderr)
    return supp


def merge(osm_locs, supp_locs):
    """Merge supplement into OSM, preferring supplement entries when within ~1km."""
    merged = list(osm_locs)
    supp_added = 0
    supp_replaced = 0

    for s in supp_locs:
        # Find any OSM entry within ~0.01 deg (~1km) of the supplement point
        replace_idx = None
        for i, o in enumerate(merged):
            if abs(o["y"] - s["y"]) < 0.01 and abs(o["x"] - s["x"]) < 0.01:
                replace_idx = i
                break
        if replace_idx is not None:
            merged[replace_idx] = s
            supp_replaced += 1
        else:
            merged.append(s)
            supp_added += 1

    return merged, supp_added, supp_replaced


def main():
    data = fetch_overpass()
    locs = process(data)
    print(f"✓ After dedupe: {len(locs)} OSM locations", file=sys.stderr)

    # Merge manual supplements (china-stores.csv + jp-stores.csv if present)
    here = Path(__file__).parent
    supp = load_supplement(here)
    if supp:
        print(f"→ Loaded {len(supp)} supplement rows total", file=sys.stderr)
        locs, added, replaced = merge(locs, supp)
        print(f"  +{added} added, {replaced} replaced/updated", file=sys.stderr)
    else:
        print(f"  (no supplement CSVs found)", file=sys.stderr)

    # Country distribution sanity check
    from collections import Counter

    def country(loc):
        lat, lng = loc["y"], loc["x"]
        if 24 < lat < 46 and 123 < lng < 146: return "JP"
        if 21 < lat < 26 and 119 < lng < 123: return "TW"
        if 22 < lat < 23 and 113 < lng < 115: return "HK"
        if 1 < lat < 2 and 103 < lng < 104: return "SG"
        if 33 < lat < 39 and 126 < lng < 130: return "KR"
        if 13 < lat < 19 and 100 < lng < 105: return "TH"
        if 18 < lat < 42 and 104 < lng < 122: return "CN"
        if -7 < lat < -6 and 106 < lng < 107: return "ID"
        if 1 < lat < 7 and 100 < lng < 120: return "MY"
        return "??"

    c = Counter(country(l) for l in locs)
    print(f"  Distribution: {dict(c)}", file=sys.stderr)

    # Read template and inject data
    template_path = here / "template.html"
    if not template_path.exists():
        print(f"ERROR: template.html not found next to build.py", file=sys.stderr)
        sys.exit(1)

    template = template_path.read_text(encoding="utf-8")
    data_json = json.dumps(locs, ensure_ascii=False, separators=(",", ":"))
    count_str = str(len(locs))

    placeholder = "/*__SUSHIRO_DATA__*/[]"
    if placeholder not in template:
        print(f"ERROR: placeholder {placeholder} not found in template.html", file=sys.stderr)
        sys.exit(1)

    html = template.replace(placeholder, data_json)
    html = html.replace("__SUSHIRO_COUNT__", count_str)

    out_path = here / "index.html"
    out_path.write_text(html, encoding="utf-8")

    size_kb = out_path.stat().st_size / 1024
    print(f"✓ Wrote {out_path} ({size_kb:.1f} KB, {len(locs)} stores embedded)", file=sys.stderr)
    print(f"\nNext step: commit and push index.html to your GitHub Pages repo.", file=sys.stderr)


if __name__ == "__main__":
    main()
