#!/usr/bin/env python3
"""
fetch-jp.py — scrapes akindo-sushiro.co.jp for all Japan store data
(name, address, precise coordinates) and writes to `jp-stores.csv`.

Usage:
    python3 fetch-jp.py

Output:
    jp-stores.csv  (~650 stores)

This takes ~5-10 minutes. It's polite to the server (0.3s between requests
and a real User-Agent). If interrupted, it saves progress — rerun to resume.

No dependencies — standard library only.
"""

import urllib.request
import urllib.error
import csv
import re
import sys
import time
import json
from pathlib import Path

BASE = "https://www.akindo-sushiro.co.jp"
UA = "Mozilla/5.0 sushiro-index-builder (personal, non-commercial)"
DELAY = 0.3  # seconds between requests

HERE = Path(__file__).parent
CACHE_FILE = HERE / ".jp-stores-cache.json"
OUTPUT_FILE = HERE / "jp-stores.csv"


def fetch_url(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8", errors="replace")


def get_store_ids_for_pref(pref):
    """Return list of store IDs from a prefecture's list page."""
    html = fetch_url(f"{BASE}/shop/?pref={pref}")
    ids = set()
    for m in re.finditer(r"detail\.php\?id=(\d+)", html):
        ids.add(int(m.group(1)))
    return sorted(ids)


def parse_store_detail(store_id):
    """Fetch one detail page and return (name, address, lat, lng) or None on failure."""
    url = f"{BASE}/apps/shop/detail.php?id={store_id}"
    html = fetch_url(url)

    # Coordinates: from the embedded Google Maps URL
    m = re.search(r"maps\.google\.com/maps\?ll=(-?\d+\.\d+),(-?\d+\.\d+)", html)
    if not m:
        return None
    lat = float(m.group(1))
    lng = float(m.group(2))

    # Store name: from <h1>XXX店の店舗情報</h1> pattern. The title tag also works.
    name = None
    m = re.search(r"<h1[^>]*>\s*([^<]+?)の店舗情報\s*</h1>", html)
    if m:
        name = m.group(1).strip()
    else:
        # Fallback: <title>XXX店の店舗情報 | ...</title>
        m = re.search(r"<title>\s*([^<|]+?)の店舗情報", html)
        if m:
            name = m.group(1).strip()
    if not name:
        name = f"スシロー (id {store_id})"

    # Address: row with 住所 label. Try a few shapes.
    address = ""
    # Shape 1: <th>住所</th><td>ADDR ...</td>
    m = re.search(r"住所[^<]*</th>\s*<td[^>]*>([^<]+)", html)
    if m:
        address = m.group(1).strip()
    if not address:
        # Shape 2: <td ...>住所</td><td ...>ADDR ...</td>
        m = re.search(r">\s*住所\s*</td>\s*<td[^>]*>([^<]+)", html)
        if m:
            address = m.group(1).strip()
    # Clean up: remove the "Google mapで開く" part and leading/trailing separators
    address = re.sub(r"\s*Google.*$", "", address).strip()
    address = address.replace("&nbsp;", " ")

    return (name, address, lat, lng)


def load_cache():
    if CACHE_FILE.exists():
        with open(CACHE_FILE, encoding="utf-8") as f:
            return json.load(f)
    return {"all_ids": [], "results": {}}


def save_cache(cache):
    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False)


def main():
    cache = load_cache()

    # Step 1: collect all store IDs from all 47 prefectures
    if not cache["all_ids"]:
        print("Step 1/2: collecting store IDs from 47 prefectures...", file=sys.stderr)
        all_ids = set()
        for pref in range(1, 48):
            try:
                ids = get_store_ids_for_pref(pref)
                all_ids.update(ids)
                print(f"  pref {pref:2d}: {len(ids):3d} stores (running total: {len(all_ids)})", file=sys.stderr)
            except Exception as e:
                print(f"  pref {pref:2d}: FAILED ({e})", file=sys.stderr)
            time.sleep(DELAY)
        cache["all_ids"] = sorted(all_ids)
        save_cache(cache)
        print(f"  → Total unique stores: {len(cache['all_ids'])}", file=sys.stderr)
    else:
        print(f"Resuming with {len(cache['all_ids'])} IDs cached", file=sys.stderr)

    # Step 2: fetch detail pages for stores not yet in cache
    print(f"\nStep 2/2: fetching {len(cache['all_ids'])} detail pages...", file=sys.stderr)
    total = len(cache["all_ids"])
    done = len(cache["results"])
    failures = 0

    try:
        for i, sid in enumerate(cache["all_ids"]):
            sid_str = str(sid)
            if sid_str in cache["results"]:
                continue
            try:
                result = parse_store_detail(sid)
                if result:
                    name, address, lat, lng = result
                    cache["results"][sid_str] = {
                        "n": name, "a": address, "y": lat, "x": lng
                    }
                    done += 1
                else:
                    failures += 1
                    cache["results"][sid_str] = None  # mark as attempted
            except urllib.error.HTTPError as e:
                if e.code == 404:
                    # Store no longer exists — skip silently
                    cache["results"][sid_str] = None
                else:
                    failures += 1
                    print(f"  id {sid}: HTTP {e.code}", file=sys.stderr)
            except Exception as e:
                failures += 1
                print(f"  id {sid}: {e}", file=sys.stderr)

            # Save progress every 25 stores and show progress every 10
            if (i + 1) % 25 == 0:
                save_cache(cache)
            if (i + 1) % 10 == 0:
                pct = (i + 1) * 100 // total
                print(f"  {i + 1:4d} / {total}  ({pct}%)  ok={done}  failed={failures}", file=sys.stderr)

            time.sleep(DELAY)
    except KeyboardInterrupt:
        print("\nInterrupted — saving progress", file=sys.stderr)
        save_cache(cache)
        sys.exit(1)

    save_cache(cache)

    # Step 3: write CSV
    rows = [r for r in cache["results"].values() if r is not None]
    print(f"\n✓ Got {len(rows)} stores with full data (failures: {failures})", file=sys.stderr)

    with open(OUTPUT_FILE, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["name", "address", "lat", "lng"])
        for r in rows:
            w.writerow([r["n"], r["a"] or "日本", round(r["y"], 6), round(r["x"], 6)])

    print(f"✓ Wrote {OUTPUT_FILE}", file=sys.stderr)
    print(f"\nNow run:  python3 build.py", file=sys.stderr)


if __name__ == "__main__":
    main()
