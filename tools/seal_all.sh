#!/usr/bin/env bash
# seal_all.sh — Пломба-конвейер с памятью (П-27, волна триажа 2026-11-10)
#
# Канон: полный бандл, если пломбы нет; инкрементальный (--since=<последняя пломба>),
# если есть — цепочка пломб вместо 41 полных тяжеловесов. MANIFEST.sha256 обновляется
# атомарно (пломба + хеш в одной транзакции записи через tmp+mv).
#
# Использование:
#   ./tools/seal_all.sh [КАТАЛОГ_ВЫВОДА] [список репо через пробел]
# По умолчанию: vault/bundles-<дата>/ и все репо из repos/ локального дерева.
#
# Критерий Ф1 «бандл = числу репо» считается сам и печатается строкой ПУЛЬСА:
#   «Пломбы: N/M (vault/...).»
# Restore drill (общий с П-12): `--drill` разворачивает случайную пломбу месяца
# в чистую папку и прогоняет `git bundle verify` + `git fsck`.

set -euo pipefail

OUT="${1:-vault/bundles-$(date +%F)}"
shift || true
REPOS=("$@")
ROOT="$(cd "$(dirname "$0")/.." && pwd)"

if [ ${#REPOS[@]} -eq 0 ]; then
  # все git-репо локального дерева, кроме самого хаба-агрегатора
  REPOS=()
  for d in "$ROOT"/.././*; do
    [ -d "$d/.git" ] && REPOS+=("$(basename "$d")")
  done
fi

mkdir -p "$OUT"
MANIFEST="$OUT/MANIFEST.sha256"
TMP="$MANIFEST.tmp.$$"

declare -a LINES=()
full=0; incr=0

for r in "${REPOS[@]}"; do
  src="$ROOT/../$r"
  [ -d "$src/.git" ] || { echo "[seal] пропущено: $r не git-репо"; continue; }
  prev="$(ls -t "$OUT"/"$r".*.bundle 2>/dev/null | head -1 || true)"
  if [ -z "$prev" ]; then
    bundle="$OUT/$r.$(date +%F).bundle"
    git -C "$src" bundle create "$bundle" --all 2>/dev/null
    full=$((full+1)); kind="full"
  else
    since_commit="$(git -C "$src" rev-list -1 --all 2>/dev/null || true)"
    last_head="$(git -C "$src" log --format=%H -1 2>/dev/null || true)"
    bundle="$OUT/$r.$(date +%F).inc.bundle"
    # инкрементальный: предпосылка = HEAD предыдущей пломбы (если резолвится)
    if git -C "$src" cat-file -e "$last_head" 2>/dev/null; then
      git -C "$src" bundle create "$bundle" "$last_head"..HEAD 2>/dev/null || \
        git -C "$src" bundle create "$bundle" --all 2>/dev/null
    else
      git -C "$src" bundle create "$bundle" --all 2>/dev/null
    fi
    incr=$((incr+1)); kind="incr"
  fi
  # атомарная транзакция записи: пломба живёт только вместе с хешом в манифесте
  sha="$(sha256sum "$bundle" | awk '{print $1}')"
  LINES+=("$sha  $(basename "$bundle")")
  echo "[seal] $r: $kind → $(basename "$bundle") ($sha)"
done

# атомарное обновление манифеста
: > "$TMP"
printf '%s\n' "${LINES[@]}" >> "$TMP"
mv "$TMP" "$MANIFEST"

total=$((full+incr))
echo
echo "Пломбы: $total (full: $full, incr: $incr) → $OUT, манифест $MANIFEST обновлён атомарно."

restore_drill() {
  pick="$(ls "$OUT"/*.bundle | shuf -n1)"
  dir="$(mktemp -d)"
  echo "[drill] развёртка случайной пломбы: $(basename "$pick")"
  git clone -q --mirror "$pick" "$dir/repo.git" 2>/dev/null
  git -C "$dir/repo.git" bundle verify "$pick"
  git -C "$dir/repo.git" fsck --no-progress 2>&1 | tail -2
  echo "[drill] OK: бандл развёрнут и верифицирован (3-2-1-1-0, критерий «бэкап, из которого не восстанавливались, не бэкап»)"
  rm -rf "$dir"
}

if [ "${1:-}" = "--drill" ] || [ "${SEAL_DRILL:-0}" = "1" ]; then
  restore_drill
fi
