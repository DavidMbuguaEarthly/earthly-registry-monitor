"""
Scraper for the Markit Environmental Registry (mer.markit.com).

Markit hosts Plan Vivo, Woodland Carbon Code and Peatland Code projects.
Project pages are plain server-rendered HTML at:

    https://mer.markit.com/br-reg/public/project.jsp?project_id={id}

Each document link looks like:

    <a href="javascript:void(0)" onclick="downloadDocument(103000000260858)">
        (PV) Annual Report</a> (01 Jan 2017-24 Nov 2022)

The number inside downloadDocument(...) is a unique document ID, which we
use as the dedup key. Documents sit under two headings: "Project Documents"
and "Issuance Documents". Issuance documents also carry a period date range.

Returns the same document dict shape as scraper.py (Verra), so the database,
alerts and dashboard work unchanged.
"""

import asyncio
import html
import re
import httpx


SECTION_RE = re.compile(
    r"<dt[^>]*>\s*(Project Documents|Issuance Documents)\s*</dt>\s*<dd[^>]*>(.*?)</dd>",
    re.S | re.I,
)
LI_RE = re.compile(r"<li[^>]*>(.*?)</li>", re.S | re.I)
DOC_RE = re.compile(r"downloadDocument\(\s*'?(\d+)'?\s*\)[^>]*>(.*?)</a>(.*)", re.S | re.I)
PERIOD_RE = re.compile(r"\(([^()]*\d{4}[^()]*)\)")
TAG_RE = re.compile(r"<[^>]+>")


def _clean(text: str) -> str:
    return " ".join(html.unescape(TAG_RE.sub(" ", text)).split())


def parse_markit_documents(page_html: str) -> list[dict]:
    """Extract documents from a Markit project page. Pure function, easy to test."""
    docs = []
    seen = set()

    blocks = SECTION_RE.findall(page_html)
    if not blocks:
        # Fallback if headings change: still grab every document link.
        blocks = [("Documents", page_html)]

    for section_name, block in blocks:
        for li in LI_RE.findall(block) or [block]:
            m = DOC_RE.search(li)
            if not m:
                continue
            doc_id, raw_title, after = m.groups()
            if doc_id in seen:
                continue
            seen.add(doc_id)
            period_match = PERIOD_RE.search(_clean(after))
            docs.append({
                "doc_id": doc_id,
                "section": section_name.strip().title(),
                "type_name": _clean(raw_title),
                "period": period_match.group(1).strip() if period_match else "",
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


async def scrape_markit_project(client, project, url_template, max_retries, base_backoff_s):
    """
    Fetch one Markit project. Returns list of doc dicts, or None on failure.
    A page that loads but yields zero documents is treated as a failure, so a
    layout change can never silently look like 'no documents' (the lesson
    from the Verra revamp).
    """
    url = url_template.format(project_id=project["id"])
    print(f"  Fetching {url}")
    page = await _fetch_html(client, url, max_retries, base_backoff_s)
    if page is None:
        print(f"  FAILED to fetch Markit {project['id']}")
        return None

    parsed = parse_markit_documents(page)
    if not parsed:
        print(f"  WARNING: page loaded but no documents parsed for {project['id']} "
              f"(possible layout change) - skipping, not treating as empty")
        return None

    docs = []
    for d in parsed:
        title = d["type_name"] + (f" ({d['period']})" if d["period"] else "")
        docs.append({
            "doc_key": f"markit:{project['id']}:{d['doc_id']}",
            "doc_id": d["doc_id"],
            "project_id": project["id"],
            "project_name": project["name"],
            "section": d["section"],
            "title": title,
            "state_code": "",
            "url": url,
        })
    print(f"  Found {len(docs)} documents")
    return docs