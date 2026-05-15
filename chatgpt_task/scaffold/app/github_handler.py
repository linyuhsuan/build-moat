"""GitHub PR fetcher — calls GitHub Search API to find PRs assigned to the user."""

import os
from datetime import UTC, datetime

import requests
from dotenv import load_dotenv

load_dotenv()


def fetch_prs_assigned_to_me(
    token: str | None = None,
    username: str | None = None,
) -> str:
    """Fetch open PRs assigned to `username` and return a formatted text summary.

    Reads GITHUB_TOKEN and GITHUB_USERNAME from environment / .env if not passed.
    Raises RuntimeError on missing credentials or API failure.
    """
    token = token or os.getenv("GITHUB_TOKEN")
    username = username or os.getenv("GITHUB_USERNAME")

    if not token:
        raise RuntimeError("GITHUB_TOKEN not set in environment or .env")
    if not username:
        raise RuntimeError("GITHUB_USERNAME not set in environment or .env")

    resp = requests.get(
        "https://api.github.com/search/issues",
        params={"q": f"is:pr is:open assignee:{username}", "per_page": 50},
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        },
        timeout=30,
    )

    if resp.status_code == 401:
        raise RuntimeError("GitHub API 401 — check GITHUB_TOKEN")
    if resp.status_code != 200:
        raise RuntimeError(f"GitHub API error {resp.status_code}: {resp.text[:200]}")

    items = resp.json().get("items", [])
    ts = datetime.now(UTC).replace(tzinfo=None).strftime("%Y-%m-%dT%H:%M:%SZ")

    if not items:
        return f"[{ts}] No open PRs assigned to {username}."

    lines = [f"[{ts}] Open PRs assigned to {username}: {len(items)} found\n"]
    for pr in items:
        repo = pr.get("repository_url", "").replace("https://api.github.com/repos/", "")
        lines.append(
            f"- [{repo}] #{pr['number']} {pr['title']}\n"
            f"  URL: {pr['html_url']}\n"
            f"  Updated: {pr['updated_at']}"
        )
    return "\n".join(lines)
