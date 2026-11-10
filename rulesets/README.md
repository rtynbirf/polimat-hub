# rulesets/ — polimat-guard как код + тираж

П-31 (polimat-hub#49), W-AUD-15 (polimat-hub#16), П-75 (polimat-hub#99).
Волна триажа polimat-hub 2026-11-10. Только факты GitHub API (fine-grained
PAT с Administration:read; пробы POST — см. ниже).

## Состав

- **polimat-guard.json** — эталонный экспорт ruleset `polimat-guard`
  (источник: `rtynbirf/cell-swarm`, id 26772136, GET
  `/repos/rtynbirf/cell-swarm/rulesets/26772136` 2026-11-10). Поле `source`
  — плейсхолдер `__REPO_FULL_NAME__`, заменяется скриптом на целевое репо.
  Суть: target=branch, условия — только `~DEFAULT_BRANCH`, правила —
  запрет `deletion` и `non_fast_forward` (force-push), enforcement=active,
  bypass_actors пуст.
- **apply_ruleset.py** — консольный скрипт: читает JSON, POST-ит на целевое
  репо, печатает HTTP-коды (201 создан / 422 уже есть или ошибка / 403 нет
  прав). Токен — из env `GITHUB_TOKEN` (или `GH_TOKEN`). Нужен классический
  PAT со scope `repo` либо fine-grained c **Administration:write**.

## Как применять

```bash
# один репо
GITHUB_TOKEN=ghp_... python3 rulesets/apply_ruleset.py rtynbirf/<repo>

# сухой прогон (показать тело POST)
python3 rulesets/apply_ruleset.py rtynbirf/<repo> --dry-run

# список целей без polimat-guard (см. инвентарь ниже)
GITHUB_TOKEN=ghp_... python3 rulesets/apply_ruleset.py rtynbirf/<repo1> rtynbirf/<repo2> ...
```

Идемпотентность: повторный POST того же имени вернёт 422 — скрипт это
печатает и не считает фатальным. На archived-репо (rumu) rulesets не
создаются — репо исключено из тиража.

## Факт пробы прав (2026-11-10)

POST `/repos/rtynbirf/language-through-the-ages/rulesets` и
`/repos/rtynbirf/red-thread-debt-audit/rulesets` fine-grained токеном
→ **403** `Resource not accessible by personal access token`; GET rulesets
тем же токеном → 200. Вывод: у токена есть Administration:read, нет
Administration:write → тираж остановлен до выдачи write-права. Роллаут не
выполнен ни на одном репо (0 создано агентом в этой волне).

## Инвентарь (замер 2026-11-10, GET /repos/*/rulesets, fine-grained Bearer)

Всего репо у `rtynbirf`: **51**, приватных: **0** (premise issues учтена),
archived: 1 (`rumu`, исключён). Сканировано не-archived публичных: **50**.

- С `polimat-guard` уже стоит: **25** репо.
- Без `polimat-guard`: **25** репо (у них ruleset
  `автопилот: защита primary (OSPS-AC-03.01)` либо `main-guard` на combain-v2).

### С `polimat-guard` (25)

- `rtynbirf/.github`
- `rtynbirf/agryp`
- `rtynbirf/cell-rs`
- `rtynbirf/cell-swarm`
- `rtynbirf/cell65-host`
- `rtynbirf/commons`
- `rtynbirf/domovoy-tweaker`
- `rtynbirf/global-video-platforms-registry`
- `rtynbirf/karaoke-dream`
- `rtynbirf/markitdown`
- `rtynbirf/neutral-browser`
- `rtynbirf/os-forge`
- `rtynbirf/polymath-atlas-v107`
- `rtynbirf/polymath-gen`
- `rtynbirf/polymath-os`
- `rtynbirf/polymath-tools-atlas`
- `rtynbirf/release-vault`
- `rtynbirf/rtynbirf`
- `rtynbirf/rtynbirf.github.io`
- `rtynbirf/runtime-protocol`
- `rtynbirf/ruvson-rse2`
- `rtynbirf/singulyar`
- `rtynbirf/singulyar-llm`
- `rtynbirf/universal-agent`
- `rtynbirf/voice-atlas-llm`

### Без `polimat-guard` (25) — цели тиража

- `rtynbirf/H-PE11-PHOENIX`
- `rtynbirf/POLYMATH-ATLAS-GESTALT-CANON`
- `rtynbirf/combain-v2`
- `rtynbirf/domovenok`
- `rtynbirf/edinyy-svod`
- `rtynbirf/github-runbook`
- `rtynbirf/language-through-the-ages`
- `rtynbirf/nous`
- `rtynbirf/polimat-hub`
- `rtynbirf/polimat-task174`
- `rtynbirf/polymat-hive`
- `rtynbirf/polymath-atlas`
- `rtynbirf/polymath-multiagent`
- `rtynbirf/polymath-stckg-core`
- `rtynbirf/red-thread-debt-audit`
- `rtynbirf/rent-mechanism-q43`
- `rtynbirf/repo-doctrine`
- `rtynbirf/revo`
- `rtynbirf/ruvson-lyrics`
- `rtynbirf/task-graph-propagator`
- `rtynbirf/uace-pml`
- `rtynbirf/uace-polymat`
- `rtynbirf/web-evolution-1991-2026`
- `rtynbirf/windows-chronicle`
- `rtynbirf/yazyk-skvoz-epohi`

### Полная карта «репо → rulesets»

| Репо | Rulesets (имя, id, enforcement) |
|---|---|
| `rtynbirf/.github` | `polimat-guard` (id 26772169, active); `автопилот: защита primary (OSPS-AC-03.01)` (id 26897374, active) |
| `rtynbirf/H-PE11-PHOENIX` | `автопилот: защита primary (OSPS-AC-03.01)` (id 26949781, active) |
| `rtynbirf/POLYMATH-ATLAS-GESTALT-CANON` | `автопилот: защита primary (OSPS-AC-03.01)` (id 26949794, active) |
| `rtynbirf/agryp` | `polimat-guard` (id 26772143, active); `автопилот: защита primary (OSPS-AC-03.01)` (id 26897378, active) |
| `rtynbirf/cell-rs` | `polimat-guard` (id 26772145, active); `автопилот: защита primary (OSPS-AC-03.01)` (id 26897382, active) |
| `rtynbirf/cell-swarm` | `polimat-guard` (id 26772136, active); `автопилот: защита primary (OSPS-AC-03.01)` (id 26897384, active) |
| `rtynbirf/cell65-host` | `polimat-guard` (id 26772146, active); `автопилот: защита primary (OSPS-AC-03.01)` (id 26897387, active) |
| `rtynbirf/combain-v2` | `main-guard: force-push/deletion ban + required checks` (id 26926982, active) |
| `rtynbirf/commons` | `polimat-guard` (id 26772154, active); `автопилот: защита primary (OSPS-AC-03.01)` (id 26897388, active) |
| `rtynbirf/domovenok` | `автопилот: защита primary (OSPS-AC-03.01)` (id 26949777, active) |
| `rtynbirf/domovoy-tweaker` | `polimat-guard` (id 26772162, active); `автопилот: защита primary (OSPS-AC-03.01)` (id 26897391, active) |
| `rtynbirf/edinyy-svod` | `автопилот: защита primary (OSPS-AC-03.01)` (id 26949779, active) |
| `rtynbirf/github-runbook` | `автопилот: защита primary (OSPS-AC-03.01)` (id 26949780, active) |
| `rtynbirf/global-video-platforms-registry` | `polimat-guard` (id 26772147, active); `автопилот: защита primary (OSPS-AC-03.01)` (id 26897400, active) |
| `rtynbirf/karaoke-dream` | `polimat-guard` (id 26772168, active); `автопилот: защита primary (OSPS-AC-03.01)` (id 26897409, active) |
| `rtynbirf/language-through-the-ages` | `автопилот: защита primary (OSPS-AC-03.01)` (id 26949782, active) |
| `rtynbirf/markitdown` | `polimat-guard` (id 26797332, active); `автопилот: защита primary (OSPS-AC-03.01)` (id 26897415, active) |
| `rtynbirf/neutral-browser` | `polimat-guard` (id 26772141, active); `автопилот: защита primary (OSPS-AC-03.01)` (id 26897419, active) |
| `rtynbirf/nous` | `автопилот: защита primary (OSPS-AC-03.01)` (id 26949783, active) |
| `rtynbirf/os-forge` | `polimat-guard` (id 26772165, active); `автопилот: защита primary (OSPS-AC-03.01)` (id 26897424, active) |
| `rtynbirf/polimat-hub` | `автопилот: защита primary (OSPS-AC-03.01)` (id 26949785, active) |
| `rtynbirf/polimat-task174` | `автопилот: защита primary (OSPS-AC-03.01)` (id 26949786, active) |
| `rtynbirf/polymat-hive` | `автопилот: защита primary (OSPS-AC-03.01)` (id 26949789, active) |
| `rtynbirf/polymath-atlas` | `автопилот: защита primary (OSPS-AC-03.01)` (id 26949791, active) |
| `rtynbirf/polymath-atlas-v107` | `polimat-guard` (id 26772164, active); `автопилот: защита primary (OSPS-AC-03.01)` (id 26897442, active) |
| `rtynbirf/polymath-gen` | `polimat-guard` (id 26797333, active); `автопилот: защита primary (OSPS-AC-03.01)` (id 26897446, active) |
| `rtynbirf/polymath-multiagent` | `автопилот: защита primary (OSPS-AC-03.01)` (id 26949799, active) |
| `rtynbirf/polymath-os` | `main-scorecard-protection` (id 26757855, active); `polimat-guard` (id 26772137, active); `автопилот: защита primary (OSPS-AC-03.01)` (id 26897449, active) |
| `rtynbirf/polymath-stckg-core` | `автопилот: защита primary (OSPS-AC-03.01)` (id 26897451, active) |
| `rtynbirf/polymath-tools-atlas` | `polimat-guard` (id 26772163, active); `автопилот: защита primary (OSPS-AC-03.01)` (id 26897454, active) |
| `rtynbirf/red-thread-debt-audit` | `автопилот: защита primary (OSPS-AC-03.01)` (id 26949802, active) |
| `rtynbirf/release-vault` | `polimat-guard` (id 26772139, active); `автопилот: защита primary (OSPS-AC-03.01)` (id 26897459, active) |
| `rtynbirf/rent-mechanism-q43` | `автопилот: защита primary (OSPS-AC-03.01)` (id 26949805, active) |
| `rtynbirf/repo-doctrine` | `автопилот: защита primary (OSPS-AC-03.01)` (id 26949806, active) |
| `rtynbirf/revo` | `автопилот: защита primary (OSPS-AC-03.01)` (id 26894798, active) |
| `rtynbirf/rtynbirf` | `polimat-guard` (id 26797331, active); `автопилот: защита primary (OSPS-AC-03.01)` (id 26897472, active) |
| `rtynbirf/rtynbirf.github.io` | `polimat-guard` (id 26772150, active); `автопилот: защита primary (OSPS-AC-03.01)` (id 26897481, active) |
| `rtynbirf/runtime-protocol` | `polimat-guard` (id 26772142, active); `автопилот: защита primary (OSPS-AC-03.01)` (id 26897484, active) |
| `rtynbirf/ruvson-lyrics` | `автопилот: защита primary (OSPS-AC-03.01)` (id 26949809, active) |
| `rtynbirf/ruvson-rse2` | `polimat-guard` (id 26772161, active); `автопилот: защита primary (OSPS-AC-03.01)` (id 26897486, active) |
| `rtynbirf/singulyar` | `main — гейт такта и честные пушы (латка С128)` (id 25155276, active); `polimat-guard` (id 26772149, active); `автопилот: защита primary (OSPS-AC-03.01)` (id 26897490, active) |
| `rtynbirf/singulyar-llm` | `polimat-guard` (id 26772160, active); `автопилот: защита primary (OSPS-AC-03.01)` (id 26897491, active) |
| `rtynbirf/task-graph-propagator` | `автопилот: защита primary (OSPS-AC-03.01)` (id 26949810, active) |
| `rtynbirf/uace-pml` | `автопилот: защита primary (OSPS-AC-03.01)` (id 26949812, active) |
| `rtynbirf/uace-polymat` | `автопилот: защита primary (OSPS-AC-03.01)` (id 26949814, active) |
| `rtynbirf/universal-agent` | `polimat-guard` (id 26772138, active); `автопилот: защита primary (OSPS-AC-03.01)` (id 26897497, active) |
| `rtynbirf/voice-atlas-llm` | `polimat-guard` (id 26772153, active); `автопилот: защита primary (OSPS-AC-03.01)` (id 26897499, active) |
| `rtynbirf/web-evolution-1991-2026` | `автопилот: защита primary (OSPS-AC-03.01)` (id 26949816, active) |
| `rtynbirf/windows-chronicle` | `автопилот: защита primary (OSPS-AC-03.01)` (id 26949818, active) |
| `rtynbirf/yazyk-skvoz-epohi` | `автопилот: защита primary (OSPS-AC-03.01)` (id 26949821, active) |

## Статус тиража в этой волне

- Экспорт эталона: выполнен (polimat-guard.json, зафиксирован в этом коммите).
- Проба POST: **403** (нет Administration:write) на 2 репо — тираж СТОП.
- Создано rulesets агентом: **0**. Повторить после выдачи write-права
  командой выше по списку «Без polimat-guard (25)».
