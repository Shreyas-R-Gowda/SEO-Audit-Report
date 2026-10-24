"""Site-wide technical SEO checks: robots.txt, sitemap, HTTPS, redirects,
broken links and page speed. These look at the crawl as a whole rather than
any single page."""
from urllib.parse import urlparse

from seoscope.config import SLOW_PAGE_CRITICAL_MS, SLOW_PAGE_WARNING_MS
from seoscope.crawler import CrawledPage
from seoscope.robots import RobotsInfo


def _issue(category, severity, title, description, recommendation, page_url=None, affected_count=1):
    return {
        "category": category, "severity": severity, "title": title,
        "description": description, "recommendation": recommendation,
        "page_url": page_url, "affected_count": affected_count,
    }


def _is_blocked(error_text: str | None) -> bool:
    """True if a fetch failed because the request was denied (401/403)
    rather than because the resource genuinely doesn't exist (404, etc.)."""
    if not error_text:
        return False
    return "HTTP 401" in error_text or "HTTP 403" in error_text


def robots_and_sitemap_issues(root_url: str, robots: RobotsInfo, sitemap_urls: list[str],
                               sitemap_error: str | None) -> list[dict]:
    issues = []

    if not robots.found:
        if _is_blocked(robots.fetch_error):
            issues.append(_issue("technical", "warning", "robots.txt request was blocked",
                                  f"The request for robots.txt was denied ({robots.fetch_error}), "
                                  "rather than returning a normal 404. This looks like bot/firewall "
                                  "protection, which may also be blocking search engine crawlers.",
                                  "Check your firewall, WAF or bot-protection rules and make sure "
                                  "they allow legitimate search engine and SEO crawlers."))
        else:
            issues.append(_issue("technical", "warning", "robots.txt not found",
                                  f"No robots.txt could be retrieved ({robots.fetch_error}).",
                                  "Add a robots.txt file at the site root to guide crawlers "
                                  "and declare your sitemap location."))

    if not sitemap_urls:
        if _is_blocked(sitemap_error):
            issues.append(_issue("technical", "warning", "Sitemap request was blocked",
                                  f"{sitemap_error} This looks like bot/firewall protection "
                                  "denying the request, rather than the sitemap being missing.",
                                  "Check your firewall, WAF or bot-protection rules and make sure "
                                  "they allow legitimate search engine and SEO crawlers."))
        else:
            issues.append(_issue("technical", "warning", "XML sitemap not found or empty",
                                  sitemap_error or "No sitemap.xml could be found via robots.txt "
                                                    "or the default location.",
                                  "Publish an XML sitemap listing your important URLs and "
                                  "reference it from robots.txt."))

    if root_url.startswith("http://"):
        issues.append(_issue("technical", "critical", "Site not served over HTTPS",
                              "The audited URL uses plain HTTP.",
                              "Serve the site over HTTPS and redirect all HTTP traffic to HTTPS."))

    return issues


def crawl_level_issues(pages: list[CrawledPage]) -> list[dict]:
    issues = []

    blocked = [p for p in pages if p.status_code in (401, 403)]
    blocked_ids = {id(p) for p in blocked}
    other_broken = [p for p in pages if id(p) not in blocked_ids
                     and (p.status_code is None or p.status_code >= 400)]

    if blocked:
        issues.append(_issue("technical", "critical", "Pages blocking the crawler (401/403)",
                              f"{len(blocked)} crawled URL(s) returned 401/403 and denied access "
                              "instead of serving the page. This usually means bot/firewall "
                              "protection, not a missing page — but it can block search engine "
                              "crawlers just as easily, so it's treated as critical.",
                              "Check your firewall, WAF, or bot-protection rules (e.g. Cloudflare, "
                              "rate limiting, User-Agent blocking) and confirm legitimate search "
                              "engine crawlers are allowed through.", affected_count=len(blocked)))
    if other_broken:
        issues.append(_issue("technical", "critical", "Pages returning errors",
                              f"{len(other_broken)} crawled URL(s) returned an error or 4xx/5xx status.",
                              "Fix or remove broken pages, and update any internal links "
                              "that point to them.", affected_count=len(other_broken)))

    redirecting = [p for p in pages if p.redirect_chain]
    long_chains = [p for p in redirecting if len(p.redirect_chain) > 1]
    if redirecting:
        issues.append(_issue("technical", "info", "Pages reached via redirects",
                              f"{len(redirecting)} URL(s) were only reachable after a redirect.",
                              "Point internal links directly at the final URL to avoid "
                              "unnecessary redirect hops.", affected_count=len(redirecting)))
    if long_chains:
        issues.append(_issue("technical", "warning", "Redirect chains longer than one hop",
                              f"{len(long_chains)} URL(s) go through more than one redirect "
                              "before reaching their final destination.",
                              "Update links/configuration so each URL redirects directly "
                              "to its final destination in a single hop.",
                              affected_count=len(long_chains)))

    slow = [p for p in pages if p.load_time_ms and p.load_time_ms > SLOW_PAGE_WARNING_MS]
    very_slow = [p for p in slow if p.load_time_ms > SLOW_PAGE_CRITICAL_MS]
    if very_slow:
        issues.append(_issue("technical", "critical", "Very slow page responses",
                              f"{len(very_slow)} page(s) took over {SLOW_PAGE_CRITICAL_MS}ms to respond.",
                              "Investigate server/backend performance, enable caching, and "
                              "optimize database queries or third-party scripts.",
                              affected_count=len(very_slow)))
    elif slow:
        issues.append(_issue("technical", "warning", "Slow page responses",
                              f"{len(slow)} page(s) took over {SLOW_PAGE_WARNING_MS}ms to respond.",
                              "Profile server response time and consider caching or a CDN.",
                              affected_count=len(slow)))

    return issues


def broken_links_issue(pages_with_broken: list[tuple[str, int]]) -> list[dict]:
    if not pages_with_broken:
        return []
    total_broken = sum(count for _, count in pages_with_broken)
    return [_issue("technical", "critical", "Broken outgoing links",
                    f"{total_broken} broken link(s) found across {len(pages_with_broken)} page(s).",
                    "Update or remove links pointing to pages that no longer exist, "
                    "returning 4xx/5xx responses.", affected_count=total_broken)]
