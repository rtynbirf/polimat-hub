#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""САРКОФАГ-НАУКА (П-71, polimat-hub#95): content-addressed манифест ДО перезаписи истории.

Строит frictionless-совместимый манифест (data-package) тяжеловеса,
чтобы идентичность данных пережила любой filter-repo: каждая запись ресурса
несёт path, size и git blob sha1 (контент-адрес).

Режимы:
  --api repo NAME [--ref BRANCH]  режим A: живой Git Trees API
                                  (GET /repos/rtynbirf/{repo}/git/trees/{ref}?recursive=1).
                                  Если ответ API усечён (truncated) — в манифесте честно
                                  ставится "truncated": true.
  --local DIR [--deep]            режим B: git ls-tree -r HEAD (subprocess) по локальному
                                  клону; --deep дополнительно считает sha256 файлов с диска.
  --out FILE                      куда записать JSON (по умолчанию — stdout).
  --selftest                      самопроверка без сети на встроенном синтетическом дереве.

Только stdlib. Токен берётся из env GITHUB_TOKEN или GH_TOKEN;
без токена режим A невозможен — exit 2.
"""

import argparse
import hashlib
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone

OWNER = "rtynbirf"
API_ROOT = "https://api.github.com"
HASH_MODE_API = "git-blob-sha1"
HASH_MODE_LOCAL = "git-blob-sha1"
HASH_MODE_LOCAL_DEEP = "git-blob-sha1+sha256"
# эталонный git blob sha1 пустого содержимого (общеизвестная константа git)
EMPTY_BLOB_SHA1 = "e69de29bb2d1d6434b8b29ae775ad8c2e48c5391"


def utc_now_iso():
    """Текущий момент в UTC, формат ISO-8601 с суффиксом Z."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def take_token():
    """Токен из env: GITHUB_TOKEN или GH_TOKEN (None, если нет)."""
    return os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")


def git_blob_sha1(data: bytes) -> str:
    """Чистый расчёт git blob sha1 (stdlib): sha1(b'blob <размер>\\0' + данные)."""
    h = hashlib.sha1()
    h.update(b"blob %d\0" % len(data))
    h.update(data)
    return h.hexdigest()


def api_request(token, url):
    """GET к GitHub API с токеном; возвращает разобранный JSON. Ошибки — понятным текстом."""
    req = urllib.request.Request(url, method="GET")
    req.add_header("Authorization", "Bearer %s" % token)
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("User-Agent", "polimat-hub-sarcofag-manifest")
    try:
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        sys.stderr.write("ОШИБКА API: %s %s для %s\n" % (exc.code, exc.reason, url))
        raise SystemExit(1)
    except urllib.error.URLError as exc:
        sys.stderr.write("ОШИБКА СЕТИ: %s для %s\n" % (exc.reason, url))
        raise SystemExit(1)


def resources_from_api_response(payload):
    """Разбор ответа Git Trees API в список ресурсов.

    Берём только записи type == 'blob' (файлы); каталоги ('tree') и субмодули
    ('commit') пропускаем. Усечение ответа API честно пробрасываем наверх.
    """
    resources = []
    for entry in payload.get("tree", []):
        if entry.get("type") != "blob":
            continue
        resources.append(
            {
                "path": entry.get("path", ""),
                "size": int(entry.get("size", 0) or 0),
                "gitBlobSha1": entry.get("sha", ""),
            }
        )
    return resources, bool(payload.get("truncated", False))


def resources_from_local(root, deep=False):
    """Режим B: git ls-tree -r -l HEAD в корне root (только блобы), + sha256 при --deep."""
    try:
        proc = subprocess.run(
            ["git", "ls-tree", "-r", "-l", "HEAD"],
            cwd=root,
            capture_output=True,
            text=True,
            check=True,
        )
    except FileNotFoundError:
        sys.stderr.write("ОШИБКА: git не найден в PATH\n")
        raise SystemExit(1)
    except subprocess.CalledProcessError as exc:
        sys.stderr.write("ОШИБКА git ls-tree: %s\n" % exc.stderr.strip())
        raise SystemExit(1)

    resources = []
    for line in proc.stdout.splitlines():
        if "\t" not in line:
            continue
        meta, path = line.split("\t", 1)
        parts = meta.split()
        if len(parts) < 4 or parts[1] != "blob":
            continue  # каталоги и субмодули не ресурсы данных
        size_text = parts[3]
        size = int(size_text) if size_text.isdigit() else 0
        resource = {"path": path, "size": size, "gitBlobSha1": parts[2]}
        if deep:
            full = os.path.join(root, path)
            try:
                with open(full, "rb") as fh:
                    resource["sha256"] = hashlib.sha256(fh.read()).hexdigest()
            except OSError:
                resource["sha256"] = None  # честно: файл не прочитался
        resources.append(resource)
    return resources


def build_manifest(name, repo, ref, resources, hash_mode, truncated, note):
    """Сборка datapackage-манифеста; count/total_bytes считаются, не декларируются."""
    ordered = sorted(resources, key=lambda r: r["path"])
    return {
        "name": name,
        "created": utc_now_iso(),
        "profile": "data-package",
        "repo": "%s/%s" % (OWNER, repo),
        "ref": ref,
        "count": len(ordered),
        "total_bytes": sum(int(r["size"]) for r in ordered),
        "hash_mode": hash_mode,
        "truncated": bool(truncated),
        "note": note,
        "resources": ordered,
    }


def validate_manifest(manifest):
    """Проверка структуры и сумм манифеста; возвращает список проблем (пустой = ОК)."""
    problems = []
    for key in ("name", "created", "profile", "repo", "ref", "count",
                "total_bytes", "hash_mode", "resources"):
        if key not in manifest:
            problems.append("нет ключа %s" % key)
    if manifest.get("profile") != "data-package":
        problems.append("profile не data-package")
    resources = manifest.get("resources", [])
    if manifest.get("count") != len(resources):
        problems.append("count не совпадает с числом ресурсов")
    if manifest.get("total_bytes") != sum(int(r.get("size", 0)) for r in resources):
        problems.append("total_bytes не совпадает с суммой размеров")
    paths = [r.get("path", "") for r in resources]
    if paths != sorted(paths):
        problems.append("ресурсы не отсортированы по path")
    for r in resources:
        if "path" not in r or "size" not in r or "gitBlobSha1" not in r:
            problems.append("ресурс без path/size/gitBlobSha1: %r" % (r,))
            break
    return problems


def run_mode_api(args):
    """Режим A: живой Git Trees API. Без токена — exit 2."""
    token = take_token()
    if not token:
        sys.stderr.write(
            "РЕЖИМ A НЕВОЗМОЖЕН: нет токена в env GITHUB_TOKEN/GH_TOKEN (exit 2)\n"
        )
        raise SystemExit(2)
    repo = args.repo
    if args.ref:
        ref = args.ref
    else:
        ref = api_request(token, "%s/repos/%s/%s" % (API_ROOT, OWNER, repo)).get(
            "default_branch", "HEAD"
        )
    payload = api_request(
        token, "%s/repos/%s/%s/git/trees/%s?recursive=1" % (API_ROOT, OWNER, repo, ref)
    )
    resources, truncated = resources_from_api_response(payload)
    note = (
        "САРКОФАГ-НАУКА (П-71, polimat-hub#95): content-addressed идентичность ДО "
        "любой перезаписи истории. sha1 = git blob sha (контент-адресованный); "
        "источник: Git Trees API, recursive=1."
    )
    return build_manifest(
        "%s-sarcofag" % repo, repo, ref, resources, HASH_MODE_API, truncated, note
    )


def run_mode_local(args):
    """Режим B: локальный git ls-tree -r HEAD (+sha256 при --deep)."""
    root = os.path.abspath(args.local)
    deep = bool(args.deep)
    resources = resources_from_local(root, deep=deep)
    note = (
        "САРКОФАГ-НАУКА (П-71, polimat-hub#95): content-addressed идентичность ДО "
        "любой перезаписи истории. sha1 = git blob sha (контент-адресованный); "
        "источник: git ls-tree -r HEAD локального клона%s."
        % (", дополнен sha256 файлов с диска" if deep else "")
    )
    return build_manifest(
        "%s-sarcofag" % os.path.basename(root),
        os.path.basename(root),
        "HEAD",
        resources,
        HASH_MODE_LOCAL_DEEP if deep else HASH_MODE_LOCAL,
        False,
        note,
    )


def selftest():
    """Самопроверка без сети: чистые функции + синтетическое дерево."""
    # 1) чистый расчёт git blob sha1 против общеизвестной константы пустого блоба
    assert git_blob_sha1(b"") == EMPTY_BLOB_SHA1, "git blob sha1 пустого блоба неверен"

    # 2) разбор синтетического ответа Trees API, включая честный truncated
    api_payload = {
        "truncated": False,
        "tree": [
            {"path": "data/a.csv", "type": "blob", "size": 5, "sha": "a" * 40},
            {"path": "docs", "type": "tree", "sha": "b" * 40},
            {"path": "docs/readme.md", "type": "blob", "size": 12, "sha": "c" * 40},
            {"path": "vendor/lib", "type": "commit", "sha": "d" * 40},
        ],
    }
    resources, truncated = resources_from_api_response(api_payload)
    assert truncated is False and len(resources) == 2, "разбор API-ответа неверен"
    api_payload["truncated"] = True
    _, truncated = resources_from_api_response(api_payload)
    assert truncated is True, "усечение API-ответа не пробросилось честно"

    # 3) сборка манифеста и проверка структуры/сумм
    manifest = build_manifest(
        "synthetic-sarcofag", "synthetic", "main", resources, HASH_MODE_API, False, "тест"
    )
    problems = validate_manifest(manifest)
    assert not problems, "валидатор нашёл проблемы: %r" % problems
    assert manifest["count"] == 2 and manifest["total_bytes"] == 17, "суммы неверны"

    # 4) валидатор ловит порчу: ломаем total_bytes — должны получить жалобу
    broken = dict(manifest)
    broken["total_bytes"] = manifest["total_bytes"] + 1
    assert validate_manifest(broken), "валидатор не поймал расхождение сумм"

    # 5) синтетическое дерево на диске: контент-адреса совпадают для одинаковых байт
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        first = os.path.join(tmp, "first.bin")
        second = os.path.join(tmp, "second.bin")
        with open(first, "wb") as fh:
            fh.write(b"hello\n")
        with open(second, "wb") as fh:
            fh.write(b"hello\n")
        with open(first, "rb") as fh:
            sha_first = git_blob_sha1(fh.read())
        with open(second, "rb") as fh:
            sha_second = git_blob_sha1(fh.read())
        assert sha_first == sha_second, "одинаковые байты дали разные контент-адреса"

    print("SELFTEST OK")


def main():
    parser = argparse.ArgumentParser(
        description="САРКОФАГ-НАУКА: content-addressed манифест до перезаписи истории"
    )
    parser.add_argument("--api", dest="api", action="store_true",
                        help="режим A: живой Git Trees API")
    parser.add_argument("--repo", metavar="NAME",
                        help="имя репо в rtynbirf (для режима A)")
    parser.add_argument("--ref", metavar="BRANCH", default=None,
                        help="ветка/тег/sha (для режима A; по умолчанию default branch)")
    parser.add_argument("--local", metavar="DIR", default=None,
                        help="режим B: путь к локальному клону")
    parser.add_argument("--deep", action="store_true",
                        help="режим B: дополнительно sha256 файлов с диска")
    parser.add_argument("--out", metavar="FILE", default=None,
                        help="записать JSON в файл (по умолчанию stdout)")
    parser.add_argument("--selftest", action="store_true",
                        help="самопроверка без сети")
    args = parser.parse_args()

    if args.selftest:
        selftest()
        return

    if args.api:
        if not args.repo:
            parser.error("режим A требует --repo NAME")
        manifest = run_mode_api(args)
    elif args.local:
        manifest = run_mode_local(args)
    else:
        parser.error("укажите режим: --api repo NAME или --local DIR (или --selftest)")

    text = json.dumps(manifest, ensure_ascii=False, indent=2)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as fh:
            fh.write(text)
        sys.stderr.write(
            "манифест: %s ресурсов, %d байт, truncated=%s → %s\n"
            % (manifest["count"], manifest["total_bytes"], manifest["truncated"], args.out)
        )
    else:
        sys.stdout.write(text + "\n")


if __name__ == "__main__":
    main()
