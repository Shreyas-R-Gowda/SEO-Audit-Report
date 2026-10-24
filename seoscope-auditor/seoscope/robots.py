"""robots.txt and sitemap.xml discovery, kept separate from the crawler so
the technical checks can report on them independently of whether the crawl
itself follows their rules."""
import urllib.robotparser as robotparser
from urllib.parse import urljoin
from xml.etree import ElementTree

import httpx

from seoscope.config import REQUEST_TIMEOUT_SECONDS, USER_AGENT


class RobotsInfo:
    def __init__(self, found: bool, fetch_error: str | None, parser: robotparser.RobotFileParser | None,
                 sitemap_urls: list[str]):
        self.found = found
        self.fetch_error = fetch_error
        self._parser = parser
        self.sitemap_urls = sitemap_urls

    def can_fetch(self, url: str) -> bool:
        if not self._parser:
            return True
        return self._parser.can_fetch(USER_AGENT, url)


def fetch_robots(root_url: str) -> RobotsInfo:
    robots_url = urljoin(root_url, "/robots.txt")
    try:
        resp = httpx.get(robots_url, timeout=REQUEST_TIMEOUT_SECONDS,
                          headers={"User-Agent": USER_AGENT}, follow_redirects=True)
    except httpx.HTTPError as exc:
        return RobotsInfo(found=False, fetch_error=str(exc), parser=None, sitemap_urls=[])

    if resp.status_code != 200:
        return RobotsInfo(found=False, fetch_error=f"HTTP {resp.status_code}", parser=None, sitemap_urls=[])

    parser = robotparser.RobotFileParser()
    parser.parse(resp.text.splitlines())

    sitemap_urls = [line.split(":", 1)[1].strip()
                     for line in resp.text.splitlines()
                     if line.lower().startswith("sitemap:")]

    return RobotsInfo(found=True, fetch_error=None, parser=parser, sitemap_urls=sitemap_urls)


def discover_sitemap_urls(root_url: str, robots: RobotsInfo, limit: int = 500) -> tuple[list[str], str | None]:
    """Returns (urls, error). Tries sitemaps declared in robots.txt first,
    then falls back to the conventional /sitemap.xml location."""
    candidates = list(robots.sitemap_urls) or [urljoin(root_url, "/sitemap.xml")]
    urls: list[str] = []
    last_error = None

    for sitemap_url in candidates:
        try:
            is_index, locs = _fetch_and_parse_sitemap(sitemap_url)
            if not is_index:
                urls.extend(locs)
                continue
            # Sitemap index: locs are child sitemap files, one level deep is enough
            # for a local audit tool.
            for child_url in locs[:20]:
                try:
                    _, child_locs = _fetch_and_parse_sitemap(child_url)
                    urls.extend(child_locs)
                except (httpx.HTTPError, ElementTree.ParseError) as exc:
                    last_error = f"{child_url}: {exc}"
        except (httpx.HTTPError, ElementTree.ParseError) as exc:
            last_error = f"{sitemap_url}: {exc}"

    if urls:
        return urls[:limit], None
    return [], last_error


def _fetch_and_parse_sitemap(sitemap_url: str) -> tuple[bool, list[str]]:
    resp = httpx.get(sitemap_url, timeout=REQUEST_TIMEOUT_SECONDS,
                      headers={"User-Agent": USER_AGENT}, follow_redirects=True)
    if resp.status_code != 200:
        raise httpx.HTTPError(f"{sitemap_url} returned HTTP {resp.status_code}")
    root = ElementTree.fromstring(resp.content)
    is_index = root.tag.lower().endswith("sitemapindex")
    locs = [el.text.strip() for el in root.iter()
            if el.tag.lower().endswith("loc") and el.text]
    return is_index, locs
