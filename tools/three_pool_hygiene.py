#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Трёхпуловая квотная гигиена GitHub (П-69, polimat-hub #93).

Квота GitHub — это три разных бюджета, а не один «глобус»:
  1) артефакты Actions и Packages делят общий пул 500 МБ на Free-плане
     (здесь и ниже 500 МБ считается как 500 * 1024 * 1024 байт);
  2) кэши Actions — отдельный пул 10 ГБ на репозиторий;
  3) биллинг догоняет показания за 6-12 часов, поэтому сразу после чистки
     «quota hit» ещё может всплывать — это ожидаемо, а не ошибка замера.

Скрипт читает REST API и печатает markdown-таблицу в stdout; по флагу --json
дополнительно сохраняет машинный срез для quota_predictor.py. Режим --sweep
по умолчанию DRY-RUN: печатает план кандидатов, но ничего не удаляет.
Реальное удаление включается двухключевой предохранительной скобой: нужны
одновременно --execute и --yes. Только стандартная библиотека Python.
"""

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone

OWNER = "rtynbirf"
API_BASE = "https://api.github.com"
API_VERSION = "2022-11-28"
PER_PAGE = 100
POOL_500_BYTES = 500 * 1024 * 1024          # пул «артефакты + Packages»
CACHE_POOL_BYTES = 10 * 1024 * 1024 * 1024  # отдельный пул кэшей на репо
SWEEP_MIN_BYTES = 1024 * 1024               # кандидаты чистки: крупнее 1 МБ
SWEEP_MIN_AGE_DAYS = 7                      # ...и старше 7 дней
KEEP_MARKERS = ("release", "publish")       # ...и без этих маркеров в имени


class ApiError(Exception):
    """Честная ошибка запроса: несём HTTP-статус и причину дальше."""

    def __init__(self, status, reason):
        super().__init__("HTTP %s: %s" % (status if status is not None else "?", reason))
        self.status = status
        self.reason = reason


def api_request(base_url, path, token, method, timeout):
    url = base_url + path
    req = urllib.request.Request(url, method=method)
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("X-GitHub-Api-Version", API_VERSION)
    if token:
        req.add_header("Authorization", "Bearer " + token)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read()
    except urllib.error.HTTPError as exc:
        raise ApiError(exc.code, str(exc.reason)) from exc
    except urllib.error.URLError as exc:
        raise ApiError(None, str(exc.reason)) from exc
    if not body:
        return {}
    return json.loads(body.decode("utf-8"))


class Api:
    """Тонкая обёртка над urllib; в --selftest подменяется подделкой."""

    def __init__(self, token, base_url=API_BASE, timeout=30):
        self.token = token
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def get(self, path):
        return api_request(self.base_url, path, self.token, "GET", self.timeout)

    def delete(self, path):
        return api_request(self.base_url, path, self.token, "DELETE", self.timeout)


class FakeApi:
    """Оффлайн-двойник Api для --selftest: раздаёт страницы из словаря."""

    def __init__(self, routes):
        self.routes = routes
        self.calls = []

    @staticmethod
    def _param(path, name, default):
        if "?" not in path:
            return default
        for part in path.split("?", 1)[1].split("&"):
            key, _, value = part.partition("=")
            if key == name:
                return int(value)
        return default

    def get(self, path):
        self.calls.append("GET " + path)
        base = path.split("?", 1)[0]
        if base not in self.routes:
            raise ApiError(404, "нет такого маршрута в подделке")
        value = self.routes[base]
        if isinstance(value, Exception):
            raise value
        if isinstance(value, list):
            page = self._param(path, "page", 1)
            per_page = self._param(path, "per_page", PER_PAGE)
            start = (page - 1) * per_page
            return value[start:start + per_page]
        return value

    def delete(self, path):
        self.calls.append("DELETE " + path)
        return {}


def iter_pages(api, path, per_page=PER_PAGE):
    """Обходит списочный эндпоинт постранично (path уже со своими параметрами)."""
    page = 1
    while True:
        sep = "&" if "?" in path else "?"
        chunk = api.get("%s%sper_page=%d&page=%d" % (path, sep, per_page, page))
        if isinstance(chunk, dict):
            # GitHub возвращает объект со списком в поле для многих эндпоинтов
            for key in ("artifacts", "caches", "packages", "versions", "results", "items"):
                if isinstance(chunk.get(key), list):
                    chunk = chunk[key]
                    break
            else:
                raise ApiError(None, "ожидался JSON-массив от %s" % path)
        if not isinstance(chunk, list):
            raise ApiError(None, "ожидался JSON-массив от %s" % path)
        if not chunk:
            return
        for item in chunk:
            yield item
        if len(chunk) < per_page:
            return
        page += 1


def collect_repo(api, owner, repo):
    """Замеряет два пула одного репозитория: артефакты и кэш."""
    stats = {
        "repo": repo,
        "artifact_bytes": 0,
        "artifact_count": 0,
        "artifact_expired": 0,
        "cache_bytes": 0,
        "cache_count": 0,
        "notes": [],
        "artifacts": [],
    }
    try:
        for art in iter_pages(api, "/repos/%s/%s/actions/artifacts" % (owner, repo)):
            size = int(art.get("size_in_bytes") or 0)
            stats["artifact_count"] += 1
            stats["artifact_bytes"] += size
            if art.get("expired"):
                stats["artifact_expired"] += 1
            stats["artifacts"].append({
                "id": art.get("id"),
                "name": art.get("name") or "",
                "size_in_bytes": size,
                "created_at": art.get("created_at") or "",
                "expired": bool(art.get("expired")),
            })
    except ApiError as exc:
        stats["notes"].append("артефакты: %s" % exc)
    try:
        data = api.get("/repos/%s/%s/actions/caches" % (owner, repo))
        stats["cache_bytes"] = int(data.get("active_caches_size_in_bytes") or 0)
        stats["cache_count"] = int(data.get("total_count") or 0)
    except ApiError as exc:
        stats["notes"].append("кэш: %s" % exc)
    return stats


def collect_packages(api):
    """Packages принадлежат пользователю целиком, а не конкретному репо.

    REST API размеры версий пакетов систематически не отдаёт, поэтому версия
    без поля размера учитывается нулём: колонка packages — честная нижняя
    граница, а не точное значение.
    """
    packages = []
    notes = []
    try:
        for pkg in iter_pages(api, "/user/packages"):
            pkg_type = pkg.get("package_type") or ""
            pkg_name = pkg.get("name") or ""
            item = {
                "name": pkg_name,
                "package_type": pkg_type,
                "repo": (pkg.get("repository") or {}).get("full_name") or "",
                "bytes": 0,
                "version_count_api": int(pkg.get("version_count") or 0),
            }
            try:
                path = "/user/packages/%s/%s/versions" % (pkg_type, pkg_name)
                for ver in iter_pages(api, path):
                    item["bytes"] += int(ver.get("size_in_bytes") or ver.get("size") or 0)
            except ApiError as exc:
                notes.append("версии %s/%s: %s" % (pkg_type, pkg_name, exc))
            packages.append(item)
    except ApiError as exc:
        if exc.status == 403:
            notes.append("нет скоупа read:packages — пул Packages не посчитан")
        else:
            notes.append("packages: %s" % exc)
    return packages, notes


def parse_iso(text):
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None


def sweep_candidates(artifacts, now):
    """Кандидаты на удаление: > 1 МБ, старше 7 дней, имя без release/publish."""
    out = []
    for art in artifacts:
        name = (art.get("name") or "").lower()
        if any(marker in name for marker in KEEP_MARKERS):
            continue
        if (art.get("size_in_bytes") or 0) <= SWEEP_MIN_BYTES:
            continue
        created = parse_iso(art.get("created_at") or "")
        if created is None or now - created <= timedelta(days=SWEEP_MIN_AGE_DAYS):
            continue
        out.append(art)
    return out


def build_rows(repos_stats, packages):
    """Строки таблицы; Packages привязываются к репо по полю repository.full_name."""
    known = set(("%s/%s" % (OWNER, st["repo"])).lower() for st in repos_stats)
    pkg_by_repo = {}
    unbound_bytes = 0
    unbound_names = []
    for pkg in packages:
        full = (pkg.get("repo") or "").lower()
        if full and full in known:
            pkg_by_repo[full] = pkg_by_repo.get(full, 0) + pkg["bytes"]
        else:
            unbound_bytes += pkg["bytes"]
            unbound_names.append(pkg["name"] or "(без имени)")
    rows = []
    for st in repos_stats:
        key = ("%s/%s" % (OWNER, st["repo"])).lower()
        packages_bytes = pkg_by_repo.get(key, 0)
        rows.append({
            "repo": st["repo"],
            "artifact_bytes": st["artifact_bytes"],
            "cache_bytes": st["cache_bytes"],
            "packages_bytes": packages_bytes,
            "pool_bytes": st["artifact_bytes"] + packages_bytes,
        })
    return rows, unbound_bytes, unbound_names


def render_markdown(rows, unbound_bytes, unbound_names, packages_notes, repo_notes):
    """Markdown-таблица + честные сноски (пул 500 МБ, кэш 10 ГБ, лаг биллинга)."""

    def fmt(n):
        return format(int(n), ",").replace(",", " ")

    header = ("репозиторий", "артефакты, байт", "кэш, байт", "packages, байт",
              "итого в пуле 500 МБ, байт", "% пула 500 МБ")
    lines = ["| " + " | ".join(header) + " |", "|---|---:|---:|---:|---:|---:|"]
    for row in rows:
        lines.append("| %s | %s | %s | %s | %s | %.2f |" % (
            row["repo"], fmt(row["artifact_bytes"]), fmt(row["cache_bytes"]),
            fmt(row["packages_bytes"]), fmt(row["pool_bytes"]),
            100.0 * row["pool_bytes"] / POOL_500_BYTES))
    total_art = sum(r["artifact_bytes"] for r in rows)
    total_cache = sum(r["cache_bytes"] for r in rows)
    total_pkg = sum(r["packages_bytes"] for r in rows) + unbound_bytes
    total_pool = total_art + total_pkg
    lines.append("| **ИТОГО** | %s | %s | %s | %s | %.2f |" % (
        fmt(total_art), fmt(total_cache), fmt(total_pkg), fmt(total_pool),
        100.0 * total_pool / POOL_500_BYTES))
    lines.append("")
    lines.append("_Пул 500 МБ (Free) делят артефакты Actions и Packages; кэш — "
                 "отдельный пул 10 ГБ на репозиторий, в процентах не участвует._")
    lines.append("_Биллинг догоняет показания за 6-12 часов: сразу после чистки "
                 "цифры могут быть завышены._")
    if unbound_bytes or unbound_names:
        lines.append("_Packages вне привязки к замеренным репо: %s байт (%s)._" % (
            fmt(unbound_bytes), ", ".join(unbound_names) if unbound_names else "имён нет"))
    for note in packages_notes + repo_notes:
        lines.append("_%s_" % note)
    return "\n".join(lines)


def build_report(owner, repos_stats, rows, unbound_bytes, packages):
    """Машинный срез для quota_predictor.py --from-json и для архива."""
    return {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "owner": owner,
        "pool_500_bytes_limit": POOL_500_BYTES,
        "cache_pool_bytes_limit": CACHE_POOL_BYTES,
        "repos": [{
            "repo": st["repo"],
            "artifact_bytes": st["artifact_bytes"],
            "artifact_count": st["artifact_count"],
            "artifact_expired": st["artifact_expired"],
            "cache_bytes": st["cache_bytes"],
            "cache_count": st["cache_count"],
            "packages_bytes": row["packages_bytes"],
            "pool_bytes": row["pool_bytes"],
        } for st, row in zip(repos_stats, rows)],
        "packages": packages,
        "packages_unbound_bytes": unbound_bytes,
        "pool_bytes_total": sum(r["pool_bytes"] for r in rows) + unbound_bytes,
    }


def run_sweep(api, owner, repos_stats, args):
    """DRY-RUN по умолчанию; DELETE только при --execute и --yes одновременно."""
    now = datetime.now(timezone.utc)
    plan = []
    for st in repos_stats:
        for art in sweep_candidates(st["artifacts"], now):
            plan.append((st["repo"], art))
    if not plan:
        print("sweep: кандидатов нет (критерии: > 1 МБ, старше 7 дней, "
              "имя без 'release'/'publish')")
        return
    total = sum(a["size_in_bytes"] for _, a in plan)
    print("sweep: план удаления — кандидатов %d, суммарно %d байт:" % (len(plan), total))
    for repo, art in plan:
        print("  - %s: id=%s «%s», %d байт, создан %s" % (
            repo, art.get("id"), art.get("name"), art["size_in_bytes"], art.get("created_at")))
    if not (args.execute and args.yes):
        print("DRY-RUN: ничего не удалено; реальное удаление требует обоих ключей: --execute и --yes")
        return
    done = 0
    failed = 0
    for repo, art in plan:
        try:
            api.delete("/repos/%s/%s/actions/artifacts/%s" % (owner, repo, art.get("id")))
            done += 1
        except ApiError as exc:
            failed += 1
            print("не удалось удалить %s id=%s: %s" % (repo, art.get("id"), exc), file=sys.stderr)
    print("удалено %d, ошибок %d" % (done, failed))


def selftest():
    """Офлайн-проверка всей логики на встроенных синтетических данных."""
    checks = 0

    def check(cond, message):
        nonlocal checks
        if not cond:
            raise AssertionError("самопроверка провалена: " + message)
        checks += 1

    mib = 1024 * 1024
    now = datetime(2025, 1, 15, 12, 0, 0, tzinfo=timezone.utc)

    # 1. Суммы, счётчики и фильтр кандидатов на встроенной синтетике.
    artifacts = [
        {"id": 1, "name": "build-logs", "size_in_bytes": 3 * mib, "created_at": "2025-01-01T00:00:00Z", "expired": False},
        {"id": 2, "name": "release-bundle", "size_in_bytes": 9 * mib, "created_at": "2024-12-01T00:00:00Z", "expired": False},
        {"id": 3, "name": "publish-site", "size_in_bytes": 5 * mib, "created_at": "2024-12-20T00:00:00Z", "expired": True},
        {"id": 4, "name": "tiny", "size_in_bytes": 1024, "created_at": "2024-11-01T00:00:00Z", "expired": False},
        {"id": 5, "name": "fresh-big", "size_in_bytes": 2 * mib, "created_at": "2025-01-14T00:00:00Z", "expired": False},
        {"id": 6, "name": "old-expired", "size_in_bytes": 4 * mib, "created_at": "2024-10-10T00:00:00Z", "expired": True},
    ]
    check(sum(int(a["size_in_bytes"]) for a in artifacts) == 23 * mib + 1024,
          "суммарный размер артефактов")
    check(sum(1 for a in artifacts if a["expired"]) == 2, "число истёкших")
    check([c["id"] for c in sweep_candidates(artifacts, now)] == [1, 6],
          "кандидаты sweep — ожидались id 1 и 6 (release/publish/мелкий/свежий отсечены)")

    # 2. Пагинация и сбор по фейковому API.
    routes = {
        "/repos/rtynbirf/r1/actions/artifacts": artifacts[:4],
        "/repos/rtynbirf/r2/actions/artifacts": artifacts[4:],
        "/repos/rtynbirf/r1/actions/caches": {"total_count": 2, "active_caches_size_in_bytes": 123456},
        "/repos/rtynbirf/r2/actions/caches": {"total_count": 0, "active_caches_size_in_bytes": 0},
        "/user/packages": [
            {"name": "img", "package_type": "container", "version_count": 2,
             "repository": {"full_name": "rtynbirf/r1"}},
            {"name": "lib", "package_type": "npm", "version_count": 1},
        ],
        "/user/packages/container/img/versions": [{"size": 7 * mib}, {"size_in_bytes": 1 * mib}],
        "/user/packages/npm/lib/versions": [{}],
    }
    fake = FakeApi(routes)
    paged = list(iter_pages(fake, "/repos/rtynbirf/r1/actions/artifacts", per_page=2))
    check([a["id"] for a in paged] == [1, 2, 3, 4], "пагинация: 2 запроса по 2 элемента")
    check(sum(1 for c in fake.calls if c.endswith("page=2")) == 1, "вторую страницу запросили ровно раз")

    st1 = collect_repo(fake, OWNER, "r1")
    st2 = collect_repo(fake, OWNER, "r2")
    check(st1["artifact_bytes"] == 17 * mib + 1024, "сумма артефактов r1")
    check(st1["artifact_expired"] == 1, "истёкшие в r1")
    check(st1["cache_bytes"] == 123456, "размер кэша r1")
    check(st2["artifact_bytes"] == 6 * mib, "сумма артефактов r2")

    packages, notes = collect_packages(fake)
    check(notes == [], "сбор packages без пометок")
    check(packages[0]["bytes"] == 8 * mib, "размер версий контейнера")
    check(packages[1]["bytes"] == 0, "версия без поля размера считается нулём")

    # 3. Привязка Packages к репо и сборка строк.
    rows, unbound_bytes, unbound_names = build_rows([st1, st2], packages)
    check(rows[0]["packages_bytes"] == 8 * mib, "привязка packages к r1")
    check(rows[1]["pool_bytes"] == 6 * mib, "пул r2 = только артефакты")
    check(unbound_names == ["lib"] and unbound_bytes == 0, "package без repository — неразобранный")

    # 4. Формат markdown-таблицы.
    table = render_markdown(rows, unbound_bytes, unbound_names, notes, [])
    check(table.startswith("| репозиторий |"), "шапка таблицы")
    check("% пула 500 МБ" in table, "колонка процентов на месте")
    check("| **ИТОГО** |" in table, "строка ИТОГО на месте")
    check(len([ln for ln in table.splitlines() if ln.startswith("|")]) == len(rows) + 3,
          "строк таблицы: шапка + разделитель + по репо + ИТОГО")

    # 5. JSON-срез: сериализация и согласованность с таблицей.
    report = build_report(OWNER, [st1, st2], rows, unbound_bytes, packages)
    rebuilt = json.loads(json.dumps(report, ensure_ascii=False))
    check(rebuilt["pool_bytes_total"] == 31 * mib + 1024, "итог пула 500 МБ в JSON-срезе")
    check(rebuilt["repos"][0]["pool_bytes"] == rows[0]["pool_bytes"], "срез согласован с таблицей")

    # 6. Честная пометка при отсутствии скоупа read:packages.
    fake403 = FakeApi({"/user/packages": ApiError(403, "read:packages")})
    _, notes403 = collect_packages(fake403)
    check(any("read:packages" in n for n in notes403), "403 помечается как отсутствие скоупа")

    print("SELFTEST OK (%d проверок)" % checks)
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="three_pool_hygiene",
        description="Трёхпуловая квотная гигиена: артефакты+Packages (500 МБ) и кэш (10 ГБ на репо).")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--repos", help="список репозиториев через запятую: repo1,repo2")
    mode.add_argument("--all", action="store_true",
                      help="обойти все репозитории владельца %s" % OWNER)
    parser.add_argument("--json", metavar="ПУТЬ",
                        help="сохранить JSON-срез (для quota_predictor.py --from-json)")
    parser.add_argument("--sweep", action="store_true",
                        help="отобрать кандидатов на удаление артефактов (по умолчанию DRY-RUN)")
    parser.add_argument("--execute", action="store_true",
                        help="первый ключ предохранителя: разрешить DELETE")
    parser.add_argument("--yes", action="store_true",
                        help="второй ключ предохранителя: подтвердить DELETE (вместе с --execute)")
    parser.add_argument("--selftest", action="store_true",
                        help="офлайн-самопроверка на синтетических данных, без сети и токена")
    parser.add_argument("--timeout", type=int, default=30, help="таймаут HTTP-запроса, секунд")
    args = parser.parse_args(argv)

    if args.selftest:
        try:
            return selftest()
        except AssertionError as exc:
            print(str(exc), file=sys.stderr)
            return 1

    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if not token:
        print("Нет токена: задайте GITHUB_TOKEN или GH_TOKEN — без него API не читать.", file=sys.stderr)
        return 2
    if not args.all and not args.repos:
        parser.error("укажите --repos repo1,repo2 или --all")

    api = Api(token, timeout=args.timeout)
    if args.repos:
        repo_names = [name.strip() for name in args.repos.split(",") if name.strip()]
        if not repo_names:
            parser.error("пустой список --repos")
    else:
        repo_names = [r["name"] for r in iter_pages(api, "/user/repos?type=owner")]
        if not repo_names:
            print("У владельца %s не найдено репозиториев." % OWNER, file=sys.stderr)
            return 1

    repos_stats = []
    for name in repo_names:
        print("замер: %s/%s" % (OWNER, name), file=sys.stderr)
        repos_stats.append(collect_repo(api, OWNER, name))

    packages, packages_notes = collect_packages(api)
    rows, unbound_bytes, unbound_names = build_rows(repos_stats, packages)
    repo_notes = ["%s: %s" % (st["repo"], note) for st in repos_stats for note in st["notes"]]
    print(render_markdown(rows, unbound_bytes, unbound_names, packages_notes, repo_notes))

    if args.json:
        report = build_report(OWNER, repos_stats, rows, unbound_bytes, packages)
        with open(args.json, "w", encoding="utf-8") as fh:
            json.dump(report, fh, ensure_ascii=False, indent=2)
            fh.write("\n")

    if args.sweep:
        run_sweep(api, OWNER, repos_stats, args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
