#!/usr/bin/env python3
# Post-push live checks. Token from env, never printed.
import json, os, sys, urllib.request

API = "https://api.github.com"
T = os.environ["GITHUB_TOKEN"]

def api(url):
    req = urllib.request.Request(url, headers={
        "Authorization": f"Bearer {T}",
        "Accept": "application/vnd.github+json",
        "User-Agent": "polimat-hub",
    })
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode("utf-8", "replace"))

out = []

# A. rumu branches — membrane really there?
br = api(f"{API}/repos/rtynbirf/rumu/branches")
out.append(("rumu branches", [(b["name"], b["commit"]["sha"][:9]) for b in br]))

# B. mystery repos
for name in ("polymath-gen", "rtynbirf"):
    r = api(f"{API}/repos/rtynbirf/{name}")
    out.append((f"repo {name}", {
        "size_kb": r["size"], "created": r["created_at"][:10],
        "pushed": r["pushed_at"][:16], "desc": (r.get("description") or "")[:80],
        "default_branch": r["default_branch"], "private": r["private"],
    }))
    try:
        t = api(f"{API}/repos/rtynbirf/{name}/git/trees/{r['default_branch']}?recursive=1")
        paths = [x["path"] for x in t.get("tree", []) if x["type"] == "blob"]
        out.append((f"{name} files ({len(paths)} blobs)", paths[:25]))
    except Exception as e:
        out.append((f"{name} tree", f"ERR {e}"))

# C. hub: size + vault dir content live
h = api(f"{API}/repos/rtynbirf/polimat-hub")
out.append(("polimat-hub", {"size_kb": h["size"], "pushed": h["pushed_at"][:16]}))
try:
    c = api(f"{API}/repos/rtynbirf/polimat-hub/contents/vault")
    out.append(("hub /vault live", [(x["name"], x["size"]) for x in c]))
except Exception as e:
    out.append(("hub /vault live", f"ERR {e}"))

# D. ruvson-lyrics releases (draft media-vault?)
rel = api(f"{API}/repos/rtynbirf/ruvson-lyrics/releases")
out.append(("ruvson releases", [{
    "name": x["name"], "draft": x["draft"], "assets": [
        {"n": a["name"], "b": a["size"], "state": a["state"]} for a in x["assets"]]}
    for x in rel]))

# E. edinyy-svod current state
s = api(f"{API}/repos/rtynbirf/edinyy-svod")
out.append(("edinyy-svod", {"size_kb": s["size"], "pushed": s["pushed_at"][:16]}))
try:
    c = api(f"{API}/repos/rtynbirf/edinyy-svod/contents/")
    out.append(("edinyy-svod top-level", [(x["name"], x["size"]) for x in c]))
except Exception as e:
    out.append(("edinyy-svod top-level", f"ERR {e}"))

for k, v in out:
    print(f"=== {k}")
    print(json.dumps(v, ensure_ascii=False, indent=1)[:2200])
