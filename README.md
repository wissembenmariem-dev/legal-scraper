# Legal Jobs Luxembourg — Daily Scraper

Automatically scrapes ~30 Luxembourg law firm career sites every morning at 08:30,
filters for lawyer / associate / legal secretary / legal assistant roles based in
Luxembourg, upserts into a Notion database, and sends a visual HTML digest to your
inbox via Resend.

## Architecture

```
┌──────────────┐  cron 06:30/07:30 UTC  ┌──────────────────┐
│ GitHub       │ ─────────────────────▶ │ Ubuntu runner    │
│ Actions      │                        │ python main.py   │
└──────────────┘                        └───────┬──────────┘
                                                │
                     ┌──────────────────────────┼──────────────────────┐
                     ▼                          ▼                      ▼
             ┌──────────────┐          ┌──────────────┐        ┌──────────────┐
             │ Workday API  │          │ Oracle HCM   │        │ HTML parsers │
             │ (6 firms)    │          │ (Dechert)    │        │ (22+ firms)  │
             └──────┬───────┘          └──────┬───────┘        └──────┬───────┘
                    │                         │                       │
                    └─────────────┬───────────┴───────────────────────┘
                                  ▼
                     normalize_and_filter() ── LU + keywords
                                  │
                                  ▼
                         Notion HTTP API  (upsert by External ID)
                                  │
                                  ▼
                           Resend HTTP API  (morning digest)
```

**State is stored exclusively in Notion** (no local state file). At each run we
load all existing pages, index by External ID, and decide per scraped job:

- Unknown External ID → **create** page with `Status=New`
- Known External ID → **update** `Last Seen` + `Status=Active`
- Present in Notion but not scraped for >2 days → **close** (`Status=Closed`)

## Local setup (test before deploying)

```bash
git clone <repo-url> legal-scraper
cd legal-scraper
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env    # then fill in your secrets
python main.py
```

Inspect the logs. Every source reports `✓ firm: N raw jobs` or `✗ firm: error`.
You should get an email within seconds.

## Required secrets / .env variables

| Key | Where to get it |
|-----|-----------------|
| `NOTION_TOKEN` | notion.so/profile/integrations → New integration → copy secret. **Also connect the integration to the "Scraping - Legal LUX" page.** |
| `NOTION_DATABASE_ID` | Already provisioned: `29106a3d-0860-4c68-8f7e-3bdeef76a452` |
| `RESEND_API_KEY` | resend.com/api-keys |
| `EMAIL_FROM` | Must be from a verified domain on Resend (e.g. `legal-watch@yourkingsley.com`) |
| `EMAIL_TO` | Destination inbox |

## GitHub Actions deployment

1. Push this repo to GitHub (private recommended).
2. Settings → Secrets and variables → Actions → New repository secret, add **each of the 5 variables above** as secrets.
3. Actions → enable workflows → "Daily Legal Jobs Scrape" → click **Run workflow** once manually to smoke-test.
4. Check your inbox.

The workflow runs twice daily (06:30 and 07:30 UTC) to cover both CET and CEST.
Upserts are idempotent so the second run is a no-op if the first succeeded.

## Sources covered

| Family | Count | Firms |
|--------|------:|-------|
| Workday API | 6 | Arendt, Linklaters, Simmons & Simmons, Hogan Lovells, Norton Rose Fulbright, White & Case |
| Oracle HCM | 1 | Dechert |
| HTML static | 14 | Elvinger Hoss, BSP, Kleyr Grasso, Luther, Molitor, Brucher, CMS, NautaDutilh, Stibbe, Loyens, Ashurst, Dentons, Clifford Chance, GSK Stockmann |
| HTML fallback (may need Playwright) | 8 | Baker McKenzie, DLA Piper, AKD, Charles Russell Speechlys, A&O Shearman, HSF Kramer, Simpson Thacher, (Dechert web) |

**Sites flagged "may need Playwright"** use a generic anchor-based fallback
parser. If they return 0 jobs during your first local run, tell me and I'll
write a dedicated Playwright adapter for them.

## Filtering logic

A scraped job is kept if and only if **both** conditions hold:

1. **Luxembourg**: location field contains `luxembourg`, `luxemburg`, or a Luxembourg postal prefix (`L-1…L-8`). LU-only firms (Arendt, Elvinger Hoss, BSP, Kleyr Grasso, Luther, Molitor, Brucher) bypass this check when their location field is empty.
2. **Keyword match** in the title: `avocat`, `lawyer`, `associate`, `counsel`, `legal secretary`, `legal assistant`, `secrétaire juridique`, `assistant juridique`, `assistant légal`, `paralegal`, `trainee`, `stagiaire`, etc.

See `config.py::KEYWORDS` and `normalizer.py::is_luxembourg()` for the full lists.

## Iterating on parsers

The first run will reveal which HTML parsers need tuning. To debug a single source:

```python
from config import HTML_SOURCES
from fetchers.html_generic import fetch_html
src = next(s for s in HTML_SOURCES if s["firm"] == "Elvinger Hoss")
print(fetch_html(src))
```

Then update the corresponding `parse_*` function in `fetchers/html_generic.py`.

## Known limitations

- **No Playwright yet.** Sites that render their job listing purely via JavaScript will return 0 jobs from the fallback parser. These need a dedicated Playwright adapter (add a `playwright_sites.py` module). I'll write one on request once the HTTP-level parsers are stable.
- **Cloudflare challenges.** Some firms (historically DLA Piper, Baker McKenzie) block headless user agents. Solutions: rotate user agents, add `curl_cffi`, or use a residential proxy. Ask if you hit this.
- **Rate limits.** Current code is sequential with no delay. At 30 sites this is fine; if you add more, introduce `time.sleep(1)` between requests.
- **Notion API rate limit.** 3 requests/sec. The client handles 429 with automatic backoff. For a first run with ~500 jobs, this will take ~3 minutes.
- **External ID stability.** Workday and Oracle emit stable IDs. HTML parsers hash firm + URL; if a site changes its URL format, the same job may be re-created as "new" once. Acceptable tradeoff.

## License

Private use only. Do not redistribute the scraped data without checking each firm's ToS.
