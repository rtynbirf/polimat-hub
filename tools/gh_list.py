#!/usr/bin/env python3
"""gh_list.py — единый обход репозиториев для инструментов hub.

Сначала /user/repos (пользовательский PAT). Если вернулось меньше 5 —
внутри Actions GITHUB_TOKEN это installation-токен: фоллбек на
/installation/repositories (СВЕДЕНИЯ О ДОМЕ: тот же API-объект репо).
Санити-щит: меньше 1 репо — исключение, честный отказ вместо пустой описи.
"""
import json
import os
import urllib.request

API = "https://api.github.com"


def _api(url: str):
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


def _page_all(url: str, limit: int = 5):
    out, page = [], 1
    while page <= limit:
        sep = "&" if "?" in url else "?"
        chunk = _api(f"{url}{sep}per_page=100&page={page}")
        if not chunk:
            break
        out.extend(chunk)
        if len(chunk) < 100:
            break
        page += 1
    return out


def get_repos():
    """Список репо аккаунта: пользовательский токен → installation-фоллбек."""
    try:
        repos = _page_all(f"{API}/user/repos?visibility=all&affiliation=owner&sort=pushed")
        if len(repos) >= 5:
            return repos, "user"
    except Exception:
        repos = []
    inst = _page_all(f"{API}/installation/repositories")
    if len(inst) < 1:
        raise SystemExit("СВЕДЕНИЯ О ДОМЕ: 0 репо ни пользователем, ни установкой — проверь токен")
    return inst, "installation"
