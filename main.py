"""
Main orchestrator — Legal Jobs Luxembourg daily scraper.

Flow:
  1. Load existing Notion pages (index by External ID)
  2. Fetch all sources (Workday API, Oracle HCM, HTML parsers) — errors isolated per source
  3. Normalize: LU filter + keyword filter + classify seniority/category + dedup
  4. Upsert into Notion (create new / update Last Seen on existing)
  5. Close stale pages (not seen in this run, with grace period)
  6. Send morning digest email via Resend

Exit code is 0 even if some sources fail — we still want the email sent.
Exit code is non-zero only if Notion or Resend is completely unreachable.
"""
from __future__ import annotations

import logging
import os
import sys
import time
import traceback
from datetime import datetime
from typing import Any, Dict, List
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

# Load .env for local runs; GitHub Actions injects env vars directly
load_dotenv()

from config import WORKDAY_SOURCES, ORACLE_SOURCES, HTML_SOURCES, DECHERT_SOURCES
from fetchers.workday import fetch_workday
from fetchers.oracle_hcm import fetch_oracle_hcm
from fetchers.html_generic import fetch_html
from fetchers.dechert import fetch_dechert
from normalizer import normalize_and_filter
from notion_client import NotionClient
import email_report

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-5s %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("main")


def run_source(fn, source, errors) -> List[Dict[str, Any]]:
    """Execute a fetcher with full error isolation."""
    label = source.get("firm") or source.get("url", "?")
    try:
        start = time.time()
        jobs = fn(source) or []
        log.info("✓ %s: %d raw jobs in %.1fs", label, len(jobs), time.time() - start)
        return jobs
    except Exception as e:
        log.error("✗ %s: %s", label, e)
        log.debug(traceback.format_exc())
        errors.append({"firm": label, "error": str(e)})
        return []


def _should_run_now() -> bool:
    """Time guard for GitHub Actions dual-cron.

    We schedule two crons (06:30 UTC and 07:30 UTC) because Brussels alternates
    between CET (UTC+1, winter) and CEST (UTC+2, summer). Only one of these
    corresponds to 08:30 Brussels on any given day. This guard lets that run
    proceed and exits early on the other, so the script effectively runs
    exactly once per day at 08:30 Brussels local time — summer and winter.

    Skipped entirely when not running under GitHub Actions (manual / local
    invocations always proceed).
    """
    if not os.environ.get("GITHUB_ACTIONS"):
        return True
    now_brussels = datetime.now(ZoneInfo("Europe/Brussels"))
    # Accept a ±15 min window around 08:30 to absorb GitHub Actions queueing delays
    in_window = now_brussels.hour == 8 and 15 <= now_brussels.minute <= 45
    if not in_window:
        log.info(
            "Skipping run: Brussels local time is %s, outside the 08:15–08:45 window.",
            now_brussels.strftime("%H:%M %Z"),
        )
    return in_window


def main() -> int:
    if not _should_run_now():
        return 0

    tz = ZoneInfo(os.environ.get("TZ", "Europe/Luxembourg"))
    today = datetime.now(tz).date().isoformat()
    log.info("=" * 60)
    log.info("Legal Jobs LUX — daily run %s", today)
    log.info("=" * 60)

    errors: List[Dict[str, Any]] = []

    # --- 1. Load Notion state ------------------------------------------
    try:
        notion = NotionClient()
        existing = notion.load_existing()
    except Exception as e:
        log.exception("FATAL: cannot load Notion state: %s", e)
        return 2

    # --- 2. Fetch all sources ------------------------------------------
    raw: List[Dict[str, Any]] = []

    log.info("-- Workday API sources --")
    for src in WORKDAY_SOURCES:
        raw.extend(run_source(fetch_workday, src, errors))

    log.info("-- Oracle HCM sources --")
    for src in ORACLE_SOURCES:
        raw.extend(run_source(fetch_oracle_hcm, src, errors))

    log.info("-- HTML sources --")
    for src in HTML_SOURCES:
        raw.extend(run_source(fetch_html, src, errors))

    log.info("-- Dechert API --")
    for src in DECHERT_SOURCES:
        raw.extend(run_source(fetch_dechert, src, errors))

    log.info("Total raw jobs scraped: %d", len(raw))

    # --- 3. Normalize & filter -----------------------------------------
    filtered = normalize_and_filter(raw)
    log.info("Filtered (LU + keywords): %d jobs", len(filtered))

    # --- 4. Upsert into Notion -----------------------------------------
    new_jobs: List[Dict[str, Any]] = []
    active_jobs: List[Dict[str, Any]] = []  # seen today but already known
    seen_ids = set()

    for job in filtered:
        seen_ids.add(job["external_id"])
        try:
            action, is_new, first_seen = notion.upsert_job(job, existing, today)
            if is_new:
                new_jobs.append(job)
            else:
                active_jobs.append({**job, "first_seen": first_seen})
        except Exception as e:
            log.error("Upsert failed for %s / %s: %s", job["firm"], job["title"], e)
            errors.append({"firm": job["firm"], "error": f"upsert: {e}"})

    # --- 5. Close stale ------------------------------------------------
    closed = notion.close_stale(seen_ids, existing, today, grace_days=2)

    # --- 5b. Firms with no relevant results today ----------------------
    all_firms = sorted({s["firm"] for s in WORKDAY_SOURCES + ORACLE_SOURCES + HTML_SOURCES + DECHERT_SOURCES})
    firms_with_results = {j["firm"] for j in filtered}
    firms_without_results = sorted(f for f in all_firms if f not in firms_with_results)

    log.info("Summary: new=%d active=%d closed=%d errors=%d no_results=%d",
             len(new_jobs), len(active_jobs), len(closed), len(errors),
             len(firms_without_results))

    # --- 6. Send email -------------------------------------------------
    try:
        email_report.build_and_send(new_jobs, active_jobs, closed, errors, firms_without_results)
    except Exception as e:
        log.exception("Email send failed: %s", e)
        return 3

    return 0


if __name__ == "__main__":
    sys.exit(main())
