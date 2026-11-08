#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""pulse_heart.py — Единое Сердце дома rtynbirf.

Один обход всех репозиториев вместо дублирующих ботов в каждом репо.
Пишет PULSE.md (человекочитаемо) и audit/pulse-<дата>.json (машиночитаемо).
Правила: stdlib-only; UNKNOWN ≠ FALSE; красные — в раздел РАНЫ.

Запуск: GITHUB_TOKEN=... python3 tools/pulse_heart.py
"""
import base64
import json
import os
import subprocess
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

API = "https://api.github.com"
ROOT = Path(__file__).resolve().parent.parent
TOKEN = os.environ.get("GITHUB_TOKEN", "")
H = {"Authorization": f"Bearer {TOKEN}", "Accept": "application/vnd.github+json",
     "User-Agent": "polimat-heart"}
TODAY = datetime.now(timezone.utc).strftime("%Y-%m-%d")

def api(url):
    req = urllib.request.Request(url, headers=H)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            b = r.read().decode()
            return json.loads(b) if b else {}
    except Exception as e:
        return {"__err": str(e)}

def api_ret(url):
    """как api, но возвращает (данные, статус) — для диагностики слепоты."""
    req = urllib.request.Request(url, headers=H)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            b = r.read().decode()
            return (json.loads(b) if b else {}), r.status
    except Exception as e:
        return {"__err": str(e)}, 0

def main():
    if not TOKEN:
        sys.exit("НЕТ ТОКЕНА — сердце не бьётся вслепую (UNKNOWN ≠ FALSE)")
    repos = []
    page = 1
    while True:
        batch = api(f"{API}/user/repos?visibility=all&affiliation=owner&sort=pushed&per_page=100&page={page}")
        if not isinstance(batch, list) or not batch:
            break
        repos.extend(batch)
        page += 1
    # Источник 2: installation-репо (GITHUB_TOKEN в Actions — не пользовательский).
    diag = {"user": len(repos)}
    page = 1
    while True:
        batch, st = api_ret(f"{API}/installation/repositories?per_page=100&page={page}")
        diag[f"installation_p{page}"] = f"st={st}"
        if not isinstance(batch, dict) or not batch.get("repositories"):
            break
        for item in batch["repositories"]:
            if item.get("id") not in {r.get("id") for r in repos}:
                repos.append(item)
        page += 1
    # Источник 3: локальные снимки инвентаря в audit/ — дом помнит сам себя.
    snap_names = []
    for p in sorted((ROOT / "audit").glob("*.json")):
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            continue
        items = data.get("repos") if isinstance(data, dict) else (data if isinstance(data, list) else [])
        for it in items or []:
            fn = (it.get("full_name") or "").split("/")
            if len(fn) == 2 and fn[0].lower() == "rtynbirf":
                snap_names.append(fn[1])
    diag["snapshots"] = len(set(snap_names))
    known = {r.get("name") for r in repos}
    for nm in sorted(set(snap_names)):
        if nm not in known:
            fresh = api(f"{API}/repos/rtynbirf/{nm}")
            if isinstance(fresh, dict) and fresh.get("name"):
                repos.append(fresh)
    if len(repos) < 5:
        sys.exit(f"СЕРДЦЕ СЛЕПО: user={diag} — пишу отказ, не пустой пульс (UNKNOWN ≠ FALSE)")
    print(f"ДИАГНОСТИКА обхода: {diag}")
    rows, wounds, total_pr = [], [], 0
    for r in repos:
        full = r["full_name"]
        name = r["name"]
        runs = api(f"{API}/repos/{full}/actions/runs?per_page=1")
        lr = {}
        wr = runs.get("workflow_runs") or []
        if wr:
            lr = {"workflow": wr[0]["name"], "status": wr[0]["status"],
                  "conclusion": wr[0]["conclusion"], "date": wr[0]["created_at"][:10]}
        prs = api(f"{API}/repos/{full}/pulls?state=open&per_page=100")
        n_pr = len(prs) if isinstance(prs, list) else 0
        total_pr += n_pr
        brs = api(f"{API}/repos/{full}/branches?per_page=100")
        n_br = len(brs) if isinstance(brs, list) else 0
        ci = lr.get("conclusion") or "none"
        if ci == "failure":
            wounds.append(f"{name} ({lr.get('workflow', '?')} {lr.get('date', '?')})")
        rows.append({
            "repo": name, "private": r["private"], "size_kb": r["size"],
            "pushed_at": (r.get("pushed_at") or "")[:10], "branches": n_br,
            "open_prs": n_pr, "ci": ci, "ci_workflow": lr.get("workflow", ""),
        })
    rows.sort(key=lambda x: -x["size_kb"])
    heavy = [x for x in rows if x["size_kb"] > 512000]
    n_pub = sum(1 for x in rows if not x["private"])
    lines = [
        f"# PULSE · {TODAY}",
        "",
        "> Сгенерировано Единым Сердцем (tools/pulse_heart.py). Числа из API, не руками.",
        "",
        f"- Репозиториев: **{len(rows)}** (публичных {n_pub}, приватных {len(rows) - n_pub})",
        f"- Открытых PR: **{total_pr}**",
        f"- РАНЫ (красные CI): **{len(wounds)}** — {', '.join(wounds) if wounds else 'нет'}",
        f"- Тяжеловесы >512 МБ: **{len(heavy)}** — {', '.join(x['repo'] + ' (' + str(x['size_kb'] // 1024) + ' МБ)' for x in heavy) if heavy else 'нет'}",
        "",
        "| Репо | Т | Ветки | PR | CI | Вес КБ | Пуш |",
        "|---|---|---|---|---|---|---|",
    ]
    for x in rows:
        ci_badge = {"success": "✅", "failure": "🔴", "none": "—"}.get(x["ci"], x["ci"])
        lines.append(f"| {x['repo']} | {'прив' if x['private'] else 'пуб'} | {x['branches']} | {x['open_prs']} | {ci_badge} {x['ci_workflow'][:24]} | {x['size_kb']} | {x['pushed_at']} |")
    pulse = "\n".join(lines) + "\n"
    (ROOT / "PULSE.md").write_text(pulse, encoding="utf-8")
    (ROOT / "audit" / f"pulse-{TODAY}.json").write_text(
        json.dumps({"date": TODAY, "repos": rows, "wounds": wounds, "open_prs_total": total_pr},
                   ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"СЕРДЦЕ БИЛОСЬ: {len(rows)} репо, ран {len(wounds)}, PR {total_pr}. PULSE.md обновлён.")

if __name__ == "__main__":
    main()
