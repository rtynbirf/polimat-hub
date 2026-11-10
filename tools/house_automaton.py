#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""house_automaton.py — машина дома: детектор висящих переходов (раунд 14).

Закон дома №23 (repo-doctrine/23-ритуал-дома-конечный-автомат): каждая
работа — конечный автомат ВЗЯЛ→СДЕЛАЛ→УБРАЛ→ДОМ_ЧИСТ (или честный ПЕРЕДАЛ).
Ни одно состояние не висит. Этот скрипт — исполнительный гейг закона:

  Сенсор 1 · Notifications: каждое живое notification = висящий переход.
             Режим --clean размечает потоки done (PUT threads/{id} —
             официальный API «Marks a thread as done»).
  Сенсор 2 · Красные CI: последний прогон на default-ветке каждого репо;
             красный свежее 72 часов = долг дома.
  Сенсор 3 · Открытые карты: открытые issues ×51 (живые карты роя).

Вердикт: ДОМ ЧИСТ (notifications 0 · свежих красных 0) или список долгов.
Выход: JSON (--json) + строка-свод в ПУЛЬС (--pulse FILE).
Токен только из env. Только stdlib.
"""
import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone

OWNER = "rtynbirf"
GH = "https://api.github.com"
FRESH_HOURS = 72


def api(url, tok, method="GET", payload=None):
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers={
        "Authorization": f"Bearer {tok}",
        "Accept": "application/vnd.github+json",
        "User-Agent": "polimat-house-automaton"})
    try:
        with urllib.request.urlopen(req) as r:
            body = r.read().decode()
            return r.status, (json.loads(body) if body else {})
    except Exception as e:  # noqa: BLE001 — честный счётчик провалов
        return None, {"__error__": str(e)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", dest="json_out", required=True)
    ap.add_argument("--pulse", dest="pulse_out", default=None)
    ap.add_argument("--env", dest="env_var", default="GITHUB_TOKEN")
    ap.add_argument("--repos", default=None, help="JSON-файл списка репо (GET /user/repos срез)")
    ap.add_argument("--clean", action="store_true",
                    help="УБРАТЬ: разметить все notifications done (действие, не отчёт)")
    a = ap.parse_args()

    tok = os.environ.get(a.env_var, "")
    if not tok:
        print(f"НЕТ ТОКЕНА в env {a.env_var} — отмена (токены только env).", file=sys.stderr)
        sys.exit(1)
    now = datetime.now(timezone.utc)

    # Сенсор 1 · Notifications
    st, notifs = api(f"{GH}/notifications?per_page=100", tok)
    threads = notifs if isinstance(notifs, list) else []
    cleaned = 0
    if a.clean:
        for t in threads:
            st2, _ = api(f"{GH}/notifications/threads/{t['id']}", tok, method="PUT")
            if st2 == 205 or st2 == 204 or st2 == 200:
                cleaned += 1
        st3, after = api(f"{GH}/notifications?per_page=100", tok)
        threads_after = after if isinstance(after, list) else []
    else:
        threads_after = threads

    # Сенсор 2 · Красные CI (последний прогон на default-ветке)
    if a.repos:
        names = [r["name"] for r in json.load(open(a.repos, encoding="utf-8"))]
    else:
        _, rj = api(f"{GH}/users/{OWNER}/repos?per_page=100", tok)
        names = [r["name"] for r in rj] if isinstance(rj, list) else []
    red, ci_ok, ci_err, ci_skip = [], 0, 0, 0
    for name in names:
        _, repo = api(f"{GH}/repos/{OWNER}/{name}", tok)
        if "__error__" in repo:
            ci_err += 1
            continue
        br = repo.get("default_branch", "main")
        st, runs = api(f"{GH}/repos/{OWNER}/{name}/actions/runs?branch={br}&per_page=1", tok)
        wfs = runs.get("workflow_runs", []) if isinstance(runs, dict) else []
        if not wfs:
            ci_skip += 1  # нет Actions — не долг
            continue
        r = wfs[0]
        created = datetime.fromisoformat(r["created_at"].replace("Z", "+00:00"))
        fresh = (now - created) < timedelta(hours=FRESH_HOURS)
        if r["conclusion"] == "failure":
            if fresh:
                red.append({"repo": name, "run": r["id"], "workflow": r["name"],
                            "created_at": r["created_at"], "url": r["html_url"]})
        elif r["conclusion"] == "success":
            ci_ok += 1

    # Сенсор 3 · Открытые карты (per-repo GET — search-индекс отстаёт, Я-24)
    cards = {}
    for name in names:
        st, q = api(f"{GH}/repos/{OWNER}/{name}/issues?state=open&per_page=100", tok)
        if isinstance(q, list):
            n = len([i for i in q if "pull_request" not in i])
            if n:
                cards[name] = n
    open_total = sum(cards.values())
    report = {
        "generated": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "tool": "tools/house_automaton.py · раунд 14 · закон дома №23",
        "automaton": "ВЗЯЛ→СДЕЛАЛ→УБРАЛ→ДОМ_ЧИСТ (| честный ПЕРЕДАЛ)",
        "notifications_before": len(threads),
        "notifications_marked_done": cleaned,
        "notifications_after": len(threads_after),
        "repos_checked": len(names),
        "ci_success_latest": ci_ok,
        "ci_no_actions": ci_skip,
        "ci_errors": ci_err,
        "red_ci_fresh_72h": red,
        "open_issue_cards": open_total,
        "open_cards_by_repo": cards,
    }
    with open(a.json_out, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=1)

    verdict = "ДОМ ЧИСТ" if (len(threads_after) == 0 and not red) else "ДОЛГИ ДОМА"
    line = (f"Дом-автомат ×{len(names)} репо: notifications {len(threads_after)} "
            f"(до {len(threads)}, done {cleaned}) · свежих красных CI {len(red)}"
            f"{' — ' + ','.join(r['repo'] for r in red) if red else ''}"
            f" · открытых карт {open_total} · вердикт: {verdict} · {report['generated']}")
    if a.pulse_out:
        with open(a.pulse_out, "a", encoding="utf-8") as f:
            f.write("- " + line + "\n")
    print(line)
    sys.exit(0 if verdict == "ДОМ ЧИСТ" else 2)


if __name__ == "__main__":
    main()
