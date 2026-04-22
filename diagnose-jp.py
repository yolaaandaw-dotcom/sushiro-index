#!/usr/bin/env python3
"""
diagnose-jp.py — figure out why some stores are failing.

Run this AFTER fetch-jp.py has made some progress. It finds stores that
failed, re-fetches a few, and shows what the regexes are/aren't matching.
"""

import json
import urllib.request
import urllib.error
import re
import sys
from pathlib import Path

BASE = "https://www.akindo-sushiro.co.jp"
UA = "Mozilla/5.0 sushiro-index-builder (personal, non-commercial)"
HERE = Path(__file__).parent
CACHE_FILE = HERE / ".jp-stores-cache.json"


def fetch_url(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8", errors="replace")


def main():
    if not CACHE_FILE.exists():
        print("No cache file. Run fetch-jp.py first.")
        sys.exit(1)

    cache = json.loads(CACHE_FILE.read_text(encoding="utf-8"))

    # Find failed store IDs (where result is None)
    failed_ids = [int(sid) for sid, r in cache["results"].items() if r is None]
    ok_ids = [int(sid) for sid, r in cache["results"].items() if r is not None]

    print(f"Cache has:")
    print(f"  {len(ok_ids)} successful stores")
    print(f"  {len(failed_ids)} failed stores")
    print(f"  {len(cache['all_ids']) - len(cache['results'])} not yet attempted")
    print()

    if not failed_ids:
        print("No failures — nothing to diagnose.")
        return

    # Inspect up to 3 failures
    sample = failed_ids[:3]
    print(f"Inspecting {len(sample)} failed stores:\n")

    for sid in sample:
        url = f"{BASE}/apps/shop/detail.php?id={sid}"
        print(f"━━━ Store ID {sid} ━━━")
        print(f"URL: {url}")
        try:
            html = fetch_url(url)
        except urllib.error.HTTPError as e:
            print(f"  → HTTP {e.code} ({e.reason})")
            print()
            continue
        except Exception as e:
            print(f"  → Fetch error: {e}")
            print()
            continue

        print(f"  HTML length: {len(html)} chars")

        # Try coord regex
        m = re.search(r"maps\.google\.com/maps\?ll=(-?\d+\.\d+),(-?\d+\.\d+)", html)
        print(f"  Coord match: {m.groups() if m else 'NONE'}")

        # Try alternate coord patterns
        alt_patterns = [
            (r'll=(-?\d+\.\d+),(-?\d+\.\d+)', 'll= anywhere'),
            (r'"lat"\s*:\s*(-?\d+\.\d+)', 'lat JSON field'),
            (r'data-lat="(-?\d+\.\d+)"', 'data-lat attribute'),
            (r'center=(-?\d+\.\d+),(-?\d+\.\d+)', 'center= param'),
            (r'@(-?\d+\.\d+),(-?\d+\.\d+)', '@LAT,LNG format'),
        ]
        for pat, desc in alt_patterns:
            m = re.search(pat, html)
            if m:
                print(f"  ✓ Alternate match [{desc}]: {m.groups()}")

        # Name
        m = re.search(r"<h1[^>]*>\s*([^<]+?)の店舗情報\s*</h1>", html)
        print(f"  Name (h1): {m.group(1) if m else 'NONE'}")
        m2 = re.search(r"<title>\s*([^<|]+?)の店舗情報", html)
        print(f"  Name (title): {m2.group(1) if m2 else 'NONE'}")

        # Show a small HTML sample around 'maps.google' or '住所' if present
        for marker in ("maps.google", "住所", "Google map"):
            idx = html.find(marker)
            if idx >= 0:
                start = max(0, idx - 100)
                end = min(len(html), idx + 300)
                snippet = html[start:end].replace("\n", " ").replace("\r", "")
                snippet = re.sub(r"\s+", " ", snippet)
                print(f"  Near '{marker}': ...{snippet}...")
                break

        # Save this HTML for manual inspection
        sample_file = HERE / f".debug-store-{sid}.html"
        sample_file.write_text(html, encoding="utf-8")
        print(f"  Saved full HTML to: {sample_file.name}")
        print()


if __name__ == "__main__":
    main()
