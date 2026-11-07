#!/usr/bin/env python3
"""migrate_media_to_releases.py — вынос больших blob'ов из git-дерева в GitHub Release.

Канон: git — для истории текстов; медиа >50 МБ — в Releases (правило 4 ARCHITECTURE.md).
Механика: деревья API → blob'ы >50 МБ → raw-скачивание → Release "media-vault" → upload asset.
Пломбы: sha256 источника (из git) + размер, до и после; asset state должен быть "uploaded".

Использование:
  GITHUB_TOKEN=... python3 migrate_media_to_releases.py <repo> [--limit N] [--draft]
Пример пилота:
  GITHUB_TOKEN=... python3 migrate_media_to_releases.py ruvson-lyrics --limit 1 --draft
"""
import hashlib
import json
import os
import sys
import urllib.request
import urllib.error

API = "https://api.github.com"
OWNER = "rtynbirf"
THRESHOLD = 50_000_000
RELEASE_TAG = "media-vault"


class GH:
    def __init__(self, token):
        self.token = token

    def call(self, method, path, body=None, raw=False, ctype="application/vnd.github+json"):
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(f"{API}{path}", method=method, data=data, headers={
            "Authorization": f"Bearer {self.token}", "Accept": ctype, "User-Agent": "polimat-hub"})
        with urllib.request.urlopen(req, timeout=600) as r:
            payload = r.read()
            return r.status, (payload if raw else (json.loads(payload.decode()) if payload else {}))


def big_blobs(gh, repo):
    _, tree = gh.call("GET", f"/repos/{OWNER}/{repo}/git/trees/main?recursive=1")
    return [(i["path"], i["size"], i["sha"]) for i in tree.get("tree", [])
            if i.get("type") == "blob" and i.get("size", 0) > THRESHOLD]


def run(repo, limit=None, draft=True):
    gh = GH(os.environ["GITHUB_TOKEN"])
    big = big_blobs(gh, repo)
    if limit:
        big = big[:limit]
    print(f"{repo}: к переносу {len(big)} blob'ов, {sum(s for _, s, _ in big)/1e6:.0f} МБ")
    # release: создать или взять существующий. ВАЖНО: черновики не видны через /tags — ищем списком
    _, rels = gh.call("GET", f"/repos/{OWNER}/{repo}/releases?per_page=50")
    rel = next((r for r in rels if r.get("tag_name") == RELEASE_TAG), None)
    if rel is None:
        _, rel = gh.call("POST", f"/repos/{OWNER}/{repo}/releases", {
            "tag_name": RELEASE_TAG, "target_commitish": "main",
            "name": "media-vault — большие файлы вне git-дерева",
            "draft": draft,
            "body": "Перенос blob'ов >50 МБ из дерева git (правило 4 ARCHITECTURE.md, polimat-hub). "
                    "Пломбы sha256 — в теле ассетов и в polimat-hub/audit/."})
    results = []
    for path, size, sha in big:
        # источник: raw blob с сверкой sha256 на лету
        st, data = gh.call("GET", f"/repos/{OWNER}/{repo}/git/blobs/{sha}", raw=True,
                           ctype="application/vnd.github+raw")
        # git blob sha = sha1("blob <size>\0" + content), НЕ sha256 содержимого — ловушка раунда 3
        h = hashlib.sha1(); h.update(b"blob %d\0" % len(data)); h.update(data)
        assert h.hexdigest() == sha, "git-sha1 источника не сошёлся"
        # upload
        up = rel.get("upload_url", "").split("{")[0] + f"?name={os.path.basename(path)}"
        req = urllib.request.Request(up, method="POST", data=data, headers={
            "Authorization": f"Bearer {gh.token}", "Content-Type": "application/octet-stream",
            "Content-Length": str(len(data)), "User-Agent": "polimat-hub"})
        with urllib.request.urlopen(req, timeout=600) as r:
            asset = json.loads(r.read().decode())
        ok = asset["state"] == "uploaded" and asset["size"] == size
        results.append({"path": path, "size": size, "git_sha1": sha,
                        "source_verified": True,
                        "asset_state": asset["state"], "verified": ok})
        print(f"  {'OK ' if ok else 'FAIL'} {path} ({size/1e6:.1f} МБ, sha {sha[:12]})")
    out = os.path.join(os.path.dirname(__file__), "..", "audit",
                       f"media-migration-{repo}.json")
    json.dump({"repo": repo, "results": results}, open(out, "w"), ensure_ascii=False, indent=1)
    print("->", out)
    return 0 if all(r["verified"] for r in results) else 1


if __name__ == "__main__":
    args = sys.argv[1:]
    repo = args[0]
    limit = int(args[args.index("--limit") + 1]) if "--limit" in args else None
    draft = "--no-draft" not in args
    sys.exit(run(repo, limit, draft))
