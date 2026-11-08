#!/usr/bin/env python3
# Verify ruvson-lyrics release assets part2-4: download stream, compute git-blob sha1.
# No disk writes. Token from env only for API metadata; asset bytes via octet-stream.
import hashlib, json, os, urllib.request

API = "https://api.github.com"
T = os.environ["GITHUB_TOKEN"]

def api_json(url):
    req = urllib.request.Request(url, headers={
        "Authorization": f"Bearer {T}", "Accept": "application/vnd.github+json",
        "User-Agent": "polimat-hub"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode("utf-8", "replace"))

EXPECTED = {  # from /tmp/bigs.txt (mirror object DB, 2026-11-08 audit)
    "RUVSON_QUANTUM_v5.part1of5": "cda1c72e2225f9394c063cda98b1ab72998abbd7",
    "RUVSON_QUANTUM_v5.part2of5": "6e4a0a6b15637b5965e8d0f0edfb5dcd006a07d7",
    "RUVSON_QUANTUM_v5.part3of5": "c0e480f515eee0573b4b07af1a23b97eb85c6f63",
    "RUVSON_QUANTUM_v5.part4of5": "c5e9839aadd2618ba00ec1eb66161c1c096367d3",
    "RUVSON_QUANTUM_v5.part5of5": "11da60f5b8f12890e4b8220b3f5bb14a5f088775",
}

rel = [r for r in api_json(f"{API}/repos/rtynbirf/ruvson-lyrics/releases")
       if r["name"].startswith("media-vault")]
assert len(rel) == 1, rel
assets = {a["name"]: a for a in rel[0]["assets"]}

for name, want in EXPECTED.items():
    a = assets[name]
    req = urllib.request.Request(a["url"], headers={
        "Authorization": f"Bearer {T}", "User-Agent": "polimat-hub",
        "Accept": "application/octet-stream"})
    h = hashlib.sha1()
    n = 0
    h.update(f"blob {a['size']}\0".encode())
    with urllib.request.urlopen(req, timeout=120) as r:
        while True:
            chunk = r.read(1 << 20)
            if not chunk:
                break
            h.update(chunk)
            n += len(chunk)
    got = h.hexdigest()
    verdict = "MATCH" if got == want else f"MISMATCH (want {want})"
    print(f"{name}: bytes={n} git-sha1={got} -> {verdict}", flush=True)
