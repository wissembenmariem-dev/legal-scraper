"""
Configuration — Legal Jobs Luxembourg scraper.
Lists of target sources grouped by adapter type.
"""

# Keywords for filtering job titles (case-insensitive).
KEYWORDS = [
    # French
    "avocat",
    "avocate",
    "juriste",
    "juristes",
    "secrétaire juridique",
    "assistant juridique",
    # English
    "lawyer",
    "associate",
    "associates",
    "counsel",
    "legal secretary",
    "legal assistant",
]

# Location tokens that indicate a Luxembourg-based role
LU_TOKENS = [
    "luxembourg", "luxemburg", "lux", "l-1", "l-2", "l-3", "l-4", "l-5", "l-8",
]

# Workday-family tenants: tenant_host, tenant_name, firm label, search URL (for humans)
WORKDAY_SOURCES = [
    {
        "firm": "Arendt",
        "host": "wd3.myworkdaysite.com",
        "tenant": "arendt",
        "site": "Jobopportunities",
        "search_url": "https://wd3.myworkdaysite.com/recruiting/arendt/Jobopportunities",
    },
    {
        "firm": "Linklaters",
        "host": "linklaters.wd3.myworkdayjobs.com",
        "tenant": "linklaters",
        "site": "Linklaters",
        "search_url": "https://linklaters.wd3.myworkdayjobs.com/fr-FR/Linklaters",
    },
    {
        "firm": "Simmons & Simmons",
        "host": "wd3.myworkdaysite.com",
        "tenant": "simmonssimmons",
        "site": "SimmonsSimmonsExternal",
        "search_url": "https://wd3.myworkdaysite.com/en-US/recruiting/simmonssimmons/SimmonsSimmonsExternal",
    },
    {
        "firm": "Hogan Lovells",
        "host": "hoganlovells.wd3.myworkdayjobs.com",
        "tenant": "hoganlovells",
        "site": "Search",
        "search_url": "https://hoganlovells.wd3.myworkdayjobs.com/en-US/Search",
    },
    {
        "firm": "Norton Rose Fulbright",
        "host": "nrf.wd3.myworkdayjobs.com",
        "tenant": "nrf",
        "site": "External",
        "search_url": "https://nrf.wd3.myworkdayjobs.com/fr-FR/External",
    },
    {
        "firm": "White & Case",
        "host": "wd1.myworkdaysite.com",
        "tenant": "whitecase",
        "site": "External",
        "search_url": "https://wd1.myworkdaysite.com/fr-FR/recruiting/whitecase/External",
    },
]

# Simple HTML sources: URL + parser key
HTML_SOURCES = [
    {"firm": "Elvinger Hoss", "url": "https://elvingerhoss.lu/join-us/opportunities?page=0", "parser": "elvinger_hoss"},
    {"firm": "Elvinger Hoss", "url": "https://elvingerhoss.lu/join-us/opportunities?page=1", "parser": "elvinger_hoss"},
    {"firm": "BSP", "url": "https://www.bsp.lu/lu/careers", "parser": "bsp"},
    {"firm": "Kleyr Grasso", "url": "https://www.kleyrgrasso.com/en/careers", "parser": "kleyr_grasso"},
    {"firm": "Luther", "url": "https://www.luther-lawfirm.lu/career/vacancies", "parser": "luther"},
    {"firm": "Molitor", "url": "https://molitorlegal.lu/careers/", "parser": "molitor"},
    {"firm": "Brucher", "url": "https://brucherlaw.lu/fr/nous-rejoindre/", "parser": "brucher"},
    {"firm": "CMS", "url": "https://cms.law/en/lux/cms-job-opportunities", "parser": "cms"},
    {"firm": "NautaDutilh", "url": "https://careers.nautadutilh.com/en/luxembourg/careers/lawyers/", "parser": "nautadutilh"},
    {"firm": "Stibbe", "url": "https://www.stibbe.com/careers/luxembourg/vacancies", "parser": "stibbe"},
    {"firm": "Loyens & Loeff", "url": "https://loyensloeffcareers.com/vacancies/?fwp_location=luxembourg", "parser": "loyens"},
    {"firm": "Ashurst", "url": "https://fsr.cvmailuk.com/ashurstcareers/main.cfm?page=jobBoard&fo=1&groupType_73=3899", "parser": "ashurst"},
    {"firm": "Dentons", "url": "https://careers.dentons.com/go/Opportunities-in-Luxembourg/8677702/", "parser": "dentons"},
    {"firm": "Clifford Chance", "url": "https://jobs.cliffordchance.com/jobs?options=203&page=1", "parser": "clifford_chance"},
    {"firm": "GSK Stockmann", "url": "https://career.gsk.de/stellenangebote/?berufsgruppe=17", "parser": "gsk"},
    {"firm": "Baker McKenzie", "url": "https://www.bakermckenzie.com/en/careers/job-opportunities?locations=2b5ec220-0463-4279-b743-e2712d02bcd9", "parser": "baker_mckenzie"},
    {"firm": "DLA Piper", "url": "https://careers.dlapiper.com/jobs/?country=Luxembourg&sort=by-default", "parser": "dla_piper"},
    {"firm": "AKD", "url": "https://careers.akd.eu/starter-positions", "parser": "akd"},
    {"firm": "Charles Russell Speechlys", "url": "https://www.charlesrussellspeechlys.com/en/careers/current-roles/?Location=L-2180+Luxembourg", "parser": "charles_russell"},
    # Dechert: scraped via fetchers/dechert.py (proprietary JSON API) — not HTML
    {"firm": "A&O Shearman", "url": "https://careers.aoshearman.com/en/search-jobs?acm=ALL", "parser": "ao_shearman"},
    {"firm": "HSF Kramer", "url": "https://careers.hsfkramer.com/global/en/luxembourg/search-results", "parser": "hsf_kramer"},
    {"firm": "Simpson Thacher", "url": "https://stblaw.allhires.com/app", "parser": "simpson_thacher"},
]

# Dechert — proprietary JSON API (backed by Workday dechert.wd12.myworkdayjobs.com)
DECHERT_SOURCES = [
    {
        "firm": "Dechert",
        "url": "https://www.dechert.com/careers.html",
    },
]

# Oracle HCM — tenant ehpy.fa.em5.oraclecloud.com belongs to Pinsent Masons (confirmed via API)
ORACLE_SOURCES = [
    {
        "firm": "Pinsent Masons",
        "base": "https://ehpy.fa.em5.oraclecloud.com",
        "site": "CX_1001",
        "search_url": "https://ehpy.fa.em5.oraclecloud.com/hcmUI/CandidateExperience/en/sites/CX_1001/jobs?location=Luxembourg",
    },
]

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

REQUEST_TIMEOUT = 25
