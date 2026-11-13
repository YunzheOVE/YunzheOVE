"""Refresh the auto-generated sections of the profile README.

Rewrites the text between these marker pairs in README.md:
  <!--START_SECTION:building-->  ...  <!--END_SECTION:building-->
  <!--START_SECTION:activity-->  ...  <!--END_SECTION:activity-->
  <!--START_SECTION:updated-->   ...  <!--END_SECTION:updated-->

Runs in GitHub Actions (see .github/workflows/profile.yml). Standard library only.
"""

import json
import os
import re
import urllib.request
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

USERNAME = os.environ.get("GH_USERNAME", "YunzheOVE")
README = "README.md"
SKIP = {USERNAME.lower(), f"{USERNAME.lower()}.github.io"}
HOW_MANY = 3


def get_json(url):
    req = urllib.request.Request(url, headers={"Accept": "application/vnd.github+json"})
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.load(resp)


def fetch_repos():
    return get_json(f"https://api.github.com/users/{USERNAME}/repos?sort=pushed&direction=desc&per_page=30")


def fetch_events():
    return get_json(f"https://api.github.com/users/{USERNAME}/events/public?per_page=100")


def time_ago(iso, now):
    seconds = (now - datetime.fromisoformat(iso.replace("Z", "+00:00"))).total_seconds()
    for unit, size in (("day", 86400), ("hour", 3600), ("minute", 60)):
        if seconds >= size:
            n = int(seconds // size)
            return f"{n} {unit}{'s' if n != 1 else ''} ago"
    return "just now"


def building_section(repos, now):
    own = [r for r in repos if not r["fork"] and not r["archived"] and r["name"].lower() not in SKIP]
    lines = []
    for r in own[:HOW_MANY]:
        desc = (r.get("description") or "").strip()
        parts = [f"**[{r['name']}]({r['html_url']})**"]
        if desc:
            parts.append(desc)
        meta = " · ".join(x for x in (f"`{r['language']}`" if r.get("language") else "", f"pushed {time_ago(r['pushed_at'], now)}") if x)
        lines.append(f"- {' — '.join(parts)}  \n  <sub>{meta}</sub>")
    return "\n".join(lines) or "- Nothing pushed recently."


def describe(event):
    """One readable line for a public event, or None to skip it."""
    kind, payload = event["type"], event.get("payload", {})
    repo = event["repo"]["name"]
    link = f"[{repo}](https://github.com/{repo})"
    if kind == "PushEvent":
        return f"Pushed to {link}"
    if kind == "CreateEvent" and payload.get("ref_type") == "repository":
        return f"Created {link}"
    if kind == "PullRequestEvent" and payload.get("action") in ("opened", "closed"):
        pr = payload.get("pull_request", {})
        verb = "Merged" if pr.get("merged") else payload["action"].capitalize()
        return f"{verb} a PR in {link}"
    if kind == "IssuesEvent" and payload.get("action") in ("opened", "closed"):
        return f"{payload['action'].capitalize()} an issue in {link}"
    if kind == "ReleaseEvent":
        return f"Released {payload.get('release', {}).get('tag_name', 'a new version')} of {link}"
    if kind == "WatchEvent":
        return f"Starred {link}"
    if kind == "ForkEvent":
        return f"Forked {link}"
    return None


def activity_section(events, now, limit=5):
    lines, seen = [], set()
    for e in events:
        text = describe(e)
        if not text or text in seen:  # collapse repeated pushes to the same repo
            continue
        seen.add(text)
        lines.append(f"{len(lines) + 1}. {text} <sub>· {time_ago(e['created_at'], now)}</sub>")
        if len(lines) == limit:
            break
    return "\n".join(lines) or "Nothing public in the last few weeks."


def replace_section(text, name, body):
    pattern = re.compile(rf"(<!--START_SECTION:{name}-->).*?(<!--END_SECTION:{name}-->)", re.S)
    if not pattern.search(text):
        raise SystemExit(f"Missing markers for section '{name}' in {README}")
    return pattern.sub(lambda m: f"{m.group(1)}\n{body}\n{m.group(2)}", text)


def main():
    now = datetime.now(timezone.utc)
    with open(README, encoding="utf-8") as f:
        text = f.read()
    text = replace_section(text, "building", building_section(fetch_repos(), now))
    text = replace_section(text, "activity", activity_section(fetch_events(), now))
    stamp = now.astimezone(ZoneInfo("America/New_York")).strftime("%b %-d, %Y")
    text = replace_section(text, "updated", f"<sub>Auto-updated daily by GitHub Actions · last run {stamp}</sub>")
    with open(README, "w", encoding="utf-8") as f:
        f.write(text)


if __name__ == "__main__":
    main()
