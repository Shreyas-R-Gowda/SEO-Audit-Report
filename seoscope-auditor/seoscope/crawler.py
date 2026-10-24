"""Breadth-first, same-domain crawler.

Sequential by design: this is a local audit tool meant to run against a
handful of pages, not a production-scale crawler. Sequential requests are
easy to reason about, keep load on the target site polite, and need no
concurrency primitives.
"""
import hashlib
import time
from dataclasses import dataclass, field
from urllib.parse import urldefrag, urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

from seoscope.config import REQUEST_TIMEOUT_SECONDS, USER_AGENT
from seoscope.robots import RobotsInfo

HEADERS = {"User-Agent": USER_AGENT}


@dataclass
class CrawledPage:
    url: str
    status_code: int | None
    redirect_chain: list[str]
    load_time_ms: float
    html: str | None
    content_type: str
    error: str | None = None
    links: list[str] = field(default_factory=list)


def _normalize(url: str) -> str:
    url, _ = urldefrag(url)
    if url.endswith("/") and url.count("/") > 2:
        url = url[:-1]
    return url


def _same_domain(url: str, root_netloc: str) -> bool:
    return urlparse(url).netloc.lower() == root_netloc.lower()


def fetch_page(url: str) -> CrawledPage:
    start = time.monotonic()
    try:
        with httpx.Client(timeout=REQUEST_TIMEOUT_SECONDS, headers=HEADERS, follow_redirects=True) as client:
            resp = client.get(url)
    except httpx.HTTPError as exc:
        elapsed_ms = (time.monotonic() - start) * 1000
        return CrawledPage(url=url, status_code=None, redirect_chain=[], load_time_ms=elapsed_ms,
                            html=None, content_type="", error=str(exc))

    elapsed_ms = (time.monotonic() - start) * 1000
    redirect_chain = [str(r.url) for r in resp.history]
    content_type = resp.headers.get("content-type", "")

    html = resp.text if "text/html" in content_type or content_type == "" else None
    return CrawledPage(url=url, status_code=resp.status_code, redirect_chain=redirect_chain,
                        load_time_ms=elapsed_ms, html=html, content_type=content_type)


def extract_links(html: str, base_url: str) -> list[str]:
    soup = BeautifulSoup(html, "html.parser")
    links = []
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if href.startswith(("mailto:", "tel:", "javascript:", "#")):
            continue
        links.append(_normalize(urljoin(base_url, href)))
    return links


def crawl_site(root_url: str, max_pages: int, robots: RobotsInfo,
                seed_urls: list[str] | None = None, on_page=None) -> list[CrawledPage]:
    """Breadth-first crawl of same-domain pages starting at root_url, plus
    any seed_urls (e.g. from a sitemap) worth checking.

    on_page(page, pages_done, pages_total_estimate) is called after each
    fetch, letting the caller report progress or persist incrementally.
    """
    root_url = _normalize(root_url)
    root_netloc = urlparse(root_url).netloc

    queue = [root_url] + [u for u in (seed_urls or []) if _same_domain(u, root_netloc)]
    seen: set[str] = set()
    results: list[CrawledPage] = []

    while queue and len(results) < max_pages:
        url = _normalize(queue.pop(0))
        if url in seen:
            continue
        seen.add(url)

        if not robots.can_fetch(url):
            continue

        page = fetch_page(url)
        results.append(page)

        if page.html:
            links = extract_links(page.html, url)
            page.links = links
            for link in links:
                if _same_domain(link, root_netloc) and link not in seen:
                    queue.append(link)

        if on_page:
            on_page(page, len(results), max_pages)

    return results


def check_broken_links(links: list[str], root_netloc: str, cache: dict[str, int]) -> tuple[int, list[str]]:
    """HEAD (falling back to GET) each unique external/internal link once,
    using `cache` to avoid re-checking the same URL across pages."""
    broken = []
    for link in links:
        if link in cache:
            status = cache[link]
        else:
            status = _probe_status(link)
            cache[link] = status
        if status is None or status >= 400:
            broken.append(link)
    return len(broken), broken


def _probe_status(url: str) -> int | None:
    try:
        with httpx.Client(timeout=REQUEST_TIMEOUT_SECONDS, headers=HEADERS, follow_redirects=True) as client:
            resp = client.head(url)
            if resp.status_code >= 400:
                resp = client.get(url)
            return resp.status_code
    except httpx.HTTPError:
        return None


def content_hash(text: str) -> str:
    normalized = " ".join(text.split()).lower()
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()
