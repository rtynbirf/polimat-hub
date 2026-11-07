# FEATURE-INTEGRATION-LOG · интеграция фич GitHub, 2026-11-08

Разведка: docs.github.com (push protection, rulesets, Dependabot, private vulnerability reporting, code scanning default setup).
Инструмент: `tools/features_integrate.py` (stdlib-only). Свидетельства: `audit/features-2026-11-08.json` (HTTP-коды каждой операции).

| Фича | Что даёт | Охват | Свидетельство |
|---|---|---|---|
| F1 Dependabot alerts | алерты по уязвимым зависимостям | **38/38** | PUT → 204 |
| F2 Dependabot security updates | авто-PR с фиксом уязвимостей | **38/38** | PUT → 204 |
| F3 delete_branch_on_merge | ветки не копятся после merge | **38/38** | PATCH → 200 |
| F4 ruleset `polimat-guard` | запрет force-push и удаления default-ветки | **22/22 публичных** | POST → 201; приватные — HTTP 403 (scope токена), см. ниже |
| F5 secret scanning + push protection | секреты не дойдут до истории | **22/22 публичных** | PATCH security_and_analysis → 200 |
| F6 private vulnerability reporting | внешние могут конфиденциально сообщить об уязвимости | **22/22 публичных** | PUT → 204 |
| F7 CodeQL default setup | статический анализ безопасности | 0/14 кодовых | PUT → 404 на всех: эндпоинт недоступен этому токену. Ручной путь: Settings → Code security → Default setup (2 клика на репо) |
| F8 topics (кластерная маркировка) | навигация и поиск по кластерам A–G | **38/38** | GET+PUT → 200 |

## Границы раунда (честно)

1. **F4 на приватных (16 шт) — HTTP 403**: REST-эндпоинт rulesets требует гранулярного права Administration (fine-grained token) либо включения в UI. Правило защиты не критично для приватных без внешних коллабораторов.
2. **F7 — HTTP 404** на всех кодовых: включается в UI вручную либо токеном с правом code_scanning_alerts (write).
3. **Не применено осознанно** (и почему):
   - Dependabot version updates (файл dependabot.yml) — поток авто-PR создаст шум на агентном аккаунте; решение за Хозяином.
   - Discussions — у аккаунта культура issues; дубль канала не нужен.
   - Wiki — флаги не трогались: возможен живой контент.
   - Sponsors / Copilot code review — уровни профиля и подписки, API-интеграции нет.

## Хронометраж ловушки раунда

- Прогон 1 отработал только публичные (эндпоинт `/users/{owner}/repos` возвращает 23 публичных из 39) — отловлен сравнением охвата, патч на `/user/repos`, дедупликация ruleset добавлена, прогон 2 — полный.
