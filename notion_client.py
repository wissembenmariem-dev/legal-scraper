"""
Notion HTTP API client for the Legal Jobs Luxembourg database.

Contract with the rest of the pipeline:
- load_existing() -> dict[external_id -> dict{page_id, first_seen, last_seen, status, title, firm, url}]
- upsert_job(job, today_iso) -> tuple[status_str, is_new: bool]
    status_str in {"created", "updated", "reopened"}
- close_stale(seen_external_ids, today_iso, grace_days=1) -> list[dict] of pages closed

All jobs are dicts with at minimum:
    external_id, title, firm, location, url, source_type,
    category, seniority, posted_date (optional ISO date or None)
"""
from __future__ import annotations

import logging
import os
import time
from datetime import datetime, date, timedelta
from typing import Any, Dict, List, Optional, Tuple

import requests

log = logging.getLogger(__name__)

NOTION_API = "https://api.notion.com/v1"
NOTION_VERSION = "2022-06-28"


class NotionClient:
    def __init__(self, token: Optional[str] = None, database_id: Optional[str] = None):
        self.token = token or os.environ["NOTION_TOKEN"]
        self.database_id = (database_id or os.environ["NOTION_DATABASE_ID"]).replace("-", "")
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {self.token}",
            "Notion-Version": NOTION_VERSION,
            "Content-Type": "application/json",
        })

    # --- low-level ------------------------------------------------------

    def _request(self, method: str, path: str, json: Optional[dict] = None, retries: int = 3) -> dict:
        url = f"{NOTION_API}{path}"
        for attempt in range(retries):
            try:
                r = self.session.request(method, url, json=json, timeout=30)
            except requests.RequestException as e:
                log.warning("Notion %s %s network error: %s", method, path, e)
                time.sleep(2 ** attempt)
                continue

            if r.status_code == 429:
                wait = int(r.headers.get("Retry-After", "2"))
                log.warning("Notion rate-limited, sleeping %ds", wait)
                time.sleep(wait)
                continue
            if r.status_code >= 500:
                time.sleep(2 ** attempt)
                continue
            if r.status_code >= 400:
                raise RuntimeError(f"Notion {method} {path} -> {r.status_code}: {r.text[:500]}")
            return r.json()
        raise RuntimeError(f"Notion {method} {path}: exhausted retries")

    # --- load existing --------------------------------------------------

    def load_existing(self) -> Dict[str, Dict[str, Any]]:
        """Load every page in the database, indexed by External ID.

        Pages without an External ID are ignored (but logged).
        """
        index: Dict[str, Dict[str, Any]] = {}
        payload = {"page_size": 100}
        has_more = True
        next_cursor = None

        while has_more:
            body = dict(payload)
            if next_cursor:
                body["start_cursor"] = next_cursor
            data = self._request("POST", f"/databases/{self.database_id}/query", json=body)

            for page in data.get("results", []):
                props = page.get("properties", {})
                ext_id = _read_rich_text(props.get("ID (interne)"))
                if not ext_id:
                    continue
                index[ext_id] = {
                    "page_id": page["id"],
                    "first_seen": _read_date(props.get("First Seen")),
                    "last_seen": _read_date(props.get("Last Seen")),
                    "status": _read_select(props.get("Status")),
                    "title": _read_title(props.get("Title")),
                    "firm": _read_select(props.get("Firm")),
                    "url": _read_url(props.get("URL")),
                }
            has_more = data.get("has_more", False)
            next_cursor = data.get("next_cursor")

        log.info("Notion: loaded %d existing pages", len(index))
        return index

    # --- upsert --------------------------------------------------------

    def upsert_job(
        self,
        job: Dict[str, Any],
        existing_index: Dict[str, Dict[str, Any]],
        today_iso: str,
    ) -> Tuple[str, bool, Optional[str]]:
        """Create a new page or update Last Seen on an existing one.

        Returns (action, is_new, first_seen) where:
          - action is "created" | "updated" | "reopened"
          - is_new is True only on creation
          - first_seen is the ISO date the job was first seen (None for new jobs)
        """
        ext_id = job["external_id"]
        existing = existing_index.get(ext_id)

        if existing is None:
            # Create
            props = self._job_to_properties(job, today_iso, is_new=True)
            body = {
                "parent": {"database_id": self.database_id},
                "properties": props,
            }
            self._request("POST", "/pages", json=body)
            log.info("  + created: [%s] %s", job["firm"], job["title"])
            return ("created", True, None)

        # Update existing — refresh mutable fields too so earlier bad scrapes
        # (e.g. a parser that once extracted junk) get cleaned up on the next run.
        was_closed = existing.get("status") == "Closed"
        new_status = "Active"
        props_update: Dict[str, Any] = {
            "Last Seen": {"date": {"start": today_iso}},
            "Status": {"select": {"name": new_status}},
            "Title": {"title": [{"text": {"content": (job.get("title") or "Untitled")[:2000]}}]},
            "Location": {"rich_text": [{"text": {"content": (job.get("location") or "")[:2000]}}]},
            "URL": {"url": job.get("url") or None},
            "Source": {"select": {"name": job["source_type"]}},
        }
        if was_closed:
            # Reopened — wipe the stale closure date.
            props_update["Closed Date"] = {"date": None}
        if job.get("category"):
            props_update["Category"] = {"select": {"name": job["category"]}}
        if job.get("seniority"):
            props_update["Seniority"] = {"select": {"name": job["seniority"]}}
        if job.get("posted_date"):
            props_update["Posted Date"] = {"date": {"start": job["posted_date"]}}
        self._request("PATCH", f"/pages/{existing['page_id']}", json={"properties": props_update})
        action = "reopened" if was_closed else "updated"
        return (action, False, existing.get("first_seen"))

    def close_stale(
        self,
        seen_external_ids: set,
        existing_index: Dict[str, Dict[str, Any]],
        today_iso: str,
        grace_days: int = 2,
    ) -> List[Dict[str, Any]]:
        """Mark pages as Closed if they were not seen in this run AND their
        Last Seen is older than `grace_days` days.

        The grace window avoids flapping if a source temporarily errors out.
        """
        today = datetime.fromisoformat(today_iso).date()
        threshold = today - timedelta(days=grace_days)
        closed: List[Dict[str, Any]] = []

        for ext_id, info in existing_index.items():
            if ext_id in seen_external_ids:
                continue
            if info.get("status") == "Closed":
                continue
            last_seen = info.get("last_seen")
            try:
                last_seen_date = datetime.fromisoformat(last_seen).date() if last_seen else None
            except ValueError:
                last_seen_date = None
            if last_seen_date is None or last_seen_date <= threshold:
                self._request(
                    "PATCH",
                    f"/pages/{info['page_id']}",
                    json={"properties": {
                        "Status": {"select": {"name": "Closed"}},
                        "Closed Date": {"date": {"start": today_iso}},
                    }},
                )
                closed.append(info | {"external_id": ext_id, "closed_date": today_iso})
                log.info("  - closed: [%s] %s", info.get("firm"), info.get("title"))
        return closed

    # --- mapping -------------------------------------------------------

    @staticmethod
    def _job_to_properties(job: Dict[str, Any], today_iso: str, is_new: bool) -> Dict[str, Any]:
        props: Dict[str, Any] = {
            "Title": {"title": [{"text": {"content": (job.get("title") or "Untitled")[:2000]}}]},
            "Firm": {"select": {"name": job["firm"]}},
            "Location": {"rich_text": [{"text": {"content": (job.get("location") or "")[:2000]}}]},
            "URL": {"url": job.get("url") or None},
            "Status": {"select": {"name": "New" if is_new else "Active"}},
            "First Seen": {"date": {"start": today_iso}},
            "Last Seen": {"date": {"start": today_iso}},
            "Source": {"select": {"name": job["source_type"]}},
            "ID (interne)": {"rich_text": [{"text": {"content": job["external_id"][:2000]}}]},
        }
        if job.get("category"):
            props["Category"] = {"select": {"name": job["category"]}}
        if job.get("seniority"):
            props["Seniority"] = {"select": {"name": job["seniority"]}}
        if job.get("posted_date"):
            props["Posted Date"] = {"date": {"start": job["posted_date"]}}
        return props


# ---------- property readers --------------------------------------------------

def _read_title(prop: Optional[dict]) -> str:
    if not prop:
        return ""
    return "".join(rt.get("plain_text", "") for rt in prop.get("title", []))


def _read_rich_text(prop: Optional[dict]) -> str:
    if not prop:
        return ""
    return "".join(rt.get("plain_text", "") for rt in prop.get("rich_text", []))


def _read_select(prop: Optional[dict]) -> Optional[str]:
    if not prop:
        return None
    sel = prop.get("select")
    return sel.get("name") if sel else None


def _read_url(prop: Optional[dict]) -> Optional[str]:
    if not prop:
        return None
    return prop.get("url")


def _read_date(prop: Optional[dict]) -> Optional[str]:
    if not prop:
        return None
    d = prop.get("date")
    return d.get("start") if d else None
