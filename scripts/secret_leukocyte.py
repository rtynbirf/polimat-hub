#!/usr/bin/env python3
"""П-40 · Секрет-лейкоцит: скан секретов как постоянный контур роя (polimat-hub#61).

Уникальность против мира: сканируются не только деревья, но и ХВОСТЫ ЛОГОВ
красных CI-прогонов — именно там секреты и утекают (IEEE-ISTAS 2025:
у агента без встроенных проверок утечки растут с каждой итерацией).

Канон-регэкспы: GitHub PAT (ghp_/ghs_/ghu_/ghr_/github_pat_), AWS AKIA,
Slack xox*, OpenAI sk-, Google AIza, приватные ключи PEM.
Ложные срабатывания глушатся двумя механизмами (можно сочетать):
  1) `.secret-immunity-ignore` в корне проверяемого репо — регэксп на строку,
     матчится на ВСЮ строку находки (старый механизм, сохранён);
  2) `scripts/leukocyte-ignore.txt` рядом со сканером — строки
     `путь:regex-имя` (# — комментарий): путь — подстрока полного пути
     или glob (*, ?), regex-имя — канон-имя из PATTERNS (см. ниже).

Два режима:
  API   (по умолчанию, как раньше): деревья default-веток + хвосты красных
        логов через api.github.com — но жжёт квоту (прошлый прогон: 2404 файла);
  local (волна ×5-финал, задача #102): `--root DIR` — рекурсивный обход
        ЛОКАЛЬНЫХ клонов, те же канон-регэкспы и фильтры, 0 API-вызовов.
        Принцип дома: «знать = вычислять из структуры» — скан локальных
        клонов дешевле API и покрывает те же файлы.

Приёмка (polimat-hub#61): прогон success; находок 0; строка «секреты: 0»
в СВОДе хаба (СВОД-СЕКРЕТЫ.md, append-only).

Проверяй строкой: находка = факт совпадения канон-регэкспа, не настроение.
Выход: 0 = отработал (детектор), 1 = не смог отработать технически.
"""
import argparse
import base64
import fnmatch
import io
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
import zipfile
from concurrent.futures import ThreadPoolExecutor

API = "https://api.github.com"
LEDGER = "СВОД-СЕКРЕТЫ.md"
ISSUE_TITLE = "🩸 секрет-лейкоцит: НАХОДКИ — убрать секреты из репо (P0)"

# (канон-имя для ignore-файла, человекочитаемое имя, регэксп)
PATTERNS = [
    ("github_pat_classic", "GitHub PAT (ghp_)", re.compile(r"ghp_[A-Za-z0-9]{36}")),
    ("github_pat_short", "GitHub PAT (ghs_/ghu_/ghr_)", re.compile(r"gh[sur]_[A-Za-z0-9]{36}")),
    ("github_pat_fine", "GitHub fine-grained", re.compile(r"github_pat_[A-Za-z0-9_]{22,255}")),
    ("aws_access_key", "AWS Access Key", re.compile(r"AKIA[0-9A-Z]{16}")),
    ("slack_token", "Slack token", re.compile(r"xox[baprs]-[A-Za-z0-9-]{10,}")),
    ("openai_key", "OpenAI key", re.compile(r"sk-[A-Za-z0-9T]{20,}")),
    ("google_api_key", "Google API key", re.compile(r"AIza[0-9A-Za-z_\-]{35}")),
    ("pem_private_key", "PEM private key", re.compile(r"-----BEGIN (?:RSA |EC |DSA |OPENSSH |PGP )?PRIVATE KEY-----")),
]
PATTERN_KEYS = {k for k, _n, _rx in PATTERNS}

TEXT_EXT = {
    ".md", ".txt", ".py", ".js", ".ts", ".yml", ".yaml", ".json", ".sh",
    ".ps1", ".bat", ".cfg", ".ini", ".toml", ".html", ".css",
    ".xml", ".csv", ".lrc", ".gitignore", ".gitattributes", ".example",
}
TEXT_NAMES = {"Dockerfile", "Makefile", "LICENSE", ".gitignore", ".nojekyll",
              ".env.example", "CODEOWNERS", "llms.txt"}
MAX_FILE = 200_000          # байт на файл — больше уже не конфиг, а данные
MAX_FILES_PER_REPO = 100    # бюджет API на репо (только API-режим; local — без лимита)
MAX_LOG_TAIL = 120          # строк хвоста лога на прогон
SKIP_DIRS = {".git", "node_modules", "__pycache__", ".venv", "venv", ".tox"}
IMMUNITY_FILE = ".secret-immunity-ignore"

# Безобидные совпадения: примеры/фикстуры, помеченные как примеры
SAFE_MARKERS = ("EXAMPLE", "ПРИМЕР", "dummy", "fixture", "xxx", "XXX",
                "<token>", "your_token", "YOUR_", "ghp_x", "ЗАМЕНИ", "example")


def req(token, path_or_url, method="GET", data=None, raw=False):
    url = path_or_url if path_or_url.startswith("http") else API + path_or_url
    r = urllib.request.Request(url, method=method,
                               data=json.dumps(data).encode() if data is not None else None)
    r.add_header("Accept",
                 "application/vnd.github.raw" if raw else "application/vnd.github+json")
    r.add_header("User-Agent", "secret-leukocyte/1.0 (P-40 polimat-hub)")
    if token:
        r.add_header("Authorization", f"Bearer {token}")
    if data is not None:
        r.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(r, timeout=45) as resp:
            body = resp.read()
            ct = resp.headers.get("Content-Type", "")
            if "json" in ct or body[:1] in (b"{", b"["):
                return resp.status, json.loads(body.decode("utf-8", "replace"))
            return resp.status, body
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode("utf-8", "replace"))
        except Exception:
            return e.code, {}
    except Exception as e:
        print(f"  сеть: {e}")
        return 0, {}


def logs_url_follow(token, url):
    """GET логов: GitHub отвечает 302 на блоб — берём Location руками."""
    r = urllib.request.Request(url)
    r.add_header("Authorization", f"Bearer {token}")
    r.add_header("User-Agent", "secret-leukocyte/1.0")

    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *a, **k):
            return None
    opener = urllib.request.build_opener(NoRedirect)
    try:
        opener.open(r, timeout=45)
        return None
    except urllib.error.HTTPError as e:
        if e.code in (301, 302, 303, 307):
            return e.headers.get("Location")
        return None
    except Exception:
        return None


def parse_path_ignores(path):
    """scripts/leukocyte-ignore.txt: строки `путь:regex-имя`; # — комментарий.
    путь — подстрока полного пути ИЛИ glob (*, ?); regex-имя — канон из PATTERNS.
    Неизвестное канон-имя = битая строка: печатаем и пропускаем (молчать нельзя)."""
    rules = []
    if not os.path.exists(path):
        return rules
    with open(path, encoding="utf-8") as fh:
        for ln in fh:
            s = ln.strip()
            if not s or s.startswith("#"):
                continue
            if ":" not in s:
                print(f"  ! ignore {path}: строка без ':' пропущена: {s!r}")
                continue
            pat, _, key = s.rpartition(":")
            if key not in PATTERN_KEYS:
                print(f"  ! ignore {path}: неизвестное канон-имя {key!r}, строка пропущена: {s!r}")
                continue
            rules.append((pat, key))
    return rules


def path_is_ignored(path_variants, rules):
    """Канон-имена, заглушённые для этого пути. path_variants — все представления
    пути (относительный и абсолютный): маточим каждый паттерн по каждому."""
    hits = set()
    for pat, key in rules:
        for pv in path_variants:
            if "*" in pat or "?" in pat:
                if fnmatch.fnmatchcase(pv, pat):
                    hits.add(key)
            elif pat in pv:
                hits.add(key)
    return hits


def scan_text(path, text, ignore_res, findings, path_rules=(), suppressed=None,
              path_variants=None):
    if path_variants is None:
        path_variants = (path,)
    muted = path_is_ignored(path_variants, path_rules)
    for i, line in enumerate(text.splitlines(), 1):
        for key, name, rx in PATTERNS:
            m = rx.search(line)
            if not m:
                continue
            frag = m.group(0)
            if any(marker in line for marker in SAFE_MARKERS):
                continue
            if any(rx2.search(line) for rx2 in ignore_res):
                continue
            if key in muted:
                if suppressed is not None:
                    suppressed.append({"where": f"{path}:{i}", "kind": name,
                                       "fragment": frag[:8] + "…"})
                continue
            findings.append({"where": f"{path}:{i}", "kind": name,
                             "fragment": frag[:8] + "…" + frag[-4:]})


def repo_ignores(token, full):
    st, data = req(token, f"/repos/{full}/contents/{IMMUNITY_FILE}")
    if st != 200:
        return []
    try:
        txt = base64.b64decode(data.get("content", "")).decode("utf-8", "replace")
    except Exception:
        return []
    out = []
    for ln in txt.splitlines():
        ln = ln.strip()
        if ln and not ln.startswith("#"):
            try:
                out.append(re.compile(ln))
            except re.error:
                print(f"  ! игнор-файл {full}: битый регэксп {ln!r}")
    return out


# ---------- ЛОКАЛЬНЫЙ РЕЖИМ (волна ×5-финал, задача #102) ----------

def parse_immunity_text(txt):
    """Регэкспы из текста .secret-immunity-ignore (битые — с печатью)."""
    out = []
    for ln in txt.splitlines():
        ln = ln.strip()
        if ln and not ln.startswith("#"):
            try:
                out.append(re.compile(ln))
            except re.error:
                print(f"  ! .secret-immunity-ignore: битый регэксп {ln!r}")
    return out


def is_text_file(name):
    base = os.path.basename(name)
    ext = os.path.splitext(base)[1].lower()
    return ext in TEXT_EXT or base in TEXT_NAMES


def scan_root(root, findings, path_rules, suppressed):
    """Рекурсивный обход локального дерева: те же канон-регэкспы и фильтры,
    что и в API-режиме, 0 сетевых вызовов. .secret-immunity-ignore уважается
    на любом уровне вложенности (как в API-режиме — на корне репо).
    Возвращает (files, logs=0, errors)."""
    root = os.path.abspath(root)
    files_n = err_n = 0
    active = []  # [(dirpath, [rx])] — стек активных .secret-immunity-ignore
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        while active and not dirpath.startswith(active[-1][0] + os.sep) and active[-1][0] != dirpath:
            active.pop()
        if IMMUNITY_FILE in filenames:
            try:
                txt = open(os.path.join(dirpath, IMMUNITY_FILE), encoding="utf-8").read()
            except Exception:
                txt = ""
            active.append((dirpath, parse_immunity_text(txt)))
        ignore_res = [rx for _d, rxs in active for rx in rxs]
        for name in sorted(filenames):
            if not is_text_file(name):
                continue
            fp = os.path.join(dirpath, name)
            try:
                if os.path.getsize(fp) > MAX_FILE:
                    continue
                with open(fp, "rb") as fh:
                    raw = fh.read(MAX_FILE + 1)
            except OSError:
                err_n += 1
                continue
            if len(raw) > MAX_FILE:
                continue
            text = raw.decode("utf-8", "replace")
            rel = os.path.relpath(fp, root)
            display = rel
            variants = (rel, display, fp)
            files_n += 1
            scan_text(display, text, ignore_res, findings,
                      path_rules=path_rules, suppressed=suppressed,
                      path_variants=variants)
    return files_n, 0, err_n


def local_scan(roots, path_rules):
    """Локальный скан одного или нескольких --root. Возвращает итоги."""
    findings, suppressed = [], []
    scanned_files = errors = 0
    repos_n = 0
    for root in roots:
        root = os.path.abspath(root)
        # репо в замере: подкаталоги с .git, иначе сам root — одно репо
        subs = [d for d in sorted(os.listdir(root))
                if os.path.isdir(os.path.join(root, d))
                and os.path.exists(os.path.join(root, d, ".git"))]
        repos_n += len(subs) if subs else 1
        print(f"локальный скан: {root} (репо {len(subs) if subs else 1})", flush=True)
        files_n, _logs, err_n = scan_root(root, findings, path_rules, suppressed)
        scanned_files += files_n
        errors += err_n
        print(f"  → файлов {files_n}, ошибок {err_n}", flush=True)
    return findings, suppressed, scanned_files, repos_n, errors


def report_and_ledger(mode, findings, suppressed, scanned_files, repos_n,
                      scanned_logs, errors, roots_desc):
    verdict = "НАХОДОК 0" if not findings else f"НАХОДОК {len(findings)} — P0"
    print(f"итог: {verdict} · файлов {scanned_files} · логов {scanned_logs} · ошибок {errors}")
    if suppressed:
        print(f"заглушено ignore-файлом: {len(suppressed)} (прозрачность П-40):")
        for s in suppressed[:20]:
            print(f"  ⚪ {s['where']} — {s['kind']} — {s['fragment']}")
    if findings:
        print("НАХОДКИ (тело нового issue, не #102):")
        for f in findings[:100]:
            print(f"  🔴 {f['where']} — {f['kind']} — {f['fragment']}")

    stamp = time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime())
    line = (f"| {stamp} ({mode}{roots_desc}) | {repos_n} | {scanned_files} | {scanned_logs} | "
            f"{len(findings)} | {'чисто' if not findings else 'СМОТРИ ISSUE P0'} |\n")

    ledger = ""
    if os.path.exists(LEDGER):
        ledger = open(LEDGER, encoding="utf-8").read()
    if not ledger:
        ledger = ("# 🩸 СВОД СЕКРЕТОВ (секрет-лейкоцит, П-40 · polimat-hub#61)\n\n"
                  "Append-only журнал фонового контура секрет-иммунитета роя. "
                  "Лейкоцит сканирует деревья и хвосты красных логов по крону "
                  "(понедельник 03:23 UTC + dispatch). Уникальность П-40: логи.\n\n"
                  "| Замер | Репо | Файлов | Логов | Находок | Вердикт |\n|---|---|---|---|---|---|\n")
    if line.strip() not in ledger:
        ledger += line
    open(LEDGER, "w", encoding="utf-8").write(ledger)

    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as fh:
            fh.write(f"\n## 🩸 секрет-лейкоцит ({mode})\n\n{verdict}\n"
                     f"\nфайлов: {scanned_files} · логов: {scanned_logs} · репо: {repos_n}"
                     f" · заглушено ignore: {len(suppressed)}\n")
            for f in findings[:20]:
                fh.write(f"- 🔴 `{f['where']}` — {f['kind']} — `{f['fragment']}`\n")
    return stamp


def main() -> int:
    ap = argparse.ArgumentParser(description="П-40 · секрет-лейкоцит (API или локальный скан)")
    ap.add_argument("--root", action="append", metavar="DIR",
                    help="локальный режим: рекурсивный скан клонов в DIR (можно несколько --root);"
                         " без --root — старый API-режим (деревья + хвосты красных логов)")
    args = ap.parse_args()

    default_ignore = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                  "leukocyte-ignore.txt")
    path_rules = parse_path_ignores(default_ignore)
    if path_rules:
        print(f"ignore-файл: {default_ignore}: правил {len(path_rules)}")

    if args.root:
        roots_desc = " · локально " + ",".join(os.path.abspath(r) for r in args.root)
        findings, suppressed, scanned_files, repos_n, errors = local_scan(args.root, path_rules)
        stamp = report_and_ledger("локальный скан", findings, suppressed,
                                  scanned_files, repos_n, 0, errors, roots_desc)
        return 0 if scanned_files > 0 else 1

    # ---------- API-режим (без изменений семантики) ----------
    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN") or ""
    owner = os.environ.get("OWNER", "rtynbirf")
    findings, suppressed = [], []
    scanned_files = scanned_logs = errors = 0

    repos, page = [], 1
    while True:
        st, data = req(token, f"/users/{owner}/repos?per_page=100&page={page}&sort=full_name")
        if st != 200 or not isinstance(data, list) or not data:
            if st != 200:
                errors += 1
                print(f"  ! список репо: HTTP {st}")
            break
        repos.extend(data)
        if len(data) < 100:
            break
        page += 1
    # PAT-эндпоинт /user/repos видит и приватные; фоллбек — публичный /users/{owner}
    endpoint = "/user/repos" if token else f"/users/{owner}/repos"
    repos, page = [], 1
    while True:
        st, data = req(token, f"{endpoint}?per_page=100&page={page}&sort=full_name&visibility=all")
        if st != 200 or not isinstance(data, list) or not data:
            if st != 200 and endpoint.startswith("/user"):
                print(f"  ! {endpoint}: HTTP {st} — фоллбек на публичный список", flush=True)
                endpoint = f"/users/{owner}/repos"
                page = 1
                continue
            if st != 200:
                errors += 1
                print(f"  ! список репо: HTTP {st}")
            break
        repos.extend(data)
        if len(data) < 100:
            break
        page += 1
    repos = [r for r in repos if not r.get("archived")]
    print(f"секрет-лейкоцит: {owner}, репо {len(repos)} (параллельно, 12 потоков)")

    with ThreadPoolExecutor(max_workers=12) as pool:
        done = 0
        for r, (files_n, logs_n, err_n) in zip(
                repos, pool.map(lambda x: scan_repo(token, x, path_rules, findings, suppressed), repos)):
            scanned_files += files_n
            scanned_logs += logs_n
            errors += err_n
            done += 1
            print(f"  [{done}/{len(repos)}] {r['full_name']}: файлов {files_n}, логов {logs_n}", flush=True)

    stamp = report_and_ledger("API", findings, suppressed, scanned_files,
                              len(repos), scanned_logs, errors, "")

    if findings:
        body = ["# 🩸 СЕКРЕТ-ЛЕЙКОЦИТ: НАЙДЕНЫ ПОДОЗРЕНИЯ (P0)", "",
                "Лейкоцит нашёл совпадения с канон-регэкспами секретов.", ""]
        body += [f"- `{f['where']}` — **{f['kind']}** — `{f['fragment']}`" for f in findings[:100]]
        body += ["", "Закон П-40: секрет убирается из репо, ротируется, история — по решению Хозяина.",
                 "", f"*Замер {stamp} · файлов {scanned_files} · логов {scanned_logs}*"]
        st, issues = req(token, f"/repos/{owner}/polimat-hub/issues?state=open&per_page=50")
        existing = None
        for it in (issues if isinstance(issues, list) else []):
            if it.get("title", "").startswith("🩸 секрет-лейкоцит"):
                existing = it
                break
        if existing:
            req(token, f"/repos/{owner}/polimat-hub/issues/{existing['number']}", method="PATCH",
                data={"body": "\n".join(body)})
            print(f"issue-пломба обновлена: #{existing['number']}")
        else:
            st2, new = req(token, f"/repos/{owner}/polimat-hub/issues", method="POST",
                           data={"title": ISSUE_TITLE, "body": "\n".join(body)})
            if st2 == 201:
                print(f"issue-пломба создана: #{new['number']}")
    return 0 if scanned_files > 0 else 1


def scan_repo(token, r, path_rules, findings, suppressed):
    """Один репо: дерево + текстовые файлы + хвосты красных логов.
    Возвращает (files, logs, errors)."""
    full = r["full_name"]
    files_n = logs_n = err_n = 0
    ign = repo_ignores(token, full)
    branch = r.get("default_branch") or "main"
    # (а) дерево дефолт-ветки
    st, tree = req(token, f"/repos/{full}/git/trees/{branch}?recursive=1")
    if st == 200:
        blobs = [t for t in tree.get("tree", []) if t.get("type") == "blob"]
        picked = 0
        for t in blobs:
            if picked >= MAX_FILES_PER_REPO:
                break
            p = t["path"]
            base = os.path.basename(p)
            ext = os.path.splitext(p)[1].lower()
            if ext not in TEXT_EXT and base not in TEXT_NAMES:
                continue
            if t.get("size", 0) > MAX_FILE:
                continue
            st2, raw = req(token, f"/repos/{full}/contents/{urllib.request.quote(p)}?ref={branch}",
                           raw=True)
            if st2 != 200 or isinstance(raw, dict):
                continue
            try:
                text = raw.decode("utf-8", "replace") if isinstance(raw, bytes) else str(raw)
            except Exception:
                continue
            files_n += 1
            picked += 1
            scan_text(f"{full}/{p}", text, ign, findings,
                      path_rules=path_rules, suppressed=suppressed,
                      path_variants=(f"{full}/{p}", p))
    else:
        print(f"  ! дерево {full}: HTTP {st}")
        err_n += 1
    # (б) хвосты логов последних красных прогонов — уникальность П-40
    st, runs = req(token, f"/repos/{full}/actions/runs?status=failure&per_page=2")
    if st == 200:
        for run in runs.get("workflow_runs", [])[:2]:
            loc = logs_url_follow(token, f"{API}/repos/{full}/actions/runs/{run['id']}/logs")
            if not loc:
                continue
            st3, blob = req(token, loc)
            if st3 != 200 or not isinstance(blob, bytes):
                continue
            try:
                z = zipfile.ZipFile(io.BytesIO(blob))
            except Exception:
                continue
            for n in z.namelist():
                if not n.endswith(".txt"):
                    continue
                try:
                    tail = "\n".join(z.read(n).decode("utf-8", "replace").splitlines()[-MAX_LOG_TAIL:])
                except Exception:
                    continue
                logs_n += 1
                scan_text(f"{full} [лог {run['name']}/{run['id']}]", tail, ign, findings,
                          path_rules=path_rules, suppressed=suppressed)
    return files_n, logs_n, err_n


if __name__ == "__main__":
    sys.exit(main())
