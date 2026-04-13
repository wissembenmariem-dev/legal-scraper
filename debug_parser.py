"""
Dumps the raw HTML of every HTML source to data/<firm>.html so you can
inspect what the scraper actually sees (vs. what your browser renders after JS).

Usage:
    python debug_parser.py              # dump everything
    python debug_parser.py bsp dla      # dump only matching firms (case-insensitive substring)

After running, zip the `data/` folder and paste it back to me; I'll write
dedicated parsers for each failing site based on the real DOM.
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path

import requests

from config import HTML_SOURCES, USER_AGENT, REQUEST_TIMEOUT

OUT = Path(__file__).parent / "data"
OUT.mkdir(exist_ok=True)


def slugify(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", s.lower()).strip("_")


def dump(source: dict) -> None:
    firm = source["firm"]
    url = source["url"]
    slug = slugify(firm)
    try:
        r = requests.get(
            url,
            headers={
                "User-Agent": USER_AGENT,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9,fr;q=0.8",
            },
            timeout=REQUEST_TIMEOUT,
        )
    except requests.RequestException as e:
        print(f"✗ {firm:<30} network error: {e}")
        return
    path = OUT / f"{slug}.html"
    path.write_text(r.text, encoding="utf-8", errors="replace")
    size_kb = len(r.text) / 1024
    print(f"✓ {firm:<30} {r.status_code}  {size_kb:>7.1f} kB  → {path.name}")


def main() -> None:
    filters = [a.lower() for a in sys.argv[1:]]
    for src in HTML_SOURCES:
        if filters and not any(f in src["firm"].lower() for f in filters):
            continue
        dump(src)
    print(f"\nAll dumps in: {OUT}")
    print("Zip this folder and share it with me for targeted parser fixes.")


if __name__ == "__main__":
    main()
