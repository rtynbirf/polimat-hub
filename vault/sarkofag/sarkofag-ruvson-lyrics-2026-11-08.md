# ПЕЧАТЬ: саркофаг ruvson-lyrics — 2026-11-08 (агент B-2)

Репозиторий: `rtynbirf/ruvson-lyrics`. Операция: блобы >50 MB вычещены из HEAD и
истории (правило дома №4: репо ≤ 500 MB). Данные не потеряны — саркофаг
(релиз `media-vault` этого репо + `release-vault` import/ruvson-lyrics) проверен
ДО переписывания.

## Сверка саркофага (ДО любых правок, 5/5 совпало)

Все 5 ассетов релиза `media-vault` скачаны через API
(`Accept: application/octet-stream`) в /tmp/B2assets и сверены
`git hash-object` против пломб из body релиза и против sha блобов истории main:

| файл | размер (bytes) | git-sha1 (пломба) | hash-object = пломба | размер байтово |
|---|---|---|---|---|
| `download/konveyer/v5_parts/RUVSON_QUANTUM_v5.part1of5` | 89342035 | `cda1c72e2225f9394c063cda98b1ab72998abbd7` | ДА | ДА (asset = git-блоб = скачанный файл) |
| `download/konveyer/v5_parts/RUVSON_QUANTUM_v5.part2of5` | 89342035 | `6e4a0a6b15637b5965e8d0f0edfb5dcd006a07d7` | ДА | ДА |
| `download/konveyer/v5_parts/RUVSON_QUANTUM_v5.part3of5` | 89342035 | `c0e480f515eee0573b4b07af1a23b97eb85c6f63` | ДА | ДА |
| `download/konveyer/v5_parts/RUVSON_QUANTUM_v5.part4of5` | 89342035 | `c5e9839aadd2618ba00ec1eb66161c1c096367d3` | ДА | ДА |
| `download/konveyer/v5_parts/RUVSON_QUANTUM_v5.part5of5` | 89342039 | `11da60f5b8f12890e4b8220b3f5bb14a5f088775` | ДА | ДА |

Вторая копия саркофага: `release-vault`, релиз `import/ruvson-lyrics`:
`r1a002.enc` 446 710 208 bytes (v5), `r1a001.enc` 219 400 112 bytes (v4).

## Размеры

| метрика | до | после |
|---|---|---|
| size-pack (git count-objects -vH, локальный mirror) | **514.09 MiB** | **34.72 MiB** (после filter-repo + `git gc --prune=now`; свежий clone тоже 34.72 MiB) |
| API `repos/rtynbirf/ruvson-lyrics` поле `size` | 526 392 KB = 514.1 MB | 514.1 MB на момент печати (lag кэша GitHub — зафиксировано; фактический pack 34.72 MiB, строку API привести в отчёте B-2) |

Ожидание по плану было ≈88 MB ±20; фактический size-pack 34.72 MiB — меньше,
потому что команда `git filter-repo --strip-blobs-bigger-than 50M` вычистила
не только 5 частей v5 (89.3 MB × 5), но и 3 части v4 из истории
(`RUVSON_QUANTUM_v4.part{1,2,3}of3`, 73.1 MB × 3; в HEAD их уже не было —
только в истории/тегах). Саркофаг v4 существует: `r1a001.enc` (release-vault);
контрольный бандл до операции сохранён на песочнице B-2 (см. ниже).

## Рефсы до (show-ref, mirror до правок)

```
7ffcbf5bbab17ab001a3f0ca4a2b10cff594599a refs/heads/main
55ea5e26b0dd2afd4a9691d7a4a135c13c0053a6 refs/pull/1/head
4d983efba6ed2542e89333663dce30e2da3b483a refs/pull/2/head
f3ab93e87d4b2268aac0aca33eaaaeaf8e6780c7 refs/pull/3/head
c21d8fb7ba90cdcd9d762c4e979fba8dd83d1b4e refs/pull/4/head
ea06a686b7f843f5929ae6ed670031eb45756628 refs/tags/media-vault
b44c9a2c485bb4844ea8a521755fcb65519a19c4 refs/tags/quantum-v4
1ff1e672db43390a902f0e390657eec38ef180fb refs/tags/quantum-v5
```

## Печать-до (контрольный бандл)

`git bundle create --all` из mirror ДО правок:

- файл: `work/B2/ruvson-lyrics-before.bundle` (515 MB)
- sha256: `1b6d1434005e74cda32ab814f3d90129b77f330fa8a75ebdaf8d0a40b31802a2`

## Что сделано с веткой main

1. Указатель (fast-forward, ДО filter-repo): `7ffcbf5 → 50476a6` — удалены 5
   файлов `download/konveyer/v5_parts/RUVSON_QUANTUM_v5.part{1..5}of5`
   (каталог `v5_parts/` остался), добавлен `download/konveyer/v5_parts/MANIFEST.md`
   (таблица «файл | 85.2 MB | git-sha1 (пломба) | где живёт», дата 2026-11-08,
   причина: правило №4 ≤500MB, двойное хранение убрано).
   Коммит: «саркофаг-проверен: v5_parts → релиз media-vault (пломбы git-sha1
   сверены); правило №4».
2. `git filter-repo --force --strip-blobs-bigger-than 50M` (ровно по плану).
3. Force-push: main `50476a6 → 9172510`; теги `media-vault ea06a68 → 078712a`,
   `quantum-v5 1ff1e67 → 97e27e0` (`quantum-v4` не изменился — в нём не было
   блобов >50MB).
4. Доп. коммит (fast-forward, поверх переписанного): `9172510 → 23433b0` —
   примечание в MANIFEST.md про v4-части (тоже >50MB, саркофаг r1a001.enc).
   Итоговый HEAD main: **23433b0**.

**Ветка main переписана, мелкие mp3 prototip/ сохранены.**

## Верификация после (свежий clone)

- `git ls-files -s` свежего main **совпадает** с пре-состоянием main (7ffcbf5)
  ЗА ИСКЛЮЧЕНИЕМ ровно 5 файлов v5_parts (272 → 268 путей; −5 части, +MANIFEST.md).
  Полные diff-таблицы: `work/B2/head-diff.txt`, `work/B2/pre-files.txt`,
  `work/B2/check-files.txt`.
- `prototip/minus/*.mp3` на месте, blob-sha 5/5 совпадают с до-состоянием
  (8e7070b0, 03a66ccd, c3b2458f, 9c4c3b1d, f9544f43). Остальные блобы >2MB
  в истории — те же 5 mp3, больше нет.
- size-pack свежего clone = 34.72 MiB.

## guardian-tripwire (CI)

- Прогон на `9172510` (force-push): **failure по замыслу** — сработал шаг
  «Чек force-push в default-ветку», ALARM-issue №5
  (https://github.com/rtynbirf/ruvson-lyrics/issues/5). Скан секретов не
  добирался (skipped) — прервался на проверке force-push.
- Прогон на итоговом `23433b0` (последний run на main после пуша): **success**
  (+ CI success; на тегах media-vault/quantum-v5 после их force-push тоже
  success).
- В issue №5 оставлен комментарий B-2 с обоснованием и вердиктами.

## Ограничения/честные замечания

- `refs/pull/1..4/head` GitHub'а держат старые (толстые) коммиты — их нельзя
  переписать удалённо; API-`size` может падать с лагом и не до нуля из-за них.
- Полный пре-снапшот остался в бандле `ruvson-lyrics-before.bundle` (sha256
  выше) на песочнице B-2 `/home/z/my-project/work/B2/` — туда же вошли v4/v5
  части до вычистки (дубликат саркофага, третья копия).
- Источник фактов до операции: `refs-before.txt`, `fat-before.txt`,
  `count-objects-before.txt`, `release-body-seals.txt`, `sarkofag-check.txt`.

— агент B-2, 2026-11-08
