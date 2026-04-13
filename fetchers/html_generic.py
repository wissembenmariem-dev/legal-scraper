"""
Generic HTML fetcher with per-site parser dispatch.

Each parser is a small function that takes a BeautifulSoup object and the
source URL, and returns a list of job dicts:
    { firm, title, location, url, external_id, source_type, posted_date? }

When a site cannot be parsed (JS-rendered, login, Cloudflare), the parser
function raises NotImplementedError — the orchestrator logs it and moves on.

Every parser is defensive: a broken selector returns an empty list, never
crashes the run. Logging is verbose so the user can see exactly what each
site returned.
"""
from __future__ import annotations

import hashlib
import logging
import re
from typing import Any, Callable, Dict, List, Optional
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from config import USER_AGENT, REQUEST_TIMEOUT

log = logging.getLogger(__name__)


# --- HTTP helper -----------------------------------------------------------

def _get(url: str, **kwargs) -> Optional[BeautifulSoup]:
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9,fr;q=0.8",
    }
    headers.update(kwargs.pop("headers", {}))
    try:
        r = requests.get(url, headers=headers, timeout=REQUEST_TIMEOUT, **kwargs)
    except requests.RequestException as e:
        log.warning("HTTP error GET %s: %s", url, e)
        return None
    if r.status_code != 200:
        log.warning("HTTP %d for %s", r.status_code, url)
        return None
    return BeautifulSoup(r.text, "lxml")


def _text(el) -> str:
    return re.sub(r"\s+", " ", el.get_text(" ", strip=True)) if el else ""


# --- Parser implementations -----------------------------------------------
#
# Each parser is based on the public structure of the site as of writing.
# If the site redesigns, the parser returns an empty list and logs a warning.
# Add new parsers here following the same contract.

def parse_elvinger_hoss(soup: BeautifulSoup, url: str, firm: str) -> List[Dict[str, Any]]:
    jobs = []
    for card in soup.select("article, .views-row, .job-item, .opportunity"):
        a = card.find("a", href=True)
        title_el = card.find(["h2", "h3", "h4"]) or a
        if not a or not title_el:
            continue
        href = urljoin(url, a["href"])
        title = _text(title_el)
        if not title:
            continue
        jobs.append({
            "firm": firm, "title": title,
            "location": "Luxembourg",
            "url": href,
            "external_id": None,
            "source_type": "HTML",
        })
    return jobs


def parse_bsp(soup: BeautifulSoup, url: str, firm: str) -> List[Dict[str, Any]]:
    """BSP's careers page lists vacancies inside cards. We only trust heading
    elements for the title — never the full card text (which is a multi-line
    description). Titles are capped at 180 chars as a safety net."""
    jobs = []
    for card in soup.select("article, .career-item, .job, .post, .vacancy"):
        title_el = card.find(["h1", "h2", "h3", "h4"])
        if not title_el:
            continue
        title = _text(title_el)
        if not title or len(title) > 180:
            continue
        a = title_el.find("a", href=True) or card.find("a", href=True)
        href = urljoin(url, a["href"]) if a else url
        jobs.append({
            "firm": firm, "title": title, "location": "Luxembourg",
            "url": href, "external_id": None, "source_type": "HTML",
        })
    return jobs


_KLEYR_GRASSO_EXCLUDE = {
    "Submit your Application",
    "Spontaneous application",
    "Internships and Stage judiciaire",
    "Independent law firm",
}


def parse_kleyr_grasso(soup: BeautifulSoup, url: str, firm: str) -> List[Dict[str, Any]]:
    """Kleyr Grasso lists jobs as bare <h3> elements — no per-job URLs.
    External ID is derived from firm+title so identical re-posts are deduped."""
    jobs = []
    for h3 in soup.find_all("h3"):
        title = _text(h3)
        if not title or title in _KLEYR_GRASSO_EXCLUDE or len(title) < 15:
            continue
        ext_id = hashlib.sha1(title.encode()).hexdigest()
        jobs.append({
            "firm": firm, "title": title, "location": "Luxembourg",
            "url": url,  # careers page — no per-job URL available
            "external_id": ext_id,
            "source_type": "HTML",
        })
    return jobs


def parse_luther(soup: BeautifulSoup, url: str, firm: str) -> List[Dict[str, Any]]:
    """Luther posts job descriptions as PDF files linked from the vacancies page.
    The anchor text is the job title (first line only — rest is contract details)."""
    jobs = []
    for a in soup.find_all("a", href=True):
        if "fileadmin" not in a["href"]:
            continue
        # Anchor text contains title + contract info on subsequent lines — take first line only
        first_line = a.get_text("\n", strip=True).split("\n")[0].strip()
        if not first_line or len(first_line) < 8:
            continue
        jobs.append({
            "firm": firm, "title": first_line, "location": "Luxembourg",
            "url": urljoin(url, a["href"]), "external_id": None, "source_type": "HTML",
        })
    return jobs


def parse_molitor(soup: BeautifulSoup, url: str, firm: str) -> List[Dict[str, Any]]:
    """Molitor lists jobs as direct <a> elements inside a #current-vacancies section."""
    jobs = []
    container = soup.find(id="current-vacancies") or soup.find(class_="current-vacancies")
    if not container:
        return jobs
    for a in container.find_all("a", href=True):
        title = _text(a)
        if not title or len(title) < 8:
            continue
        jobs.append({
            "firm": firm, "title": title, "location": "Luxembourg",
            "url": urljoin(url, a["href"]), "external_id": None, "source_type": "HTML",
        })
    return jobs


def parse_brucher(soup: BeautifulSoup, url: str, firm: str) -> List[Dict[str, Any]]:
    """Brucher posts jobs as links to PDF files in wp-content/uploads.
    Anchor text is the job title."""
    jobs = []
    for a in soup.find_all("a", href=True):
        if "wp-content/uploads" not in a["href"]:
            continue
        title = _text(a)
        if not title or len(title) < 8:
            continue
        jobs.append({
            "firm": firm, "title": title, "location": "Luxembourg",
            "url": a["href"], "external_id": None, "source_type": "HTML",
        })
    return jobs


def parse_cms(soup: BeautifulSoup, url: str, firm: str) -> List[Dict[str, Any]]:
    """CMS Luxembourg lists jobs as div.expert-card elements.
    The "View" link carries the URL; the title is in the card text between
    the all-caps category prefix and the LUXEMBOURG location suffix."""
    jobs = []
    for card in soup.select("div.expert-card"):
        a = card.select_one('a[class*="ptm_search--career-card"]')
        if not a:
            continue
        href = a.get("href", "")
        if not href:
            continue
        raw = _text(card).replace("View", "").strip()
        # Strip location suffix: "… LUXEMBOURG, LUXEMBOURG 16 Feb 2026"
        if "LUXEMBOURG" in raw:
            raw = raw[: raw.index("LUXEMBOURG")].strip()
        # Strip leading all-caps category prefix e.g. "STUDENT OPPORTUNITIES "
        title = re.sub(r"^[A-Z][A-Z\s&]+\s+", "", raw).strip()
        if not title or len(title) < 5:
            continue
        jobs.append({
            "firm": firm, "title": title, "location": "Luxembourg",
            "url": href, "external_id": None, "source_type": "HTML",
        })
    return jobs


def parse_nautadutilh(soup: BeautifulSoup, url: str, firm: str) -> List[Dict[str, Any]]:
    """NautaDutilh Luxembourg job links contain '/our-jobs/' in their href.
    The anchor text includes a description — we take only the first 120 chars
    up to the last word boundary to avoid truncating mid-word."""
    jobs = []
    seen_hrefs: set = set()
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if "our-jobs" not in href or href in seen_hrefs:
            continue
        seen_hrefs.add(href)
        # Prefer a heading child element; fall back to truncated anchor text
        heading = a.find(["h2", "h3", "h4"])
        if heading:
            title = _text(heading)
        else:
            full = _text(a)
            title = (full[:120].rsplit(" ", 1)[0] if len(full) > 120 else full).strip(" –-")
        if not title or len(title) < 10:
            continue
        jobs.append({
            "firm": firm, "title": title, "location": "Luxembourg",
            "url": urljoin(url, href), "external_id": None, "source_type": "HTML",
        })
    return jobs


def parse_stibbe(soup: BeautifulSoup, url: str, firm: str) -> List[Dict[str, Any]]:
    jobs = []
    for card in soup.select(".vacancy, .career-item, article"):
        a = card.find("a", href=True)
        title_el = card.find(["h2", "h3", "h4"]) or a
        if not (a and title_el):
            continue
        jobs.append({
            "firm": firm, "title": _text(title_el), "location": "Luxembourg",
            "url": urljoin(url, a["href"]), "external_id": None, "source_type": "HTML",
        })
    return jobs


def parse_loyens(soup: BeautifulSoup, url: str, firm: str) -> List[Dict[str, Any]]:
    """Loyens & Loeff Luxembourg uses FacetWP — job cards are div.fwpl-row.vacancy-card.
    Title is in .vacancy-title; link in .vacancy-link a (or first anchor in card)."""
    jobs = []
    for card in soup.select("div.fwpl-row.vacancy-card"):
        title_el = card.select_one(".vacancy-title")
        link_el = card.select_one(".vacancy-link a") or card.find("a", href=True)
        if not (title_el and link_el):
            continue
        jobs.append({
            "firm": firm, "title": _text(title_el), "location": "Luxembourg",
            "url": urljoin(url, link_el["href"]), "external_id": None, "source_type": "HTML",
        })
    return jobs


def parse_ashurst(soup: BeautifulSoup, url: str, firm: str) -> List[Dict[str, Any]]:
    """Ashurst uses cvmailuk, an old server-rendered ASP-style table."""
    jobs = []
    for row in soup.select("table tr"):
        a = row.find("a", href=True)
        if not a:
            continue
        cells = [_text(td) for td in row.find_all("td")]
        title = _text(a)
        location = cells[1] if len(cells) > 1 else ""
        jobs.append({
            "firm": firm, "title": title, "location": location,
            "url": urljoin(url, a["href"]), "external_id": None, "source_type": "HTML",
        })
    return jobs


def parse_dentons(soup: BeautifulSoup, url: str, firm: str) -> List[Dict[str, Any]]:
    jobs = []
    for card in soup.select(".jobTitle-link, .job-result, article, .tileContent"):
        a = card if card.name == "a" else card.find("a", href=True)
        if not a:
            continue
        title = _text(a)
        if not title:
            continue
        jobs.append({
            "firm": firm, "title": title, "location": "Luxembourg",
            "url": urljoin(url, a.get("href", url)), "external_id": None, "source_type": "HTML",
        })
    return jobs


def parse_clifford_chance(soup: BeautifulSoup, url: str, firm: str) -> List[Dict[str, Any]]:
    """Clifford Chance uses the Attrax ATS — job tiles are <a class="attrax-vacancy-tile__title">.
    Location is derived from the href slug (contains "in-luxembourg" for LU roles)."""
    jobs = []
    for a in soup.select("a.attrax-vacancy-tile__title"):
        title = _text(a)
        href = urljoin(url, a["href"])
        loc = "Luxembourg" if "luxembourg" in href.lower() or "luxembourg" in title.lower() else ""
        if not title:
            continue
        jobs.append({
            "firm": firm, "title": title, "location": loc,
            "url": href, "external_id": None, "source_type": "HTML",
        })
    if not jobs:
        log.info("[%s] No jobs parsed — attrax tile selector returned empty", firm)
    return jobs


def parse_gsk(soup: BeautifulSoup, url: str, firm: str) -> List[Dict[str, Any]]:
    jobs = []
    for card in soup.select(".job-item, .vacancy, article, li.job"):
        a = card.find("a", href=True)
        title_el = card.find(["h2", "h3", "h4"]) or a
        if not (a and title_el):
            continue
        loc = _text(card.find(class_=re.compile(r"location|standort", re.I)))
        jobs.append({
            "firm": firm, "title": _text(title_el), "location": loc,
            "url": urljoin(url, a["href"]), "external_id": None, "source_type": "HTML",
        })
    return jobs


def parse_generic_fallback(soup: BeautifulSoup, url: str, firm: str) -> List[Dict[str, Any]]:
    """Last-resort: find any anchor that looks like a job link.

    IMPORTANT: location is left blank — do NOT assume Luxembourg. The
    normalizer's is_luxembourg() filter will then drop off-country roles.
    Parents containing a '.location' / 'location' class are inspected as a
    best effort to recover a real location.
    """
    jobs = []
    for a in soup.select("a[href]"):
        title = _text(a)
        if not title or len(title) < 8 or len(title) > 200:
            continue
        href = urljoin(url, a["href"])
        if not any(seg in href.lower() for seg in ["/job", "/career", "/vacan", "/opport", "/position"]):
            continue
        # Try to pull a location from the nearest ancestor
        loc = ""
        parent = a.find_parent(["article", "li", "div", "tr"])
        if parent:
            loc_el = parent.find(class_=re.compile(r"location|city|place", re.I))
            loc = _text(loc_el)
            if not loc:
                # Scan ancestor text for a Luxembourg mention to avoid false positives
                ptxt = _text(parent).lower()
                if "luxembourg" in ptxt or "luxemburg" in ptxt:
                    loc = "Luxembourg"
        jobs.append({
            "firm": firm, "title": title, "location": loc,
            "url": href, "external_id": None, "source_type": "HTML",
        })
    return jobs


# Dispatch registry
PARSERS: Dict[str, Callable[[BeautifulSoup, str, str], List[Dict[str, Any]]]] = {
    "elvinger_hoss": parse_elvinger_hoss,
    "bsp": parse_bsp,
    "kleyr_grasso": parse_kleyr_grasso,
    "luther": parse_luther,
    "molitor": parse_molitor,
    "brucher": parse_brucher,
    "cms": parse_cms,
    "nautadutilh": parse_nautadutilh,
    "stibbe": parse_stibbe,
    "loyens": parse_loyens,
    "ashurst": parse_ashurst,
    "dentons": parse_dentons,
    "clifford_chance": parse_clifford_chance,
    "gsk": parse_gsk,
    # Sites below known to require JS — rely on fallback or Playwright later
    "baker_mckenzie": parse_generic_fallback,
    "dla_piper": parse_generic_fallback,
    "akd": parse_generic_fallback,
    "charles_russell": parse_generic_fallback,
    "ao_shearman": parse_generic_fallback,
    "hsf_kramer": parse_generic_fallback,
    "simpson_thacher": parse_generic_fallback,
}


def fetch_html(source: Dict[str, Any]) -> List[Dict[str, Any]]:
    url = source["url"]
    firm = source["firm"]
    parser_key = source.get("parser", "generic")

    soup = _get(url)
    if soup is None:
        return []

    parser = PARSERS.get(parser_key, parse_generic_fallback)
    try:
        jobs = parser(soup, url, firm)
    except Exception as e:
        log.exception("[%s] parser %s crashed: %s", firm, parser_key, e)
        return []

    log.info("[%s] HTML parser %s → %d jobs", firm, parser_key, len(jobs))
    return jobs
