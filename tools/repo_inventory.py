#!/usr/bin/env python3
"""repo_inventory.py — полная опись аккаунта GitHub: API → JSON.

Только stdlib. Токен берётся из GITHUB_TOKEN, в файлы не пишется.
Вывод: audit/inventory-YYYY-MM-DD.json
"""
import json
import os
import sys
import urllib.request
from datetime import date

API = "https://api.github.com"


def api(url: str):
    token = os.environ["GITHUB_TOKEN"]
    req = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "User-Agent": "polimat-hub",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode("utf-8", "replace"))


def main() -> int:
    me = api(f"{API}/user")
    repos = api(f"{API}/user/repos?visibility=all&affiliation=owner&per_page=100&sort=pushed")
    inventory = {
        "collected_at": date.today().isoformat(),
        "account": {
            "login": me.get("login"),
            "created": me.get("created_at"),
            "followers": me.get("followers"),
        },
        "repos": [
            {
                "name": r["name"],
                "private": r["private"],
                "fork": r["fork"],
                "language": r["language"],
                "size_kb": r["size"],
                "stars": r["stargazers_count"],
                "open_issues": r["open_issues_count"],
                "created": r["created_at"][:10],
                "pushed": r["pushed_at"][:10],
                "archived": r["archived"],
                "description": r["description"],
            }
            for r in repos
        ],
    }
    out_dir = os.path.join(os.path.dirname(__file__), "..", "audit")
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, f"inventory-{date.today().isoformat()}.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(inventory, f, ensure_ascii=False, indent=1)
    print(f"repos: {len(inventory['repos'])}  ->  {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
