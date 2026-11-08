# ПЕЧАТЬ: перенос СВЯТОГО media-vault → публичный Маяк — 2026-11-08 (агент ПОЛИМАТ, ревизия «Добей»)

Репозиторий: `rtynbirf/ruvson-lyrics` (приватный). Операция: удаление приватного релиза
`media-vault` (5 × 89.3 МБ = 446 710 179 байт) из квоты хранилища ПОСЛЕ трёхслойной
сверки с публичной шифрованной копией в release-vault (закон «публично или Маяк», П-25).

## Причина
`Artifact storage quota has been hit` — Pages-деплой ruvson-lyrics (run 42366826088,
14:57 UTC 08.11) не смог загрузить артефакт: приватные релизные ассеты держали
446.7/500 МБ квоты. СВЯТОЕ должно жить в Маяке, а не душить живые деплои.

## Трёхслойная сверка (ДО удаления)

1. **Оригинал** (релиз `media-vault`, digest API GitHub = локальный sha256, 5/5):

| файл | bytes | sha256 | git-sha1 (пломба B-2) |
|---|---|---|---|
| RUVSON_QUANTUM_v5.part1of5 | 89 342 035 | `ffce387bafbb61dee08562ca1adae182fe59e5828586327f0f819783ad1f13c9` | `cda1c72e2225f9394c063cda98b1ab72998abbd7` |
| RUVSON_QUANTUM_v5.part2of5 | 89 342 035 | `704a3e2c7d4d530031780f8b3acd3eb2009fb89ad129205ad89b2a67bc4551df` | `6e4a0a6b15637b5965e8d0f0edfb5dcd006a07d7` |
| RUVSON_QUANTUM_v5.part3of5 | 89 342 035 | `d976e4cc1705db98c3d06bdd8ddbf2b3eafd343a01e2fbb5ad76d8b1761964a9` | `c0e480f515eee0573b4b07af1a23b97eb85c6f63` |
| RUVSON_QUANTUM_v5.part4of5 | 89 342 035 | `52b54849e8275732b6f85d27f19133258ba8eb97f8e6758595b3b1ffcb3a6883` | `c5e9839aadd2618ba00ec1eb66161c1c096367d3` |
| RUVSON_QUANTUM_v5.part5of5 | 89 342 039 | `0b4b76632d7cbb5dc8442e9f6b17f6468787a62dd1075af62a43f8d296ae10fa` | `11da60f5b8f12890e4b8220b3f5bb14a5f088775` |

2. **Публичная шифрованная копия** (release-vault, релиз `import/ruvson-lyrics`):
   `r1a002.enc` = **446 710 208 bytes**, digest API = `sha256:a0ccb3d0268c66be2ca879c50fca00df1dfcab9dc936b60de741e9d5ac9c87f5`,
   совпадает с `ruvson-lyrics__SHA256SUMS.txt` (публичный). Математика сходится:
   446 710 179 (5 частей) + 16 байт openssl-заголовка + 13 байт паддинга = 446 710 208.
   Схема: AES-256-CBC, PBKDF2-SHA1, 600 000 итераций; ключ только у владельца.

3. **Печать агента B-2** (`sarkofag-check-ruvson-lyrics-2026-11-08.txt`): «проверено ДО
   переписывания, 5/5 совпало» — git-sha1 локальной пятерки повторены байт-в-байт.

## Операция
- `DELETE /repos/rtynbirf/ruvson-lyrics/releases/437833423` → 204 No Content, 15:2x UTC 08.11.
- Тег `media-vault` в git **оставлен** — надгробие-указатель (саркофаг-не-могила).
- Релизы `quantum-v4`/`quantum-v5` (малые) не тронуты.

## Результат
- Приватные релизные ассеты аккаунта: **446.7 МБ → 0.0 МБ** (замер API сразу после операции).
- Квота Actions/Storage приватных репо освобождена: Pages-деплои и CI-артефакты снова имеют воздух.
- Ничего не разрушено: полная восстановимость из `r1a002.enc` при наличии ключа владельца:
  `openssl enc -d -aes-256-cbc -pbkdf2 -iter 600000 -in r1a002.enc -out QUANTUM_v5 -pass file:key.txt`
  (потом разрезать на 5 частей по размерам из таблицы).

## Осталось
- GitHub пересчитывает usage 6–12 ч: Pages-диспатч добить после пересчёта
  (страж 514749, 09:00 МСК 09.11, инструменты `finisher_rerun3.py` + `wave1_verdict.py`).
