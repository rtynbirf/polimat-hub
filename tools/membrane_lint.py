#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Мембрана как исполняемый договор (П-73, polimat-hub#97).

Линт проверяет машину договорённостей роя: у каждого публичного репо rtynbirf
на ветке по умолчанию присутствуют README.md, AGENTS.md, llms.txt; в AGENTS.md
есть секция запретов (маркер Never или «Никогда»); llms.txt ссылается на
AGENTS.md и PULSE.

Шкала вердиктов (честно, по фактам наличия):
  ✅ — все три файла на месте И в AGENTS.md есть Never/«Никогда»
       И llms.txt упоминает AGENTS.md и PULSE;
  🟡 — мембрана частичная: два из трёх файлов, либо три, но без части маркеров;
  ⬜ — мембраны нет: ноль или один файл из трёх.

Гейт для CI: exit 1, если хотя бы одно репо ⬜ (нет мембраны) или не
проверилось из-за ошибки API; --strict краснит также 🟡.
Вывод: JSON (--json FILE) + таблица соответствия в stdout (колонка «вердикт»).

Только stdlib. Токен из env GITHUB_TOKEN/GH_TOKEN; без токена живой обход —
exit 2. --selftest работает без сети на встроенных синтетических данных.
"""

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone

OWNER = "rtynbirf"
API_ROOT = "https://api.github.com"
PER_PAGE = 100

MEMBRANE_FILES = ("README.md", "AGENTS.md", "llms.txt")
NEVER_MARKERS = ("Never", "Никогда")
LLMS_MUST_MENTION = ("AGENTS.md", "PULSE")


def utc_now_iso():
    """Текущий момент в UTC (ISO-8601, Z)."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def take_token():
    """Токен из env: GITHUB_TOKEN или GH_TOKEN (None, если нет)."""
    return os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")


def membrane_verdict(readme_present, agents_present, llms_present,
                     agents_text, llms_text):
    """Чистая функция вердикта мембраны (используется и в живом обходе, и в selftest).

    agents_text/llms_text — содержимое файлов или None, если файла нет.
    Возвращает (вердикт, детали-словарь с булевыми фактами).
    """
    details = {
        "readme": bool(readme_present),
        "agents": bool(agents_present),
        "llms": bool(llms_present),
        "agents_never": False,
        "llms_agents": False,
        "llms_pulse": False,
    }
    present_count = sum(1 for flag in (details["readme"], details["agents"],
                                       details["llms"]) if flag)
    if agents_text:
        details["agents_never"] = any(m in agents_text for m in NEVER_MARKERS)
    if llms_text:
        details["llms_agents"] = LLMS_MUST_MENTION[0] in llms_text
        details["llms_pulse"] = LLMS_MUST_MENTION[1] in llms_text

    if present_count <= 1:
        verdict = "⬜"
    elif (present_count == 3 and details["agents_never"]
          and details["llms_agents"] and details["llms_pulse"]):
        verdict = "✅"
    else:
        verdict = "🟡"
    return verdict, details


def api_get(token, url, raw=False):
    """GET к GitHub API; для raw=True — сырой текст (Accept raw). 404 → None."""
    req = urllib.request.Request(url, method="GET")
    if token:
        req.add_header("Authorization", "Bearer %s" % token)
    req.add_header("Accept", "application/vnd.github.raw" if raw
                   else "application/vnd.github+json")
    req.add_header("User-Agent", "polimat-hub-membrane-lint")
    try:
        with urllib.request.urlopen(req) as resp:
            body = resp.read()
            return body.decode("utf-8", errors="replace") if raw \
                else json.loads(body.decode("utf-8"))
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return None
        raise  # сетевые/квотовые ошибки пусть поднимаются — честный статус error
    except urllib.error.URLError as exc:
        raise RuntimeError("сеть недоступна: %s" % exc)


def list_all_repos(token):
    """Пагинация /users/rtynbirf/repos?per_page=100 → [{name, default_branch}]."""
    repos = []
    page = 1
    while True:
        batch = api_get(
            token,
            "%s/user/repos?type=owner&per_page=%d&page=%d" % (API_ROOT, PER_PAGE, page),
        )
        if not batch:
            break
        for item in batch:
            repos.append({
                "name": item.get("name", ""),
                "default_branch": item.get("default_branch", "main"),
            })
        if len(batch) < PER_PAGE:
            break
        page += 1
    return repos


def check_repo(token, name, ref):
    """Проверка мембраны одного репо. Возвращает запись для отчёта."""
    entry = {"repo": name, "verdict": "⬜", "error": None,
             "readme": False, "agents": False, "llms": False,
             "agents_never": False, "llms_agents": False, "llms_pulse": False}
    try:
        tree = api_get(token, "%s/repos/%s/%s/git/trees/%s" % (API_ROOT, OWNER, name, ref))
        if tree is None:
            entry["error"] = "дерево %s не получено (404)" % ref
            return entry
        root_paths = {item.get("path", "") for item in tree.get("tree", [])}
        readme_present = "README.md" in root_paths
        agents_present = "AGENTS.md" in root_paths
        llms_present = "llms.txt" in root_paths

        agents_text = None
        if agents_present:
            agents_text = api_get(
                token,
                "%s/repos/%s/%s/contents/AGENTS.md?ref=%s" % (API_ROOT, OWNER, name, ref),
                raw=True,
            )
        llms_text = None
        if llms_present:
            llms_text = api_get(
                token,
                "%s/repos/%s/%s/contents/llms.txt?ref=%s" % (API_ROOT, OWNER, name, ref),
                raw=True,
            )

        verdict, details = membrane_verdict(
            readme_present, agents_present, llms_present, agents_text, llms_text
        )
        entry.update(details)
        entry["verdict"] = verdict
        return entry
    except (urllib.error.HTTPError, RuntimeError) as exc:
        entry["error"] = "API: %s" % exc
        return entry


def build_report(generated, entries):
    """Итоговый JSON-отчёт линта (числа считаются, не декларируются)."""
    counts = {"ok": 0, "partial": 0, "absent": 0, "error": 0}
    for e in entries:
        if e.get("error"):
            counts["error"] += 1
        elif e["verdict"] == "✅":
            counts["ok"] += 1
        elif e["verdict"] == "🟡":
            counts["partial"] += 1
        else:
            counts["absent"] += 1
    return {
        "generated": generated,
        "owner": OWNER,
        "repos_scanned": len(entries),
        "counts": counts,
        "repos": entries,
    }


def render_markdown(report):
    """Таблица соответствия с колонкой вердикт ✅/🟡/⬜ (для stdout и step summary)."""
    marks = {True: "✅", False: "⬜"}
    lines = []
    counts = report["counts"]
    lines.append("## Мембрана README/AGENTS/llms · %s" % report["generated"])
    lines.append("")
    lines.append("Репо просмотрено: **%d** · ✅ %d · 🟡 %d · ⬜ %d · ошибок %d"
                 % (report["repos_scanned"], counts["ok"], counts["partial"],
                    counts["absent"], counts["error"]))
    lines.append("")
    lines.append("| репо | README.md | AGENTS.md | llms.txt | Never/Никогда "
                 "| llms→AGENTS.md | llms→PULSE | вердикт |")
    lines.append("|---|---|---|---|---|---|---|---|")
    for e in report["repos"]:
        lines.append("| `%s` | %s | %s | %s | %s | %s | %s | %s |" % (
            e["repo"],
            marks[e["readme"]], marks[e["agents"]], marks[e["llms"]],
            marks[e["agents_never"]], marks[e["llms_agents"]], marks[e["llms_pulse"]],
            "ошибка: %s" % e["error"] if e.get("error") else e["verdict"],
        ))
    lines.append("")
    lines.append("Шкала: ✅ полная мембрана · 🟡 частичная · ⬜ мембраны нет "
                 "(гейт краснеет на ⬜, с --strict и на 🟡).")
    return "\n".join(lines) + "\n"


def selftest():
    """Самопроверка без сети: синтетические репо на чистой функции вердикта."""
    # альфа: полная мембрана
    verdict, details = membrane_verdict(
        True, True, True,
        "## 4. Границы\n- Never: не ходить в сеть из самопроверок.\n",
        "Контракт репо: AGENTS.md и PULSE.md в polimat-hub.\n",
    )
    assert verdict == "✅", "полная мембрана оценена неверно: %s" % verdict
    assert details["agents_never"] and details["llms_agents"] and details["llms_pulse"]

    # бета: три файла, но в AGENTS.md нет запретов
    verdict, _ = membrane_verdict(True, True, True, "нет границы запретов тут",
                                  "см. AGENTS.md и PULSE")
    assert verdict == "🟡", "пропаганда без Never должна быть 🟡: %s" % verdict

    # гамма: только README — мембраны нет
    verdict, _ = membrane_verdict(True, False, False, None, None)
    assert verdict == "⬜", "голый README должен быть ⬜: %s" % verdict

    # дельта: README + llms.txt без AGENTS.md
    verdict, _ = membrane_verdict(True, False, True, None, "AGENTS.md и PULSE")
    assert verdict == "🟡", "два из трёх файлов должны быть 🟡: %s" % verdict

    # эпсилон: три файла, но llms.txt не упоминает PULSE
    verdict, details = membrane_verdict(True, True, True, "Never ничего не ломать",
                                        "см. AGENTS.md")
    assert verdict == "🟡" and details["llms_pulse"] is False, \
        "llms.txt без PULSE должен быть 🟡: %s" % verdict

    # отчёт и таблица: колонка вердикт присутствует, числа сходятся
    entries = [
        {"repo": "alpha", "verdict": "✅", "error": None, "readme": True,
         "agents": True, "llms": True, "agents_never": True,
         "llms_agents": True, "llms_pulse": True},
        {"repo": "gamma", "verdict": "⬜", "error": None, "readme": True,
         "agents": False, "llms": False, "agents_never": False,
         "llms_agents": False, "llms_pulse": False},
    ]
    report = build_report(utc_now_iso(), entries)
    assert report["counts"] == {"ok": 1, "partial": 0, "absent": 1, "error": 0}
    md = render_markdown(report)
    assert "| вердикт |" in md and "⬜" in md and "🟡" in md, \
        "таблица без колонки вердикт или шкалы"

    print("SELFTEST OK")


def main():
    parser = argparse.ArgumentParser(
        description="Линт мембраны README/AGENTS/llms по всем репо роя (П-73)"
    )
    parser.add_argument("--all", action="store_true",
                        help="обойти все репо роя (поведение по умолчанию)")
    parser.add_argument("--repos", metavar="R1,R2", default=None,
                        help="ограничить обход списком имён")
    parser.add_argument("--json", dest="json_path", metavar="FILE", default=None,
                        help="куда записать JSON-отчёт")
    parser.add_argument("--strict", action="store_true",
                        help="красить также 🟡 (частичную мембрану)")
    parser.add_argument("--selftest", action="store_true",
                        help="самопроверка без сети")
    args = parser.parse_args()

    if args.selftest:
        selftest()
        return

    token = take_token()
    if not token:
        sys.stderr.write("ЖИВОЙ ЛИНТ НЕВОЗМОЖЕН: нет токена в env "
                         "GITHUB_TOKEN/GH_TOKEN (exit 2)\n")
        raise SystemExit(2)

    repos = list_all_repos(token)
    if args.repos:
        wanted = {x.strip() for x in args.repos.split(",")}
        repos = [r for r in repos if r["name"] in wanted]

    entries = [check_repo(token, r["name"], r["default_branch"]) for r in repos]
    report = build_report(utc_now_iso(), entries)

    if args.json_path:
        with open(args.json_path, "w", encoding="utf-8") as fh:
            json.dump(report, fh, ensure_ascii=False, indent=2)
        sys.stderr.write("JSON-отчёт: %s (%d байт)\n"
                         % (args.json_path, os.path.getsize(args.json_path)))

    sys.stdout.write(render_markdown(report))

    counts = report["counts"]
    if counts["absent"] or counts["error"]:
        sys.stderr.write("ГАЙТ: ⬜ без мембраны — %d, ошибок проверки — %d\n"
                         % (counts["absent"], counts["error"]))
        raise SystemExit(1)
    if args.strict and counts["partial"]:
        sys.stderr.write("ГАЙТ (--strict): 🟡 частичная мембрана — %d\n"
                         % counts["partial"])
        raise SystemExit(1)
    raise SystemExit(0)


if __name__ == "__main__":
    main()
