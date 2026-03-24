#!/usr/bin/env python3
"""Collect daily work status from GitHub PRs and Jira tickets,
and optionally post to a Slack thread."""

import json
import os
import re
import subprocess
import sys
from datetime import datetime, timedelta, timezone

import requests


# --- Config from environment ---
GITHUB_ORG = os.getenv("GITHUB_ORG", "ThriveMarket")
SLACK_CHANNEL_ID = os.getenv("SLACK_CHANNEL_ID", "")
SLACK_BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN", "")
SLACK_THREAD_KEYWORD = os.getenv("SLACK_THREAD_KEYWORD", "Daily Status Updates")
JIRA_BASE_URL = os.getenv("JIRA_BASE_URL", "")
JIRA_USER_EMAIL = os.getenv("JIRA_USER_EMAIL", "")
JIRA_API_TOKEN = os.getenv("JIRA_API_TOKEN", "")
LOOKBACK_HOURS = int(os.getenv("LOOKBACK_HOURS", "14"))


# ── GitHub ────────────────────────────────────────────────────────────────────

def search_prs(**extra_flags):
    """Search GitHub PRs using gh CLI."""
    cmd = [
        "gh", "search", "prs",
        "--owner", GITHUB_ORG,
        "--author", "@me",
        "--json", "title,url,repository,state,createdAt,updatedAt,number",
        "--limit", "100",
    ]
    for flag, value in extra_flags.items():
        cmd.extend([f"--{flag}", value])

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"Error: {result.stderr.strip()}", file=sys.stderr)
        sys.exit(1)
    return json.loads(result.stdout)


def get_recent_prs(since):
    """Get PRs created or updated since the given timestamp, excluding closed."""
    created = search_prs(created=f">={since}")
    updated = search_prs(updated=f">={since}")

    seen = set()
    prs = []
    for pr in created + updated:
        key = pr["url"]
        if key not in seen and pr["state"].upper() != "CLOSED":
            seen.add(key)
            prs.append(pr)
    return prs


# ── Jira ──────────────────────────────────────────────────────────────────────

def _jira_request(endpoint, params=None):
    """Make an authenticated Jira API request."""
    if not all([JIRA_BASE_URL, JIRA_USER_EMAIL, JIRA_API_TOKEN]):
        return None
    url = f"{JIRA_BASE_URL}{endpoint}"
    resp = requests.get(url, auth=(JIRA_USER_EMAIL, JIRA_API_TOKEN),
                        headers={"Accept": "application/json"}, params=params)
    if resp.status_code != 200:
        print(f"Jira error ({resp.status_code}): {endpoint}", file=sys.stderr)
        return None
    return resp.json()


def get_jira_issue(ticket_id):
    """Fetch a single Jira issue. Returns (summary, status, link) or Nones."""
    data = _jira_request(f"/rest/api/3/issue/{ticket_id}",
                         params={"fields": "summary,status"})
    if not data or "errorMessages" in data:
        return None, None, None
    summary = data["fields"]["summary"]
    status = data["fields"]["status"]["name"]
    link = f"{JIRA_BASE_URL}/browse/{ticket_id}"
    return summary, status, link


def search_jira_tickets(jql):
    """Search Jira by JQL. Returns dict {key: (summary, link)}."""
    data = _jira_request("/rest/api/3/search/jql",
                         params={"jql": jql, "fields": "summary,status"})
    if not data:
        return {}
    tickets = {}
    for issue in data.get("issues", []):
        key = issue["key"]
        summary = issue["fields"]["summary"]
        link = f"{JIRA_BASE_URL}/browse/{key}"
        tickets[key] = (summary, link)
    return tickets


def get_done_tickets(since):
    """Tickets moved to Done after `since` (format: YYYY-MM-DD HH:MM)."""
    jql = f'assignee = currentUser() AND status changed to Done after "{since}"'
    return search_jira_tickets(jql)


def get_in_progress_tickets():
    """Tickets currently In Progress assigned to the current user."""
    jql = 'assignee = currentUser() AND status = "In Progress"'
    return search_jira_tickets(jql)


# ── Ticket aggregation ────────────────────────────────────────────────────────

def tickets_from_prs(prs):
    """Extract ticket IDs from PR titles and fetch Jira data.
    Returns dict {ticket_id: (summary, link, status)}."""
    ticket_pattern = re.compile(r"\[?([A-Z]+-\d+)\]?")
    ticket_ids = set()
    for pr in prs:
        match = ticket_pattern.search(pr["title"])
        if match:
            ticket_ids.add(match.group(1))

    tickets = {}
    for tid in sorted(ticket_ids):
        summary, status, link = get_jira_issue(tid)
        if summary and link:
            s = "done" if status and status.lower() == "done" else "in_progress"
            tickets[tid] = (summary, link, s)
    return tickets


def tickets_from_jira(since):
    """Get In Progress + Done tickets from Jira.
    Returns dict {ticket_id: (summary, link, status)}."""
    tickets = {}
    for key, (summary, link) in get_in_progress_tickets().items():
        tickets[key] = (summary, link, "in_progress")
    for key, (summary, link) in get_done_tickets(since).items():
        if key not in tickets:
            tickets[key] = (summary, link, "done")
    return tickets


def merge_tickets(*ticket_dicts):
    """Merge ticket dicts, first occurrence wins."""
    merged = {}
    for d in ticket_dicts:
        for tid, data in d.items():
            if tid not in merged:
                merged[tid] = data
    return merged


# ── Slack ─────────────────────────────────────────────────────────────────────

def find_daily_thread():
    """Find the most recent matching thread in the Slack channel."""
    url = "https://slack.com/api/conversations.history"
    headers = {"Authorization": f"Bearer {SLACK_BOT_TOKEN}"}
    resp = requests.get(url, headers=headers,
                        params={"channel": SLACK_CHANNEL_ID, "limit": 50})
    resp.raise_for_status()
    data = resp.json()
    if not data.get("ok"):
        print(f"Slack error: {data.get('error')}", file=sys.stderr)
        return None
    for msg in data.get("messages", []):
        if SLACK_THREAD_KEYWORD in msg.get("text", ""):
            return msg["ts"]
    print("Could not find Daily Status Updates thread.", file=sys.stderr)
    return None


def post_thread_reply(thread_ts, message):
    """Post a threaded reply to the Slack channel."""
    url = "https://slack.com/api/chat.postMessage"
    headers = {"Authorization": f"Bearer {SLACK_BOT_TOKEN}",
               "Content-Type": "application/json"}
    resp = requests.post(url, headers=headers, json={
        "channel": SLACK_CHANNEL_ID,
        "thread_ts": thread_ts,
        "text": message,
    })
    resp.raise_for_status()
    result = resp.json()
    if not result.get("ok"):
        print(f"Slack post error: {result.get('error')}", file=sys.stderr)
        return False
    return True


# ── Output ────────────────────────────────────────────────────────────────────

def build_slack_message(tickets):
    """Build Slack-formatted status message with In Progress / Done sections."""
    in_progress = {k: v for k, v in tickets.items() if v[2] == "in_progress"}
    done = {k: v for k, v in tickets.items() if v[2] == "done"}

    lines = []
    if in_progress:
        lines.append("*In Progress:*")
        for tid in sorted(in_progress):
            summary, link, _ = in_progress[tid]
            lines.append(f"\u2022 <{link}|{tid}: {summary}>")
    if done:
        if lines:
            lines.append("")
        lines.append("*Done:*")
        for tid in sorted(done):
            summary, link, _ = done[tid]
            lines.append(f"\u2022 <{link}|{tid}: {summary}>")
    return "\n".join(lines)


def print_summary(prs, tickets):
    """Print human-readable summary to stdout."""
    if prs:
        print(f"PRs created/updated/merged in the last {LOOKBACK_HOURS} hours ({len(prs)} found):\n")
        for pr in prs:
            repo = pr["repository"]["name"]
            updated_at = datetime.fromisoformat(pr["updatedAt"].replace("Z", "+00:00"))
            age = datetime.now(timezone.utc) - updated_at
            h, m = int(age.total_seconds() // 3600), int((age.total_seconds() % 3600) // 60)
            print(f"  [{pr['state'].upper()}] {repo}#{pr['number']}: {pr['title']}")
            print(f"    {pr['url']}  (updated {h}h {m}m ago)")
            print()
    else:
        print(f"No PRs found in the last {LOOKBACK_HOURS} hours.\n")

    if tickets:
        in_progress = {k: v for k, v in tickets.items() if v[2] == "in_progress"}
        done = {k: v for k, v in tickets.items() if v[2] == "done"}
        if in_progress:
            print(f"In Progress ({len(in_progress)}):")
            for tid in sorted(in_progress):
                summary, link, _ = in_progress[tid]
                print(f"  {tid}: {summary}")
                print(f"    {link}")
        if done:
            print(f"Done ({len(done)}):")
            for tid in sorted(done):
                summary, link, _ = done[tid]
                print(f"  {tid}: {summary}")
                print(f"    {link}")
    else:
        print("No tickets found.")


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    post_to_slack = "--slack" in sys.argv
    since_gh = (datetime.now(timezone.utc) - timedelta(hours=LOOKBACK_HOURS)).strftime("%Y-%m-%dT%H:%M:%SZ")
    since_jira = (datetime.now(timezone.utc) - timedelta(hours=LOOKBACK_HOURS)).strftime("%Y-%m-%d %H:%M")

    prs = get_recent_prs(since_gh)
    pr_tickets = tickets_from_prs(prs)
    jira_tickets = tickets_from_jira(since_jira)
    all_tickets = merge_tickets(pr_tickets, jira_tickets)

    print_summary(prs, all_tickets)

    if post_to_slack:
        if not all_tickets:
            print("\nNo tickets found -- skipping Slack post.")
            return
        if not SLACK_BOT_TOKEN or not SLACK_CHANNEL_ID:
            print("\nError: SLACK_BOT_TOKEN and SLACK_CHANNEL_ID required", file=sys.stderr)
            sys.exit(1)

        print("\n--- Posting to Slack ---")
        thread_ts = find_daily_thread()
        if not thread_ts:
            sys.exit(1)

        message = build_slack_message(all_tickets)
        print(f"\nMessage preview:\n{message}\n")

        if post_thread_reply(thread_ts, message):
            print("Posted to Slack!")
        else:
            print("Failed to post update", file=sys.stderr)
            sys.exit(1)


if __name__ == "__main__":
    main()
