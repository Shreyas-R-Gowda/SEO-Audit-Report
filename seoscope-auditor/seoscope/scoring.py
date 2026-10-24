"""Turns a flat list of issues into a 0-100 overall score plus a per-category
breakdown, by deducting a severity-weighted penalty within each category and
blending the categories by their configured weight."""
from seoscope.config import CATEGORY_WEIGHTS, SEVERITY_PENALTY


def compute_score(issues: list[dict], analyzed_pages: int | None = None) -> tuple[float, dict]:
    """analyzed_pages is the number of pages whose on-page/content was
    actually inspected (i.e. excluding pages that errored or were blocked
    before any content could be read). When it's 0, "onpage" and "content"
    have no real data to score — reporting them as a perfect 100 would be
    misleading, so they're left out of the score entirely rather than
    assumed to pass."""
    category_raw_scores = {}
    no_data_categories = set()

    for category in CATEGORY_WEIGHTS:
        if category in ("onpage", "content") and analyzed_pages == 0:
            category_raw_scores[category] = None
            no_data_categories.add(category)
            continue
        category_issues = [i for i in issues if i["category"] == category]
        penalty = sum(SEVERITY_PENALTY.get(i["severity"], 0) * i.get("affected_count", 1)
                       for i in category_issues)
        category_raw_scores[category] = max(0, 100 - penalty)

    scored_weight = sum(w for c, w in CATEGORY_WEIGHTS.items() if c not in no_data_categories)
    if scored_weight == 0:
        overall = 0.0
    else:
        overall = sum(category_raw_scores[c] * (w / scored_weight)
                       for c, w in CATEGORY_WEIGHTS.items() if c not in no_data_categories)

    rounded_scores = {c: (round(s, 1) if s is not None else None) for c, s in category_raw_scores.items()}
    return round(overall, 1), rounded_scores


def grade_for_score(score: float) -> str:
    if score >= 90:
        return "A"
    if score >= 80:
        return "B"
    if score >= 70:
        return "C"
    if score >= 60:
        return "D"
    return "F"
