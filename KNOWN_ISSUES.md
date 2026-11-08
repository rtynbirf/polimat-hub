# KNOWN_ISSUES · polimat-hub · Волна ×5 (2026-11-09)

> Живой список красных и квирков. Было → после патча. Пломбы только живыми прогонами.

## Красные CI

| Run | Workflow | Что было | Диагноз | После патча |
|---|---|---|---|---|
| 42500555202 (16:34) | pulse-heart | failure, шаг «Коммит пульса» | push rejected «fetch first»: checkout на SHA диспатча ad8f571d, параллельный inventory-weekly (42500557176, тот же SHA) успел запушить первым | патч rebase+retry → диспатч см. ниже |
| 42466954893 (09:23) | pulse-heart | failure | та же гонка: два диспатча подряд 09:19/09:23 поверх свежих пушей волн | тот же патч |
| 42466691086 (09:19) | pulse-heart | failure | та же гонка | тот же патч |
| 42480621320 (12:31) | pip in /. - Update (Dependabot) | failure | `dependency_file_not_found: No files found in /` — pip-экосистема в dependabot.yml при отсутствии pip-манифестов в корне | невоспроизводим: в актуальном dependabot.yml только github-actions; живые успешные dynamic-раны 42493141329/42493142929 (15:06) на SHA de4d9dba |

## Патч pulse-heart (этот репо)

- SHA коммита: см. git log по `.github/workflows/pulse-heart.yml` («🌊 Волна ×5»).
- Суть: перед коммитом `git fetch origin main && git rebase origin/main`; push в retry-петле до 5 попыток, при отклонении — fetch+rebase и повтор. Итог: диспатч после патча — run **(заполняется диспатчем ×5-D)**, conclusion **…** (sha {SHA8}).

## Квирки

- `concurrency: dom-obhod` защищает только pulse-heart сам от себя; inventory-weekly ходит в своей группе и тоже пишет в main — гонка между ними была реальной причиной всех трёх красных. Retry-патч снимает её.
- Размер репо ~82 МБ (правило ≤500 МБ соблюдено), клоны советовать только `--filter=blob:none`.
- 89 открытых issues — это живые волны Э-1/Э-2/W-AUD/КОСЯКИ, НЕ болячки; не «чистить» их.
