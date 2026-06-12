"""
Slack notifier for the registry monitor.

Sends one message per new or updated document to a Slack incoming webhook.
Uses Block Kit so messages are nicely formatted rather than raw text.

Failures are logged but never raised — a Slack outage should not break the
scraper. The DB still gets updated either way; the worst case is you miss
a notification but the data is correct.
"""

import httpx


def _build_block_message(
    project_name: str, section: str, title: str,
    date_updated: str, url: str, alert_type: str, change_note: str = "",
) -> dict:
    """Build a Slack Block Kit payload for one document alert."""
    if alert_type == "NEW":
        emoji = ":new:"
        header_text = "New document on Verra"
        color_accent = "good"
    else:
        emoji = ":pencil:"
        header_text = "Document updated on Verra"
        color_accent = "warning"

    fields = [
        {"type": "mrkdwn", "text": f"*Project*\n{project_name}"},
        {"type": "mrkdwn", "text": f"*Section*\n{section}"},
        {"type": "mrkdwn", "text": f"*Date on Verra*\n{date_updated}"},
    ]
    if change_note:
        fields.append({"type": "mrkdwn", "text": f"*What changed*\n{change_note}"})

    return {
        "text": f"{header_text}: {title} ({project_name})",
        "blocks": [
            {
                "type": "header",
                "text": {"type": "plain_text", "text": f"{emoji} {header_text}"},
            },
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": f"*<{url}|{title}>*"},
            },
            {"type": "section", "fields": fields},
            {"type": "divider"},
        ],
        "attachments": [{"color": color_accent, "blocks": []}],
    }


def send_slack_alert(
    webhook_url: str, project_name: str, section: str, title: str,
    date_updated: str, url: str, alert_type: str, change_note: str = "",
) -> bool:
    """
    Send one alert to Slack. Returns True on success, False on failure.
    Errors are printed to console but never raised.
    """
    if not webhook_url:
        return False

    payload = _build_block_message(
        project_name=project_name, section=section, title=title,
        date_updated=date_updated, url=url,
        alert_type=alert_type, change_note=change_note,
    )

    try:
        response = httpx.post(webhook_url, json=payload, timeout=10.0)
        response.raise_for_status()
        return True
    except httpx.HTTPError as e:
        print(f"  [Slack] Failed to send alert: {e}")
        return False


def send_run_summary(webhook_url: str, new_count: int, updated_count: int, total_tracked: int) -> bool:
    """Send a small summary message after the run completes."""
    if not webhook_url or (new_count == 0 and updated_count == 0):
        return False

    summary = f"_Run complete: {new_count} new, {updated_count} updated. {total_tracked} documents now tracked._"
    payload = {
        "text": summary,
        "blocks": [{"type": "context", "elements": [{"type": "mrkdwn", "text": summary}]}],
    }

    try:
        response = httpx.post(webhook_url, json=payload, timeout=10.0)
        response.raise_for_status()
        return True
    except httpx.HTTPError as e:
        print(f"  [Slack] Failed to send summary: {e}")
        return False
    