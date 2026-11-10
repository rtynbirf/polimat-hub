#!/usr/bin/env python3
"""Применить ruleset как код к целевому репозиторию GitHub.

П-31 / W-AUD-15 (polimat-hub#49, #16): polimat-guard тиражируется из
эталона rulesets/polimat-guard.json. Поле source заменяется на целевое
репо; id/node_id/created_at/updated_at/_links вырезаются (не нужны в POST).

Использование:
    GITHUB_TOKEN=ghp_... python3 apply_ruleset.py rtynbirf/<repo> \
        [--file polimat-guard.json] [--dry-run]

Токен берётся из env GITHUB_TOKEN (или GH_TOKEN). Нужен классический PAT
со scope repo, либо fine-grained с Administration:write — иначе POST
вернёт 403 "Resource not accessible by personal access token".

Печатает HTTP-код ответа API по каждому репо: 201 = создан,
422 = уже существует/ошибка валидации, 403 = нет прав.
"""
import argparse
import json
import os
import sys
import urllib.error
import urllib.request

API = "https://api.github.com"
STRIP_KEYS = ("id", "node_id", "created_at", "updated_at", "_links",
              "current_user_can_bypass")
PLACEHOLDER = "__REPO_FULL_NAME__"


def load_ruleset(path: str, repo: str) -> dict:
    with open(path, encoding="utf-8") as fh:
        body = json.load(fh)
    for key in STRIP_KEYS:
        body.pop(key, None)
    if body.get("source", "").startswith(PLACEHOLDER) or PLACEHOLDER in body.get("source", ""):
        body["source"] = repo
    else:
        body["source"] = repo  # source всегда указывает на целевое репо
    return body


def post_ruleset(repo: str, body: dict, token: str) -> tuple:
    req = urllib.request.Request(
        f"{API}/repos/{repo}/rulesets",
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "User-Agent": "polimat-hub-apply-ruleset",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req) as resp:
            data = json.load(resp)
            return resp.status, {"id": data.get("id"), "name": data.get("name"),
                                 "enforcement": data.get("enforcement"),
                                 "source": data.get("source")}
    except urllib.error.HTTPError as exc:
        try:
            return exc.code, json.loads(exc.read().decode("utf-8"))
        except Exception:
            return exc.code, {}


def main() -> int:
    ap = argparse.ArgumentParser(description="POST ruleset на целевое репо")
    ap.add_argument("repos", nargs="+", help="целевые репо: owner/name ...")
    ap.add_argument("--file", default=os.path.join(os.path.dirname(__file__), "polimat-guard.json"))
    ap.add_argument("--dry-run", action="store_true", help="показать тело POST без отправки")
    args = ap.parse_args()

    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if not token and not args.dry_run:
        print("ОШИБКА: GITHUB_TOKEN (или GH_TOKEN) не задан в окружении", file=sys.stderr)
        return 2

    results = []
    for repo in args.repos:
        body = load_ruleset(args.file, repo)
        if args.dry_run:
            print(f"[dry-run] {repo} <- {args.file}")
            print(json.dumps(body, indent=2, ensure_ascii=False))
            continue
        code, payload = post_ruleset(repo, body, token)
        mark = "OK" if code == 201 else ("SKIP/ERR" if code in (403, 422) else "ERR")
        print(f"{repo}: {code} {mark} :: {json.dumps(payload, ensure_ascii=False)[:300]}")
        results.append((repo, code))

    codes = {code for _, code in results}
    return 0 if codes <= {201, 422} else 1


if __name__ == "__main__":
    sys.exit(main())
