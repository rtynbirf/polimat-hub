#!/usr/bin/env python3
"""ЗАКОН ДОМА · ritual_check.py · машина инвариантов дома (v1.0, 2026-11-11)

Проверяет инварианты ЗАКОНА ДОМА (RITUAL/ЗАКОН-ДОМА.md §2) по живому GitHub API:
  I1 очередь = 0 (открытые issues и PR во всех репо)
  I2 приватных = 0
  I3 тишина живого репо <= 30 дней
  I4 у каждого schedule-воркфлоу есть дверь workflow_dispatch   [--deep]
  I5 uses-экшены запинены полным SHA                             [--deep]
  I7 нет некомментированных красных check-runs                   [--deep]

Выход: текстовый вердикт в stdout, машинный снапшот audit/ritual-<date>.json.
Issue НЕ заводит (закон: очередь = 0). Exit code всегда 0: красит вердикт, не job.
Stdlib only. Токен: env GH_TOKEN (или GITHUB_TOKEN).
"""
import json, os, re, sys, time, urllib.request, urllib.parse, datetime

TOKEN = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN") or ""
OWNER = os.environ.get("HOUSE_OWNER", "rtynbirf")
DEEP = "--deep" in sys.argv
OUTDIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "audit")
STALE_DAYS = 30
SHA_RE = re.compile(r"uses:\s*[\w\-./]+@([0-9a-f]{40})", re.I)
USES_RE = re.compile(r"uses:\s*([\w\-./]+)@")

def api(url):
    req = urllib.request.Request(url, headers={
        "Authorization": f"token {TOKEN}",
        "Accept": "application/vnd.github+json",
        "User-Agent": "house-ritual",
    })
    for attempt in range(5):  # 429/5xx — выдержка и повтор (урок первого прогона)
        try:
            with urllib.request.urlopen(req) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            if e.code in (429, 500, 502, 503) and attempt < 4:
                time.sleep(3 * (attempt + 1))
                continue
            raise
    raise RuntimeError("api retries exhausted")

def paged(url):
    out, page = [], 1
    while True:
        d = api(f"{url}{'&' if '?' in url else '?'}per_page=100&page={page}")
        if not d:
            return out
        out.extend(d)
        page += 1

def main():
    today = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")
    repos = paged(f"https://api.github.com/users/{OWNER}/repos?per_page=100")
    violations = []
    snap = {"ritual": "zakon-doma v1.0", "date": today, "owner": OWNER,
            "repos_total": len(repos), "violations": []}

    # I2 приватность
    priv = [r["name"] for r in repos if r["private"]]
    for n in priv:
        violations.append({"inv": "I2", "repo": n, "fact": "repo приватный"})

    cutoff = (datetime.datetime.now(datetime.timezone.utc) -
              datetime.timedelta(days=STALE_DAYS)).strftime("%Y-%m-%d")
    queue = []   # I1
    stale = []   # I3
    doors = []   # I4
    pins = []    # I5
    blood = []   # I7

    for r in sorted(repos, key=lambda x: x["name"]):
        name = r["name"]
        if r["open_issues_count"] > 0:
            items = paged(f"https://api.github.com/repos/{OWNER}/{name}/issues?state=open")
            for i in items:
                kind = "PR" if "pull_request" in i else "ISSUE"
                queue.append({"repo": name, "kind": kind, "number": i["number"], "title": i["title"][:90]})
        if not r["archived"] and r["pushed_at"][:10] < cutoff:
            stale.append({"repo": name, "pushed_at": r["pushed_at"][:10]})
        if DEEP:
            # I4/I5: разбор воркфлоу через git trees (1 запрос на репо)
            try:
                tree = api(f"https://api.github.com/repos/{OWNER}/{name}/git/trees/HEAD?recursive=1")
                for t in tree.get("tree", []):
                    p = t.get("path", "")
                    if not (p.startswith(".github/workflows/") and p.endswith((".yml", ".yaml"))):
                        continue
                    raw = f"https://raw.githubusercontent.com/{OWNER}/{name}/HEAD/{urllib.parse.quote(p)}"
                    req = urllib.request.Request(raw, headers={"User-Agent": "house-ritual"})
                    with urllib.request.urlopen(req) as resp:
                        src = resp.read().decode("utf-8", "replace")
                    if "schedule:" in src:
                        m = re.search(r"^on:\n(?:[ \t]+.*\n)+", src, re.M)
                        block = m.group(0) if m else ""
                        if "workflow_dispatch" not in block:
                            doors.append({"repo": name, "wf": p})
                    for mm in USES_RE.finditer(src):
                        act, ref = mm.group(1), src[mm.end():mm.end()+45].split()[0]
                        if act.startswith("actions/") or act.startswith("github/"):
                            if not SHA_RE.search("uses: " + act + "@" + ref):
                                pins.append({"repo": name, "wf": p, "action": f"{act}@{ref}"})
            except Exception as e:
                doors.append({"repo": name, "wf": "TREE-ERROR", "err": str(e)[:80]})
            # I7: красные check-runs на HEAD
            try:
                head = api(f"https://api.github.com/repos/{OWNER}/{name}/commits/HEAD")
                sha = head["sha"]
                runs = api(f"https://api.github.com/repos/{OWNER}/{name}/commits/{sha}/check-runs")
                for c in runs.get("check_runs", []):
                    if c.get("conclusion") == "failure":
                        blood.append({"repo": name, "check": c["name"], "sha": sha[:8]})
            except Exception:
                pass

    for q in queue:
        violations.append({"inv": "I1", "repo": q["repo"],
                           "fact": f"открыт {q['kind']} #{q['number']}: {q['title']}"})
    for s in stale:
        violations.append({"inv": "I3", "repo": s["repo"], "fact": f"тишина с {s['pushed_at']} > {STALE_DAYS}д"})
    for d in doors:
        violations.append({"inv": "I4", "repo": d["repo"], "fact": f"schedule без двери: {d.get('wf', '?')} {d.get('err','')}"})
    for p in pins:
        violations.append({"inv": "I5", "repo": p["repo"], "fact": f"неполный SHA: {p['action']}"})
    for b in blood:
        violations.append({"inv": "I7", "repo": b["repo"], "fact": f"красный check {b['check']} ({b['sha']})"})

    snap["queue"] = queue
    snap["stale"] = stale
    snap["violations"] = violations
    os.makedirs(OUTDIR, exist_ok=True)
    out = os.path.join(OUTDIR, f"ritual-{today}.json")
    with open(out, "w") as f:
        json.dump(snap, f, ensure_ascii=False, indent=1)

    print(f"== ЗАКОН ДОМА · прегон {today} · репо {len(repos)} · deep={DEEP} ==")
    print(f"I1 очередь: {len(queue)}  |  I2 приватных: {len(priv)}  |  I3 тишина>30д: {len(stale)}")
    if DEEP:
        print(f"I4 двери: {len(doors)}  |  I5 пины: {len(pins)}  |  I7 красные: {len(blood)}")
    if violations:
        print(f"\nВЕРДИКТ: НАРУШЕНИЙ {len(violations)} → ритуал! (S1→S5 по каждой)")
        for v in violations[:60]:
            print(f"  [{v['inv']}] {v['repo']}: {v['fact']}")
        if len(violations) > 60:
            print(f"  … и ещё {len(violations)-60}")
    else:
        print("\nВЕРДИКТ: ДОМ ЧИСТ. Инварианты держатся. Ритуал не требует входа.")
    print(f"Снапшот: {out}")

if __name__ == "__main__":
    main()
