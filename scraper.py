"""
Scraper for the new Verra registry (S&P Global / Platts backend).

The old APX site was replaced ~July 2026 by an S&P-built platform. Project
data now comes from a JSON API rather than a scraped HTML page, so this no
longer uses Playwright - just httpx against:

    https://prod-us.api.platts.com/ci-raas-prod/br-reg/rest/
        public-report-manager/getProjectById/{project_id}/Markit

Key differences from the old scraper, all handled here:
  - Documents live in the JSON `documentList` array.
  - Each document has a unique `id` (our dedup key; old FileID is gone).
  - There is NO per-document date (`doc_modify_date` is null) and NO usable
    per-document URL (`document_link` is identical for all docs), so we track
    existence only and link to the project page, not the file.
  - The API rate-limits aggressively (HTTP 429). We respect Retry-After and
    back off with retries.
"""

import asyncio
import httpx


PROJECT_PAGE_TEMPLATE = (
    "https://registry.verra.org/verra/public/program/VCS/projects/{project_id}"
)


def _doc_key(project_id: int, doc_id) -> str:
    """Composite unique key: project + document id. Stable across runs."""
    return f"{project_id}:{doc_id}"


async def _fetch_with_backoff(
    client: httpx.AsyncClient, url: str,
    max_retries: int, base_backoff_s: float,
) -> dict | None:
    """
    GET a URL, respecting 429 rate limits. Returns parsed JSON dict, or None
    if it ultimately failed. Honors Retry-After when the server provides it.
    """
    for attempt in range(1, max_retries + 1):
        try:
            resp = await client.get(url, timeout=30.0, follow_redirects=True)
        except httpx.HTTPError as e:
            print(f"    network error (attempt {attempt}/{max_retries}): {e}")
            await asyncio.sleep(base_backoff_s * attempt)
            continue

        if resp.status_code == 200:
            try:
                return resp.json()
            except ValueError:
                print(f"    got 200 but response was not JSON")
                return None

        if resp.status_code == 429:
            # Respect Retry-After if present, else exponential-ish backoff.
            retry_after = resp.headers.get("Retry-After")
            if retry_after and retry_after.isdigit():
                wait = int(retry_after) + 2
            else:
                wait = base_backoff_s * (2 ** (attempt - 1))
            print(f"    429 rate limited (attempt {attempt}/{max_retries}); "
                  f"waiting {wait:.0f}s")
            await asyncio.sleep(wait)
            continue

        if resp.status_code == 400:
            # A 400 means the request is malformed (e.g. missing headers).
            # Retrying won't help - fail fast so we don't waste attempts.
            print(f"    HTTP 400 Bad Request - not retrying (check headers)")
            return None

        print(f"    HTTP {resp.status_code} (attempt {attempt}/{max_retries})")
        await asyncio.sleep(base_backoff_s * attempt)

    return None


async def scrape_project(
    client: httpx.AsyncClient, project: dict, api_url_template: str,
    max_retries: int, base_backoff_s: float,
) -> list[dict] | None:
    """
    Fetch one project's documents from the API.

    Returns a list of document dicts ready for the DB, or None if the fetch
    failed entirely (so the caller can distinguish "0 documents" from
    "couldn't reach the API" - important, since the latter must NOT be treated
    as 'all documents disappeared').
    """
    url = api_url_template.format(project_id=project["id"])
    print(f"  Fetching {url}")
    data = await _fetch_with_backoff(client, url, max_retries, base_backoff_s)

    if data is None:
        print(f"  FAILED to fetch VCS {project['id']} after retries")
        return None

    doc_list = data.get("documentList") or []
    project_page = PROJECT_PAGE_TEMPLATE.format(project_id=project["id"])

    docs = []
    skipped = 0
    for item in doc_list:
        doc_id = item.get("id")
        if doc_id is None:
            skipped += 1
            continue
        docs.append({
            "doc_key": _doc_key(project["id"], doc_id),
            "doc_id": str(doc_id),
            "project_id": project["id"],
            "project_name": project["name"],
            "section": item.get("type_name", "Unknown"),
            "title": item.get("document_name", "(untitled)"),
            "state_code": item.get("state_code", ""),
            # No per-doc date or URL available from this API; use project page.
            "url": project_page,
        })

    print(f"  Found {len(docs)} documents ({skipped} rows skipped)")
    return docs