#!/usr/bin/env python3
"""
РИТУАЛ ДОМА · исполняющий автомат (закон дома №13, canon repo-doctrine/25).
Формула: ПОРАБОТАЛ → СДЕЛАЛ → УБОРКА → ЧИСТ. Автомат не останавливается в грязном состоянии.
Прогон: невод фактов → уборка следов → пломба вердикта в PULSE.md (маркеры RITUAL).
Stdlib only. Токен из env GH_TOKEN (не хардкод — У-1). Наследные чужие следы не трогает (У-5).
"""
import os, re, json, time, base64, urllib.request

H = 'https://api.github.com'
TOK = os.environ['GH_TOKEN']
OWNER = 'rtynbirf'
PULSE_REPO = 'polimat-hub'
PULSE_PATH = 'PULSE.md'
BEGIN, END = '<!-- RITUAL:BEGIN -->', '<!-- RITUAL:END -->'

def gh(url, method='GET', body=None):
    r = urllib.request.Request(url, method=method)
    r.add_header('Authorization', f'token {TOK}')
    r.add_header('Accept', 'application/vnd.github+json')
    data = json.dumps(body).encode() if body is not None else None
    try:
        with urllib.request.urlopen(r, data) as resp:
            return resp.status, json.loads(resp.read().decode() or 'null')
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode() or 'null')
        except Exception:
            return e.code, None

REPORT_PAT = re.compile(r'(ОТЧЁТ О ПРОДЕЛАННОМ)|((ОТЧЁТ|отчёт).*Волна ×)')
DOCIOR_CLEAN_PAT = re.compile(r'МЕСТА К ВЫЛИЗЫВАНИЮ:\s*публичных 0')

# ---------- S1: РАЗВЕДКА (невод) ----------
now = time.gmtime()
def age_hours(iso):
    return (time.mktime(now) - time.mktime(time.strptime(iso[:19], '%Y-%m-%dT%H:%M:%S'))) / 3600

# нотификации
st, notifs = gh(f'{H}/notifications?all=false&per_page=100')
notifs = notifs if st == 200 else []
unread_total = len(notifs)

# открытые issues флота (search, дешевле перебора)
st, sr = gh(f"{H}/search/issues?q=user:{OWNER}+state:open+type:issue&per_page=100&sort=created&order=asc")
open_issues = sr.get('items', []) if st == 200 else []
# search-индекс отстаёт: верифицируем состояние каждого живым API перед действием
report_targets, docior_targets, legit = [], [], []
for it in open_issues:
    repo_full = it['repository_url'].split(f'{H}/repos/')[-1]
    title = it['title'] or ''
    body = it['body'] or ''
    st2, live = gh(f'{H}/repos/{repo_full}/issues/{it["number"]}')
    if st2 != 200 or live.get('state') != 'open':
        continue
    if REPORT_PAT.search(title) and age_hours(it['created_at']) > 6:
        report_targets.append((repo_full, it['number'], title))
    elif repo_full == f'{OWNER}/.github' and title.startswith('🛡 ДОЗИОР') and DOCIOR_CLEAN_PAT.search(body) and age_hours(it['created_at']) > 1:
        docior_targets.append((repo_full, it['number'], title))
    else:
        legit.append((repo_full, it['number'], title[:60]))

# красные последние прогоны активных клеток (пуш < 7 дней)
st, repos = gh(f'{H}/users/{OWNER}/repos?per_page=100&sort=pushed')
repos = [r for r in (repos if st == 200 else []) if not r['archived'] and age_hours(r['pushed_at']) < 24*7]
red = {}
for r in repos:
    st2, runs = gh(f'{H}/repos/{r["full_name"]}/actions/runs?per_page=12')
    if st2 != 200:
        continue
    seen, last_by_wf = 0, {}
    for run in runs.get('workflow_runs', []):
        if run['name'] in last_by_wf:
            continue
        last_by_wf[run['name']] = run
    for name, run in last_by_wf.items():
        if run['conclusion'] == 'failure':
            red.setdefault(r['name'], []).append({'wf': name, 'at': run['created_at'][:16]})
    time.sleep(0.05)
red_total = sum(len(v) for v in red.values())

print(json.dumps({'unread': unread_total, 'open_legit': len(legit),
                  'report_targets': [f'{a}#{b}' for a, b, _ in report_targets],
                  'docior_targets': [f'{a}#{b}' for a, b, _ in docior_targets],
                  'red_last_runs': red_total}, ensure_ascii=False))

# ---------- S2: РАБОТА (уборка следов) ----------
closed_now = []
for repo_full, n, title in report_targets:
    body = (f'🏠 **Ритуал дома · авто-уборка следа (закон №13, прогон {time.strftime("%Y-%m-%dT%H:%M:%SZ", now)}).** '
            f'Отчёт волны «{title[:80]}» издан и исполнен: отчёт живёт файлом в репо, а issue — след, который убирается сам. '
            f'Хвосты — в мастер-реестре {OWNER}/github-runbook#10.')
    gh(f'{H}/repos/{repo_full}/issues/{n}/comments', 'POST', {'body': body})
    st3, _ = gh(f'{H}/repos/{repo_full}/issues/{n}', 'PATCH', {'state': 'closed', 'state_reason': 'completed'})
    if st3 == 200:
        closed_now.append(f'{repo_full}#{n}')

for repo_full, n, title in docior_targets:
    body = (f'🏠 **Ритуал дома · авто-уборка следа (закон №13).** Вердикт дозора чист («МЕСТА К ВЫЛИЗЫВАНИЮ: публичных 0») — '
            f'авто-issue с чистым вердиктом убирается сам; следующий дозор откроет новый только при грязи. Тишина = чистота.')
    gh(f'{H}/repos/{repo_full}/issues/{n}/comments', 'POST', {'body': body})
    st3, _ = gh(f'{H}/repos/{repo_full}/issues/{n}', 'PATCH', {'state': 'closed', 'state_reason': 'completed'})
    if st3 == 200:
        closed_now.append(f'{repo_full}#{n}')

# свои ci_activity-нотификации — подметаем (наследные/mention не трогаем)
swept = 0
for n in notifs:
    if n.get('reason') == 'ci_activity':
        st4, _ = gh(f"{H}/notifications/threads/{n['id']}", 'PATCH')
        if st4 in (200, 205):
            swept += 1
            time.sleep(0.05)
st, after = gh(f'{H}/notifications?all=false&per_page=100')
for _ in range(3):
    if st == 200:
        break
    time.sleep(5)
    st, after = gh(f'{H}/notifications?all=false&per_page=100')
unread_after = len(after) if st == 200 else -1

# ---------- S3: ПЛОМБА в PULSE.md ----------
verdict = 'ЧИСТ' if (unread_after == 0 and red_total == 0 and len(legit) == 0) else 'РАБОТА ПРОДОЛЖАЕТСЯ'
block_lines = [
    BEGIN,
    f'- РИТУАЛ (закон дома №13, canon repo-doctrine/25): автомат {time.strftime("%Y-%m-%dT%H:%M:%SZ", now)} · вердикт **{verdict}**',
    f'- Открытых issues флота: {len(legit)} легитимных (трекеры/очередь/решение-Хозяина) · убрано следом за прогон: {len(closed_now)}' + (f' ({", ".join(closed_now[:6])})' if closed_now else ''),
    f'- Нотификации: unread {unread_after} (своих ci_activity подметено {swept}; наследные чужие не тронуты — У-5)',
    f'- Красных последних прогонов: {red_total} в {len(red)} клетках (каждый несёт пломбу или ждёт свою волну)' + (' — ' + ', '.join(f'{k}:{len(v)}' for k, v in list(red.items())[:5]) if red else ''),
    END,
]
block = '\n'.join(block_lines) + '\n'

st, pf = gh(f'{H}/repos/{OWNER}/{PULSE_REPO}/contents/{PULSE_PATH}?ref=main')
assert st == 200, st
pulse = base64.b64decode(pf['content']).decode()
if BEGIN in pulse and END in pulse:
    new_pulse = re.sub(re.escape(BEGIN) + r'.*?' + re.escape(END), block.strip(), pulse, flags=re.S)
else:
    new_pulse = pulse.rstrip() + '\n\n' + block
if new_pulse != pulse:
    st5, r5 = gh(f'{H}/repos/{OWNER}/{PULSE_REPO}/contents/{PULSE_PATH}', 'PUT', {
        'message': f'ritual: пломба вердикта {verdict} — issues {len(legit)}/следы {len(closed_now)}/unread {unread_after}/красные {red_total} [skip ci]',
        'content': base64.b64encode(new_pulse.encode()).decode(),
        'sha': pf['sha'], 'branch': 'main'})
    print('PULSE PUT:', st5, 'commit', (r5 or {}).get('commit', {}).get('sha', '')[:10])
else:
    print('PULSE без изменений')

# ---------- S4: вердикт ----------
print(json.dumps({'verdict': verdict, 'closed_now': closed_now, 'swept_notifications': swept,
                  'unread_after': unread_after, 'red_last_runs': red_total}, ensure_ascii=False))
