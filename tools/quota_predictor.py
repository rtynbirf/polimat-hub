#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Квота-предиктор «дней до 500 МБ» (П-70, polimat-hub #94).

Нативного гейджа «500 МБ» в GitHub API не существует — число синтезируется:
  1) при каждом прогоне скрипт дописывает сегодняшнее измерение в историю
     reports/quota-history.jsonl (JSON-строки: date, pool_bytes, repos);
  2) по накопленной истории линейный склон считается методом наименьших
     квадратов по последним <= 14 точкам;
  3) дней до лимита = (500 МиБ - текущий пул) / склон, и только если склон > 0.
Вердикты: меньше 7 дней — 🔴, 7-14 — 🟡, больше — 🟢; точек меньше двух —
честное «склон неизвестен: нужно ≥2 ежедневных измерений».
Только стандартная библиотека Python, сеть не нужна.
"""

import argparse
import json
import os
import sys
import tempfile
from datetime import date, datetime, timedelta, timezone

DEFAULT_HISTORY = os.path.join("reports", "quota-history.jsonl")
LIMIT_BYTES = 500 * 1024 * 1024
MAX_POINTS = 14
SLOPE_UNKNOWN = "склон неизвестен: нужно ≥2 ежедневных измерений"


def read_history(path):
    """Читает историю; битые строки пропускает с честной пометкой в stderr."""
    points = []
    if not os.path.exists(path):
        return points
    with open(path, "r", encoding="utf-8") as fh:
        for lineno, raw in enumerate(fh, 1):
            line = raw.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
                day = date.fromisoformat(str(obj["date"]))
                pool = int(obj["pool_bytes"])
                repos = int(obj.get("repos") or 0)
            except (ValueError, KeyError, TypeError):
                print("предупреждение: %s: строка %d не разобрана и пропущена" % (path, lineno),
                      file=sys.stderr)
                continue
            points.append({"date": day, "pool_bytes": pool, "repos": repos})
    merged = {}
    for point in points:
        merged[point["date"]] = point  # при повторных датах остаётся последняя
    return [merged[d] for d in sorted(merged)]


def append_measurement(path, day, pool_bytes, repos):
    """Дописывает измерение; точка за ту же дату заменяется, а не дублируется."""
    day = date.fromisoformat(str(day))
    merged = {p["date"]: p for p in read_history(path)}
    merged[day] = {"date": day, "pool_bytes": int(pool_bytes), "repos": int(repos or 0)}
    folder = os.path.dirname(path)
    if folder:
        os.makedirs(folder, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        for key in sorted(merged):
            fh.write(json.dumps({
                "date": key.isoformat(),
                "pool_bytes": merged[key]["pool_bytes"],
                "repos": merged[key]["repos"],
            }, ensure_ascii=False) + "\n")


def load_measurement(path):
    """Читает срез трёх пулов, выгруженный three_pool_hygiene.py --json."""
    with open(path, "r", encoding="utf-8") as fh:
        data = json.load(fh)
    total = data.get("pool_bytes_total")
    if total is None:
        total = sum(int(r.get("pool_bytes") or 0) for r in (data.get("repos") or []))
        total += int(data.get("packages_unbound_bytes") or 0)
    repos = len(data.get("repos") or [])
    return int(total), repos


def ols_slope(series):
    """МНК по точкам (порядковый день, байты); None, если склон не определить."""
    n = len(series)
    if n < 2:
        return None
    mean_x = sum(x for x, _ in series) / float(n)
    mean_y = sum(y for _, y in series) / float(n)
    sxx = sum((x - mean_x) ** 2 for x, _ in series)
    if sxx == 0:
        return None
    sxy = sum((x - mean_x) * (y - mean_y) for x, y in series)
    return sxy / sxx


def predict(points, current_pool, limit_bytes=LIMIT_BYTES, max_points=MAX_POINTS):
    """(склон байт/день, дней до лимита, вердикт); дней None означает «н/д»."""
    if max_points is not None and max_points > 0 and len(points) > max_points:
        tail = points[-max_points:]
    else:
        tail = points
    series = [(p["date"].toordinal(), p["pool_bytes"]) for p in tail]
    slope = ols_slope(series)
    if slope is None:
        return None, None, "н/д"
    if current_pool >= limit_bytes:
        return slope, 0.0, "🔴"
    if slope <= 0:
        return slope, None, "🟢"
    days = (limit_bytes - current_pool) / slope
    if days < 7:
        verdict = "🔴"
    elif days <= 14:
        verdict = "🟡"
    else:
        verdict = "🟢"
    return slope, days, verdict


def fmt_mib(num_bytes):
    return "%.1f МБ" % (num_bytes / (1024.0 * 1024.0))


def fmt_days(days):
    return "н/д" if days is None else "%.1f" % days


def selftest():
    """Проверка формул и вердиктов: инъекция искусственного склона без сети."""
    checks = 0

    def check(cond, message):
        nonlocal checks
        if not cond:
            raise AssertionError("самопроверка провалена: " + message)
        checks += 1

    mib = 1024 * 1024
    base = date(2025, 6, 1)

    def synth(n_points, start_pool, step):
        return [{"date": base + timedelta(days=i), "pool_bytes": start_pool + i * step, "repos": 3}
                for i in range(n_points)]

    # 1. Инъекция склона: 20 МБ/день, текущий пул 400 МБ -> дней ~5, вердикт 🔴.
    points = synth(9, 400 * mib - 8 * 20 * mib, 20 * mib)
    check(points[-1]["pool_bytes"] == 400 * mib, "последняя точка инъекции равна 400 МБ")
    slope, days, verdict = predict(points, 400 * mib)
    check(slope is not None and abs(slope - 20 * mib) < 0.001, "склон инъекции 20 МБ/день")
    check(days is not None and abs(days - 5.0) < 0.01, "дней ~5 при пуле 400 МБ и склоне 20 МБ/день")
    check(verdict == "🔴", "вердикт 🔴 при ~5 днях")

    # 2. Меньше двух точек — честное «склон неизвестен».
    check(SLOPE_UNKNOWN == "склон неизвестен: нужно ≥2 ежедневных измерений",
          "формулировка про недостаток точек")
    slope, days, verdict = predict(points[:1], 400 * mib)
    check(slope is None and days is None and verdict == "н/д", "одна точка -> склон неизвестен, н/д")

    # 3. Отрицательный склон: до лимита не растёт, предсказания нет.
    slope, days, verdict = predict(synth(5, 400 * mib, -5 * mib), 380 * mib)
    check(slope is not None and slope < 0 and days is None and verdict == "🟢",
          "убывающий пул -> дней н/д, 🟢")

    # 4. Границы вердиктов: ровно 7 -> 🟡, ровно 14 -> 🟡, 15 -> 🟢.
    def case(current, step):
        return predict(synth(10, current - 9 * step, step), current)

    _, days, verdict = case(486 * mib, 2 * mib)
    check(abs(days - 7.0) < 0.01 and verdict == "🟡", "ровно 7 дней -> 🟡")
    _, days, verdict = case(472 * mib, 2 * mib)
    check(abs(days - 14.0) < 0.01 and verdict == "🟡", "ровно 14 дней -> 🟡")
    _, days, verdict = case(470 * mib, 2 * mib)
    check(abs(days - 15.0) < 0.01 and verdict == "🟢", "15 дней -> 🟢")

    # 5. Пул на лимите или выше -> 0 дней и 🔴.
    slope, days, verdict = predict(synth(3, 500 * mib, 1 * mib), 505 * mib)
    check(days == 0.0 and verdict == "🔴", "пул >= лимита -> 0 дней, 🔴")

    # 6. Файл истории: запись, дедупликация по дате, формат строк, битые строки.
    with tempfile.TemporaryDirectory() as tmp:
        hist = os.path.join(tmp, "reports", "quota-history.jsonl")
        append_measurement(hist, "2025-06-10", 100, 2)
        append_measurement(hist, "2025-06-11", 200, 2)
        append_measurement(hist, "2025-06-11", 250, 4)
        loaded = read_history(hist)
        check(len(loaded) == 2, "дедупликация по дате")
        check(loaded[-1]["pool_bytes"] == 250 and loaded[-1]["repos"] == 4,
              "точка за ту же дату заменяется")
        with open(hist, "r", encoding="utf-8") as fh:
            lines = [json.loads(ln) for ln in fh if ln.strip()]
        check(lines == [{"date": "2025-06-10", "pool_bytes": 100, "repos": 2},
                        {"date": "2025-06-11", "pool_bytes": 250, "repos": 4}],
              "формат строк истории: date, pool_bytes, repos")
        with open(hist, "a", encoding="utf-8") as fh:
            fh.write("мусорная строка\n")
        check(len(read_history(hist)) == 2, "битая строка пропускается")

    # 7. Разбор среза от three_pool_hygiene (--from-json).
    with tempfile.TemporaryDirectory() as tmp:
        cut = os.path.join(tmp, "pool.json")
        with open(cut, "w", encoding="utf-8") as fh:
            json.dump({"pool_bytes_total": 3 * mib,
                       "repos": [{"repo": "a"}, {"repo": "b"}, {"repo": "c"}]}, fh)
        total, repos_n = load_measurement(cut)
        check(total == 3 * mib and repos_n == 3, "разбор JSON-среза пула")

    print("SELFTEST OK (%d проверок)" % checks)
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="quota_predictor",
        description="Предиктор «дней до 500 МБ»: история измерений + линейный склон (МНК).")
    parser.add_argument("--current-bytes", type=int,
                        help="сегодняшний пул, байт (артефакты + Packages)")
    parser.add_argument("--repos", type=int, help="число репозиториев в замере, для истории")
    parser.add_argument("--from-json", metavar="ПУТЬ",
                        help="взять замер из JSON-среза three_pool_hygiene.py")
    parser.add_argument("--history", metavar="ПУТЬ", default=DEFAULT_HISTORY,
                        help="файл истории (по умолчанию %(default)s)")
    parser.add_argument("--limit-bytes", type=int, default=LIMIT_BYTES,
                        help="лимит пула, байт (по умолчанию %(default)s)")
    parser.add_argument("--max-points", type=int, default=MAX_POINTS,
                        help="сколько последних точек входит в склон (по умолчанию %(default)s)")
    parser.add_argument("--no-append", action="store_true",
                        help="не менять историю, только проанализировать")
    parser.add_argument("--selftest", action="store_true",
                        help="офлайн-самопроверка с инъекцией склона, без сети")
    args = parser.parse_args(argv)

    if args.selftest:
        try:
            return selftest()
        except AssertionError as exc:
            print(str(exc), file=sys.stderr)
            return 1

    current = None
    repos = 0
    if args.from_json:
        current, repos = load_measurement(args.from_json)
    if args.current_bytes is not None:
        current = args.current_bytes  # явный ключ важнее --from-json
    if args.repos is not None:
        repos = args.repos

    if current is not None and not args.no_append:
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        append_measurement(args.history, today, current, repos)
        print("история: точка за %s записана в %s" % (today, args.history), file=sys.stderr)

    points = read_history(args.history)
    print("история: %s, валидных точек: %d" % (args.history, len(points)))
    if not points:
        print("история пуста: нужен хотя бы один замер (--current-bytes или --from-json)")
        print("дней до 500 МБ: н/д")
        print("вердикт: н/д (мало данных)")
        return 0

    if current is None:
        current = points[-1]["pool_bytes"]
        print("свежий замер не передан — берётся последняя точка истории", file=sys.stderr)

    shown_repos = repos if repos else points[-1]["repos"]
    print("текущий пул: %d байт (%s); репозиториев в замере: %s" % (
        current, fmt_mib(current), shown_repos if shown_repos else "неизвестно"))

    slope, days, verdict = predict(points, current, args.limit_bytes, args.max_points)
    if slope is None:
        print(SLOPE_UNKNOWN)
    else:
        if args.max_points and args.max_points > 0:
            tail_used = min(len(points), args.max_points)
        else:
            tail_used = len(points)
        sign = "-" if slope < 0 else ""
        print("склон: %.1f байт/день (%s%s/день) по последним %d точкам" % (
            slope, sign, fmt_mib(abs(slope)), tail_used))
    print("дней до 500 МБ: %s" % fmt_days(days))
    reason = {
        "🔴": "меньше 7 дней до лимита",
        "🟡": "7-14 дней до лимита",
        "🟢": "больше 14 дней или пул не растёт",
        "н/д": "мало данных",
    }
    print("вердикт: %s (%s)" % (verdict, reason.get(verdict, "—")))
    return 0


if __name__ == "__main__":
    sys.exit(main())
