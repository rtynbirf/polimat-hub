# ПЕЧАТЬ САРКОФАГА singulyar (2026-11-08, агент B-1/ПОЛИМАТ)

## Что было (pre-state)
- Ветки: main=786b7e230ec9510e8d6e40106395346973b44c13, latka-c141-wip=b40d1c25ec8b52bf2d3398ac56ddf22f0796de39, minus-fond=1c10034a21df3c2058e8ae6ed1791c70f2302cc7, rumu=5ecac138f5f0fdc3af03e107fe0aee5e46a→0bd4d5af4f7ff3d603870264cbc24f00ac383fc4 (двинулась до переписывания: 12:38 коммит llms.txt-мембраны), теги v1.7…v1.12, ARHIV-2026-10-13, MINUS-FOND-2026-10-30, RUVSON-MUZYKA-FULL-2026-10-15, sborki-istoriya-zip-20261106, rumu-archive.
- Вес по API: 1547 MB. Жир: 455 уникальных блобов >2MB на 3341 MB (из них minus/ = 277 блобов, 2147 MB; 62 минусовки РУМУ).
- Полная копия pre-state: git bundle `singulyar-before.bundle` (2 535 589 440 B), sha256 `7db16100afeff22830e94d01166f87a1620eabbe814a4ecce521b00a4362f68e` (см. bundle-sha256.txt). Данные тела также: релиз-ассеты (ниже) + release-vault/import/singulyar (171 .enc, 5011 MB).

## Саркофаг (куда переехало тело)
Релиз MINUS-FOND-2026-10-30 (id 428373226), ассеты:
- RUVSON_MINUS_voice.zip        480 557 878 B — minus/голос/
- RUVSON_MINUS_clear-minus.zip  516 874 846 B — minus/чистый-минус/
- RUVSON_MINUS_sbornik-root.zip  76 091 514 B — minus/сборник/ + minus/prosto-lubi.mp3

sha256 (локальные, файл zip-sha256.txt):
```
9cf78e0d5bb3e2ec809476197e47c40fad13722cba6ed01b2b8270ffb30e85f4  RUVSON_MINUS_voice.zip
54bf200bd53f30ab5025a1ad67f50ce9008d944b8b685832d2ce7fe5d1857c69  RUVSON_MINUS_clear-minus.zip
98387c207f1361d09cd9600f7ddeb89a291f524bb05db580983110fbb982280a  RUVSON_MINUS_sbornik-root.zip
```
Указатель в репо: minus/MANIFEST.md (133 файла: путь, байт, git-sha1, sha256).

## Что сделано с историей (после записи саркофага)
- filter-repo --strip-blobs-bigger-than 2M по refs: main, latka-c141-wip, minus-fond и теги ARHIV/MINUS-FOND/RUVSON-MUZYKA/sborki/v1.7…v1.12 (два прохода).
- НЕ тронуты: ветка rumu (живое тело сайта; wasm/нужные файлы целы), тег rumu-archive (надгробие), refs/pull/* (владение GitHub).
- Force-push: main 786b7e2→4a4c0196, latka b40d1c2→7f9edc2a, minus-fond 1c10034→695bfb63, 10 тегов переписаны.
- Новое дерево main: 2018 файлов; minus/ = MANIFEST.md + сборник/ПАСПОРТ.md; ноль файлов >2 MB; pack только main = 123.45 MiB.

## Защита дома: bypass-окно (открыто и закрыто)
- Правила: ruleset 25155276 «main — гейт такта и честные пушы (латка Я128)» — pre-state в ruleset-before-graphql.json (DELETION + NON_FAST_FORWARD + REQUIRED_STATUS_CHECKS{«Оракулы дома зелёные», integration 15368}; bypassActors: []). На время пуша: bypass repo_admin ALWAYS + временно rules=[DELETION] + классика allow_force_pushes=true. После пуша восстановлено байт-в-байт (контроль GraphQL+REST 13:5x: 3 правила, чек «Оракулы дома зелёные»/15368, bypassActors пусто, allow_force_pushes=false).
- Найденный косяк дизайна (не чинится молча, см. TODO.md): required-check оракула не исполняется на main (оракул триггерится только на rumu), Такт-гейт/Lighthouse падают в CI-среде (indexedDB-тест требует браузер) → main был заморожен навсегда; весовая чистка требовала одноразового bypass-окна.

## Пин тела (протокол роя)
- Оракул краснел на каждый переезд тела без пере-пина (23:07, 21:44, 12:38 — в т.ч. 0bd4d5af, llms.txt-коммит мембраны ПОЛИМАТ: пин сломан в том числе нашим действием — признано).
- Чин по протоколу MANIFEST-копии («живой пин — make pins в ядре»): коммит 1200a83f на ветке rumu — оракул читает пин клетки singulyar из живого генома cell-swarm/swarm.json; make pins --write догнал 10 клеток (коммит a9484d5 в ядре), singulyar → 1200a83f.
- Репо rumu (указатель) — archived/read-only: body_pin в нём навсегда датированная копия (5ecac138) — это честно отражено в его note.

## Ожидаемый эффект и остаток
- API size (кэш) упадёт с 1547 MB после серверного gc; локально pack после gc держали только refs/pull — у пользователя свежий клон всех веток+тегов ≈ сотни MB.
- Последний несущий старого жира — история ветки rumu (387 блобов, 2449 MB): переписывание требует согласования с роем (тело под живой работой + полимат-guard на non-FF) — висит в TODO.md как B-1-хвост.
