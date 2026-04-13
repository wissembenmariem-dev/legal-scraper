# AGENTS.md — Handoff to Cursor

> **Read this file in full before touching anything.**
> This project was partially built in a sandboxed environment and is being
> handed off to a Cursor-based local workflow. The document below is the
> authoritative spec for agents (human or LLM) continuing the work.

---

## 1. Mission

Build and operate a **daily job scraper for Luxembourg legal roles**
("Legal jobs Daily Scrape — Luxembourg"). The scraper must:

1. Run automatically **every day at 08:30 Europe/Brussels local time**,
   summer and winter, via **GitHub Actions**.
2. Scrape ~30 law firm career sites (Workday CXS API, Oracle HCM REST, and
   ~22 site-specific HTML parsers).
3. Filter jobs to Luxembourg-based roles matching the keywords:
   **AVOCAT, LAWYER, LEGAL SECRETARY, LEGAL ASSISTANT, ASSOCIATE,
   SECRÉTAIRE JURIDIQUE, ASSISTANT LÉGAL**.
4. Persist results in a **Notion database** (source of truth, dedup, history).
5. Send a **visual HTML email digest** each morning to the user.

### Principal and stakeholders
- **Primary user / operator:** Wissem Ben Mariem — `wissem.benmariem@gmail.com`
- **Final recipient of the digest:** `ch@yourkingsley.com` (reached via a
  Gmail forwarding filter from `wissem.benmariem@gmail.com`, see §5).
- **User preference (critical):** Wissem has asked for expert-tone answers
  that challenge assumptions and are supported by concrete, verifiable
  evidence. Do not produce superficial work. When in doubt, push back with
  facts rather than rubber-stamping.

---

## 2. Current architecture (as of handoff)

```
                 ┌─────────────────────────────────────────┐
                 │        GitHub Actions runner            │
                 │        (Ubuntu, Python 3.11)            │
                 │                                         │
                 │   ┌────────────┐   ┌──────────────┐     │
                 │   │  main.py   │──▶│  fetchers/   │     │
                 │   │            │   │  - workday   │     │
                 │   │            │   │  - oracle_hcm│     │
                 │   │            │   │  - html_gen. │     │
                 │   └─────┬──────┘   └──────┬───────┘     │
                 │         │                 │             │
                 │         ▼                 ▼             │
                 │   ┌────────────┐   ┌──────────────┐     │
                 │   │normalizer  │   │   config     │     │
                 │   │(LU + keyw) │   │(URL sources) │     │
                 │   └─────┬──────┘   └──────────────┘     │
                 │         ▼                                │
                 │   ┌────────────┐   ┌──────────────┐     │
                 │   │ notion_    │   │email_report  │     │
                 │   │ client     │   │(Resend HTTP) │     │
                 │   └─────┬──────┘   └──────┬───────┘     │
                 └─────────┼─────────────────┼─────────────┘
                           │ HTTPS           │ HTTPS
                           ▼                 ▼
                      ┌─────────┐       ┌─────────┐
                      │ Notion  │       │ Resend  │
                      │  API    │       │   API   │
                      └─────────┘       └─────────┘
                                              │
                                              ▼
                                    wissem.benmariem@gmail.com
                                              │ Gmail filter (FROM: onboarding@resend.dev)
                                              ▼
                                        ch@yourkingsley.com
```

### Module responsibilities

| File | Role |
|---|---|
| `main.py` | Orchestrator. Loads Notion state, runs fetchers with per-source error isolation, normalizes, upserts, closes stale pages, sends digest. Includes an 8:30 Brussels time guard for GitHub Actions. |
| `config.py` | Static config: keyword list, LU tokens, source lists (`WORKDAY_SOURCES`, `ORACLE_SOURCES`, `HTML_SOURCES`), HTTP constants. |
| `normalizer.py` | Accent-stripping `_norm()`, `matches_keywords()` with word-boundary regex, `is_luxembourg()`, `classify_seniority`, `classify_category`, `dedup_by_external_id`. **Subtlety:** the partner keyword has an explicit exclusion for `business|hr|people|delivery|channel|industry partner` to avoid false positives. |
| `fetchers/workday.py` | Calls the Workday CXS JSON API (`/wday/cxs/<tenant>/<site>/jobs`). Includes `_parse_workday_posted()` that converts strings like "Posted Yesterday", "Posted 7 Days Ago", "Posted Today" into ISO dates. |
| `fetchers/oracle_hcm.py` | Calls Oracle HCM Cloud REST (`/hcmRestApi/resources/latest/recruitingCEJobRequisitions`). Used for Dechert. |
| `fetchers/html_generic.py` | 14 site-specific BeautifulSoup parsers + a defensive fallback. **Subtlety:** the fallback no longer defaults location to "Luxembourg" — it scans ancestor HTML for a real location. |
| `notion_client.py` | Notion HTTP API client. `load_existing()` builds an index by External ID; `upsert_job()` creates or updates (and refreshes mutable fields on update); `close_stale()` marks pages as Closed after a 2-day grace window. |
| `email_report.py` | Renders an inlined-CSS HTML digest and POSTs to Resend. |
| `.github/workflows/daily.yml` | Dual cron (06:30 UTC and 07:30 UTC) — main.py's time guard picks the right one. |
| `debug_parser.py` | Dumps the raw HTML of every `HTML_SOURCES` entry to `data/<slug>.html` for parser development. |

---

## 3. Environment variables (.env)

```bash
# Resend (HTTP email API)
RESEND_API_KEY=re_h9NJgmXk_8uAwdM3wbcX9opCime2SHqx2
EMAIL_FROM=onboarding@resend.dev          # temporary — see §5
EMAIL_TO=wissem.benmariem@gmail.com       # temporary — see §5

# Notion
NOTION_TOKEN=ntn_Q6312189028a1DuTszSBJzgpA4Qguc5ZO5yKQOzrlRLfC6
NOTION_DATABASE_ID=29106a3d-0860-4c68-8f7e-3bdeef76a452

# Local
TZ=Europe/Luxembourg
```

**Security:** `.env` is gitignored. Never commit. On GitHub Actions these
are provided as repository secrets (see §6).

**Notion token provenance:** internal integration created at
`https://www.notion.com/profile/integrations`. Must be **connected** to the
parent page "Scraping - Legal LUX"
(`https://www.notion.so/Scraping-Legal-LUX-33d1783c5c6480cfab9ee776966a10b4`)
via the `•••` → `Connections` menu — otherwise the API returns 404 on
page creation.

---

## 4. Notion database schema

- **Database ID:** `29106a3d08604c688f7e3bdeef76a452`
- **Data source ID:** `320528ee-9896-4759-afc6-8ef56db85b9f`
- **Parent page:** "Scraping - Legal LUX"

| Property | Type | Purpose |
|---|---|---|
| Title | title | Job title |
| Firm | select | Law firm name |
| Location | rich_text | Raw location string from the source |
| URL | url | Canonical job URL |
| Status | select | `New` · `Active` · `Closed` |
| Category | select | `Lawyer` · `Legal Secretary` · `Legal Assistant` · `Other` |
| Seniority | select | `Intern` · `Junior` · `Mid` · `Senior` · `Counsel` · `Partner` · `Unknown` |
| Posted Date | date | From source (best effort) |
| First Seen | date | Set on creation |
| Last Seen | date | Refreshed on every run where the job still appears |
| Source Type | select | `Workday` · `Oracle HCM` · `HTML` |
| External ID | rich_text | SHA-1 of `firm + url` — stable dedup key |

**Dedup / state model:** Notion is the single source of truth — there is no
local `state.json`. On every run: load all pages → index by External ID →
for each scraped job, either create or refresh Last Seen (+ mutable
fields) → any existing page not seen this run and older than 2 days is
marked Closed.

---

## 5. Email delivery — current state and evolution path

### Current (Option 3, temporary)
- `EMAIL_FROM=onboarding@resend.dev` (Resend's shared onboarding sender;
  usable without domain verification, but **only** to the email tied to
  the Resend account).
- `EMAIL_TO=wissem.benmariem@gmail.com` (the Resend account owner).
- A Gmail filter on `wissem.benmariem@gmail.com` forwards mails where
  `From: onboarding@resend.dev` to `ch@yourkingsley.com`.

**Why this is a stop-gap and not the final state:**
- `onboarding@resend.dev` has a mutualized reputation. After a few days of
  daily sending, Gmail will likely route the digest to the Promotions tab
  or spam.
- The forwarding chain adds a point of failure: if Gmail breaks the filter
  for phishing reasons, the digest is silently lost.

### Target (Option 1 or Option 2)
Two paths to a proper setup — either is acceptable, pick based on what's
politically feasible at Kingsley and partners:

**Option 1 — Gmail SMTP with App Password.** Send the digest from
`wissem.benmariem@gmail.com` directly to `ch@yourkingsley.com` via Gmail's
`smtp.gmail.com:587` using a 16-char App Password. Zero cost, no DNS work,
but the email appears in Wissem's Sent folder.

**Option 2 — Proper domain DKIM/SPF on yourkingsley.com.** The domain is
registered at **Gandi SAS**, owned by `Kingsley and partners sprl`,
managed by a third party (suspected: **Foxconcept**, a local LU web
agency). Wissem is an employee, not an admin, and has been unable to get
the DNS records added. To unblock: either get `Technical` role on the
Gandi organization, or ask Foxconcept to add these three records on
`send.yourkingsley.com`:
- `MX  send.yourkingsley.com. → 10 feedback-smtp.eu-west-1.amazonses.com.`
- `TXT send.yourkingsley.com. → "v=spf1 include:amazonses.com ~all"`
- `TXT resend._domainkey.yourkingsley.com. → "p=<DKIM from Resend>"`
Plus optional DMARC: `TXT _dmarc.yourkingsley.com. → "v=DMARC1; p=none; rua=mailto:ch@yourkingsley.com"`.

When Option 1 or Option 2 is reachable, swap the backend in `email_report.py`
and update the two `.env` keys — no other code changes needed.

---

## 6. GitHub Actions deployment

### Scheduling — the 08:30 Brussels problem
Brussels alternates between **CET (UTC+1)** in winter and **CEST (UTC+2)**
in summer. GitHub Actions cron only supports UTC. Therefore the workflow
has **two cron triggers**:
- `30 6 * * *` → 08:30 CEST (summer)
- `30 7 * * *` → 08:30 CET (winter)

Both fire every day. `main.py._should_run_now()` reads the current
`Europe/Brussels` local time and exits 0 silently unless it's within the
**08:15–08:45 window**. Net effect: the pipeline runs exactly once per day
at 08:30 Brussels, year-round.

### Secrets to configure on GitHub
`Settings → Secrets and variables → Actions → New repository secret`:
- `RESEND_API_KEY`
- `EMAIL_FROM`
- `EMAIL_TO`
- `NOTION_TOKEN`
- `NOTION_DATABASE_ID`

(`TZ` is set as a plain env in the workflow, not a secret.)

### Repo setup steps
```bash
# From the project root
git init
git add .
git commit -m "Initial commit — legal jobs LUX scraper"
git branch -M main
git remote add origin git@github.com:<user>/legal-jobs-lux.git
git push -u origin main

# Then on GitHub:
#  - Add all 5 secrets above
#  - Enable Actions (if disabled by default)
#  - Trigger a manual run via Actions → Daily Legal Jobs Scrape → Run workflow
#    to verify end-to-end before waiting for tomorrow 08:30
```

---

## 7. Known bugs & open work (what Cursor must finish)

### Already fixed (verified in code, await a fresh run to confirm)
1. **Workday date parsing** — `_parse_workday_posted()` is now wired into the job dict construction in `fetchers/workday.py`. "Posted Yesterday" etc. no longer reach Notion as raw strings.
2. **BSP title extraction** — `parse_bsp()` in `fetchers/html_generic.py` now only trusts heading elements (`h1–h4`) for the title and caps at 180 characters. No more article descriptions as titles.
3. **Generic fallback location** — `parse_generic_fallback()` no longer defaults `location="Luxembourg"`. It scans ancestor HTML for a real location. Kills the DLA Piper false positives (London / Italy / Prague previously tagged as LU).
4. **Notion upsert refresh** — `upsert_job()` now refreshes `Title / Location / URL / Source Type / Category / Seniority / Posted Date` on update, not just `Last Seen` and `Status`. Dirty pages from earlier runs auto-clean on the next scrape.
5. **Email config** — `.env` switched to Option 3 (`onboarding@resend.dev` → `wissem.benmariem@gmail.com`).
6. **Time guard** — `_should_run_now()` added to `main.py`.

### Still to do — in priority order

#### P0 — Re-run and verify
```bash
python main.py
```
Expected differences vs. the previous run (678 raw → 30 filtered → 23 created, 7 Workday date errors):
- Zero `Posted Yesterday`-style errors.
- BSP titles should look like real job titles, not paragraph fragments.
- DLA Piper false positives should drop from ~131 to near zero.
- Already-created junk pages should auto-refresh into clean ones.
- Email send should return HTTP 200 (because `EMAIL_FROM` is now `onboarding@resend.dev`).

#### P1 — Dump HTML of the 10 sites that return 0 jobs
```bash
python debug_parser.py
```
Produces `data/*.html` for every HTML source. The 10 currently broken
parsers (return 0 jobs) that need real HTML samples to fix:
1. Kleyr Grasso
2. Luther
3. Molitor
4. Brucher
5. CMS
6. NautaDutilh
7. Loyens
8. Clifford Chance (possibly JS-rendered — may need Playwright)
9. GSK Stockmann
10. HSF Kramer
11. Simpson Thacher

For each, inspect the dumped HTML in a browser or editor, write a
dedicated `parse_<firm>()` function in `fetchers/html_generic.py`
following the contract (take `soup, url, firm`, return a list of job
dicts with `firm / title / location / url / external_id / source_type`),
and wire it into the `PARSERS` dispatch dict.

#### P2 — JS-rendered sites
Clifford Chance logs `No jobs parsed — site may be JS-rendered`. Options:
- Add Playwright as a dependency and run it headlessly.
- Or find the underlying XHR the site uses and call it directly (always
  preferable — faster, more reliable, no browser in CI).

#### P3 — Email upgrade
Move from Option 3 to Option 1 (Gmail SMTP) or Option 2 (yourkingsley.com
DKIM). See §5.

#### P4 — Deploy to GitHub Actions
Create the repo, push, add secrets, enable the workflow, trigger a manual
dry-run to verify. See §6.

---

## 8. Local development workflow

```bash
# Clone or open in Cursor
cd legal-scraper

# Python 3.11+ required (3.14 also works)
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Local test — time guard is bypassed unless GITHUB_ACTIONS is set
python main.py

# Dump HTML for parser development
python debug_parser.py
python debug_parser.py bsp dla    # filter by firm substring
```

### Testing the normalizer in isolation
`normalizer.py` has no external dependencies. You can drop a
`pytest`-compatible test file next to it and assert on:
- `matches_keywords("Avocat en droit des sociétés")` → True
- `matches_keywords("HR Business Partner")` → False
- `classify_seniority("Senior Associate")` → `"Senior"`
- `classify_category("Legal Secretary")` → `"Legal Secretary"`
- `is_luxembourg(job_with_lu_token)` → True

### Gotchas
- **Python 3.14 + lxml:** on some Macs, `pip install lxml` fails on 3.14
  without pre-built wheels. If so, either fall back to 3.11, or use
  `pip install --only-binary=:all: lxml`.
- **Notion rate limit:** 3 req/s, handled with exponential backoff in
  `notion_client._request()`. Don't parallelize upserts.
- **Luxembourg-only firms with empty location:** the LU filter whitelists
  firms via `LU_ONLY_FIRMS` (see `normalizer.py`). If you add a new LU-only
  firm and forget the whitelist, all its jobs get dropped because the
  source doesn't emit a location string.
- **Workday CXS pagination:** `fetch_workday()` paginates by `offset`
  until the returned count is < `limit`. Tenants with thousands of jobs
  take ~10 seconds each.

---

## 9. Prompts history and user preferences (context for agents)

- Wissem requested an **expert tone** with **rigorous challenge of
  assumptions**. Avoid generic agreement. Ground every recommendation in
  verifiable facts (docs URLs, `dig` outputs, actual log content).
- Wissem prefers **French** for conversation.
- When deliverables are files, **always save to the working directory
  and provide a path**, rather than pasting long code blocks in chat.
- The original sandbox was network-restricted (egress allowlist), which
  is why the project was pivoted from in-sandbox execution to GitHub
  Actions deployment. Cursor running locally does not have this
  restriction and can run `main.py` directly against live sites.

---

## 10. Quick sanity check on first open

When an agent (or Wissem) opens this folder in Cursor for the first time,
run this checklist:

```bash
# 1. Virtualenv + deps
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# 2. Verify .env is present and well-formed
test -f .env && grep -E '^(RESEND_API_KEY|EMAIL_FROM|EMAIL_TO|NOTION_TOKEN|NOTION_DATABASE_ID)=' .env

# 3. Verify Notion connectivity (should print existing page count)
python -c "from notion_client import NotionClient; print(len(NotionClient().load_existing()))"

# 4. Smoke run — time guard is bypassed locally
python main.py

# 5. Dump debug HTML for broken parsers
python debug_parser.py
```

If step 3 fails with 401, the Notion token is wrong.
If step 3 fails with 404, the integration isn't connected to the parent page.
If step 4 succeeds but email returns 403, `EMAIL_FROM` isn't `onboarding@resend.dev`.
If step 4 succeeds and email returns 200 but nothing arrives at `ch@yourkingsley.com`, the Gmail forward filter isn't set up.

---

*Last updated at handoff. Keep this file current as you make changes — it
is the only source of truth for agents continuing the project.*
