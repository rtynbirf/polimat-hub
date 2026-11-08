#!/usr/bin/env python3
"""П-40 · Секрет-лейкоцит: скан секретов как постоянный контур роя (polimat-hub#61).

Уникальность против мира: сканируются не только деревья, но и ХВОСТЫ ЛОГОВ
красных CI-прогонов — именно там секреты и утекают (IEEE-ISTAS 2025:
у агента без встроенных проверок утечки растут с каждой итерацией).

Канон-регэкспы: GitHub PAT (ghp_/ghs_/ghu_/ghr_/github_pat_), AWS AKIA,
Slack xox*, OpenAI sk-, Google AIza, приватные ключи PEM.
Ложные срабатывания глушатся файлом-игнором `.secret-immunity-ignore`
(по одному регэкспу на строку, # — комментарий) в корне проверяемого репо.

Приёмка (polimat-hub#61): прогон success; находок 0; строка «секреты: 0»
в СВОДе хаба (СВОД-СЕКРЕТЫ.md, append-only).

Проверяй строкой: находка = факт совпадения канон-регэкспа, не настроение.
Выход: 0 = отработал (детектор), 1 = не смог отработать технически.
"""
import base64
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

PATTERNS = [
    ("GitHub PAT (ghp_)", re.compile(r"ghp_[A-Za-z0-9]{36}")),
    ("GitHub PAT (ghs_/ghu_/ghr_)", re.compile(r"gh[sur]_[A-Za-z0-9]{36}")),
    ("GitHub fine-grained", re.compile(r"github_pat_[A-Za-z0-9_]{22,255}")),
    ("AWS Access Key", re.compile(r"AKIA[0-9A-Z]{16}")),
    ("Slack token", re.compile(r"xox[baprs]-[A-Za-z0-9-]{10,}")),
    ("OpenAI key", re.compile(r"sk-[A-Za-z0-9T]{20,}")),
    ("Google API key", re.compile(r"AIza[0-9A-Za-z_\-]{35}")),
    ("PEM private key", re.compile(r"-----BEGIN (?:RSA |EC |DSA |OPENSSH |PGP )?PRIVATE KEY-----")),
]

TEXT_EXT = {
    ".md", ".txt", ".py", ".js", ".ts", ".yml", ".yaml", ".json", ".sh",
    ".ps1", ".bat", ".cfg", ".ini", ".toml", ".html", ".css",
    ".xml", ".csv", ".lrc", ".gitignore", ".gitattributes", ".example",
}
TEXT_NAMES = {"Dockerfile", "Makefile", "LICENSE", ".gitignore", ".nojekyll",
              ".env.example", "CODEOWNERS", "llms.txt"}
MAX_FILE = 200_000          # байт на файл — больше уже не конфиг, а данные
MAX_FILES_PER_REPO = 100    # бюджет API на репо
MAX_LOG_TAIL = 120          # строк хвоста лога на прогон

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


def scan_text(path, text, ignore_res, findings):
    for i, line in enumerate(text.splitlines(), 1):
        for name, rx in PATTERNS:
            m = rx.search(line)
            if not m:
                continue
            frag = m.group(0)
            if any(marker in line for marker in SAFE_MARKERS):
                continue
            if any(rx2.search(line) for rx2 in ignore_res):
                continue
            findings.append({"where": f"{path}:{i}", "kind": name,
                             "fragment": frag[:8] + "…" + frag[-4:]})


def repo_ignores(token, full):
    st, data = req(token, f"/repos/{full}/contents/.secret-immunity-ignore")
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


def scan_repo(token, r, findings):
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
            scan_text(f"{full}/{p}", text, ign, findings)
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
                scan_text(f"{full} [лог {run['name']}/{run['id']}]", tail, ign, findings)
    return files_n, logs_n, err_n


def main() -> int:
    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN") or ""
    owner = os.environ.get("OWNER", "rtynbirf")
    findings = []
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
                repos, pool.map(lambda x: scan_repo(token, x, findings), repos)):
            scanned_files += files_n
            scanned_logs += logs_n
            errors += err_n
            done += 1
            print(f"  [{done}/{len(repos)}] {r['full_name']}: файлов {files_n}, логов {logs_n}", flush=True)

    verdict = "НАХОДОК 0" if not findings else f"НАХОДОК {len(findings)} — P0"
    print(f"итог: {verdict} · файлов {scanned_files} · логов {scanned_logs} · ошибок {errors}")

    stamp = time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime())
    line = (f"| {stamp} | {len(repos)} | {scanned_files} | {scanned_logs} | "
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
            fh.write(f"\n## 🩸 секрет-лейкоцит\n\n{verdict}\n"
                     f"\nфайлов: {scanned_files} · логов: {scanned_logs} · репо: {len(repos)}\n")
            for f in findings[:20]:
                fh.write(f"- 🔴 `{f['where']}` — {f['kind']} — `{f['fragment']}`\n")

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


if __name__ == "__main__":
    sys.exit(main())
