#!/usr/bin/env python3
"""make_bundles.py — батч пломб-бандлов Ф1: bare-клон → git bundle → SHA256 → MANIFEST.
Только лёгкие репо (бандл ≤ лимита). Токен из GITHUB_TOKEN. Свидетельства в stdout.
"""
import hashlib
import json
import os
import subprocess
import sys

TOKEN = os.environ["GITHUB_TOKEN"]
WORK = "/tmp/bundles-work"
OUT = "/home/z/my-project/workspace/polimat/hub/vault/bundles-2026-11-08"
LIMIT_MB = float(sys.argv[1]) if len(sys.argv) > 1 else 2.0
# Ярус B (>10 МБ бандла) — в hub git НЕ кладём: пломба = SHA256 + офлайн-копия у Хозяина
EXCLUDE = {"singulyar", "voice-atlas-llm", "ruvson-lyrics"}

os.makedirs(WORK, exist_ok=True)
os.makedirs(OUT, exist_ok=True)

AUTH_URL = f"https://x-access-token:{TOKEN}@github.com/rtynbirf"
repos = json.load(open('/home/z/my-project/workspace/polimat/hub/audit/inventory-2026-11-08-kozyaki.json'))['repos']

done, skipped, failed = [], [], []
manifest_lines = []

for r in repos:
    name = r['name']
    if name in EXCLUDE:
        skipped.append((name, 'ярус B — бандл вне hub git (офлайн+SHA256)'))
        continue
    dst = os.path.join(WORK, name + '.git')
    try:
        if not os.path.isdir(dst):
            subprocess.run(['git', 'clone', '--bare', f'{AUTH_URL}/{name}.git', dst],
                           check=True, capture_output=True, timeout=600)
        bundle = os.path.join(OUT, f'{name}.bundle')
        subprocess.run(['git', '-C', dst, 'bundle', 'create', bundle, '--all'],
                       check=True, capture_output=True, timeout=600)
        size_mb = os.path.getsize(bundle) / 1e6
        if size_mb > LIMIT_MB:
            os.remove(bundle)
            skipped.append((name, f'бандл {size_mb:.1f} МБ > {LIMIT_MB}'))
            continue
        h = hashlib.sha256(open(bundle, 'rb').read()).hexdigest()
        manifest_lines.append(f'{h}  {name}.bundle')
        done.append((name, f'{size_mb:.2f} МБ', h[:12]))
    except Exception as e:
        failed.append((name, str(e)[:90]))

man_path = os.path.join(OUT, 'MANIFEST.sha256')
if os.path.exists(man_path):
    existing = [l for l in open(man_path).read().splitlines() if l.strip()]
    seen = {l.split('  ')[-1] for l in existing}
    for l in manifest_lines:
        if l.split('  ')[-1] not in seen:
            existing.append(l)
    manifest_lines = sorted(set(existing))
open(man_path, 'w').write('\n'.join(manifest_lines) + '\n')

print(f'=== ПЛОМБЫ {len(done)} ===')
for n, s, h in done:
    print(f'  OK {n}: {s} sha256:{h}')
print(f'=== ПРОПУЩЕНО {len(skipped)} ===')
for n, why in skipped:
    print(f'  -- {n}: {why}')
if failed:
    print(f'=== ПРОВАЛЫ {len(failed)} ===')
    for n, e in failed:
        print(f'  XX {n}: {e}')
