"""
Earthly registry monitor — main entrypoint.

Run with:
    python run.py

What it does:
1. Opens a headless browser
2. Visits each project in config.PROJECTS
3. Diffs scraped documents against monitor.db
4. Prints + logs + sends Slack alert for each new or updated document
5. Regenerates dashboard.html from the current DB state
6. Closes cleanly
"""

import asyncio
from datetime import datetime, timezone
from pathlib import Path
from playwright.async_api import async_playwright

import config
import db
from scraper import scrape_project
from notifier import send_slack_alert, send_run_summary
from dashboard import build_dashboard


def log_alert(message: str, log_path: Path) -> None:
    """Print to console and append to the log file with a timestamp."""
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    line = f"[{ts}] {message}"
    print(line)
    with log_path.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def diff_and_alert(conn, scraped_docs: list[dict], log_path: Path, webhook_url: str) -> tuple[int, int, int]:
    """
    For each scraped doc, compare to DB. Returns (new_count, updated_count, unchanged_count).
    """
    new_count = updated_count = unchanged_count = 0

    for doc in scraped_docs:
        existing = db.get_document(conn, doc["file_id"])

        if existing is None:
            db.insert_document(conn, doc)
            new_count += 1
            log_alert(
                f"NEW    | {doc['project_name']} | {doc['section']} | "
                f"{doc['title']} | uploaded {doc['date_updated']} | {doc['url']}",
                log_path,
            )
            send_slack_alert(
                webhook_url=webhook_url,
                project_name=doc["project_name"],
                section=doc["section"],
                title=doc["title"],
                date_updated=doc["date_updated"],
                url=doc["url"],
                alert_type="NEW",
            )
        elif (
            existing["date_updated"] != doc["date_updated"]
            or existing["title"] != doc["title"]
            or existing["url"] != doc["url"]
        ):
            db.update_document(conn, doc)
            updated_count += 1
            changes = []
            if existing["date_updated"] != doc["date_updated"]:
                changes.append(f"date: {existing['date_updated']} -> {doc['date_updated']}")
            if existing["title"] != doc["title"]:
                changes.append("title changed")
            change_note = ", ".join(changes)
            log_alert(
                f"UPDATE | {doc['project_name']} | {doc['section']} | "
                f"{doc['title']} | {change_note} | {doc['url']}",
                log_path,
            )
            send_slack_alert(
                webhook_url=webhook_url,
                project_name=doc["project_name"],
                section=doc["section"],
                title=doc["title"],
                date_updated=doc["date_updated"],
                url=doc["url"],
                alert_type="UPDATE",
                change_note=change_note,
            )
        else:
            db.touch_last_seen(conn, doc["file_id"])
            unchanged_count += 1

    return new_count, updated_count, unchanged_count


async def main():
    conn = db.init_db(config.DB_PATH)
    existing_count = db.total_docs(conn)
    is_first_run = existing_count == 0

    print(f"Starting registry monitor at {db.now_iso()}")
    print(f"Database: {config.DB_PATH} ({existing_count} documents currently tracked)")

    if not config.SLACK_WEBHOOK_URL:
        print("WARNING: SLACK_WEBHOOK_URL not set in .env — Slack alerts disabled")
    else:
        print("Slack notifications: ENABLED")

    if is_first_run:
        print("First run detected -> seeding database; alerts will be quiet this round.\n")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent=config.USER_AGENT,
            viewport={"width": 1400, "height": 900},
        )
        page = await context.new_page()

        totals = {"new": 0, "updated": 0, "unchanged": 0}

        for i, project in enumerate(config.PROJECTS):
            print(f"\n[{i + 1}/{len(config.PROJECTS)}] {project['name']} (VCS {project['id']})")
            try:
                docs = await scrape_project(
                    page, project,
                    config.REGISTRY_URL_TEMPLATE,
                    config.PAGE_LOAD_TIMEOUT_MS,
                    config.LAZY_CONTENT_WAIT_MS,
                )
            except Exception as e:
                print(f"  ERROR scraping VCS {project['id']}: {e}")
                continue

            if is_first_run:
                for doc in docs:
                    if db.get_document(conn, doc["file_id"]) is None:
                        db.insert_document(conn, doc)
                print(f"  Seeded {len(docs)} documents (no alerts on first run)")
            else:
                n, u, s = diff_and_alert(conn, docs, config.LOG_PATH, config.SLACK_WEBHOOK_URL)
                totals["new"] += n
                totals["updated"] += u
                totals["unchanged"] += s

            if i < len(config.PROJECTS) - 1:
                await page.wait_for_timeout(config.DELAY_BETWEEN_PROJECTS_MS)

        await browser.close()

    # Regenerate the dashboard from current DB state
    print("\nRegenerating dashboard...")
    dashboard_path = config.PROJECT_ROOT / "dashboard.html"
    doc_count = build_dashboard(config.DB_PATH, dashboard_path, config.PROJECTS)
    print(f"Dashboard updated: {dashboard_path} ({doc_count} documents)")

    print("\n" + "=" * 60)
    if is_first_run:
        print(f"Seeding complete. {db.total_docs(conn)} documents now tracked.")
        print("Next run will alert on any changes from this baseline.")
    else:
        print(
            f"Run complete. New: {totals['new']} | "
            f"Updated: {totals['updated']} | Unchanged: {totals['unchanged']}"
        )
        print(f"Full alert log: {config.LOG_PATH}")
        send_run_summary(
            webhook_url=config.SLACK_WEBHOOK_URL,
            new_count=totals["new"],
            updated_count=totals["updated"],
            total_tracked=db.total_docs(conn),
        )
    print("=" * 60)

    conn.close()


if __name__ == "__main__":
    asyncio.run(main())