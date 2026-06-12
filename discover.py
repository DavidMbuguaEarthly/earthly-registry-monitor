"""
Discovery script for the Verra registry monitor.

Purpose: load ONE project page (VCS 2250 - Delta Blue Carbon) in a visible
browser, wait for the documents tab/table to render, then dump everything
we can find about its structure to the console.

Run with the browser visible so you can watch what happens and click around
manually if needed. Once we know the selectors, we'll automate them in the
real scraper.

Usage:
    source venv/bin/activate
    python discover.py
"""

import asyncio
import json
from pathlib import Path
from playwright.async_api import async_playwright

PROJECT_ID = 2250  # Delta Blue Carbon
PROJECT_URL = f"https://registry.verra.org/app/projectDetail/VCS/{PROJECT_ID}"
OUTPUT_DIR = Path(__file__).parent / "discovery_output"
OUTPUT_DIR.mkdir(exist_ok=True)


async def discover():
    async with async_playwright() as p:
        # headless=False -> you see the browser window open and load the page.
        # slow_mo adds a small delay between actions so you can follow along.
        browser = await p.chromium.launch(headless=False, slow_mo=300)
        context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1400, "height": 900},
        )
        page = await context.new_page()

        # Capture every XHR / fetch request the page makes. If the documents
        # are loaded via a JSON API, we'll spot it here and may be able to
        # skip the browser entirely in v2.
        xhr_log = []
        page.on(
            "response",
            lambda r: xhr_log.append(
                {
                    "url": r.url,
                    "status": r.status,
                    "content_type": r.headers.get("content-type", ""),
                }
            )
            if r.request.resource_type in ("xhr", "fetch")
            else None,
        )

        print(f"\nLoading {PROJECT_URL} ...")
        await page.goto(PROJECT_URL, wait_until="networkidle", timeout=60_000)
        print("Page loaded. Waiting 5s for any lazy content ...")
        await page.wait_for_timeout(5_000)

        # ---------- 1. Page title and basic metadata ----------
        title = await page.title()
        print(f"\nPage title: {title}")

        # ---------- 2. Look for the documents tab/section ----------
        # Verra typically uses a tabbed layout. The documents are usually
        # under a tab labelled "Documents" or similar. We'll search for
        # anything that looks like it.
        print("\nSearching for 'Documents' related elements ...")
        candidates = await page.evaluate(
            """() => {
                const results = [];
                document.querySelectorAll('a, button, div, span, li').forEach(el => {
                    const text = (el.textContent || '').trim();
                    if (text && text.length < 50 && /document/i.test(text)) {
                        results.push({
                            tag: el.tagName,
                            text: text,
                            id: el.id || null,
                            classes: el.className && typeof el.className === 'string'
                                ? el.className : null,
                            href: el.href || null,
                        });
                    }
                });
                return results.slice(0, 30);
            }"""
        )
        for c in candidates:
            print(f"  {c['tag']:6} text='{c['text']}' id={c['id']} class={c['classes']}")

        # ---------- 3. Try to click the Documents tab if found ----------
        # Common patterns. We try several selectors in priority order.
        tab_clicked = False
        for selector in [
            "text=Documents",
            "a:has-text('Documents')",
            "button:has-text('Documents')",
            "li:has-text('Documents')",
        ]:
            try:
                el = page.locator(selector).first
                if await el.count() > 0 and await el.is_visible():
                    print(f"\nClicking selector: {selector}")
                    await el.click(timeout=5_000)
                    await page.wait_for_timeout(3_000)
                    tab_clicked = True
                    break
            except Exception as e:
                print(f"  selector {selector} -> {e}")

        if not tab_clicked:
            print("\nCould not auto-click a Documents tab.")
            print("Click it MANUALLY in the browser, then press Enter here...")
            input()

        # ---------- 4. Inspect tables on the page ----------
        print("\nInspecting tables ...")
        table_info = await page.evaluate(
            """() => {
                const tables = Array.from(document.querySelectorAll('table'));
                return tables.map((t, i) => ({
                    index: i,
                    rows: t.rows.length,
                    headers: Array.from(t.querySelectorAll('thead th, tr:first-child th, tr:first-child td'))
                        .map(h => h.textContent.trim()).slice(0, 10),
                    sample_row: t.rows[1]
                        ? Array.from(t.rows[1].cells).map(c => c.textContent.trim().slice(0, 80))
                        : null,
                    id: t.id || null,
                    classes: t.className || null,
                }));
            }"""
        )
        for t in table_info:
            print(f"\n  Table #{t['index']} ({t['rows']} rows)")
            print(f"    id={t['id']} class={t['classes']}")
            print(f"    headers: {t['headers']}")
            print(f"    sample row: {t['sample_row']}")

        # ---------- 5. Look for direct document links (PDFs, etc) ----------
        print("\nLooking for direct file links ...")
        file_links = await page.evaluate(
            """() => {
                return Array.from(document.querySelectorAll('a[href]'))
                    .map(a => ({ href: a.href, text: a.textContent.trim().slice(0, 100) }))
                    .filter(l => /\\.(pdf|docx?|xlsx?)$/i.test(l.href)
                             || /document|attachment|file/i.test(l.href))
                    .slice(0, 40);
            }"""
        )
        for l in file_links:
            print(f"  {l['text'][:60]:60} -> {l['href']}")

        # ---------- 6. Save the rendered HTML for offline analysis ----------
        html = await page.content()
        html_path = OUTPUT_DIR / f"vcs_{PROJECT_ID}.html"
        html_path.write_text(html, encoding="utf-8")
        print(f"\nFull HTML saved to: {html_path}")

        # ---------- 7. Save the XHR request log ----------
        xhr_path = OUTPUT_DIR / f"vcs_{PROJECT_ID}_xhr.json"
        xhr_path.write_text(json.dumps(xhr_log, indent=2), encoding="utf-8")
        print(f"XHR log saved to:   {xhr_path}  ({len(xhr_log)} requests)")

        # ---------- 8. Take a screenshot ----------
        screenshot_path = OUTPUT_DIR / f"vcs_{PROJECT_ID}.png"
        await page.screenshot(path=str(screenshot_path), full_page=True)
        print(f"Screenshot saved:   {screenshot_path}")

        print("\nBrowser stays open. Click around, inspect with DevTools (Cmd+Opt+I).")
        print("Press Enter here when done to close.")
        input()
        await browser.close()


if __name__ == "__main__":
    asyncio.run(discover())