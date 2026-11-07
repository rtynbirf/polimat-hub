#!/usr/bin/env python3
"""features_integrate.py — интеграция современных фич GitHub в аккаунт (2026-11-08).

Фичи (по разведке в вебе, docs.github.com):
  F1 Dependabot alerts                PUT  /repos/{o}/{r}/vulnerability-alerts          (все репо)
  F2 Dependabot security updates      PUT  /repos/{o}/{r}/automated-security-fixes      (все репо)
  F3 delete_branch_on_merge           PATCH/repos/{o}/{r}                               (все репо)
  F4 ruleset polimat-guard            POST /repos/{o}/{r}/rulesets                      (все репо, запрет force-push/deletion)
  F5 secret scanning + push protect   PATCH/repos/{o}/{r} security_and_analysis         (публичные)
  F6 private vulnerability reporting  PUT  /repos/{o}/{r}/private-vulnerability-reporting (публичные)
  F7 CodeQL default setup             PUT  /repos/{o}/{r}/code-scanning/default-setup   (публичные кодовые)
  F8 topics (кластерная маркировка)   GET+PUT /repos/{o}/{r}/topics                     (все репо)

Каждая операция пишет HTTP-код в evidence-JSON. Никаких внешних зависимостей.
"""
import json
import os
import sys
import time
import urllib.request
import urllib.error
import concurrent.futures

API = "https://api.github.com"
OWNER = "rtynbirf"

CLUSTER_TOPICS = {
    "A": "system-layer", "B": "swarm-agents", "C": "ruvson",
    "D": "research-verification", "E": "windows-canon", "F": "exposition", "G": "meta-tools",
}
CLUSTER = {
    "polymath-os": "A", "neutral-browser": "A", "agryp": "A", "os-forge": "A",
    "H-PE11-PHOENIX": "A", "domovoy-tweaker": "A", "cell65-host": "A", "release-vault": "A",
    "nous": "B", "cell-swarm": "B", "runtime-protocol": "B", "cell-rs": "B",
    "universal-agent": "B", "commons": "B",
    "singulyar": "C", "ruvson-lyrics": "C", "ruvson-rse2": "C", "karaoke-dream": "C",
    "singulyar-llm": "C", "rtynbirf.github.io": "C", "voice-atlas-llm": "C",
    "red-thread-debt-audit": "D", "rent-mechanism-q43": "D", "polymath-atlas-v107": "D",
    "task-graph-propagator": "D", "global-video-platforms-registry": "D",
    "polymath-tools-atlas": "D", "uace-pml": "D", "polimat-task174": "D",
    "windows-chronicle": "E",
    "language-through-the-ages": "F", "web-evolution-1991-2026": "F", "edinyy-svod": "F",
    "repo-doctrine": "G", "github-runbook": "G", ".github": "G",
    "markitdown": "G", "polimat-vault": "G", "polimat-hub": "G",
}
CODEQL_LANGS = {"Python", "JavaScript", "Rust", "C"}
SKIP_FULL = {"markitdown"}  # форк: политика — зона upstream


class GH:
    def __init__(self, token):
        self.h = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "User-Agent": "polimat-hub",
        }

    def call(self, method, path, body=None):
        req = urllib.request.Request(f"{API}{path}", method=method, headers=self.h,
                                     data=json.dumps(body).encode() if body is not None else None)
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                raw = r.read().decode("utf-8", "replace")
                return r.status, (json.loads(raw) if raw.strip() else {})
        except urllib.error.HTTPError as e:
            try:
                msg = json.loads(e.read().decode("utf-8", "replace"))
            except Exception:
                msg = {}
            return e.code, msg


def feature_pack(gh, repo, is_public, language):
    o = {"repo": repo}
    s, _ = gh.call("PUT", f"/repos/{OWNER}/{repo}/vulnerability-alerts");          o["F1_dependabot_alerts"] = s
    s, _ = gh.call("PUT", f"/repos/{OWNER}/{repo}/automated-security-fixes");      o["F2_security_updates"] = s
    s, _ = gh.call("PATCH", f"/repos/{OWNER}/{repo}", {"delete_branch_on_merge": True}); o["F3_delete_branch_on_merge"] = s
    # дедупликация: не ставить polimat-guard дважды
    s_rs, existing = gh.call("GET", f"/repos/{OWNER}/{repo}/rulesets")
    has_guard = isinstance(existing, list) and any(
        isinstance(x, dict) and x.get("name") == "polimat-guard" for x in existing)
    if has_guard:
        o["F4_ruleset_guard"] = "already-present"
        s, body = 0, {}
    else:
        s, body = gh.call("POST", f"/repos/{OWNER}/{repo}/rulesets", {
        "name": "polimat-guard",
        "target": "branch",
        "enforcement": "active",
        "conditions": {"ref_name": {"include": ["~DEFAULT_BRANCH"], "exclude": []}},
            "rules": [{"type": "deletion"}, {"type": "non_fast_forward"}],
            "bypass_actors": [],
        })
    o["F4_ruleset_guard"] = ("already-present" if has_guard else f"{s}") + (f" id={body.get('id')}" if isinstance(body, dict) and body.get("id") else "")
    if is_public:
        s, m = gh.call("PATCH", f"/repos/{OWNER}/{repo}", {"security_and_analysis": {
            "secret_scanning": {"status": "enabled"},
            "secret_scanning_push_protection": {"status": "enabled"},
        }}); o["F5_secret_scanning"] = f"{s}" + (f" {m.get('message','')[:60]}" if s >= 400 else "")
        s, _ = gh.call("PUT", f"/repos/{OWNER}/{repo}/private-vulnerability-reporting"); o["F6_private_vuln_reporting"] = s
        if language in CODEQL_LANGS:
            s, m = gh.call("PUT", f"/repos/{OWNER}/{repo}/code-scanning/default-setup",
                           {"state": "configured", "query_suite": "default"})
            o["F7_codeql_default"] = f"{s}" + (f" {m.get('message','')[:60]}" if s >= 400 else "")
        else:
            o["F7_codeql_default"] = "skip-lang"
    # F8: темы — мердж, не замена
    s, cur = gh.call("GET", f"/repos/{OWNER}/{repo}/topics")
    have = set(cur.get("names", [])) if isinstance(cur, dict) else set()
    want = {CLUSTER_TOPICS[CLUSTER[repo]]}
    merged = sorted(have | want)[:20]
    s2, _ = gh.call("PUT", f"/repos/{OWNER}/{repo}/topics", {"names": merged})
    o["F8_topics"] = f"get={s},put={s2},added={sorted(want - have)}"
    return o


def main():
    token = os.environ["GITHUB_TOKEN"]
    gh = GH(token)
    # только /user/repos — видит и приватные; /users/... возвращает лишь публичные (ловушка раунда 1)
    s, repos = gh.call("GET", "/user/repos?visibility=all&affiliation=owner&per_page=100&sort=pushed")
    if s != 200:
        print(f"FATAL: /user/repos HTTP {s}", file=sys.stderr); return 2
    names = [(r["name"], not r["private"], r["language"] or "") for r in repos]
    print(f"processing {len(names)} repos", file=sys.stderr)
    evidence = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as ex:
        futs = {ex.submit(feature_pack, gh, n, p, l): n for n, p, l in names if n not in SKIP_FULL}
        for f in concurrent.futures.as_completed(futs):
            o = f.result(); evidence[o["repo"]] = o; print("packed:", o["repo"], file=sys.stderr)
    out = os.path.join(os.path.dirname(__file__), "..", "audit", "features-2026-11-08.json")
    json.dump({"integrated_at": "2026-11-08", "features": "F1-F8 см. tools/features_integrate.py",
               "results": evidence}, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    # сводка
    def count(prefix):
        ok = sum(1 for v in evidence.values() for k in v if k.startswith(prefix) and str(v[k]).startswith("20"))
        return ok
    print(json.dumps({p: count(p) for p in
          ["F1", "F2", "F3", "F4", "F5", "F6", "F7", "F8"]}, indent=1))
    print(f"-> {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
