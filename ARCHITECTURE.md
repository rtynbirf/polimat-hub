# ARCHITECTURE · целевая архитектура аккаунта rtynbirf

Составлена мультиагентом ПОЛИМАТ 2026-11-08 по мандату Хозяина.
Источник данных: `audit/inventory-2026-11-08.json` (машинный снимок API, 40 репозиториев до реструктуризации).

## Триада аккаунта

- **НОУС** (`nous`) — конституция и генезис. Не трогается архитектором: это орган права, а не работы.
- **ПОЛИМАТ-HUB** (`polimat-hub`) — место сверок и хранения архитектора: журнал, пломбы, инструменты.
- **ПОЛИМАТ-VAULT** (`polimat-vault`) — хранилище пломб: git-бандлы и SHA256 всего, что перемещается или удаляется.

## Кластеры (7)

### A. SYSTEM — суверенная инфраструктура
| Репозиторий | Роль | Канон? |
|---|---|---|
| `polymath-os` | самосборочная ОС-среда, `make verify` | да |
| `neutral-browser` | браузерный движок на Rust, ноль зависимостей | да |
| `agryp` | PID1-супервизор AI-агентов, один файл C | да |
| `os-forge` | сборщик ISO из карты среды | да |
| `H-PE11-PHOENIX` | WinPE 11 без ADK/DISM (wimlib+pycdlib) | да |
| `domovoy-tweaker` | твикер как состояние (журнал изменений) | да |
| `cell65-host` | антицензорный узел sing-box, три транспорта | да |
| `release-vault` | шифрованный офсайт-архив ассетов | да |

### B. SWARM — рой и агенты
`nous` (конституция), `cell-swarm` (геном роя), `runtime-protocol` (модель узла),
`cell-rs` (Rust-клетка), `universal-agent` (одномозговый агент), `commons` (организм upstream-проектов).

### C. RUVSON — карaoke-вселенная
`singulyar` (флагман-монолит, поглощает `rumu` веткой), `ruvson-lyrics` (корпус текстов),
`ruvson-rse2` (конвейер одной песни), `karaoke-dream` (браузерная сцена),
`singulyar-llm` (локальная модель), `rtynbirf.github.io` (лицо/PWA), `voice-atlas-llm` (атлас голоса).

### D. RESEARCH — исследования и верификация
`red-thread-debt-audit`, `rent-mechanism-q43`, `polymath-atlas-v107` (Lean 4),
`task-graph-propagator` (функция Грина на графе), `global-video-platforms-registry`,
`polymath-tools-atlas`, `uace-pml`, `polimat-task174`.

### E. WINDOWS-CANON — единый канон Windows
`windows-chronicle` — **единственный канонический репозиторий** истории Windows 1985–2026.
Ветка `merged/encyclopedia` и каталог `merged-from/` хранят поглощённые тела
`windows-encyclopedia` и `windows-full-report` (пломбы их истории — в `polimat-vault`).

### F. EXPOSITION — автономные экспозиции
`language-through-the-ages`, `web-evolution-1991-2026`, `edinyy-svod` (свод-самоописание архива).

### G. META — мета-органы
`repo-doctrine` (доктрина), `github-runbook` (ранбук настроек), `.github` (health files),
`markitdown` (форк-инструмент), `polimat-vault` (пломбы), `polimat-hub` (сверки).

## Правила архитектуры (не противоречащие GitHub и лучшим практикам)

1. **Имена**: `kebab-case`, без брендов Microsoft/Apple в имени репо (описание — да).
2. **Лицензии**: каждый публичный репозиторий с кодом — MIT + REUSE-заголовки (стандарт уже задан в polymath-os).
3. **Здоровье**: community files наследуются от `.github`; у каждого репо — description и topics (≥3).
4. **Вес**: git — для истории текстов; медиа >50 МБ — в Releases/asset или в шифрованный `release-vault`, не в дерево коммитов. Цель к 2027: ни одного репо >500 МБ в дереве.
5. **Дубли**: один факт — один канонический репозиторий; зеркала и заглушки запрещены (указатели вместо копий — закон роя).
6. **Пломбы**: любая деструктивная операция = бандл в `polimat-vault` + SHA256 в `MANIFEST.sha256` + запись в `RESTRUCTURE-LOG.md` ДО операции.
7. **Токены**: полный токен живёт не более срока сессии; в чаты и файлы не попадает; после мандата — отзыв Хозяином.
8. **Архивация**: репозиторий без пуша 90 дней и без плана — помечается `archived: true` (обратимо), а не удаляется.

## Реестр операций 2026-11-08 (см. RESTRUCTURE-LOG.md)

| Операция | Объект | Результат |
|---|---|---|
| CREATE | `polimat-vault` | хранилище пломб, private |
| CREATE | `polimat-hub` | место сверок, private |
| MERGE | `windows-encyclopedia` + `windows-full-report` → `windows-chronicle` | канон E |
| ABSORB | `rumu` → ветка `rumu` в `singulyar` (код уже там), репо-носитель имени удалён | кластер C |
| DELETE | `windows-encyclopedia`, `windows-full-report`, `rumu` | после пломб |
