"""
Dechert careers fetcher.

Dechert exposes a proprietary JSON API at /bin/careersSearch (backed by
Workday dechert.wd12.myworkdayjobs.com). We hit that directly, filter by
Luxembourg location, and return lawyer/law-student type positions only.

Endpoint discovered from clientlib-site JS:
  buildCareersSearchQuery = path + "?pageApp=getCareers&count=N&display=N"
  fetch(url) -> { Total, OpenPositions: [{ID, Title, Locations, Type, Url, Posted}] }
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List

import requests

from config import USER_AGENT, REQUEST_TIMEOUT

log = logging.getLogger(__name__)

DECHERT_API = "https://www.dechert.com/bin/careersSearch"
_LAWYER_TYPES = {"Experienced Lawyer", "Law Student"}


def fetch_dechert(source: Dict[str, Any]) -> List[Dict[str, Any]]:
    firm = source["firm"]
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "application/json",
        "Referer": "https://www.dechert.com/careers.html",
    }
    params = {
        "pageApp": "getCareers",
        "count": "200",
        "display": "200",
        "isLink": "false",
    }
    try:
        r = requests.get(DECHERT_API, headers=headers, params=params, timeout=REQUEST_TIMEOUT)
    except requests.RequestException as e:
        log.warning("[%s] Dechert API request failed: %s", firm, e)
        return []

    if r.status_code != 200:
        log.warning("[%s] Dechert API returned %d", firm, r.status_code)
        return []

    try:
        data = r.json()
    except ValueError:
        log.warning("[%s] Dechert API non-JSON response", firm)
        return []

    positions = data.get("OpenPositions", [])
    jobs: List[Dict[str, Any]] = []

    for p in positions:
        # Only legal roles
        if p.get("Type") not in _LAWYER_TYPES:
            continue

        locations = p.get("Locations", [])
        loc_names = [loc.get("Location", "") for loc in locations]

        # Keep only Luxembourg-based positions
        lu_locs = [l for l in loc_names if "luxembourg" in l.lower()]
        if not lu_locs:
            continue

        title = (p.get("Title") or "").strip()
        if not title:
            continue

        job_id = p.get("ID") or ""
        url = p.get("Url") or source.get("url", "")
        posted = p.get("Posted") or None
        # Posted field can be "2026-03-30" (ISO) or free text — pass as-is, normalizer ignores non-ISO
        if posted and len(posted) >= 10:
            posted = posted[:10]
        else:
            posted = None

        jobs.append({
            "firm": firm,
            "title": title,
            "location": lu_locs[0],
            "url": url,
            "external_id": f"dechert::{job_id}",
            "posted_date": posted,
            "source_type": "Dechert API",
        })

    log.info("[%s] Dechert API: %d Luxembourg lawyer jobs (of %d total)", firm, len(jobs), len(positions))
    return jobs
