"""Orchestrates a full audit: crawl the site, run every check, score the
result and persist everything, so the web app and CLI can both call one
function."""
from urllib.parse import urlparse

from seoscope import db
from seoscope.checks.duplicates import find_duplicate_content
from seoscope.checks.onpage import analyze_page, onpage_issues
from seoscope.checks.technical import broken_links_issue, crawl_level_issues, robots_and_sitemap_issues
from seoscope.crawler import check_broken_links, crawl_site
from seoscope.robots import discover_sitemap_urls, fetch_robots
from seoscope.scoring import compute_score


def run_audit(root_url: str, max_pages: int, progress_cb=None) -> int:
    """Creates a new audit row and runs it to completion. Used by the CLI."""
    audit_id = db.create_audit(root_url, max_pages)
    execute_audit(audit_id, root_url, max_pages, progress_cb=progress_cb)
    return audit_id


def execute_audit(audit_id: int, root_url: str, max_pages: int, progress_cb=None) -> None:
    """Runs the crawl/check/score/save pipeline against an audit row that
    already exists. Split out from run_audit so a caller (e.g. the web app)
    can create the row up front, redirect to it, and run this part in the
    background."""
    if not root_url.startswith(("http://", "https://")):
        root_url = "https://" + root_url
    root_netloc = urlparse(root_url).netloc

    try:
        _report(progress_cb, "Fetching robots.txt and sitemap...")
        robots = fetch_robots(root_url)
        sitemap_urls, sitemap_error = discover_sitemap_urls(root_url, robots)

        all_issues = robots_and_sitemap_issues(root_url, robots, sitemap_urls, sitemap_error)

        _report(progress_cb, "Crawling pages...")

        def on_page(page, done, total):
            _report(progress_cb, f"Crawled {done}/{total}: {page.url}")

        pages = crawl_site(root_url, max_pages, robots, seed_urls=sitemap_urls, on_page=on_page)
        all_issues.extend(crawl_level_issues(pages))

        _report(progress_cb, "Checking for broken links...")
        link_status_cache: dict[str, int] = {}
        pages_with_broken: list[tuple[str, int]] = []
        page_records = []
        analyzed_pages = 0

        for page in pages:
            is_ok_status = page.status_code is not None and 200 <= page.status_code < 300
            if not page.html or not is_ok_status:
                # Error/blocked responses (4xx/5xx) often still return an HTML body
                # (e.g. a "403 Forbidden" page), but that body isn't the site's real
                # content — analyzing it as on-page/content would misreport the
                # error page's own title/text as the site's SEO issues.
                page_records.append({
                    "url": page.url, "status_code": page.status_code,
                    "redirect_chain": page.redirect_chain, "load_time_ms": page.load_time_ms,
                    "broken_links": 0,
                })
                continue

            analysis = analyze_page(page.url, page.html, root_netloc)
            analyzed_pages += 1
            broken_count, _ = check_broken_links(page.links, root_netloc, link_status_cache)
            if broken_count:
                pages_with_broken.append((page.url, broken_count))

            record = {
                "url": page.url, "status_code": page.status_code,
                "redirect_chain": page.redirect_chain, "load_time_ms": page.load_time_ms,
                "broken_links": broken_count,
                **{k: v for k, v in analysis.items() if k != "all_links" and k != "headings"
                   and k != "h1_text" and k != "heading_order_issue" and k != "robots_meta"
                   and k != "title_len" and k != "meta_description_len" and k != "thin_content"},
            }
            page_records.append(record)
            all_issues.extend(onpage_issues(page.url, analysis))

        all_issues.extend(broken_links_issue(pages_with_broken))
        all_issues.extend(find_duplicate_content(page_records))

        if analyzed_pages == 0 and pages:
            all_issues.append({
                "category": "technical", "severity": "critical",
                "title": "No pages could be analyzed",
                "description": f"All {len(pages)} crawled URL(s) returned an error or blocked "
                                "response, so no on-page or content checks could run. The "
                                "On-page and Content scores below have no data behind them.",
                "recommendation": "Resolve the access/error issues above, then re-run the audit "
                                   "once the crawler can actually reach the page content.",
                "page_url": None, "affected_count": len(pages),
            })

        overall_score, category_scores = compute_score(all_issues, analyzed_pages=analyzed_pages)

        _report(progress_cb, "Saving results...")
        for record in page_records:
            db.add_page(audit_id, record)
        for issue in all_issues:
            db.add_issue(audit_id, issue)

        db.finish_audit(audit_id, len(pages), overall_score, category_scores)
        _report(progress_cb, "Done")

    except Exception as exc:  # noqa: BLE001 - surfaced to the user via audit status
        db.fail_audit(audit_id, str(exc))
        raise


def _report(progress_cb, message: str):
    if progress_cb:
        progress_cb(message)
