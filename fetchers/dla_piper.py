"""
DLA Piper careers fetcher.

DLA Piper uses a proprietary OpenCms endpoint at
  /system/modules/com.dlapiper.careers/functions/get-jobs.json
accepting POST with JSON body: {query, country, page, sort}.

Endpoint discovered from the `LoadPosts` class in bundle.js — the same one
the jobs page uses to render job cards client-side. Much more reliable than
trying to scrape the JS-rendered HTML.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List
from urllib.parse import urljoin

import requests

from config import USER_AGENT, REQUEST_TIMEOUT

log = logging.getLogger(__name__)

DLA_API = "https://careers.dlapiper.com/system/modules/com.dlapiper.careers/functions/get-jobs.json"
DLA_BASE = "https://careers.dlapiper.com"


def fetch_dla_piper(source: Dict[str, Any]) -> List[Dict[str, Any]]:
    firm = source["firm"]
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "application/json",
        "Content-Type": "application/json",
        "Referer": "https://careers.dlapiper.com/jobs/?country=Luxembourg&sort=by-default",
    }

    jobs: List[Dict[str, Any]] = []
    page = 1
    max_pages = 10

    while page <= max_pages:
        payload = {"query": "", "country": "Luxembourg", "page": str(page), "sort": "by-default"}
        try:
            r = requests.post(DLA_API, json=payload, headers=headers, timeout=REQUEST_TIMEOUT)
        except requests.RequestException as e:
            log.warning("[%s] DLA Piper request failed page=%d: %s", firm, page, e)
            break

        if r.status_code != 200:
            log.warning("[%s] DLA Piper returned %d", firm, r.status_code)
            break

        try:
            data = r.json()
        except ValueError:
            log.warning("[%s] DLA Piper non-JSON response", firm)
            break

        items = data.get("items", [])
        if not items:
            break

        for item in items:
            title = (item.get("title") or "").strip()
            if not title:
                continue
            jobs.append({
                "firm": firm,
                "title": title,
                "location": item.get("location") or "Luxembourg",
                "url": urljoin(DLA_BASE, item.get("url", "")),
                "external_id": f"dla::{item.get('id','')}",
                "source_type": "DLA Piper API",
            })

        if not data.get("hasMore"):
            break
        page += 1

    log.info("[%s] DLA Piper API: %d Luxembourg jobs", firm, len(jobs))
    return jobs
