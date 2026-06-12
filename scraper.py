"""
Scraper for a single Verra project page.

For each project, walks every 'card-header bg-primary' section, finds the
table inside it, and pulls (file_id, title, date, url, section) for each row.
"""

import re
from urllib.parse import urlparse, parse_qs
from playwright.async_api import Page


JS_EXTRACT_DOCUMENTS = """
() => {
    const results = [];
    const sectionHeaders = document.querySelectorAll('.card-header.bg-primary');

    sectionHeaders.forEach(header => {
        const sectionName = header.textContent.trim();
        // The table is inside the same parent .card as the header.
        const card = header.closest('.card');
        if (!card) return;

        const tables = card.querySelectorAll('table.table-striped');
        tables.forEach(table => {
            const rows = table.querySelectorAll('tbody tr, tr');
            rows.forEach(row => {
                const cells = row.querySelectorAll('td');
                if (cells.length < 2) return;

                const link = cells[0].querySelector('a[href]');
                if (!link) return;

                results.push({
                    section: sectionName,
                    title: cells[0].textContent.trim(),
                    date_updated: cells[1].textContent.trim(),
                    url: link.href,
                });
            });
        });
    });
    return results;
}
"""


def extract_file_id(url: str) -> int | None:
    """Pull the FileID query param out of a Verra document URL."""
    try:
        qs = parse_qs(urlparse(url).query)
        if "FileID" in qs:
            return int(qs["FileID"][0])
    except (ValueError, KeyError):
        return None
    return None


async def scrape_project(
    page: Page, project: dict, registry_url_template: str,
    page_timeout_ms: int, lazy_wait_ms: int,
) -> list[dict]:
    """
    Load one project page and return all documents found.
    Each doc is a dict ready to hand to db.insert_document().

    Wait strategy: 'domcontentloaded' rather than 'networkidle'. The Verra
    project pages embed a live map (Microsoft/TomTom) that keeps the network
    busy indefinitely, so 'networkidle' never fires and times out. We only
    need the DOM/tables, which are ready at domcontentloaded; a short fixed
    wait afterward lets any table rendering settle.
    """
    url = registry_url_template.format(project_id=project["id"])
    print(f"  Loading {url}")
    await page.goto(url, wait_until="domcontentloaded", timeout=page_timeout_ms)

    # Wait for the document tables to actually appear in the DOM, with a
    # generous timeout. If they never show (e.g. a project with no docs),
    # fall through after lazy_wait and let extraction return what it finds.
    try:
        await page.wait_for_selector(".card-header.bg-primary", timeout=15_000)
    except Exception:
        pass

    await page.wait_for_timeout(lazy_wait_ms)

    raw = await page.evaluate(JS_EXTRACT_DOCUMENTS)
    docs = []
    skipped = 0

    for item in raw:
        file_id = extract_file_id(item["url"])
        if file_id is None:
            skipped += 1
            continue
        docs.append({
            "file_id": file_id,
            "project_id": project["id"],
            "project_name": project["name"],
            "section": item["section"],
            "title": item["title"],
            "date_updated": item["date_updated"],
            "url": item["url"],
        })

    print(f"  Found {len(docs)} documents ({skipped} rows skipped)")
    return docs