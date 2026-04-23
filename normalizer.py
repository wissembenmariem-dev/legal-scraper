"""
Normalization, filtering, and classification of scraped jobs.

Pipeline:
    raw_jobs -> normalize() -> is_luxembourg() -> matches_keywords() -> classify()

Each raw job comes from a fetcher with at least: firm, title, location, url,
external_id, source_type. Optional: posted_date.
"""
from __future__ import annotations

import hashlib
import logging
import re
import unicodedata
from typing import Any, Dict, List, Optional

from config import KEYWORDS, LU_TOKENS

log = logging.getLogger(__name__)

# IMPORTANT: all patterns match against titles that have been normalized
# with _norm() — lowercased AND stripped of diacritics. So write patterns
# without accents ("secretaire", not "secrétaire").
#
# Seniority detection — first match wins, order matters
SENIORITY_PATTERNS = [
    ("Managing Associate", r"\bmanaging\s+associate\b"),
    ("Senior Associate", r"\bsenior\s+associate\b"),
    ("Counsel", r"\b(of\s+counsel|counsel)\b"),
    ("Trainee/Stagiaire", r"\b(trainee|stagiaire|internship|intern|graduate)\b"),
    ("Junior", r"\b(junior|entry[\s-]?level)\b"),
    ("Associate", r"\bassociate\b"),
    ("Support", r"\b(secretaire|secretary|assistant|paralegal|administrative|support)\b"),
    # Partner is deliberately LAST because "business partner" is a false positive.
    # We only accept it when it's the whole word or at title start.
    ("Partner", r"(?:^|[\s\-|,])partner(?:s)?(?:\s|$|[\-\/,])"),
]

# Category detection based on title
CATEGORY_PATTERNS = [
    ("Trainee", r"\b(trainee|stagiaire|graduate|internship|intern)\b"),
    ("Legal Support", r"\b(secretaire\s+juridique|legal\s+secretary|legal\s+assistant|assistant\s+juridique|assistant\s+legal|paralegal|secretary)\b"),
    ("Lawyer", r"\b(avocat[es]?|lawyer|associate|counsel|attorney|jurist[e]?|partner)\b"),
]


def _norm(text: str) -> str:
    """Lowercase + strip accents + collapse whitespace. Used for matching."""
    if not text:
        return ""
    text = unicodedata.normalize("NFD", text)
    text = "".join(c for c in text if unicodedata.category(c) != "Mn")
    return re.sub(r"\s+", " ", text.lower()).strip()


def is_luxembourg(job: Dict[str, Any]) -> bool:
    """Return True if the job is clearly Luxembourg-based.

    Uses location field primarily; falls back to title hints.
    Empty location defaults to False — we prefer false negatives to false positives.
    """
    loc = _norm(job.get("location", ""))
    title = _norm(job.get("title", ""))
    for token in LU_TOKENS:
        if token in loc:
            return True
    # A couple of Luxembourg-only firms from our config can be whitelisted
    # so we keep their jobs even when location is blank.
    LU_ONLY_FIRMS = {
        "Elvinger Hoss", "BSP", "Kleyr Grasso", "Luther", "Molitor",
        "Brucher", "Arendt",
    }
    if job.get("firm") in LU_ONLY_FIRMS and not loc:
        return True
    # Title fallback (rare but useful)
    if "luxembourg" in title:
        return True
    return False


def matches_keywords(job: Dict[str, Any]) -> bool:
    """Return True if the job title matches at least one target keyword.

    Uses word-boundary regex — 'partner' will NOT match 'business partner'.
    All keywords are accent-stripped to match the normalized title.
    """
    title = _norm(job.get("title", ""))
    if not title:
        return False
    # Exclude leading trainee/intern/stagiaire roles (e.g. "Trainee Lawyer ...")
    # but allow combined roles like "Avocat(e) Stagiaire" where the senior term leads.
    if re.match(r"^(trainee|intern(?:ship)?|stagiaire|graduate)\b", title):
        return False
    for kw in KEYWORDS:
        kw_n = _norm(kw)
        # Multi-word keywords: substring is fine
        if " " in kw_n:
            if kw_n in title:
                return True
            continue
        # Single-word keywords: require word boundaries.
        # Special case: "partner" is only accepted as a standalone role,
        # never inside "business partner" / "hr partner" / etc.
        if kw_n == "partner":
            if re.search(r"(?:^|[\s\-|,\/])partner(?:s)?(?:\s|$|[\-\/,])", title):
                # reject common false positives
                if re.search(r"\b(business|hr|people|delivery|channel|industry)\s+partner", title):
                    continue
                return True
            continue
        if re.search(rf"\b{re.escape(kw_n)}\b", title):
            return True
    return False


def classify_seniority(title: str) -> Optional[str]:
    t = _norm(title)
    for label, pattern in SENIORITY_PATTERNS:
        if re.search(pattern, t):
            return label
    return None  # left blank in Notion rather than writing a placeholder


def classify_category(title: str) -> str:
    t = _norm(title)
    for label, pattern in CATEGORY_PATTERNS:
        if re.search(pattern, t):
            return label
    return "Other"


def make_external_id(job: Dict[str, Any]) -> str:
    """Build a stable unique ID for dedup across runs.

    Priority:
      1. Explicit external_id from source (if present)
      2. SHA-1 of (firm + normalized URL)
      3. SHA-1 of (firm + normalized title + normalized location)
    """
    if job.get("external_id"):
        return f"{job['firm']}::{job['external_id']}"[:1000]
    url = (job.get("url") or "").split("?")[0].rstrip("/")
    if url:
        h = hashlib.sha1(f"{job['firm']}|{url}".encode()).hexdigest()
        return f"{job['firm']}::url::{h}"
    title = _norm(job.get("title", ""))
    loc = _norm(job.get("location", ""))
    h = hashlib.sha1(f"{job['firm']}|{title}|{loc}".encode()).hexdigest()
    return f"{job['firm']}::tl::{h}"


def normalize_and_filter(raw_jobs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Apply the full pipeline: dedup + LU filter + keyword filter + classify."""
    out: List[Dict[str, Any]] = []
    seen_ids = set()

    for j in raw_jobs:
        # Normalize fields
        j["title"] = (j.get("title") or "").strip()
        j["location"] = (j.get("location") or "").strip()
        j["url"] = (j.get("url") or "").strip()
        j["firm"] = j.get("firm", "Unknown")

        if not j["title"]:
            continue

        # Luxembourg filter
        if not is_luxembourg(j):
            continue

        # Keyword filter
        if not matches_keywords(j):
            continue

        # External ID
        ext_id = make_external_id(j)
        if ext_id in seen_ids:
            continue
        seen_ids.add(ext_id)
        j["external_id"] = ext_id

        # Classification
        j["category"] = classify_category(j["title"])
        j["seniority"] = classify_seniority(j["title"])

        out.append(j)

    log.info("Normalizer: kept %d / %d raw jobs after LU + keyword filters", len(out), len(raw_jobs))
    return out
