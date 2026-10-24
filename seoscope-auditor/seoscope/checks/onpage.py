"""Per-page on-page SEO checks: titles, meta descriptions, headings, alt
text, internal linking and indexability signals."""
from urllib.parse import urlparse

from bs4 import BeautifulSoup

from seoscope.config import (META_DESC_MAX_LEN, META_DESC_MIN_LEN, THIN_CONTENT_WORD_COUNT,
                              TITLE_MAX_LEN, TITLE_MIN_LEN)
from seoscope.crawler import content_hash


def analyze_page(url: str, html: str, root_netloc: str) -> dict:
    soup = BeautifulSoup(html, "html.parser")

    title_tag = soup.find("title")
    title = title_tag.get_text(strip=True) if title_tag else None

    meta_desc_tag = soup.find("meta", attrs={"name": "description"})
    meta_description = meta_desc_tag.get("content", "").strip() if meta_desc_tag else None

    robots_meta = soup.find("meta", attrs={"name": "robots"})
    robots_content = (robots_meta.get("content", "") if robots_meta else "").lower()
    is_indexable = "noindex" not in robots_content

    canonical_tag = soup.find("link", attrs={"rel": "canonical"})
    canonical = canonical_tag.get("href", "").strip() if canonical_tag else None

    h1_tags = soup.find_all("h1")
    headings = {f"h{i}": len(soup.find_all(f"h{i}")) for i in range(1, 7)}

    images = soup.find_all("img")
    missing_alt = [img for img in images if not img.get("alt", "").strip()]

    body_text = soup.get_text(separator=" ", strip=True)
    word_count = len(body_text.split())

    internal_links = 0
    external_links = 0
    all_links = []
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if href.startswith(("mailto:", "tel:", "javascript:", "#")) or not href:
            continue
        all_links.append(href)
        netloc = urlparse(href).netloc
        if not netloc or netloc.lower() == root_netloc.lower():
            internal_links += 1
        else:
            external_links += 1

    heading_order_issue = _check_heading_hierarchy(headings)

    return {
        "title": title,
        "title_len": len(title) if title else 0,
        "meta_description": meta_description,
        "meta_description_len": len(meta_description) if meta_description else 0,
        "is_indexable": is_indexable,
        "robots_meta": robots_content or None,
        "canonical": canonical,
        "h1_count": len(h1_tags),
        "h1_text": [h.get_text(strip=True) for h in h1_tags[:3]],
        "headings": headings,
        "heading_order_issue": heading_order_issue,
        "images_count": len(images),
        "missing_alt_count": len(missing_alt),
        "word_count": word_count,
        "internal_links": internal_links,
        "external_links": external_links,
        "all_links": all_links,
        "content_hash": content_hash(body_text) if word_count > 20 else None,
        "thin_content": word_count < THIN_CONTENT_WORD_COUNT,
    }


def _check_heading_hierarchy(headings: dict) -> bool:
    """True if a heading level is used while a shallower level (other than
    h1) was skipped entirely, e.g. an h3 with no h2 anywhere on the page."""
    levels_present = [i for i in range(2, 7) if headings.get(f"h{i}", 0) > 0]
    if not levels_present:
        return False
    deepest = max(levels_present)
    for i in range(2, deepest):
        if headings.get(f"h{i}", 0) == 0:
            return True
    return False


def onpage_issues(page_url: str, data: dict) -> list[dict]:
    issues = []

    if not data["title"]:
        issues.append(_issue("onpage", "critical", "Missing title tag",
                              "This page has no <title> tag.",
                              "Add a unique, descriptive title tag between "
                              f"{TITLE_MIN_LEN} and {TITLE_MAX_LEN} characters.", page_url))
    elif data["title_len"] < TITLE_MIN_LEN:
        issues.append(_issue("onpage", "warning", "Title tag too short",
                              f'Title is {data["title_len"]} characters: "{data["title"]}".',
                              f"Expand the title to at least {TITLE_MIN_LEN} characters "
                              "while keeping it accurate and compelling.", page_url))
    elif data["title_len"] > TITLE_MAX_LEN:
        issues.append(_issue("onpage", "warning", "Title tag too long",
                              f'Title is {data["title_len"]} characters and may be truncated in search results: '
                              f'"{data["title"]}".',
                              f"Shorten the title to under {TITLE_MAX_LEN} characters.", page_url))

    if not data["meta_description"]:
        issues.append(_issue("onpage", "warning", "Missing meta description",
                              "This page has no meta description.",
                              "Add a meta description summarizing the page's content "
                              f"in {META_DESC_MIN_LEN}-{META_DESC_MAX_LEN} characters.", page_url))
    elif data["meta_description_len"] < META_DESC_MIN_LEN:
        issues.append(_issue("onpage", "info", "Meta description too short",
                              f'Meta description is {data["meta_description_len"]} characters.',
                              f"Expand it to at least {META_DESC_MIN_LEN} characters.", page_url))
    elif data["meta_description_len"] > META_DESC_MAX_LEN:
        issues.append(_issue("onpage", "info", "Meta description too long",
                              f'Meta description is {data["meta_description_len"]} characters and may be truncated.',
                              f"Shorten it to under {META_DESC_MAX_LEN} characters.", page_url))

    if data["h1_count"] == 0:
        issues.append(_issue("onpage", "warning", "Missing H1 heading",
                              "This page has no H1 heading.",
                              "Add a single H1 that describes the page's main topic.", page_url))
    elif data["h1_count"] > 1:
        issues.append(_issue("onpage", "info", "Multiple H1 headings",
                              f'This page has {data["h1_count"]} H1 tags.',
                              "Use a single H1 per page and demote the others to H2/H3.", page_url))

    if data["heading_order_issue"]:
        issues.append(_issue("onpage", "info", "Skipped heading level",
                              "A deeper heading level is used without its parent level "
                              "appearing earlier on the page.",
                              "Keep headings in order (H1 > H2 > H3...) to preserve a "
                              "clear document outline.", page_url))

    if data["missing_alt_count"] > 0:
        issues.append(_issue("onpage", "warning", "Images missing alt text",
                              f'{data["missing_alt_count"]} of {data["images_count"]} images '
                              "have no alt attribute.",
                              "Add descriptive alt text to every meaningful image for "
                              "accessibility and image search visibility.", page_url,
                              affected_count=data["missing_alt_count"]))

    if not data["is_indexable"]:
        issues.append(_issue("onpage", "critical", "Page excluded from indexing",
                              'This page has a robots meta tag containing "noindex".',
                              "Remove the noindex directive if this page should appear "
                              "in search results.", page_url))

    if not data["canonical"]:
        issues.append(_issue("onpage", "info", "Missing canonical tag",
                              "This page has no rel=canonical link.",
                              "Add a self-referencing canonical tag to prevent duplicate "
                              "content issues.", page_url))

    if data["thin_content"]:
        issues.append(_issue("content", "info", "Thin content",
                              f'This page has only {data["word_count"]} words of visible text.',
                              f"Expand the content to at least {THIN_CONTENT_WORD_COUNT} words "
                              "where it adds genuine value to the reader.", page_url))

    return issues


def _issue(category, severity, title, description, recommendation, page_url, affected_count=1):
    return {
        "category": category, "severity": severity, "title": title,
        "description": description, "recommendation": recommendation,
        "page_url": page_url, "affected_count": affected_count,
    }
