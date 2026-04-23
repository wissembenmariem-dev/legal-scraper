"""
Workday CXS (Candidate Experience Service) JSON API fetcher.

Workday sites expose a public JSON endpoint under /wday/cxs/<tenant>/<site>/jobs
which accepts POST with limit/offset/searchText/appliedFacets.
This is the same endpoint the React SPA calls — much faster and more reliable
than scraping the rendered HTML.
"""
from __future__ import annotations

import logging
import re
from datetime import date, timedelta
from typing import List, Dict, Any, Optional
import requests

from config import USER_AGENT, REQUEST_TIMEOUT

log = logging.getLogger(__name__)


def _parse_workday_posted(raw: Optional[str]) -> Optional[str]:
    """Workday returns human-readable relative dates like:
        'Posted Today', 'Posted Yesterday', 'Posted 7 Days Ago',
        'Posted 30+ Days Ago', 'Posted Jan 15, 2026'
    We convert to ISO 8601 date strings (best effort).
    Returns None if we can't parse — the caller will skip the field.
    """
    if not raw:
        return None
    s = str(raw).strip().lower().replace("posted", "").strip()
    today = date.today()
    if not s or s in {"today"}:
        return today.isoformat()
    if s in {"yesterday"}:
        return (today - timedelta(days=1)).isoformat()
    # "7 days ago", "30+ days ago"
    m = re.match(r"(\d+)\+?\s+days?\s+ago", s)
    if m:
        return (today - timedelta(days=int(m.group(1)))).isoformat()
    m = re.match(r"(\d+)\+?\s+months?\s+ago", s)
    if m:
        return (today - timedelta(days=30 * int(m.group(1)))).isoformat()
    # Try ISO passthrough
    m = re.match(r"\d{4}-\d{2}-\d{2}", s)
    if m:
        return m.group(0)
    return None


def fetch_workday(source: Dict[str, Any], location_filter: str = "luxembourg") -> List[Dict[str, Any]]:
    """Fetch Workday jobs matching the location_filter keyword.

    We pass searchText=<location_filter> so Workday filters server-side. This
    catches multi-location jobs like "3 Locations" whose locationsText hides
    the actual cities — they still come back if Luxembourg is one of them.
    False positives (Luxembourg mentioned in description only) are filtered
    out downstream by normalizer.is_luxembourg().
    """
    host = source["host"]
    tenant = source["tenant"]
    site = source["site"]
    firm = source["firm"]

    endpoint = f"https://{host}/wday/cxs/{tenant}/{site}/jobs"
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "application/json",
        "Content-Type": "application/json",
        "Origin": f"https://{host}",
        "Referer": source["search_url"],
    }

    jobs: List[Dict[str, Any]] = []
    limit = 20
    offset = 0
    max_pages = 20  # safety cap — 400 jobs max per tenant

    for _ in range(max_pages):
        payload = {
            "appliedFacets": {},
            "limit": limit,
            "offset": offset,
            "searchText": location_filter,
        }
        try:
            r = requests.post(endpoint, json=payload, headers=headers, timeout=REQUEST_TIMEOUT)
        except requests.RequestException as e:
            log.warning("[%s] Workday request failed offset=%d: %s", firm, offset, e)
            break

        if r.status_code != 200:
            log.warning("[%s] Workday returned %d at offset=%d", firm, r.status_code, offset)
            break

        try:
            data = r.json()
        except ValueError:
            log.warning("[%s] Workday returned non-JSON at offset=%d", firm, offset)
            break

        postings = data.get("jobPostings", [])
        if not postings:
            break

        for p in postings:
            external_path = p.get("externalPath", "")
            # Build absolute URL
            if external_path.startswith("/"):
                url = f"https://{host}{external_path}"
            else:
                # myworkdaysite URLs usually need the /recruiting/ prefix
                url = f"{source['search_url'].rstrip('/')}{external_path}" if external_path else source["search_url"]

            # locationsText can be "N Locations" for multi-city jobs — in that case
            # fall back to the city segment in the externalPath (e.g. /job/Luxembourg/...)
            loc = (p.get("locationsText") or "").strip()
            if re.match(r"^\d+\s+Locations?$", loc, re.I):
                m = re.search(r"/job/([^/]+)/", external_path)
                if m:
                    loc = m.group(1).replace("-", " ")

            jobs.append({
                "firm": firm,
                "title": (p.get("title") or "").strip(),
                "location": loc,
                "url": url,
                "external_id": p.get("bulletFields", [""])[0] or external_path,
                "posted_date": _parse_workday_posted(p.get("postedOn")),
                "source_type": "Workday API",
            })

        total = data.get("total", 0)
        offset += limit
        if offset >= total:
            break

    log.info("[%s] Workday fetched %d jobs", firm, len(jobs))
    return jobs
