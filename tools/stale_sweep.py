#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""stale_sweep.py — stale-детектор роя (П-62 / issue #83, раунд 13).

Колонка «возраст тишины» для всей описи флота: для каждого репо из
meta-manifest.yml (единственный источник правды, П-45) читается pushed_at
живым API и считается дней с последнего пуша. Порог политики №8 роя —
90 дней (мир: официальный github/stale-repos — тот же принцип
«отчёт прежде решения», архивация = отдельный гейт, слово Хозяина).
Детектор НЕ архивирует ничего — только честная колонка и свод.

Выход: JSON-отчёт (--json) + одна строка-свод для ПУЛЬСА (--pulse FILE).
Коды выхода: 0 — прогон состоялся, 1 — сетевой провал.
Токен только из env. Только stdlib.
"""
import argparse
import json
import os
import re
import sys
import urllib.request
from datetime import datetime, timezone

OWNER = "rtynbirf"
GH = "https://api.github.com"
MANIFEST = "meta-manifest.yml"


def api(url, tok):
    req = urllib.request.Request(url, headers={
        "Authorization": f"Bearer {tok}",
        "Accept": "application/vnd.github+json",
        "User-Agent": "polimat-stale-sweep"})
    try:
        with urllib.request.urlopen(req) as r:
            return json.loads(r.read().decode())
    except Exception as e:  # noqa: BLE001 — честный счётчик провалов
        return {"__error__": str(e)}


def manifest_repos(path):
    """Имена репо из meta-manifest.yml без внешних зависимостей."""
    names = []
    for line in open(path, encoding="utf-8"):
        m = re.match(r"^- name:\s*(\S+)\s*$", line)
        if m:
            names.append(m.group(1))
    return names


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", dest="json_out", required=True)
    ap.add_argument("--pulse", dest="pulse_out", default=None)
    ap.add_argument("--env", dest="env_var", default="GITHUB_TOKEN")
    ap.add_argument("--threshold", type=int, default=90)
    ap.add_argument("--manifest", default=MANIFEST)
    a = ap.parse_args()

    tok = os.environ.get(a.env_var, "")
    if not tok:
        print(f"НЕТ ТОКЕНА в env {a.env_var} — отмена (токены только env).", file=sys.stderr)
        sys.exit(1)

    repos = manifest_repos(a.manifest)
    now = datetime.now(timezone.utc)
    rows, errs = [], 0
    for name in repos:
        d = api(f"{GH}/repos/{OWNER}/{name}", tok)
        if "__error__" in d or "pushed_at" not in d:
            errs += 1
            rows.append({"name": name, "error": d.get("__error__", "no pushed_at")})
            continue
        pushed = datetime.fromisoformat(d["pushed_at"].replace("Z", "+00:00"))
        days = (now - pushed).days
        rows.append({"name": name, "pushed_at": d["pushed_at"], "days_since_push": days,
                     "archived": bool(d.get("archived")), "size_kb": d.get("size", 0)})

    live = [r for r in rows if "error" not in r]
    act = [r for r in live if not r["archived"]]
    stale_90 = [r["name"] for r in act if r["days_since_push"] > a.threshold]
    stale_180 = [r["name"] for r in act if r["days_since_push"] > 180]
    arch = [r["name"] for r in live if r["archived"]]
    oldest = sorted(act, key=lambda r: -r["days_since_push"])[:5]

    report = {
        "generated": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "tool": "tools/stale_sweep.py · раунд 13 · П-62/#83",
        "source_manifest": a.manifest,
        "threshold_days": a.threshold,
        "repos_in_manifest": len(repos),
        "repos_live": len(live),
        "api_errors": errs,
        "archived": arch,
        "stale_over_90d": stale_90,
        "stale_over_180d": stale_180,
        "top_oldest": [{"name": r["name"], "days": r["days_since_push"]} for r in oldest],
        "rows": rows,
    }
    with open(a.json_out, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=1)

    line = (f"Stale-сенсор ×{len(live)}/{len(repos)} (опись {a.manifest}): "
            f"тишина >{a.threshold}д — {len(stale_90)} · >180д — {len(stale_180)} · "
            f"архив {len(arch)} ({','.join(arch) if arch else '—'}) · "
            f"старейшие: {' '.join(r['name']+':'+str(r['days_since_push'])+'д' for r in oldest[:3])} · "
            f"API-ошибок {errs} · {report['generated']}")
    if a.pulse_out:
        with open(a.pulse_out, "a", encoding="utf-8") as f:
            f.write("- " + line + "\n")
    print(line)
    sys.exit(0 if errs == 0 else 1)


if __name__ == "__main__":
    main()
