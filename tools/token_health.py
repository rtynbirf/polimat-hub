#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""token_health.py — пульс токен-конверта (П-35/П-74, polimat-hub#53/#98, раунд 11).

Читает токены ТОЛЬКО из переменных окружения, для каждого печатает:
  маску (ghp_…a1b2) · тип (classic/fine-grained) · login · scopes ·
  expiry (заголовок X-GitHub-Expiration) · days_left · warning при days_left < 1.

ГАРАНТИЯ МАСКИ: полный токен не появляется ни в одном байте вывода —
единственная точка печати маски — mask(); selftest проверяет это без сети.

Приём:
    GITHUB_TOKEN=… GITHUB_TOKEN2=… python3 tools/token_health.py
    python3 tools/token_health.py --json OUT.json        # + машиночитаемый отчёт
    python3 tools/token_health.py --selftest             # без сети

Коды выхода: 0 — есть живой токен · 1 — живых нет · 2 — токенов в env нет.
Правило роя: токен = одноразовая валюта; вышел из чата = подлежит отзыву.
Только stdlib.
"""
import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone

API = "https://api.github.com"
DEFAULT_ENVS = ("GITHUB_TOKEN", "GITHUB_TOKEN2", "GH_TOKEN")


def mask(tok: str) -> str:
    """Маска: первые 4 символа + «…» + последние 4 (ghp_…a1b2)."""
    if len(tok) <= 8:
        return "…" * len(tok)
    return tok[:4] + "…" + tok[-4:]


def kind_of(tok: str) -> str:
    if tok.startswith("github_pat_"):
        return "fine-grained"
    if tok.startswith(("ghp_", "gho_", "ghu_", "ghs_")):
        return "classic"
    return "unknown"


def parse_iso(s: str):
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return None


def probe(tok: str):
    """Живой опрос одного токена. Возвращает факт-словарь (без полного токена)."""
    req = urllib.request.Request(f"{API}/user", headers={
        "Authorization": f"Bearer {tok}",
        "Accept": "application/vnd.github+json",
        "User-Agent": "polimat-token-health",
    })
    fact = {"env_mask": mask(tok), "kind": kind_of(tok), "alive": False}
    try:
        with urllib.request.urlopen(req) as resp:
            d = json.loads(resp.read().decode("utf-8"))
            fact["alive"] = True
            fact["login"] = d.get("login")
            scopes = resp.headers.get("X-OAuth-Scopes", "")
            fact["scopes"] = [s for s in scopes.split(", ") if s] or ["(fine-grained: скоупы в токене)"]
            exp_raw = resp.headers.get("X-GitHub-Expiration")
            fact["expires"] = exp_raw or "(бессрочный/не отдаётся API)"
            exp = parse_iso(exp_raw)
            if exp:
                days = (exp - datetime.now(timezone.utc)).total_seconds() / 86400.0
                fact["days_left"] = round(days, 1)
                if days < 1:
                    fact["warning"] = "days_left < 1 — конверт умирает, готовь замену"
    except urllib.error.HTTPError as e:
        fact["http"] = e.code
        fact["note"] = "401/403 — токен мёртв или ограничен"
    return fact


def selftest():
    t = "[REDACTED-DEAD-TOKEN]"
    m = mask(t)
    assert "…" in m and len(m) <= len("ghp_") + 1 + 4, m
    assert t not in m, "МАСКА ПРОТЕКЛА!"
    assert kind_of(t) == "classic" and kind_of("github_pat_xx") == "fine-grained"
    print("selftest OK: маска держит (полный токен в вывод невозможен)")
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--env", default=",".join(DEFAULT_ENVS),
                    help="имена env-переменных через запятую")
    ap.add_argument("--json", dest="json_out", help="файл машиночитаемого отчёта")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        sys.exit(selftest())
    toks = [(n, os.environ.get(n, "")) for n in [x.strip() for x in a.env.split(",") if x.strip()]]
    toks = [(n, t) for n, t in toks if t]
    if not toks:
        print("exit 2: в env нет ни одного токена (имена: %s)" % a.env)
        sys.exit(2)
    report = {"checked": [], "alive": 0, "dead": 0}
    print("## token_health · конверт роя · %s UTC" % datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"))
    for name, t in toks:
        f = probe(t)
        f["env_name"] = name
        report["checked"].append(f)
        report["alive" if f["alive"] else "dead"] += 1
        state = "🟢 жив" if f["alive"] else "🔴 мёртв"
        print(f"- {name}: {f['env_mask']} · {f['kind']} · {state}")
        if f["alive"]:
            print(f"    login: {f.get('login')} · scopes: {', '.join(f.get('scopes', []))}")
            print(f"    expiry: {f.get('expires')} · days_left: {f.get('days_left', '—')}")
            if f.get("warning"):
                print(f"    ⚠ {f['warning']}")
    if a.json_out:
        json.dump(report, open(a.json_out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        print(f"JSON: {a.json_out}")
    sys.exit(0 if report["alive"] else 1)


if __name__ == "__main__":
    main()
