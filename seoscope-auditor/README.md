# SEOScope

A local, self-hosted SEO audit tool. Give it a URL, it crawls the site, runs
technical and on-page SEO checks, scores the result, and generates a
prioritized issue list plus a step-by-step optimization roadmap — viewable
in a web dashboard or downloadable as an HTML/PDF report.

## Features

- **Crawler**: breadth-first, same-domain crawl seeded from `robots.txt` /
  `sitemap.xml` (including sitemap indexes), with a configurable page limit.
- **Technical SEO checks**: robots.txt presence, sitemap presence, HTTPS,
  broken pages (4xx/5xx), redirect chains, page response-time thresholds,
  broken outgoing links.
- **On-page SEO checks**: title tag presence/length, meta description
  presence/length, H1 presence/duplication, heading order, image alt text,
  canonical tags, `noindex` detection, internal/external link counts, thin
  content, duplicate titles, duplicate body content (via content hashing).
- **Scoring**: a 0–100 overall score blended from weighted Technical /
  On-page / Content category scores, each reduced by severity-weighted
  issue penalties.
- **Prioritized issues** with `critical` / `warning` / `info` severity and
  affected-page counts.
- **Optimization roadmap**: an ordered, step-by-step action plan grouped by
  severity.
- **Dashboard**: score gauge, category breakdown, issue table, roadmap, and
  a per-page crawl table. Audit history is kept in SQLite so past runs stay
  browsable.
- **Downloadable report**: a standalone HTML report, or a PDF (rendered
  with `xhtml2pdf`, a pure-Python PDF writer — no system/GTK dependencies).
- **CLI**: run an audit from the terminal without the dashboard.

## Architecture

```
seoscope/
  crawler.py        same-domain BFS crawler, link extraction, broken-link probing
  robots.py         robots.txt + sitemap.xml/sitemap index discovery
  checks/
    technical.py    site-wide technical issues (robots/sitemap/HTTPS/speed/redirects)
    onpage.py        per-page on-page analysis + issues
    duplicates.py    duplicate title / duplicate content detection
  scoring.py        issue list -> category scores -> overall score
  roadmap.py        issue list -> ordered optimization steps
  auditor.py        orchestrates crawl -> checks -> scoring -> persistence
  db.py             SQLite persistence (audits, pages, issues)
  pdf.py            HTML report -> PDF
  app.py            FastAPI dashboard (routes, background audit runner)
  cli.py            terminal entry point
templates/          Jinja2 templates for the dashboard + the standalone report
static/style.css    dashboard styling
```

An audit runs synchronously end-to-end inside a background thread kicked
off by the dashboard's `POST /audits`, so the browser can redirect to a
live-updating progress page immediately instead of blocking on the whole
crawl.

## Setup

Requires Python 3.11+.

```bash
python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS / Linux
source .venv/bin/activate

pip install -r requirements.txt
```

## Running the dashboard

```bash
uvicorn seoscope.app:app --reload
```

Open http://127.0.0.1:8000, enter a URL, choose how many pages to crawl,
and run the audit. You'll land on a live progress page that refreshes
automatically until the crawl finishes, then shows the full dashboard with
the score, prioritized issues, optimization roadmap, and crawled-page
table. From there you can open the full HTML report or download it as PDF.

## Running from the command line

```bash
python -m seoscope.cli example.com --max-pages 25
```

Prints a summary (score, issue counts) and the audit id; start the
dashboard afterwards to see the full report for that id.

## Configuration

Tunables (thresholds, scoring weights, crawl limits) live in one place:
[seoscope/config.py](seoscope/config.py).

## Data

All audits are stored in a local SQLite database at `data/seoscope.db`
(created automatically). Delete that file to reset history.

## Notes / limitations

This is intentionally a *simple* local tool: the crawler is sequential
(polite, easy to reason about, not built for large-scale crawling),
JavaScript-rendered content isn't executed (pages are fetched as static
HTML), and "page speed" means raw HTTP response time rather than a full
Core Web Vitals audit. For a quick, functional, self-hosted SEO audit of a
small-to-medium site, that trade-off keeps the tool easy to run and read.
