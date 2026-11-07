#!/usr/bin/env python3
"""verify_architecture.py — сверка аккаунта с целевой архитектурой (ARCHITECTURE.md).

Проверяет строкой, не смыслом. Каждый вердикт — из машинных данных описи.
Использование: python3 verify_architecture.py audit/inventory-YYYY-MM-DD.json
"""
import json
import sys

# Канон кластеров: имя репозитория -> кластер (ARCHITECTURE.md, версия 2026-11-08)
CANON = {
    "polymath-os": "A", "neutral-browser": "A", "agryp": "A", "os-forge": "A",
    "H-PE11-PHOENIX": "A", "domovoy-tweaker": "A", "cell65-host": "A", "release-vault": "A",
    "nous": "B", "cell-swarm": "B", "runtime-protocol": "B", "cell-rs": "B",
    "universal-agent": "B", "commons": "B",
    "singulyar": "C", "ruvson-lyrics": "C", "ruvson-rse2": "C", "karaoke-dream": "C",
    "singulyar-llm": "C", "rtynbirf.github.io": "C", "voice-atlas-llm": "C", "rumu": "C",
    "red-thread-debt-audit": "D", "rent-mechanism-q43": "D", "polymath-atlas-v107": "D",
    "task-graph-propagator": "D", "global-video-platforms-registry": "D",
    "polymath-tools-atlas": "D", "uace-pml": "D", "polimat-task174": "D",
    "windows-chronicle": "E",
    "language-through-the-ages": "F", "web-evolution-1991-2026": "F", "edinyy-svod": "F",
    "repo-doctrine": "G", "github-runbook": "G", ".github": "G",
    "markitdown": "G", "polimat-vault": "G", "polimat-hub": "G",
}

# Запрещённые имена после реструктуризации (поглощены/удалены)
# rumu исключён из FORBIDDEN по ADR-011 (2026-11-08): восстановлен Хозяином из пломбы
# polimat-vault добавлен: поглощён в polimat-hub/vault (РАУНД 3, п.7)
FORBIDDEN = {"windows-encyclopedia", "windows-full-report", "polimat-vault"}

SIZE_WARN_KB = 500_000   # 500 МБ: цель архитектуры — ни одного дерева больше


def main() -> int:
    inv = json.load(open(sys.argv[1], encoding="utf-8"))
    repos = inv["repos"]
    names = {r["name"] for r in repos}
    failures, warnings = [], []

    unexpected = sorted(names - set(CANON) - set(FORBIDDEN))
    if unexpected:
        warnings.append(f"ВНЕ КАНОНA (нет в ARCHITECTURE.md): {unexpected}")

    still_there = sorted(names & FORBIDDEN)
    if still_there:
        failures.append(f"ПОВТОРЫ/ЗАГЛУШКИ ЕЩЁ ЖИВЫ (должны быть поглощены): {still_there}")

    for r in repos:
        if r["size_kb"] > SIZE_WARN_KB:
            warnings.append(f"ВЕС: {r['name']} = {r['size_kb']//1024} МБ > 500 МБ (медиа в git-дереве)")
        if not r["description"]:
            warnings.append(f"ОПИСАНИЕ пусто: {r['name']}")

    windows_canon = [r for r in repos if r["name"] == "windows-chronicle"]
    if len(windows_canon) != 1:
        failures.append("КАНОН E: windows-chronicle отсутствует или задвоен")

    print(f"=== СВЕРКА АРХИТЕКТУРЫ · опись {inv.get('collected_at')} ===")
    print(f"репозиториев в описи: {len(repos)}")
    print(f"по кластерам: " + ", ".join(
        f"{c}={sum(1 for r in repos if CANON.get(r['name']) == c)}"
        for c in "ABCDEFG"
    ))
    for f in failures:
        print(f"[FAIL] {f}")
    for w in warnings:
        print(f"[WARN] {w}")
    verdict = "СОГЛАСОВАНА" if not failures else "НЕ СОГЛАСОВАНА"
    print(f"ВЕРДИКТ: {verdict}  (fails={len(failures)}, warns={len(warnings)})")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
