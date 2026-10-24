"""Central tunables for crawling and scoring. Kept in one place so the
behavior of an audit can be reasoned about without hunting through modules."""

USER_AGENT = "SEOScopeBot/1.0 (+local SEO audit tool)"
REQUEST_TIMEOUT_SECONDS = 10
DEFAULT_MAX_PAGES = 40
MAX_MAX_PAGES = 200

# Response time thresholds (milliseconds) used by the technical speed check.
SLOW_PAGE_WARNING_MS = 1000
SLOW_PAGE_CRITICAL_MS = 3000

# On-page content thresholds.
TITLE_MIN_LEN = 30
TITLE_MAX_LEN = 60
META_DESC_MIN_LEN = 50
META_DESC_MAX_LEN = 160
THIN_CONTENT_WORD_COUNT = 200

# Category weights must sum to 100; used by scoring.compute_score.
CATEGORY_WEIGHTS = {
    "technical": 40,
    "onpage": 40,
    "content": 20,
}

# Score deducted per issue occurrence, before category weighting/capping.
SEVERITY_PENALTY = {
    "critical": 12,
    "warning": 5,
    "info": 1,
}

DB_PATH = "data/seoscope.db"
