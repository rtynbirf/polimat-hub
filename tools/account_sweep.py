#!/usr/bin/env python3
"""account_sweep.py — обход всех репо аккаунта живым API: ветки, CI, topics, homepage.

Дополняет repo_inventory.py (тот хранит базу, этот — здоровье).
Только stdlib. Токен из GITHUB_TOKEN, в файлы не пишется.
Вывод: audit/sweep-YYYY-MM-DD.json + печать сводки косяков.
"""
import json
import os
import sys
import urllib.request
from datetime import date, datetime, timezone

sys.path.insert(0, os.path.dirname(__file__))
from gh_list import get_repos

API = "https://api.github.com"


def api(url: str, raw: bool = False):
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
        data = r.read()
        return data if raw else json.loads(data.decode("utf-8", "replace"))


def all_pages(url: str, limit: int = 3):
    out, page = [], 1
    while page <= limit:
        sep = "&" if "?" in url else "?"
        chunk = api(f"{url}{sep}per_page=100&page={page}")
        if not chunk:
            break
        out.extend(chunk)
        if len(chunk) < 100:
            break
        page += 1
    return out


def main() -> int:
    repos, _source = get_repos()
    sweep = {"collected_at": datetime.now(timezone.utc).isoformat(), "repos": []}
    problems = []
    for r in repos:
        full = r["full_name"]
        rec = {
            "name": full,
            "private": r["private"],
            "fork": r["fork"],
            "topics": r.get("topics", []),
            "homepage": r.get("homepage") or "",
            "description": r.get("description") or "",
            "pushed": r["pushed_at"],
            "branches": [],
            "last_run": None,
        }
        try:
            rec["branches"] = [b["name"] for b in all_pages(f"{API}/repos/{full}/branches")]
        except Exception as e:
            rec["branches_err"] = str(e)[:80]
        try:
            runs = api(f"{API}/repos/{full}/actions/runs?per_page=1")
            wr = runs.get("workflow_runs", [])
            if wr:
                rec["last_run"] = {
                    "name": wr[0]["name"],
                    "branch": wr[0]["head_branch"],
                    "conclusion": wr[0]["conclusion"],
                    "created": wr[0]["created_at"],
                }
        except Exception as e:
            rec["last_run_err"] = str(e)[:80]
        sweep["repos"].append(rec)

        if not r["private"]:
            if len(rec["topics"]) < 3:
                problems.append(f"TOPICS<3  {full}: {rec['topics']}")
            if not rec["homepage"]:
                problems.append(f"NO-HOME   {full}")
        lr = rec.get("last_run")
        if lr and lr["conclusion"] not in ("success", None):
            problems.append(f"CI-{lr['conclusion'].upper():<8} {full} [{lr['branch']}] «{lr['name'][:40]}» {lr['created']}")
        if rec.get("last_run_err"):
            problems.append(f"CI-ERR    {full}: {rec['last_run_err']}")

    out_dir = os.path.join(os.path.dirname(__file__), "..", "audit")
    os.makedirs(out_dir, exist_ok=True)
    suffix = sys.argv[1] if len(sys.argv) > 1 else ""
    out_path = os.path.join(out_dir, f"sweep-{date.today().isoformat()}{suffix}.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(sweep, f, ensure_ascii=False, indent=1)
    print(f"repos: {len(sweep['repos'])}  ->  {out_path}")
    print(f"problems: {len(problems)}")
    for p in problems:
        print(" ", p)
    return 0


if __name__ == "__main__":
    sys.exit(main())
