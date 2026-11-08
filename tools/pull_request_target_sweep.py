#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Гейт pull_request_target (П-72, polimat-hub#96).

Обходит все публичные репо rtynbirf (пагинация /users/rtynbirf/repos?per_page=100),
для каждого листает .github/workflows на ветке по умолчанию
(GET /repos/{o}/{r}/contents/.github/workflows?ref=<default>), тянет каждый
.yml/.yaml по download_url и собирает:

  1. где встречается `pull_request_target` (строка и контекст строки);
  2. какие триггеры объявлены в `on:` (по-честному: без yaml-библиотеки,
     только stdlib, поэтому разбор блока `on:` — построчная эвристика);
  3. битые фильтры веток вида `branches: ain]` (известный косяк шаблона роя);
  4. воркфлоу без `workflow_dispatch`.

Вывод: JSON (--json FILE) + markdown-дайджест в stdout.
Гейт: с --allowlist FILE каждое найденное pull_request_target сверяется
с белым списком осознанных записей (repo+path); кто вне списка — exit 1.

Только stdlib. Токен из env GITHUB_TOKEN/GH_TOKEN; без токена живой обход
невозможен — exit 2. --selftest работает без сети и без токена.
"""

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone

OWNER = "rtynbirf"
API_ROOT = "https://api.github.com"
PER_PAGE = 100

ON_KEY_RE = re.compile(r"^(?:on|true|[\"']on[\"'])\s*:(.*)$")
BLOCK_KEY_RE = re.compile(r"^\s*-?\s*([A-Za-z0-9_./-]+)\s*:")
FLOW_ITEM_RE = re.compile(r"^\s*-\s*([A-Za-z0-9_./-]+)\s*$")
BROKEN_FILTER_RE = re.compile(r"branches:\s*ain\s*\]")  # значение фильтра ровно ain] (не внутри корректного [main])


def utc_now_iso():
    """Текущий момент в UTC (ISO-8601, Z)."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def take_token():
    """Токен из env: GITHUB_TOKEN или GH_TOKEN (None, если нет)."""
    return os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")


def analyse_workflow_text(text):
    """Построчный разбор YAML воркфлоу (эвристика без yaml-библиотеки).

    Возвращает dict: pr_target (триггер pull_request_target в блоке on:), triggers
    (объявленные триггеры on:), broken_filters (строки с `ain]`).

    Эвристика блока `on:`: первая непустая строка после `on:` задаёт отступ
    уровня триггеров; ключи с тем же отступом — триггеры, ключи глубже —
    их свойства (branches и пр.), они триггерами не считаются.
    """
    pr_target = []
    broken_filters = []
    triggers = []
    in_on_block = False
    on_indent = None

    for idx, raw in enumerate(text.splitlines(), start=1):
        stripped = raw.strip()

        if BROKEN_FILTER_RE.search(raw) and not stripped.startswith("#"):
            broken_filters.append({"line": idx, "text": stripped})

        if (in_on_block and not stripped.startswith("#")
                and stripped.split(":")[0].strip() == "pull_request_target"):
            pr_target.append({"line": idx, "text": stripped})

        on_match = ON_KEY_RE.match(raw)
        if on_match:
            inline = on_match.group(1).strip()
            if inline:
                # потоковый стиль: on: [push, pull_request_target] или on: push
                if inline.startswith("[") and inline.endswith("]"):
                    for chunk in inline[1:-1].split(","):
                        name = chunk.strip().strip("\"'")
                        if name:
                            triggers.append(name)
                            if name == "pull_request_target":
                                pr_target.append({"line": idx, "text": stripped})
                else:
                    triggers.append(inline.strip("\"'"))
                    if inline.strip("\"'") == "pull_request_target":
                        pr_target.append({"line": idx, "text": stripped})
                in_on_block = False
            else:
                in_on_block = True
                on_indent = None
            continue

        if in_on_block:
            if not stripped:
                continue  # пустая строка блок не закрывает
            if not raw[0].isspace():
                in_on_block = False  # вернулись на верхний уровень
                continue
            indent = len(raw) - len(raw.lstrip())
            if on_indent is None:
                on_indent = indent  # первая строка блока = уровень триггеров
            if indent < on_indent:
                in_on_block = False
                continue
            if indent == on_indent:
                key_match = FLOW_ITEM_RE.match(raw) or BLOCK_KEY_RE.match(raw)
                if key_match:
                    triggers.append(key_match.group(1))
            # глубже уровня триггеров — свойства триггера, пропускаем

    return {
        "pr_target": pr_target,
        "triggers": triggers,
        "broken_filters": broken_filters,
        "has_workflow_dispatch": "workflow_dispatch" in triggers,
    }


def load_allowlist(path):
    """Белый список осознанных pull_request_target: {"entries": [{repo, path, ...}]}."""
    with open(path, "r", encoding="utf-8") as fh:
        data = json.load(fh)
    entries = data.get("entries", [])
    return {(e.get("repo", ""), e.get("path", "")) for e in entries}


def build_report(generated, repos_scanned, workflows_scanned, findings,
                 broken, missing_dispatch, repos_without_workflows, gate):
    """Сборка итогового JSON-отчёта свипа (числа считаются, не декларируются)."""
    return {
        "generated": generated,
        "owner": OWNER,
        "repos_scanned": repos_scanned,
        "workflows_scanned": workflows_scanned,
        "pull_request_target_count": len(findings),
        "pull_request_target": findings,
        "broken_branch_filter_count": len(broken),
        "broken_branch_filters": broken,
        "missing_workflow_dispatch_count": len(missing_dispatch),
        "missing_workflow_dispatch": missing_dispatch,
        "repos_without_workflows": repos_without_workflows,
        "gate": gate,
    }


def render_markdown(report):
    """Markdown-дайджест свипа (печатается в stdout, попадает в step summary)."""
    lines = []
    lines.append("## Гейт `pull_request_target` · %s" % report["generated"])
    lines.append("")
    lines.append("- репо просмотрено: **%d**" % report["repos_scanned"])
    lines.append("- воркфлоу просмотрено: **%d**" % report["workflows_scanned"])
    lines.append("- находок `pull_request_target`: **%d**" % report["pull_request_target_count"])
    lines.append("- битых фильтров `ain]`: **%d**" % report["broken_branch_filter_count"])
    lines.append("- воркфлоу без `workflow_dispatch`: **%d**"
                 % report["missing_workflow_dispatch_count"])
    lines.append("")
    if report["pull_request_target"]:
        lines.append("### `pull_request_target` (репо → файл → строка)")
        lines.append("")
        for f in report["pull_request_target"]:
            lines.append("- `%s` → `%s` → строка %d: `%s`"
                         % (f["repo"], f["path"], f["line"], f["text"]))
        lines.append("")
    if report["broken_branch_filters"]:
        lines.append("### Битые фильтры веток `ain]`")
        lines.append("")
        for f in report["broken_branch_filters"]:
            lines.append("- `%s` → `%s` → строка %d: `%s`"
                         % (f["repo"], f["path"], f["line"], f["text"]))
        lines.append("")
    verdict = report.get("gate", {}).get("verdict", "гейт не запускался")
    lines.append("**Вердикт гейта:** %s" % verdict)
    return "\n".join(lines) + "\n"


def api_get_json(token, url):
    """GET к GitHub API с токеном → разобранный JSON (404 → None)."""
    url = urllib.parse.quote(url, safe=":/?&=%._-~")
    req = urllib.request.Request(url, method="GET")
    req.add_header("Authorization", "Bearer %s" % token)
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("User-Agent", "polimat-hub-pr-target-sweep")
    try:
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return None
        sys.stderr.write("ОШИБКА API: %s %s для %s\n" % (exc.code, exc.reason, url))
        raise SystemExit(1)
    except urllib.error.URLError as exc:
        sys.stderr.write("ОШИБКА СЕТИ: %s для %s\n" % (exc.reason, url))
        raise SystemExit(1)


def list_all_repos(token):
    """Пагинация /users/rtynbirf/repos?per_page=100 → [{name, default_branch}]."""
    repos = []
    page = 1
    while True:
        batch = api_get_json(
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


def fetch_text(token, url):
    """Тянем сырой текст воркфлоу по download_url (raw.githubusercontent)."""
    url = urllib.parse.quote(url, safe=":/?&=%._-~")
    req = urllib.request.Request(url, method="GET")
    if token:
        req.add_header("Authorization", "Bearer %s" % token)
    req.add_header("User-Agent", "polimat-hub-pr-target-sweep")
    try:
        with urllib.request.urlopen(req) as resp:
            return resp.read().decode("utf-8", errors="replace")
    except (urllib.error.HTTPError, urllib.error.URLError) as exc:
        sys.stderr.write("ПРЕДУПРЕЖДЕНИЕ: не скачался %s (%s)\n" % (url, exc))
        return None


def sweep(token, only_repos=None):
    """Живой обход всех репо и воркфлоу; возвращает (данные для отчёта)."""
    findings = []
    broken = []
    missing_dispatch = []
    repos_without_workflows = []
    workflows_scanned = 0

    repos = list_all_repos(token)
    if only_repos:
        wanted = set(only_repos)
        repos = [r for r in repos if r["name"] in wanted]

    for repo in repos:
        name = repo["name"]
        ref = repo["default_branch"]
        listing = api_get_json(
            token,
            "%s/repos/%s/%s/contents/.github/workflows?ref=%s"
            % (API_ROOT, OWNER, name, ref),
        )
        if not listing:
            repos_without_workflows.append(name)
            continue
        for item in listing:
            if item.get("type") != "file":
                continue
            fname = item.get("name", "")
            if not (fname.endswith(".yml") or fname.endswith(".yaml")):
                continue
            path = item.get("path", ".github/workflows/%s" % fname)
            url = item.get("download_url")
            if not url:
                continue
            text = fetch_text(token, url)
            if text is None:
                continue
            workflows_scanned += 1
            analysis = analyse_workflow_text(text)
            for hit in analysis["pr_target"]:
                findings.append({
                    "repo": name,
                    "path": path,
                    "line": hit["line"],
                    "text": hit["text"],
                })
            for hit in analysis["broken_filters"]:
                broken.append({
                    "repo": name,
                    "path": path,
                    "line": hit["line"],
                    "text": hit["text"],
                })
            if not analysis["has_workflow_dispatch"]:
                missing_dispatch.append({"repo": name, "path": path})

    return {
        "repos_scanned": len(repos),
        "workflows_scanned": workflows_scanned,
        "findings": findings,
        "broken": broken,
        "missing_dispatch": missing_dispatch,
        "repos_without_workflows": repos_without_workflows,
    }


def selftest():
    """Самопроверка без сети: два синтетических YAML + логика гейта."""
    yaml_a = "\n".join([
        "name: ci",
        "on:",
        "  push:",
        "    branches: [ main ]",
        "  pull_request_target:",
        "    branches: [ main ]",
        "  workflow_dispatch:",
        "jobs:",
        "  build:",
        "    runs-on: ubuntu-latest",
    ])
    yaml_b = "\n".join([
        "name: template",
        "on:",
        "  push:",
        "    branches: ain]",
        "  pull_request:",
        "jobs:",
        "  build:",
        "    runs-on: ubuntu-latest",
    ])

    a = analyse_workflow_text(yaml_a)
    assert a["has_workflow_dispatch"] is True, "workflow_dispatch не распознан"
    assert a["triggers"] == ["push", "pull_request_target", "workflow_dispatch"], \
        "триггеры разобраны неверно: %r" % a["triggers"]
    assert len(a["pr_target"]) == 1 and a["pr_target"][0]["line"] == 5, \
        "pull_request_target не найден там, где ожидается: %r" % a["pr_target"]
    assert not a["broken_filters"], "ложное срабатывание на битый фильтр"

    b = analyse_workflow_text(yaml_b)
    assert b["pr_target"] == [], "ложное срабатывание pull_request_target"
    assert b["has_workflow_dispatch"] is False, "workfow_dispatch придуман"
    assert "pull_request" in b["triggers"], "триггер pull_request потерян"
    assert len(b["broken_filters"]) == 1 and "ain]" in b["broken_filters"][0]["text"], \
        "битый фильтр ain] не пойман: %r" % b["broken_filters"]

    # гейт: осознанная запись пропускается, незнакомая — нарушение
    report = build_report(
        utc_now_iso(), 2, 2,
        [{"repo": "r1", "path": ".github/workflows/a.yml", "line": 5, "text": "x"}],
        [], [{"repo": "r2", "path": ".github/workflows/b.yml"}], [], {},
    )
    allowed = {("r1", ".github/workflows/a.yml")}
    violations = [
        f for f in report["pull_request_target"]
        if (f["repo"], f["path"]) not in allowed
    ]
    assert violations == [], "allowlist не пропустил осознанную запись"
    violations2 = [
        f for f in report["pull_request_target"]
        if (f["repo"], f["path"]) not in {("other", "other.yml")}
    ]
    assert len(violations2) == 1, "гейт не заметил чужое pull_request_target"

    md = render_markdown(report)
    assert "репо просмотрено: **2**" in md and "Вердикт гейта" in md, \
        "markdown-дайджест собран неверно"

    print("SELFTEST OK")


def main():
    parser = argparse.ArgumentParser(
        description="Свип pull_request_target по всем репо роя (П-72)"
    )
    parser.add_argument("--json", dest="json_path", metavar="FILE", default=None,
                        help="куда записать JSON-отчёт")
    parser.add_argument("--allowlist", metavar="FILE", default=None,
                        help="белый список осознанных pull_request_target (гейт)")
    parser.add_argument("--all", action="store_true",
                        help="обойти все репо роя (поведение по умолчанию)")
    parser.add_argument("--repos", metavar="R1,R2", default=None,
                        help="ограничить обход списком имён (по умолчанию все)")
    parser.add_argument("--selftest", action="store_true",
                        help="самопроверка без сети")
    args = parser.parse_args()

    if args.selftest:
        selftest()
        return

    token = take_token()
    if not token:
        sys.stderr.write("ЖИВОЙ ОБХОД НЕВОЗМОЖЕН: нет токена в env "
                         "GITHUB_TOKEN/GH_TOKEN (exit 2)\n")
        raise SystemExit(2)

    only_repos = [x.strip() for x in args.repos.split(",")] if args.repos else None
    data = sweep(token, only_repos=only_repos)

    gate = {"allowlist": args.allowlist, "allowlisted": 0, "violations": [],
            "verdict": "гейт не запускался"}
    exit_code = 0
    if args.allowlist:
        allowed = load_allowlist(args.allowlist)
        violations = [
            {"repo": f["repo"], "path": f["path"], "line": f["line"]}
            for f in data["findings"]
            if (f["repo"], f["path"]) not in allowed
        ]
        gate["allowlisted"] = sum(
            1 for f in data["findings"] if (f["repo"], f["path"]) in allowed
        )
        gate["violations"] = violations
        if violations:
            gate["verdict"] = ("КРАСНЫЙ: %d pull_request_target вне белого списка"
                               % len(violations))
            exit_code = 1
        else:
            gate["verdict"] = "ЗЕЛЁНЫЙ: pull_request_target нет или все осознаны"

    report = build_report(
        utc_now_iso(), data["repos_scanned"], data["workflows_scanned"],
        data["findings"], data["broken"], data["missing_dispatch"],
        data["repos_without_workflows"], gate,
    )

    if args.json_path:
        with open(args.json_path, "w", encoding="utf-8") as fh:
            json.dump(report, fh, ensure_ascii=False, indent=2)
        fh_size = os.path.getsize(args.json_path)
        sys.stderr.write("JSON-отчёт: %s (%d байт)\n" % (args.json_path, fh_size))

    sys.stdout.write(render_markdown(report))

    if gate.get("violations"):
        sys.stderr.write("ГАЙТ: %d нарушение(й) белого списка pull_request_target\n"
                         % len(gate["violations"]))
    raise SystemExit(exit_code)


if __name__ == "__main__":
    main()
