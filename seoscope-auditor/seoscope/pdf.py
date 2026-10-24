"""Renders the HTML audit report to PDF using xhtml2pdf, a pure-Python
PDF writer with no native/system dependencies — important for an "easy to
run locally" tool on any OS."""
from io import BytesIO

from xhtml2pdf import pisa


def html_to_pdf(html: str) -> bytes:
    buffer = BytesIO()
    result = pisa.CreatePDF(src=html, dest=buffer)
    if result.err:
        raise RuntimeError("Failed to render PDF report")
    return buffer.getvalue()
