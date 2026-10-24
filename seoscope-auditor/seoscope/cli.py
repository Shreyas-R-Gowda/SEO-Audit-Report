"""Command-line entry point: run an audit without the web dashboard and
print a plain-text summary, e.g. `python -m seoscope.cli example.com`."""
import argparse
import sys

from seoscope import db
from seoscope.auditor import run_audit
from seoscope.config import DEFAULT_MAX_PAGES


def main():
    parser = argparse.ArgumentParser(description="Run a local SEO audit against a website.")
    parser.add_argument("url", help="Website URL to audit, e.g. example.com")
    parser.add_argument("--max-pages", type=int, default=DEFAULT_MAX_PAGES,
                         help=f"Maximum pages to crawl (default: {DEFAULT_MAX_PAGES})")
    args = parser.parse_args()

    db.init_db()
    print(f"Auditing {args.url} (up to {args.max_pages} pages)...")

    audit_id = run_audit(args.url, args.max_pages, progress_cb=lambda msg: print(f"  {msg}"))
    audit = db.get_audit(audit_id)

    if audit["status"] == "failed":
        print(f"\nAudit failed: {audit['error']}", file=sys.stderr)
        sys.exit(1)

    print(f"\nOverall score: {audit['overall_score']}/100")
    print(f"Pages crawled: {audit['pages_crawled']}")

    issues = db.get_issues(audit_id)
    counts = {}
    for issue in issues:
        counts[issue["severity"]] = counts.get(issue["severity"], 0) + issue["affected_count"]
    for severity in ("critical", "warning", "info"):
        print(f"  {severity}: {counts.get(severity, 0)}")

    print(f"\nStart the dashboard with `uvicorn seoscope.app:app --reload` to "
          f"view the full report, roadmap and download a PDF for audit #{audit_id}.")


if __name__ == "__main__":
    main()
