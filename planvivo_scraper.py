"""
Scraper for Plan Vivo project pages on planvivo.org.

Used for Plan Vivo projects that have no working Markit registry page
(e.g. Kukumuty, Scolel'te, Fes Enying). Each project page lists its documents
as direct file links, grouped under headings, for example:

    <h3>Latest Annual Report</h3>
    <a href="https://s3.eu-west-2.amazonaws.com/assets.planvivo.org/documents/
             PV-Climate-Certified-Projects/Kukumuty-Project-Documents/
             kukumuty-annual-report-2024-2025.pdf">View PDF</a>

    <h3>Annual reports</h3>
    <li><a href=".../scolelte-annual-report-2023.pdf">2023</a></li>

The file URL is unique per document, so it doubles as our dedup key, and the
Slack alert can link straight to the PDF.

Returns the same document dict shape as scraper.py, so the database, alerts
and dashboard work unchanged.
"""

import asyncio
import html
import re
from urllib.parse import unquote
import httpx


TOKEN_RE = re.compile(
    r"<h([23])[^>]*>(.*?)</h\1>"                       # section headings
    r"|<a\s[^>]*?href=[\"']([^\"']+)[\"'][^>]*>(.*?)</a>",  # links
    re.S | re.I,
)
TAG_RE = re.compile(r"<[^>]+>")
DOC_MARKER = "assets.planvivo.org/documents/"
EXCLUDE_MARKERS = ("Plan-Vivo-Organisational-Documents",)  # site footer docs
GENERIC_LINK_TEXT = {"view pdf", "download", "view", "pdf", ""}


def _clean(text: str) -> str:
    return " ".join(html.unescape(TAG_RE.sub(" ", text)).split())


def parse_planvivo_documents(page_html: str) -> list[dict]:
    """Extract project documents from a planvivo.org project page."""
    docs, seen = [], set()
    heading = "Documents"

    for m in TOKEN_RE.finditer(page_html):
        level, head_text, href, link_text = m.groups()
        if head_text is not None:
            heading = _clean(head_text) or heading
            continue

        href = html.unescape(href)
        if DOC_MARKER not in href or any(x in href for x in EXCLUDE_MARKERS):
            continue
        path = href.split(DOC_MARKER, 1)[1].split("?", 1)[0]
        if path in seen:
            continue
        seen.add(path)

        text = _clean(link_text)
        if text.lower() in GENERIC_LINK_TEXT or text == heading:
            title = heading
        else:
            title = f"{heading}: {text}"

        docs.append({
            "doc_id": unquote(path),
            "section": heading,
            "title": title,
            "url": href,
        })
    return docs


async def _fetch_html(client, url, max_retries, base_backoff_s):
    for attempt in range(1, max_retries + 1):
        try:
            resp = await client.get(url, timeout=30.0, follow_redirects=True)
        except httpx.HTTPError as e:
            print(f"    network error (attempt {attempt}/{max_retries}): {e}")
            await asyncio.sleep(base_backoff_s * attempt)
            continue
        if resp.status_code == 200:
            return resp.text
        if resp.status_code == 429 or resp.status_code >= 500:
            wait = base_backoff_s * attempt
            print(f"    HTTP {resp.status_code} (attempt {attempt}/{max_retries}); waiting {wait:.0f}s")
            await asyncio.sleep(wait)
            continue
        print(f"    HTTP {resp.status_code} - not retrying")
        return None
    return None


async def scrape_planvivo_project(client, project, url_template, max_retries, base_backoff_s):
    """
    Fetch one planvivo.org project page. Returns doc dicts, or None on failure.
    Zero parsed documents is treated as a failure (possible layout change),
    never as 'the project has no documents'.
    """
    url = url_template.format(project_id=project["id"])
    print(f"  Fetching {url}")
    page = await _fetch_html(client, url, max_retries, base_backoff_s)
    if page is None:
        print(f"  FAILED to fetch Plan Vivo page {project['id']}")
        return None

    parsed = parse_planvivo_documents(page)
    if not parsed:
        print(f"  WARNING: page loaded but no documents parsed for {project['id']} "
              f"(possible layout change) - skipping, not treating as empty")
        return None

    docs = [{
        "doc_key": f"planvivo:{project['id']}:{d['doc_id']}",
        "doc_id": d["doc_id"],
        "project_id": project["id"],
        "project_name": project["name"],
        "section": d["section"],
        "title": d["title"],
        "state_code": "",
        "url": d["url"],  # direct link to the PDF
    } for d in parsed]
    print(f"  Found {len(docs)} documents")
    return docs