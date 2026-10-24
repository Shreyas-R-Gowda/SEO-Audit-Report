"""Builds a step-by-step optimization roadmap from an audit's issues:
critical fixes first, then warnings, then polish, each step naming the
concrete issues it resolves."""

STEP_INTROS = {
    "critical": "Fix critical issues first — these most directly block indexing or ranking.",
    "warning": "Resolve these warnings next to strengthen on-page and technical SEO.",
    "info": "Polish these lower-priority items once the above are handled.",
}


def build_roadmap(issues: list[dict]) -> list[dict]:
    roadmap = []
    step_number = 1
    for severity in ("critical", "warning", "info"):
        severity_issues = [i for i in issues if i["severity"] == severity]
        if not severity_issues:
            continue

        grouped = {}
        for issue in severity_issues:
            grouped.setdefault(issue["title"], []).append(issue)

        actions = []
        for title, group in grouped.items():
            affected = sum(i.get("affected_count", 1) for i in group)
            actions.append({
                "title": title,
                "recommendation": group[0]["recommendation"],
                "affected_count": affected,
            })

        roadmap.append({
            "step": step_number,
            "severity": severity,
            "intro": STEP_INTROS[severity],
            "actions": sorted(actions, key=lambda a: a["affected_count"], reverse=True),
        })
        step_number += 1

    return roadmap
