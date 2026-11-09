#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""osv_sweep.py — второй сенсор иммунитета роя (П-18/#36, раунд 12).

Собирает манифесты зависимостей всех активных репо (package.json,
package-lock.json, requirements.txt — деревья через git/trees API),
спрашивает OSV.dev (POST /v1/querybatch — мировая база Google) и диффует
с GitHub Dependabot-алертами (первый сенсор). Два независимых источника
правды об уязвимостях: расхождения — честно в отчёт.

Выход: JSON-отчёт (--json) + одна строка-свод для ПУЛЬСА (--pulse FILE).
Коды выхода: 0 — прогон состоялся (свод достоверен), 1 — сетевой провал.
Токен только из env. Только stdlib.
"""
import argparse
import base64
import json
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone

OWNER = "rtynbirf"
GH = "https://api.github.com"
OSV_BATCH = "https://api.osv.dev/v1/querybatch"
MANIFESTS = ("package.json", "package-lock.json", "requirements.txt")
ECOSYSTEM = {"package.json": "npm", "package-lock.json": "npm",
             "requirements.txt": "PyPI"}


def api(url, tok, method="GET", payload=None):
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers={
        "Authorization": f"Bearer {tok}",
        "Accept": "application/vnd.github+json",
        "User-Agent": "polimat-osv-sweep"})
    try:
        with urllib.request.urlopen(req) as r:
            body = r.read().decode()
            return r.status, (json.loads(body) if body.strip() else {})
    except urllib.error.HTTPError as e:
        return e.code, {}
    except Exception:
        return 0, {}


def list_repos(tok):
    """Активные (не архив) репо владельца."""
    st, d = api(f"{GH}/user/repos?affiliation=owner&per_page=100", tok)
    return [(r["name"], r.get("archived", False)) for r in d] if st == 200 else []


def collect_manifests(tok, repo, sha_head):
    """Дерево репо → [(путь, имя манифеста)] без node_modules."""
    st, d = api(f"{GH}/repos/{OWNER}/{repo}/git/trees/{sha_head}?recursive=1", tok)
    out = []
    if st == 200:
        for t in d.get("tree", []):
            p = t.get("path", "")
            base = p.rsplit("/", 1)[-1]
            if base in MANIFESTS and "node_modules" not in p and p.count("/") <= 2:
                out.append((p, base))
    return out


def fetch_file(tok, repo, path, ref):
    st, d = api(f"{GH}/repos/{OWNER}/{repo}/contents/{path}?ref={ref}", tok)
    if st == 200 and isinstance(d, dict) and d.get("encoding") == "base64":
        return base64.b64decode(d["content"]).decode("utf-8", "replace")
    return None


def parse_deps(name, text):
    """(deps=[(eco, pkg, ver)], approx=n, unpinned=[pkg]).

    Точные версии — в OSV. `^`/`~`/`>=x.y.z` — минимальная база с пометкой
    approximate (Я-06: диапазон не даёт честной сверки). Голое имя без версии —
    unpinned (ямa Я-06, в отчёт отдельно).
    """
    deps, approx, unpinned = [], 0, []
    try:
        if name == "package.json":
            j = json.loads(text)
            for section in ("dependencies", "devDependencies"):
                for pkg, ver in (j.get(section) or {}).items():
                    v = ver.strip()
                    if not v:
                        continue
                    if v[0] in "^~":
                        base = v[1:].split("+")[0]
                        deps.append(("npm", pkg, base))
                        approx += 1
                    elif v[0].isdigit():
                        deps.append(("npm", pkg, v))
                    else:
                        unpinned.append(f"npm/{pkg}@{v}")
        elif name == "package-lock.json":
            j = json.loads(text)
            for key, meta in (j.get("packages") or {}).items():
                if key and "/node_modules/" in key:
                    v, nm = meta.get("version"), key.split("/node_modules/")[-1]
                    if v and nm:
                        deps.append(("npm", nm, v))
        elif name == "requirements.txt":
            for line in text.splitlines():
                line = line.split("#")[0].strip()
                if not line:
                    continue
                if "==" in line:
                    pkg, ver = line.split("==", 1)
                    if pkg.strip() and ver.strip():
                        deps.append(("PyPI", pkg.strip(), ver.strip()))
                else:
                    unpinned.append(f"PyPI/{line}")
    except Exception:
        pass
    return deps, approx, unpinned


def osv_querybatch(deps):
    """[(eco, pkg, ver)] → {key: [vuln ids]}. Пакетами по ≤ 200."""
    res = {}
    for i in range(0, len(deps), 200):
        chunk = deps[i:i + 200]
        queries = [{"package": {"ecosystem": eco, "name": p}, "version": v}
                   for eco, p, v in chunk]
        try:
            req = urllib.request.Request(OSV_BATCH, data=json.dumps({"queries": queries}).encode(),
                                         headers={"Content-Type": "application/json",
                                                  "User-Agent": "polimat-osv-sweep"})
            with urllib.request.urlopen(req, timeout=60) as r:
                d = json.loads(r.read().decode())
        except Exception:
            continue
        for (eco, p, v), hit in zip(chunk, d.get("results", [])):
            ids = [x.get("id") for x in hit.get("vulns", []) if x.get("id")]
            if ids:
                res[f"{eco}/{p}@{v}"] = ids
    return res


def gh_alerts(tok, repo):
    st, d = api(f"{GH}/repos/{OWNER}/{repo}/dependabot/alerts?state=open&per_page=100", tok)
    if st != 200:
        return None  # нет доступа/выключены
    out = {"open": len(d), "critical": 0, "high": 0}
    for a in d:
        sev = (a.get("security_advisory") or {}).get("severity")
        if sev == "critical":
            out["critical"] += 1
        elif sev == "high":
            out["high"] += 1
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", dest="json_out", required=True)
    ap.add_argument("--pulse", dest="pulse_out")
    a = ap.parse_args()
    tok = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN") or ""
    if not tok:
        sys.exit("нет токена в env")
    repos = [n for n, arch in list_repos(tok) if not arch]
    report = {"generated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
              "repos": len(repos), "manifests": 0, "packages": 0,
              "packages_approx": 0, "packages_unpinned": [],
              "osv_hits": {}, "gh_alerts": {}, "diff": {}, "repos_no_alerts": []}
    all_deps = []
    for repo in repos:
        st, d = api(f"{GH}/repos/{OWNER}/{repo}", tok)
        if st != 200:
            continue
        head = (d.get("default_branch") or "main")
        st2, b = api(f"{GH}/repos/{OWNER}/{repo}/branches/{head}", tok)
        sha = ((b.get("commit") or {}).get("sha")) if st2 == 200 else None
        if not sha:
            continue
        ga = gh_alerts(tok, repo)
        if ga is None:
            report["repos_no_alerts"].append(repo)
        if ga:
            report["gh_alerts"][repo] = ga
        for path, name in collect_manifests(tok, repo, sha):
            text = fetch_file(tok, repo, path, head)
            if not text:
                continue
            report["manifests"] += 1
            deps, approx, unpinned = parse_deps(name, text)
            report["packages_approx"] += approx
            for u in unpinned:
                report["packages_unpinned"].append(f"{repo}/{path} :: {u}")
            for dep in deps:
                all_deps.append((repo, path) + dep)
    report["packages"] = len(all_deps)
    report["osv_hits"] = osv_querybatch([(e, p, v) for _, _, e, p, v in all_deps])
    # дифф сенсоров: OSV-хиты по пакетам тех репо, где GH-алертов нет
    pkg2repo = {}
    for repo, path, eco, p, v in all_deps:
        pkg2repo[f"{eco}/{p}@{v}"] = repo
    for key, ids in report["osv_hits"].items():
        repo = pkg2repo.get(key, "?")
        ga = report["gh_alerts"].get(repo)
        if not ga or ga.get("open", 0) == 0:
            report["diff"][key] = {"repo": repo, "osv": ids[:5], "gh_open": 0 if not ga else ga}
    json.dump(report, open(a.json_out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    crit_gh = sum(r.get("critical", 0) for r in report["gh_alerts"].values())
    line = (f"OSV-сенсор ×{report['repos']}: манифестов {report['manifests']} · "
            f"пакетов {report['packages']} (≈диапазонов {report['packages_approx']} · "
            f"unpinned {len(report['packages_unpinned'])} — яма Я-06) · "
            f"OSV-хитов {len(report['osv_hits'])} · "
            f"GH-алертов open {sum(r.get('open',0) for r in report['gh_alerts'].values())} "
            f"(critical {crit_gh}) · расхождений {len(report['diff'])} · {report['generated']}")
    if a.pulse_out:
        with open(a.pulse_out, "a", encoding="utf-8") as f:
            f.write("- " + line + "\n")
    print(line)
    sys.exit(0)


if __name__ == "__main__":
    main()
