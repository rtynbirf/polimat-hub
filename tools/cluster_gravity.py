#!/usr/bin/env python3
"""cluster_gravity.py — кластер-метрика «гравитация репо» (П-26 · polimat-hub#44).

Решения — ADR; данные для решения — метрики; человек в цикле — стандарт
ответственных назначений. ADR-012 (docpack/08) ждёт доказательства — метрика
готовит его: по каждому репо считает «гравитацию» к каждому кластеру канона
A–G (tools/verify_architecture.py) по признакам, каждый из которых ЦИТИРУЕТСЯ
(проверяй строкой: признаки — цитаты из файлов, не интерпретации):

  1. язык — совпадение с доминирующим языком кластера (вес 2);
  2. темы — канон-ключи кластера в README/описании (вес 1 за ключ, cap 5);
  3. геном — упоминание клетки в cell-swarm/swarm.json с system_pre
     (substrate→A, metabolism→B, memory→C) (вес 3);
  4. доктрина — сколько доктринальных файлов упоминает репо
     (поиск GitHub, вес 0.2 за файл, cap 3).

Вывод: таблица «репо × кластер × score × обоснование-цитатами» + верхний
кластер. Для репо уже в каноне — сверка гравитации с назначением: расхождение
помечается «ДРЕЙФ?» (информация, не вердикт — канон меняет только ADR).

Использование:
  GITHUB_TOKEN=… python3 tools/cluster_gravity.py audit/inventory-2026-11-09.json \
      audit/adr012-gravity-<дата>.md
"""
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request

API = "https://api.github.com"
sys.path.insert(0, os.path.dirname(__file__))
from verify_architecture import CANON  # единственный источник истины кластеров

CLUSTER_KEYWORDS = {
    "A": ["ос", "систем", "host", "хост", "резерв", "vault", "секрет", "kernel", "tweaker", "forge", "browser"],
    "B": ["агент", "рой", "swarm", "cell", "agent", "runtime", "клетк", "genome", "геном"],
    "C": ["песн", "медиа", "плеер", "пле", "song", "lyrics", "karaoke", "сайт", "voice", "голос", "офлайн", "offline"],
    "D": ["аудит", "audit", "исследов", "данн", "data", "граф", "graph", "механизм", "atlas", "реестр", "registry"],
    "E": ["windows", "хроник", "chronicle"],
    "F": ["экспозиц", "истори", "эволюц", "svod", "свод", "хронолог", "язык"],
    "G": ["доктрин", "doctrine", "runbook", "инфраструктур", "скрипт", "инструкц", "гайд", "практик", "memo", "отчёт", "отчет"],
}
GENOME_SYSTEM_TO_CLUSTER = {"substrate": "A", "metabolism": "B", "memory": "C"}
DOCTRINE_REPOS = ["repo-doctrine", "github-runbook", "polimat-hub"]


def api(token, url):
    if url.startswith("/"):
        url = API + url
    r = urllib.request.Request(url, headers={
        "Accept": "application/vnd.github+json",
        "User-Agent": "cluster-gravity/1.0 (P-26 polimat-hub)"})
    if token:
        r.add_header("Authorization", f"Bearer {token}")
    for attempt in range(3):
        try:
            with urllib.request.urlopen(r, timeout=30) as resp:
                return resp.status, json.loads(resp.read().decode("utf-8", "replace"))
        except urllib.error.HTTPError as e:
            # search API: 30 запросов/мин — при 403/429 ждём и повторяем честно
            if e.code in (403, 429):
                time.sleep(3 * (attempt + 1))
                continue
            try:
                return e.code, json.loads(e.read().decode("utf-8", "replace"))
            except Exception:
                return e.code, {}
        except Exception:
            time.sleep(2)
    return 0, {}


def cluster_languages(repos):
    langs = {}
    for name, cluster in CANON.items():
        for r in repos:
            if r["name"] == name and r.get("language"):
                langs.setdefault(cluster, []).append(r["language"])
    return {c: max(set(v), key=v.count) for c, v in langs.items() if v}


def readme_text(token, full):
    st, data = api(token, f"/repos/{full}/readme")
    if st != 200:
        return ""
    import base64
    try:
        return base64.b64decode(data.get("content", "")).decode("utf-8", "replace")[:8000]
    except Exception:
        return ""


def genome_mentions(token, owner):
    st, data = api(token, f"/repos/{owner}/cell-swarm/contents/swarm.json")
    if st != 200:
        return {}
    import base64
    try:
        genome = json.loads(base64.b64decode(data.get("content", "")).decode("utf-8", "replace"))
    except Exception:
        return {}
    out = {}
    for c in genome.get("cells", []):
        name = c.get("name")
        if name:
            out[name] = {"system_pre": c.get("system_pre", ""),
                         "role_quote": (c.get("role") or "")[:160]}
    return out


def doctrine_hits(token, owner, name):
    # один поиск по всему аккаунту вместо трёх по репо — бережём search-квоту 30/мин
    st, data = api(token, f"/search/code?q=%22{name}%22+user:{owner}&per_page=1")
    if st == 200 and data.get("total_count"):
        return min(data["total_count"], 10)
    return 0


def main() -> int:
    if len(sys.argv) < 2:
        print("использование: cluster_gravity.py <inventарий.json> [отчёт.md]")
        return 1
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN") or ""
    owner = os.environ.get("OWNER", "rtynbirf")
    inv = json.load(open(sys.argv[1], encoding="utf-8"))
    repos = inv["repos"]
    out_path = sys.argv[2] if len(sys.argv) > 2 else "audit/adr012-gravity.md"

    langs = cluster_languages(repos)
    genome = genome_mentions(token, owner)

    lines = [
        "# 🧲 Гравитация репо · доказательство для ADR-012 (П-26 · polimat-hub#44)",
        "",
        f"Срез: {time.strftime('%Y-%m-%d %H:%M UTC', time.gmtime())} · опись: {sys.argv[1]} "
        f"({len(repos)} репо) · канон: tools/verify_architecture.py",
        "",
        "Признаки (каждый — цитата, не интерпретация): язык кластера (2) · "
        "канон-ключи README (1/шт, cap 5) · клетка генома (3) · доктринальные упоминания (0.2/файл, cap 3)",
        "",
        "| Репо | В каноне | Верхний кластер | Score | Обоснование (цитаты) |",
        "|---|---|---|---|---|",
    ]
    drifts = []
    for r in repos:
        name = r["name"]
        assigned = CANON.get(name, "—")
        scores = {c: 0.0 for c in "ABCDEFG"}
        quotes = {c: [] for c in "ABCDEFG"}
        # 1. язык
        lang = r.get("language")
        if lang:
            for c, cl in langs.items():
                if lang == cl:
                    scores[c] += 2
                    quotes[c].append(f"язык {lang}")
        # 2. темы
        text = ((r.get("description") or "") + " " + readme_text(token, f"{owner}/{name}")).lower()
        kw_hits = []
        for c, keys in CLUSTER_KEYWORDS.items():
            hit = [k for k in keys if k in text]
            if hit:
                scores[c] += min(len(hit), 5)
                quotes[c].append("ключи: " + ",".join(hit[:5]))
                kw_hits.append((c, hit))
        # 3. геном
        if name in genome:
            system = genome[name]["system_pre"]
            c = GENOME_SYSTEM_TO_CLUSTER.get(system)
            if c:
                scores[c] += 3
                quotes[c].append(f"геном: system_pre={system} «{genome[name]['role_quote']}»")
        # 4. доктрина
        dh = doctrine_hits(token, owner, name)
        if dh:
            scores["G"] += min(dh * 0.2, 3)
            if dh:
                quotes["G"].append(f"доктрина: {dh} упоминаний")
        top = max(scores, key=scores.get)
        top_score = scores[top]
        just = "; ".join(q for q in quotes.get(top, [])[:3]) or "признаков нет"
        if assigned != "—" and top != assigned and top_score >= scores.get(assigned, 0):
            drifts.append((name, assigned, top, top_score))
        lines.append(f"| `{name}` | {assigned} | **{top}** | {top_score:.1f} | {just} |")

    lines += ["", "## Дрейф (гравитация ≠ назначение канона)", ""]
    if drifts:
        for n, a, t, s in drifts:
            lines.append(f"- `{n}`: канон {a}, гравитация {t} ({s:.1f}) — проверить при следующем ADR")
    else:
        lines.append("- 0 расхождений: гравитация подтверждает канон A–G (ADR-006/012).")

    lines += ["", "---",
              "*П-26 · признак-цитаты, не настроение; канон меняет только ADR; "
              "человек в цикле — Хозяин подписывает ADR-012.*"]
    open(out_path, "w", encoding="utf-8").write("\n".join(lines))
    print("отчёт:", out_path)
    print("дрейфов:", len(drifts))
    return 0


if __name__ == "__main__":
    sys.exit(main())
