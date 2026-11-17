# Roadmap: WISHENKA-32

## Task Metadata

- **Implementation language**: Python

## Step Status

- [x] **STEP 1: Requirements Gathering and Documentation**
  - `ai-tasks/WISHENKA-32/10-requirements.md` — документированы бизнес-требования по модели профиля пользователя (TG ID, username, name, avatar, birthday, locale), протоколу переключения и синхронизации языка (RU/EN) между ботом и Mini App, а также каскадным эффектам удаления аккаунта.
- [x] **STEP 2: High-Level Architecture Design**
  - `ai-tasks/WISHENKA-32/20-architecture.md` — спроектирована декомпозиция по задачам `WISHENKA-32/33/34/35`, дельта схемы `users` и таблица `deleted_session_revocations` (Alembic от `add_idempotency_records`), протокол синхронизации локали `RU`/`EN` (Mini App ↔ Bot ↔ Outbox), транзакционный каскад удаления аккаунта в `BEGIN IMMEDIATE` (учитывающий `telegram_id` vs `users.id`, детерминированную передачу владения и Surprise Invariant) и матрица red-тестов для `WISHENKA-33/34/35` (Step 3 в `WISHENKA-32` — `N/A`).
- [x] **STEP 3: Failing Repro Test**
  - N/A — no behavioral change (см. `ai-tasks/WISHENKA-32/20-architecture.md`, раздел «Mandatory — Failing Repro»): задача декомпозиции и спецификации не изменяет runtime-код и тесты; перечисленные в `20-architecture.md` failing-repro тесты относятся к `WISHENKA-33`, `WISHENKA-34` и `WISHENKA-35`.
- [x] **STEP 4: Development**
  - [x] Итерация 1: обновлены разделы §10, §11 и UC-10 в `in-docs/spec.md` — формализованы поля профиля (`Telegram ID`, отображаемое имя, `username`, аватар, дата рождения с поддержкой даты без года и приоритетом ручного ввода, локаль `ru`/`en` с приоритетом `явная` над `автоматическая` и немедленной синхронизацией Mini App ↔ бот ↔ уведомления), а также полный каскад удаления аккаунта, передача владения совместными вишлистами, отзыв сессий и защита тайны сюрприза (без утечки низкоуровневых SQL/кодовых деталей).
  - [x] Итерация 2: закрыты решённые вопросы в `in-docs/spec.md` §16 (судьба совместных вишлистов при удалении профиля владельца и поведение при недоступности даты рождения, аватара и `username` из Telegram) и проведена сквозная сверка согласованности `10-requirements.md`, `20-architecture.md` и `in-docs/spec.md`; изменения в `doc/dev/` оставлены за STEP 8, Python-код и тесты не менялись (реализация отнесена к `WISHENKA-33/34/35`).
- [x] **STEP 5: Code Cleanup**
  - `ai-tasks/WISHENKA-32/40-code-cleanup.md` — проверены форматирование Markdown (`lsr-markdown`), заголовки, таблицы, ссылки, отступы, отсутствие конфликтов слияния и хвостовых пробелов в `in-docs/spec.md` (затронутые разделы §10, §11, UC-10, §16) и `ai-tasks/WISHENKA-32/*.md`; исправлены пустые строки после подзаголовков в `10-requirements.md` и разделитель таблицы в `in-docs/spec.md` §10.1; выполнен `make analyze` (Ruff lint, Ruff format, Mypy — без ошибок).
- [x] **STEP 6: Observability**
  - `ai-tasks/WISHENKA-32/50-observability.md` — определены контракты наблюдаемости (структурированные события логирования на базе `wishenka/logging.py`, безопасные поля без ПДн/секретов/раскрытия тайны сюрприза, метрики и критерии `caplog`/метрик-проверок) для декомпозированных задач `WISHENKA-33`, `WISHENKA-34` и `WISHENKA-35`; live-изменения runtime-кода в `WISHENKA-32` — `N/A`.
- [x] **STEP 7: Technical Debt Analysis**
  - `ai-tasks/WISHENKA-32/60-tech-debt.md` — проведён анализ технического долга, архитектурных допущений и граничных случаев контрактов для `WISHENKA-33`, `WISHENKA-34`, `WISHENKA-35` (расщепление `telegram_id`/`users.id`, двойной DDL `users`, сигнатура `upsert_from_bot` vs `upsert_user`, частота опроса `ChatFullInfo.birthdate`, `is_collaborative` при передаче владения, log-only метрики) и зафиксированы новые follow-up задачи вне рамок спринтовых задач.
- [x] **STEP 8: Dev Docs**
  - `doc/dev/architecture.md` — отражена целевая архитектура `WISHENKA-32` (профиль пользователя, `RU`/`EN` i18n-синхронизация, транзакционное удаление аккаунта, `deleted_session_revocations` и интеграция `users` в Alembic) и добавлена ссылка на `doc/dev/users.md` с явным разграничением реализованного baseline и плановых контрактов `WISHENKA-33/34/35`.
  - `doc/dev/users.md` — создана документация домена `users`: матрица статуса реализации, расщепление ключей `telegram_id` vs `users.id`, дельта схемы `users` и стратегия Alembic от `add_idempotency_records`, протокол синхронизации локали `RU`/`EN` (TMA ↔ Bot ↔ Outbox), пошаговый каскад `AccountDeletionService` в `BEGIN IMMEDIATE`, `deleted_session_revocations`, целевые API/интерфейсы и контракт наблюдаемости/приватности из `50-observability.md`.
  - `doc/dev/auth.md` — добавлены cross-references на целевые контракты `WISHENKA-33/34/35` (`TelegramUser.photo_url`, `locale` sync, проверка живости `users.id` и `deleted_session_revocations`, а также правила санитизации логов в `doc/dev/users.md`) без смешения с реализованным baseline.
- [x] **COMMIT: Commit Changes**

## Status Legend

- `[ ]` — step not started
- `[/]` — step in progress
- `[x]` — step completed and accepted (acceptance gate passed)

See the `td-roadmap` skill for who writes which mark and when.

## Artifacts

### STEP 1: Requirements

- `ai-tasks/WISHENKA-32/10-requirements.md`

### STEP 2: Architecture

- `ai-tasks/WISHENKA-32/20-architecture.md`

### STEP 3: Failing Repro

- Automated red test(s) under `tests/` (or N/A note in roadmap)

### STEP 4: Development

- Source code
- Tests
- Documentation updates

### STEP 5: Code Cleanup

- `ai-tasks/WISHENKA-32/40-code-cleanup.md`

### STEP 6: Observability

- `ai-tasks/WISHENKA-32/50-observability.md`

### STEP 7: Technical Debt

- `ai-tasks/WISHENKA-32/60-tech-debt.md`

### STEP 8: Dev Docs

- `doc/dev/`

### COMMIT

- No artifact recorded here beyond the `[x]` mark above. Branch name and commit hash are reported
  in chat only, never written to this file.
