"""
Earthly registry monitor - main entrypoint (API version, Aug 2026).

Verra migrated to an S&P Global / Platts JSON API. This no longer uses a
browser; it calls the API directly with httpx, respecting rate limits.

Run with:
    python run.py

Flow:
1. For each project, fetch its documents from the API (with 429 backoff)
2. Diff against monitor.db by doc_key
3. Alert (console + log + Slack) on NEW documents and state_code changes
4. Regenerate dashboard.html
5. IMPORTANT: if a project fetch FAILS, skip it - never treat a failed fetch
   as 'documents disappeared'.
"""

import asyncio
from datetime import datetime, timezone
from pathlib import Path
import httpx

import config
import db
from scraper import scrape_project
from markit_scraper import scrape_markit_project
from planvivo_scraper import scrape_planvivo_project
from notifier import send_slack_alert, send_run_summary
from dashboard import build_dashboard


def log_alert(message: str, log_path: Path) -> None:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    line = f"[{ts}] {message}"
    print(line)
    with log_path.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def diff_and_alert(conn, scraped_docs, log_path, webhook_url, registry="Verra"):
    """Returns (new, updated, unchanged)."""
    new_count = updated_count = unchanged_count = 0

    for doc in scraped_docs:
        existing = db.get_document(conn, doc["doc_key"])

        if existing is None:
            db.insert_document(conn, doc)
            new_count += 1
            log_alert(
                f"NEW    | {doc['project_name']} | {doc['section']} | "
                f"{doc['title']} | {doc['url']}",
                log_path,
            )
            send_slack_alert(
                webhook_url=webhook_url,
                project_name=doc["project_name"],
                section=doc["section"],
                title=doc["title"],
                date_updated="",  # no per-doc date from new API
                url=doc["url"],
                alert_type="NEW",
                registry=registry,
            )
        elif (existing["state_code"] != doc["state_code"]
              or existing["title"] != doc["title"]
              or existing["section"] != doc["section"]):
            db.update_document(conn, doc)
            updated_count += 1
            note_bits = []
            if existing["state_code"] != doc["state_code"]:
                note_bits.append(f"state: {existing['state_code']} -> {doc['state_code']}")
            if existing["title"] != doc["title"]:
                note_bits.append("title changed")
            change_note = ", ".join(note_bits)
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
                date_updated="",
                url=doc["url"],
                alert_type="UPDATE",
                registry=registry,
                change_note=change_note,
            )
        else:
            db.touch_last_seen(conn, doc["doc_key"])
            unchanged_count += 1

    return new_count, updated_count, unchanged_count


async def main():
    conn = db.init_db(config.DB_PATH)
    existing_count = db.total_docs(conn)
    is_first_run = existing_count == 0

    print(f"Starting registry monitor at {db.now_iso()}")
    print(f"Database: {config.DB_PATH} ({existing_count} documents currently tracked)")

    if not config.SLACK_WEBHOOK_URL:
        print("WARNING: SLACK_WEBHOOK_URL not set in .env - Slack alerts disabled")
    else:
        print("Slack notifications: ENABLED")

    if is_first_run:
        print("First run detected -> seeding database; alerts will be quiet this round.\n")

    totals = {"new": 0, "updated": 0, "unchanged": 0}
    failed_projects = []

    # The Platts API requires these headers or it returns HTTP 400. Captured
    # from the registry frontend's own requests. The Appkey is a public,
    # frontend-embedded key (not a secret - it ships in the public site's JS).
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/126.0.0.0 Safari/537.36"
        ),
        "Accept": "application/json",
        "Accept-Language": "en-US,en;q=0.9",
        "Appkey": config.API_APPKEY,
        "Application": "Markit",
        "Language": "en",
        "Registry": "VERRA",
        "Standardacronym": "VCS",
        "Standardid": config.API_STANDARD_ID,
        "Origin": "https://registry.verra.org",
        "Referer": "https://registry.verra.org/",
    }

    # Markit and planvivo.org are plain public HTML; no special headers needed.
    markit_headers = {"User-Agent": headers["User-Agent"]}

    async with httpx.AsyncClient(headers=headers) as client, \
               httpx.AsyncClient(headers=markit_headers) as markit_client:
        for i, project in enumerate(config.PROJECTS):
            registry = project.get("registry", "verra")
            label = config.REGISTRY_LABELS.get(registry, registry)
            print(f"\n[{i + 1}/{len(config.PROJECTS)}] {project['name']} ({label} {project['id']})")

            if registry == "planvivo":
                docs = await scrape_planvivo_project(
                    markit_client, project,
                    config.PLANVIVO_URL_TEMPLATE,
                    config.MAX_RETRIES,
                    config.BASE_BACKOFF_S,
                )
            elif registry == "markit":
                docs = await scrape_markit_project(
                    markit_client, project,
                    config.MARKIT_URL_TEMPLATE,
                    config.MAX_RETRIES,
                    config.BASE_BACKOFF_S,
                )
            else:
                docs = await scrape_project(
                    client, project,
                    config.API_URL_TEMPLATE,
                    config.MAX_RETRIES,
                    config.BASE_BACKOFF_S,
                )

            # CRITICAL: a failed fetch (None) is NOT 'zero documents'. Skip it,
            # so we never delete/miss tracking for a project the API throttled.
            if docs is None:
                failed_projects.append(f"{label} {project['id']} ({project['name']})")
                if i < len(config.PROJECTS) - 1:
                    await asyncio.sleep(config.DELAY_BETWEEN_PROJECTS_S)
                continue

            # Seed quietly on the first ever run, AND whenever a project is newly
            # added to the watchlist (no docs tracked yet). This stops a new
            # project's whole history from flooding Slack.
            if is_first_run or db.project_doc_count(conn, project["id"]) == 0:
                for doc in docs:
                    if db.get_document(conn, doc["doc_key"]) is None:
                        db.insert_document(conn, doc)
                print(f"  Seeded {len(docs)} documents (new project, no alerts)")
            else:
                n, u, s = diff_and_alert(conn, docs, config.LOG_PATH,
                                         config.SLACK_WEBHOOK_URL, registry=label)
                totals["new"] += n
                totals["updated"] += u
                totals["unchanged"] += s

            if i < len(config.PROJECTS) - 1:
                await asyncio.sleep(config.DELAY_BETWEEN_PROJECTS_S)

    # Regenerate dashboard
    print("\nRegenerating dashboard...")
    dashboard_path = config.PROJECT_ROOT / "dashboard.html"
    doc_count = build_dashboard(config.DB_PATH, dashboard_path, config.PROJECTS)
    print(f"Dashboard updated: {dashboard_path} ({doc_count} documents)")

    print("\n" + "=" * 60)
    if is_first_run:
        print(f"Seeding complete. {db.total_docs(conn)} documents now tracked.")
    else:
        print(f"Run complete. New: {totals['new']} | "
              f"Updated: {totals['updated']} | Unchanged: {totals['unchanged']}")
        send_run_summary(
            webhook_url=config.SLACK_WEBHOOK_URL,
            new_count=totals["new"],
            updated_count=totals["updated"],
            total_tracked=db.total_docs(conn),
        )
    if failed_projects:
        print(f"\nWARNING: {len(failed_projects)} project(s) could not be fetched "
              f"(rate-limited or error) and were SKIPPED, not lost:")
        for fp in failed_projects:
            print(f"  - {fp}")
    print("=" * 60)

    conn.close()


if __name__ == "__main__":
    asyncio.run(main())