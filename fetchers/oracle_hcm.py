"""
Oracle HCM Cloud Candidate Experience (CX) API fetcher.

Oracle HCM exposes a public REST endpoint used by its candidate site:
    {base}/hcmRestApi/resources/latest/recruitingCEJobRequisitions
It accepts query parameters:
    onlyData=true
    expand=requisitionList.secondaryLocations,requisitionList.requisitionFlexFields
    finder=findReqs;siteNumber={SITE},facetsList=LOCATIONS;SKILLS;DEPARTMENTS;JOB_FUNCTION;LOCATIONS_CITY;POSTING_DATES,limit=25,sortBy=POSTING_DATES_DESC

We fetch in pages, client-filter by location containing "luxembourg".
Pinsent Masons uses tenant `ehpy.fa.em5.oraclecloud.com` site `CX_1001`.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List

import requests

from config import USER_AGENT, REQUEST_TIMEOUT

log = logging.getLogger(__name__)


def fetch_oracle_hcm(source: Dict[str, Any]) -> List[Dict[str, Any]]:
    base = source["base"]
    site = source["site"]
    firm = source["firm"]

    endpoint = f"{base}/hcmRestApi/resources/latest/recruitingCEJobRequisitions"
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "application/json",
        "Referer": source["search_url"],
    }

    jobs: List[Dict[str, Any]] = []
    limit = 25
    offset = 0
    max_pages = 20

    for _ in range(max_pages):
        params = {
            "onlyData": "true",
            "expand": "requisitionList.secondaryLocations,requisitionList.requisitionFlexFields",
            "finder": (
                f"findReqs;siteNumber={site},"
                f"facetsList=LOCATIONS;POSTING_DATES;JOB_FUNCTION,"
                f"limit={limit},offset={offset},"
                f"sortBy=POSTING_DATES_DESC"
            ),
        }
        try:
            r = requests.get(endpoint, headers=headers, params=params, timeout=REQUEST_TIMEOUT)
        except requests.RequestException as e:
            log.warning("[%s] Oracle HCM request failed: %s", firm, e)
            break
        if r.status_code != 200:
            log.warning("[%s] Oracle HCM returned %d", firm, r.status_code)
            break
        try:
            data = r.json()
        except ValueError:
            log.warning("[%s] Oracle HCM non-JSON response", firm)
            break

        items = data.get("items", [])
        if not items:
            break

        # The API nests the actual requisition list
        reqs = items[0].get("requisitionList", []) if items else []
        if not reqs:
            break

        for req in reqs:
            title = req.get("Title") or req.get("title") or ""
            # Location can be in several fields
            location = (
                req.get("PrimaryLocation")
                or req.get("primaryLocation")
                or ""
            )
            req_id = req.get("Id") or req.get("id") or req.get("ReqId") or ""
            # Build candidate-facing URL
            url = f"{source['search_url'].split('?')[0]}/job/{req_id}"
            posted = req.get("PostedDate") or req.get("postedDate")

            jobs.append({
                "firm": firm,
                "title": str(title).strip(),
                "location": str(location).strip(),
                "url": url,
                "external_id": f"oracle::{req_id}",
                "posted_date": posted[:10] if posted else None,
                "source_type": "Oracle HCM",
            })

        total = items[0].get("TotalJobsCount", len(reqs))
        offset += limit
        if offset >= total:
            break

    log.info("[%s] Oracle HCM fetched %d jobs", firm, len(jobs))
    return jobs
