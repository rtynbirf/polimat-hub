#!/usr/bin/env python3
"""osps_baseline_check.py — OSPS-Baseline матрица аккаунта (ПАРТИЯ-1 «ОСПС»).

Машиноисполняемый аудит публичных репо по духу OpenSSF OSPS Baseline
(v2026.08.28: 41 контроль, 3 уровня зрелости, 6 стадий жизненного цикла —
openssf.org/projects/osps-baseline). Проверяются те контроли, которые
машиночитаемы через GitHub API без участия человека.

Честность канона роя:
- id OSPS-XX-N.NN проставлены ТОЛЬКО там, где контроль подтверждён
  каталогом (OSPS-AC-3.01 «прямой коммит в primary MUST быть заблокирован»,
  OSPS-VM-02.01 «документация MUST содержать security contacts»);
  остальные — собственная нумерация роя OSP-P-NN с полем osps_analog="—"
  (аналог не заявляется без подтверждённого id).
- UNKNOWN ≠ FALSE: сетевые ошибки не превращаются в красный вердикт.
- Selftest ходит в сеть НЕ ходит: фикстура-снапшот внутри файла.

Запуск:
    python3 tools/osps_baseline_check.py --selftest        # без сети
    python3 tools/osps_baseline_check.py --live [--repos a,b] [--out audit/…]
Токен: env GITHUB_TOKEN (классический или fine-grained с read).
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
API = "https://api.github.com"

CONTROLS = [
    # (id роя, название, osps_analog, проверка)
    ("OSP-P-01", "Механизм принуждения на primary (active branch ruleset)",
     "OSPS-AC-3.01", "rulesets_active"),
    ("OSP-P-02", "Security contacts (SECURITY.md на месте)",
     "OSPS-VM-02.01", "file_exists:SECURITY.md"),
    ("OSP-P-03", "CODEOWNERS (ответственные за дерево)",
     "—", "file_exists:.github/CODEOWNERS"),
    ("OSP-P-04", "README с описанием и границами",
     "—", "file_exists:README.md"),
    ("OSP-P-05", "License-файл (SPDX-определённый)",
     "—", "file_exists:LICENSE"),
    ("OSP-P-06", "Dependabot активен (мембрана)",
     "—", "file_exists:.github/dependabot.yml"),
    ("OSP-P-07", "AGENTS.md канона роя (шесть секций, Always/Ask first/Never)",
     "—", "file_exists:AGENTS.md"),
    ("OSP-P-08", "llms.txt машинный контракт",
     "—", "file_exists:llms.txt"),
    ("OSP-P-09", "Actions пинованы SHA-каноном (uses …@<40-hex>)",
     "—", "actions_pinned"),
    ("OSP-P-10", "Живой зелёный последний прогон CI (закон §5)",
     "—", "latest_run_green"),
    ("OSP-P-11", "Release-гигиена: latest релиз не пуст (notes/assets)",
     "—", "release_hygiene"),
]

FIXTURE = {  # selftest-снапшот: два фейковых репо, ожидания в EXPECTED
    "alpha": {
        "rulesets": [{"enforcement": "active", "target": "branch"}],
        "files": {"SECURITY.md": True, "README.md": True, "LICENSE": True,
                  ".github/CODEOWNERS": True, ".github/dependabot.yml": True,
                  "AGENTS.md": True, "llms.txt": True},
        "workflows": ["name: ci\n  uses: actions/checkout@"
                      "0123456789abcdef0123456789abcdef01234567"],
        "latest_run": {"conclusion": "success"},
        "latest_release": {"body": "v1", "assets": 2},
    },
    "beta": {
        "rulesets": [],
        "files": {"README.md": True},
        "workflows": ["uses: actions/checkout@v4"],
        "latest_run": {"conclusion": None},
        "latest_release": None,
    },
}


def _http(url: str, token: str) -> tuple[int, object | str]:
    req = urllib.request.Request(url, headers={
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "User-Agent": "polymath-osps",
    })
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            raw = r.read()
            try:
                return r.status, json.loads(raw)
            except Exception:
                return r.status, raw.decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")[:300]
    except Exception as e:  # сеть/таймаут — UNKNOWN, не FALSE
        return 0, f"error: {type(e).__name__}"


def check_rulesets_active(data) -> str:
    if not isinstance(data, list):
        return "error"
    active = [r for r in data
              if isinstance(r, dict) and r.get("enforcement") == "active"
              and r.get("target") == "branch"]
    return "yes" if active else "no"


def check_actions_pinned(workflows: list[dict]) -> str:
    import re
    pins, bare = 0, 0
    for wf in workflows or []:
        for m in re.finditer(r"uses:\s*([^\s]+)@(\S+)", wf.get("content", "")):
            ref = m.group(2)
            if re.fullmatch(r"[0-9a-f]{40}", ref):
                pins += 1
            else:
                bare += 1
    if pins and not bare:
        return "yes"
    if bare:
        return "no"
    return "n/a"  # нет uses — гейтов нет


def evaluate_repo(repo: str, token: str) -> dict:
    row: dict = {"repo": repo, "controls": {}, "notes": []}
    for cid, name, analog, kind in CONTROLS:
        verdict = "error"
        note = ""
        if kind.startswith("file_exists:"):
            path = kind.split(":", 1)[1]
            code, _ = _http(f"{API}/repos/{repo}/contents/{path}", token)
            verdict = {200: "yes", 404: "no"}.get(code, "unknown")
            if verdict == "unknown":
                note = f"HTTP {code}"
        elif kind == "rulesets_active":
            code, data = _http(f"{API}/repos/{repo}/rulesets", token)
            verdict = check_rulesets_active(data) if code == 200 else "unknown"
            if verdict == "unknown":
                note = f"HTTP {code}"
        elif kind == "actions_pinned":
            code, data = _http(f"{API}/repos/{repo}/contents/.github/workflows", token)
            if code != 200:
                verdict = "unknown"; note = f"HTTP {code}"
            else:
                wfs = [f for f in (data or []) if isinstance(f, dict)
                       and str(f.get("name", "")).endswith((".yml", ".yaml"))]
                parsed = []
                for f in wfs:
                    c, d = _http(f"{API}/repos/{repo}/contents/.github/workflows/"
                                 f"{f['name']}", token)
                    body = d.get("content") if isinstance(d, dict) and c == 200 else ""
                    content = base64.b64decode(body).decode("utf-8", "replace") if body else ""
                    parsed.append({"name": f["name"], "content": content})
                verdict = check_actions_pinned(parsed)
                if not wfs:
                    verdict = "n/a"; note = "workflows: 0"
        elif kind == "latest_run_green":
            code, data = _http(f"{API}/repos/{repo}/actions/runs?per_page=1", token)
            if code != 200:
                verdict = "unknown"; note = f"HTTP {code}"
            else:
                runs = (data or {}).get("workflow_runs") or []
                if not runs:
                    verdict = "n/a"; note = "runs: 0"
                else:
                    concl = runs[0].get("conclusion")
                    verdict = {"success": "yes"}.get(concl,
                        "pending" if concl is None else "no")
        elif kind == "release_hygiene":
            code, data = _http(f"{API}/repos/{repo}/releases?per_page=1", token)
            if code != 200:
                verdict = "unknown"; note = f"HTTP {code}"
            else:
                rels = data or []
                if not rels:
                    verdict = "n/a"; note = "releases: 0"
                else:
                    rel = rels[0]
                    assets = len(rel.get("assets") or [])
                    body = (rel.get("body") or "").strip()
                    verdict = "yes" if (body or assets) else "no"
        row["controls"][cid] = verdict
        if note:
            row["notes"].append(f"{cid}: {note}")
    return row


def run_selftest() -> int:
    ok = 0
    for repo, snap in FIXTURE.items():
        verdicts = {}
        for cid, name, analog, kind in CONTROLS:
            if kind.startswith("file_exists:"):
                verdicts[cid] = "yes" if snap["files"].get(
                    kind.split(":", 1)[1]) else "no"
            elif kind == "rulesets_active":
                verdicts[cid] = check_rulesets_active(snap["rulesets"])
            elif kind == "actions_pinned":
                verdicts[cid] = check_actions_pinned(
                    [{"content": w} for w in snap["workflows"]])
            elif kind == "latest_run_green":
                concl = snap["latest_run"]["conclusion"]
                verdicts[cid] = {"success": "yes"}.get(concl,
                    "pending" if concl is None else "no")
            elif kind == "release_hygiene":
                rel = snap["latest_release"]
                verdicts[cid] = ("yes" if rel and (rel["body"] or rel["assets"])
                                 else ("no" if rel else "n/a"))
        want_alpha = {"OSP-P-01": "yes", "OSP-P-02": "yes", "OSP-P-09": "yes",
                      "OSP-P-10": "yes", "OSP-P-11": "yes"}
        want_beta = {"OSP-P-01": "no", "OSP-P-02": "no", "OSP-P-09": "no",
                     "OSP-P-11": "n/a"}
        want = want_alpha if repo == "alpha" else want_beta
        bad = {k: verdicts[k] for k, v in want.items() if verdicts[k] != v}
        if bad:
            print(f"SELFTEST FAIL {repo}: {bad}")
            return 1
        print(f"SELFTEST OK {repo}: {len(verdicts)} контролей, "
              f"{sum(1 for v in verdicts.values() if v == 'yes')} yes")
        ok += 1
    print("SELFTEST PASS (2/2 фикстуры, сеть не тронута)")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--live", action="store_true")
    ap.add_argument("--repos", help="список через запятую (owner/repo)")
    ap.add_argument("--out", default=None, help="базовое имя выхода в audit/")
    args = ap.parse_args()

    if args.selftest:
        return run_selftest()

    if not args.live:
        print("нужно --live или --selftest")
        return 1
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN") or ""
    if not token:
        print("нет GITHUB_TOKEN в env")
        return 1

    repos = (args.repos or "").strip()
    if not repos:
        code, data = _http(f"{API}/users/rtynbirf/repos?per_page=100&sort=full_name",
                           token)
        if code != 200:
            print(f"список репо недоступен: HTTP {code}")
            return 1
        repos = [r["full_name"] for r in data
                 if not r.get("archived") and not r.get("private")]
    else:
        repos = [r.strip() for r in repos.split(",") if r.strip()]

    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    base = args.out or f"audit/osps-baseline-{stamp}"
    rows = []
    for repo in repos:
        row = evaluate_repo(repo, token)
        rows.append(row)
        yes = sum(1 for v in row["controls"].values() if v == "yes")
        print(f"  {repo}: {yes}/{len(CONTROLS)} yes")

    Path(ROOT / "audit").mkdir(exist_ok=True)
    (ROOT / f"{base}.json").write_text(
        json.dumps({"generated_at": datetime.now(timezone.utc).isoformat(),
                    "baseline": "OSPS Baseline (OpenSSF) v2026.08.28 — по духу",
                    "controls": [{"id": c[0], "name": c[1], "osps_analog": c[2]}
                                 for c in CONTROLS],
                    "rows": rows}, ensure_ascii=False, indent=1),
        encoding="utf-8")

    # Markdown-матрица
    lines = ["# 🛡️ OSPS-Baseline матрица аккаунта",
             "",
             f"*прогон {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')} · "
             f"репо: {len(rows)} · контролей: {len(CONTROLS)} · "
             "id OSPS-XX только из подтверждённого каталога; OSP-P-NN — нумерация роя*",
             "",
             "| Репо | " + " | ".join(c[0] for c in CONTROLS) + " | yes |",
             "|---|" + "---|" * (len(CONTROLS) + 1)]
    for row in rows:
        vals = [row["controls"][c[0]] for c in CONTROLS]
        mark = {"yes": "✅", "no": "⬜", "n/a": "–", "unknown": "❔",
                "pending": "🟡", "error": "⚠️"}
        lines.append(f"| `{row['repo'].split('/')[1]}` | "
                     + " | ".join(mark.get(v, v) for v in vals)
                     + f" | {sum(1 for v in vals if v == 'yes')} |")
    gaps: dict = {}
    for row in rows:
        for cid, v in row["controls"].items():
            if v in ("no", "unknown", "error"):
                gaps[cid] = gaps.get(cid, 0) + 1
    lines += ["", "## Топ-пробелы (⬜/❔ по колонкам)",
              ""]
    lines += [f"- {cid} ×{n}" for cid, n in
              sorted(gaps.items(), key=lambda x: -x[1])] or ["- пусто: ✅ everywhere"]
    (ROOT / f"{base}.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"выход: {base}.json + {base}.md")
    return 0


if __name__ == "__main__":
    sys.exit(main())
