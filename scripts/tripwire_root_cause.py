#!/usr/bin/env python3
"""П-23 · Оракул корня: единый диагноз из логов, один патч на всех (polimat-hub#41).

Мировая практика (arXiv:2602.02307): у «одинаковых» красных чаще всего один
корень; нормализуй логи и кластеризуй, а не читай глазами шесть раз.

Метод:
  1. у каждого репо-цели взять последние прогоны; красные — лог-хвосты;
  2. нормализовать: срезать метки времени, SHA, абсолютные пути, числа;
  3. искать общие подстроки ошибок между репо (difflib, проверяй строкой);
  4. гипотеза корня — самая длинная общая нормализованная подстрока
     с ранжированием по коэффициенту схожести.

Приёмка (polimat-hub#41): последний run = success ×N; оракул выдал общий корень
с совпадением > порога ИЛИ честно доложил «все зелёные — корней нет» (артефакт).

Цели (карта W-AUD-02): task-graph-propagator, rent-mechanism-q43,
red-thread-debt-audit, polimat-task174, web-evolution-1991-2026, uace-pml.
"""
import difflib
import io
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
import zipfile

API = "https://api.github.com"
DEFAULT_TARGETS = [
    "task-graph-propagator",
    "rent-mechanism-q43",
    "red-thread-debt-audit",
    "polimat-task174",
    "web-evolution-1991-2026",
    "uace-pml",
]
THRESHOLD = 0.55   # порог схожести нормализованных хвостов


def req(token, path_or_url):
    url = path_or_url if path_or_url.startswith("http") else API + path_or_url
    r = urllib.request.Request(url)
    r.add_header("Accept", "application/vnd.github+json")
    r.add_header("User-Agent", "tripwire-root-cause/1.0 (P-23 polimat-hub)")
    if token:
        r.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(r, timeout=45) as resp:
            body = resp.read()
            if body[:1] in (b"{", b"["):
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


def log_tail(token, full, run_id, lines=80):
    """Хвост лога прогона: 302 → блоб → zip → последние строки каждого шага."""
    r = urllib.request.Request(f"{API}/repos/{full}/actions/runs/{run_id}/logs")
    r.add_header("Authorization", f"Bearer {token}")
    r.add_header("User-Agent", "tripwire-root-cause/1.0")

    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *a, **k):
            return None
    try:
        opener = urllib.request.build_opener(NoRedirect)
        opener.open(r, timeout=45)
        return ""
    except urllib.error.HTTPError as e:
        loc = e.headers.get("Location") if e.code in (301, 302, 303, 307) else None
        if not loc:
            return ""
        st, blob = req(token, loc)
        if st != 200 or not isinstance(blob, bytes):
            return ""
        try:
            z = zipfile.ZipFile(io.BytesIO(blob))
        except Exception:
            return ""
        parts = []
        for n in z.namelist():
            if not n.endswith(".txt"):
                continue
            try:
                txt = z.read(n).decode("utf-8", "replace")
            except Exception:
                continue
            parts.extend(txt.splitlines()[-lines:])
        return "\n".join(parts)


def normalize(text):
    """Срезаем всё, что мешает строковому сравнению: время, SHA, пути, числа."""
    text = re.sub(r"^\d{4}-\d{2}-\d{2}T[\d:.]+Z?\s*", "", text, flags=re.M)
    text = re.sub(r"##\[[a-z ]+\]", "", text)
    text = re.sub(r"[0-9a-f]{7,40}", "<SHA>", text)
    text = re.sub(r"/[\w.\-/]+", "<PATH>", text)
    text = re.sub(r"\d+", "<N>", text)
    text = re.sub(r"\s+", " ", text)
    # только содержательные строки: ошибки/фаталы/exit
    keep = [ln.strip() for ln in text.split(" <N> ") if ln.strip()]
    err = [ln for ln in keep if re.search(
        r"error|fail|fatal|exit code|refused|denied|not found|quota|limit", ln, re.I)]
    return " ".join(err) if err else " ".join(keep[:40])


def main() -> int:
    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN") or ""
    owner = os.environ.get("OWNER", "rtynbirf")
    targets = [t for t in os.environ.get("TARGETS", "").split(",") if t] or DEFAULT_TARGETS

    report = {"generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
              "targets": targets, "repos": [], "pairs": [], "hypothesis": None}
    tails = {}

    for name in targets:
        full = f"{owner}/{name}"
        st, runs = req(token, f"/repos/{full}/actions/runs?per_page=6")
        entry = {"repo": full, "last_conclusion": None, "red_runs": []}
        if st == 200:
            wr = runs.get("workflow_runs", [])
            if wr:
                entry["last_conclusion"] = wr[0].get("conclusion") or wr[0].get("status")
            for run in wr:
                concl = run.get("conclusion") or run.get("status")
                if concl in ("failure", "timed_out", "startup_failure"):
                    tail = log_tail(token, full, run["id"])
                    entry["red_runs"].append({"run_id": run["id"], "name": run["name"],
                                              "conclusion": concl})
                    if tail:
                        tails[full] = (tail, run["id"])
                    break
        report["repos"].append(entry)
        print(f"{full}: последний = {entry['last_conclusion']}")

    red = [r for r in report["repos"] if r["last_conclusion"] == "failure"]
    if len(red) == 0:
        report["hypothesis"] = ("корней нет: все " + str(len(targets)) +
                                " целей зелёные — оракул ничего не лечит (честный ноль)")
        print("оракул корня:", report["hypothesis"])
    elif len(tails) >= 2:
        keys = list(tails)
        best = None
        for i in range(len(keys)):
            for j in range(i + 1, len(keys)):
                a, b = normalize(tails[keys[i]][0]), normalize(tails[keys[j]][0])
                sm = difflib.SequenceMatcher(None, a, b)
                # длиннейшая общая подстрока нормализованных хвостов
                m = sm.find_longest_match(0, len(a), 0, len(b))
                common = a[m.a:m.a + m.size].strip()
                ratio = round(sm.ratio(), 3)
                report["pairs"].append({"a": keys[i], "b": keys[j],
                                        "ratio": ratio,
                                        "common": common[:300] if m.size else ""})
                if m.size >= 40 and (best is None or m.size > best["size"]):
                    best = {"size": m.size, "a": keys[i], "b": keys[j],
                            "ratio": ratio, "common": common[:300]}
        if best and best["ratio"] >= THRESHOLD:
            report["hypothesis"] = (f"общий корень у {best['a']} и {best['b']}: "
                                    f"схожесть {best['ratio']} ≥ {THRESHOLD}; "
                                    f"общая подстрока: «{best['common']}»")
        else:
            report["hypothesis"] = ("общего корня не найдено — красные разных корней, "
                                    "лечить по-отдельности (пары ниже)")
        print("оракул корня:", report["hypothesis"])

    out = os.environ.get("ROOT_CAUSE_JSON", "tripwire-root-cause.json")
    json.dump(report, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("артефакт:", out)

    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as fh:
            fh.write("\n## 🩺 Оракул корня (П-23)\n\n")
            for r in report["repos"]:
                fh.write(f"- `{r['repo']}`: последний = **{r['last_conclusion']}**\n")
            fh.write(f"\n**Гипотеза:** {report['hypothesis']}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
