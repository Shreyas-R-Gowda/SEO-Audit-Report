"""Duplicate content detection: groups crawled pages that hash to the same
normalized body text, and pages that share an identical title."""
from collections import defaultdict


def _issue(category, severity, title, description, recommendation, page_url=None, affected_count=1):
    return {
        "category": category, "severity": severity, "title": title,
        "description": description, "recommendation": recommendation,
        "page_url": page_url, "affected_count": affected_count,
    }


def find_duplicate_content(pages: list[dict]) -> list[dict]:
    """pages: list of dicts with 'url' and 'content_hash'."""
    by_hash = defaultdict(list)
    for p in pages:
        if p.get("content_hash"):
            by_hash[p["content_hash"]].append(p["url"])

    issues = []
    for urls in by_hash.values():
        if len(urls) > 1:
            issues.append(_issue(
                "content", "warning", "Duplicate content across pages",
                f"{len(urls)} pages have near-identical body content: {', '.join(urls[:4])}"
                + (" ..." if len(urls) > 4 else ""),
                "Consolidate duplicate pages, add canonical tags pointing to the "
                "preferred version, or differentiate the content.",
                affected_count=len(urls),
            ))

    by_title = defaultdict(list)
    for p in pages:
        if p.get("title"):
            by_title[p["title"].strip().lower()].append(p["url"])

    for title, urls in by_title.items():
        if len(urls) > 1:
            issues.append(_issue(
                "onpage", "warning", "Duplicate title tags",
                f'{len(urls)} pages share the title "{title}": {", ".join(urls[:4])}'
                + (" ..." if len(urls) > 4 else ""),
                "Give each page a unique, descriptive title tag.",
                affected_count=len(urls),
            ))

    return issues
