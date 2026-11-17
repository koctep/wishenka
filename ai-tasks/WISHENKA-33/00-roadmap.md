# Roadmap: WISHENKA-33

## Task Metadata

- **Implementation language**: Python (plus HTML/JS for Mini App templates)

## Step Status

- [x] **STEP 1: Requirements Gathering and Documentation**
  - `ai-tasks/WISHENKA-33/10-requirements.md` — документированы бизнес-требования по двуязычному интерфейсу (`RU`/`EN`) Mini App и Telegram-бота, определению и приоритетам `auto`/`explicit` локали, синхронизации уведомлений и границам с `WISHENKA-73`/`WISHENKA-89`.
- [x] **STEP 2: High-Level Architecture Design**
  - `ai-tasks/WISHENKA-33/20-architecture.md` — архитектура двуязычной локализации (`RU`/`EN`), эволюции схемы `users` (Alembic + `UserStore`), синхронизации Mini App / `aiogram` / `NoticeStore` & `reminders` и матрица Failing Repro (`tests/test_i18n_sync.py`).
- [x] **STEP 3: Failing Repro Test**
  - `tests/test_i18n_sync.py` — red-тесты первичного определения локали (`ru`/`en`/fallback), автообновления до явного выбора, приоритета `explicit` и сквозной синхронизации Mini App (`GET /`, `/settings`, `/web/reservations`, `/share/{token}`), Telegram-бота (`/start`, `/help`, `/birthdays`, `/support`, `SetMyCommands`) и отложенных уведомлений/напоминаний (`NoticeStore`/`NoticeWorker`/`reminders`).
- [x] **STEP 4: Development**
  - [x] Iteration 1: Created `wishenka/i18n/` (`locale.py`, `catalog.py`, `dependencies.py`, `__init__.py`) with RU/EN normalization, Accept-Language parser, centralized catalog `t()`, and FastAPI `LocaleDep`.
  - [x] Iteration 2: Created Alembic revision `add_user_locale.py` (with `PRAGMA table_info` + backfill), extended `UserRecord` (`locale`, `locale_source`, `display_name`) and `UserStore` (`initialize()`, atomic `upsert_user`, `upsert_from_bot`, `set_locale`/`set_explicit_locale`); `test_first_login_locale_mapping_ru_en_and_fallback` and user-store/migration tests green.
  - [x] Iteration 3: Created `wishenka/bot/i18n.py` (`LocaleMiddleware`, `bot_commands_for_locale`, `sync_user_bot_commands`, and shared `_private_bot_user` log filter).
  - [x] Iteration 4: Wired Jinja2 `t`/locale context processor, `base.html` `<html lang>` + settings link, `settings.html`, `routes/profile.py` (`GET /settings`, `PATCH /api/profile/locale` with `HX-Refresh: true` + best-effort command sync), `miniapp.py`/`miniapp.js`/`miniapp.css`, `/api/auth/me`, and SSR routes (`sharing.py`, `items_ui.py`, `reservations_ui.py`).
  - [x] Iteration 5: Wired `LocaleMiddleware` as outer middleware on `entry.create_router`, localized all messages/keyboards in `entry.py`, `birthdays.py`, `support.py`, and `capture.py` via `wishenka.i18n.t()`, and added best-effort `sync_user_bot_commands` on `/start`; `test_auto_locale_tracks_telegram_client_until_explicit_switch` and bot repro suites green.
  - [x] Iteration 6: Switched `NoticeStore`, `NoticeWorker`, and `wishenka/notices/reminders.py` to read `users.locale` with `'en'` fallback and render via `wishenka.i18n.t()`; all three `tests/test_i18n_sync.py` repro tests are green.
  - [x] Iteration 7: Updated legacy fallback assertions (`test_notice_wishlist_events.py`, `test_notice_delivery_repro.py`, `test_bot_support.py`), added `tests/test_i18n_unit.py` (catalog key/placeholder parity, fallback logging, Accept-Language, Alembic/UserStore backfill, web/bot/notice edge cases), and verified `make analyze` and `make test`.
  - [x] Iteration 8 (Review Fixes): Refined anonymous `?lang=` fallback to `Accept-Language` -> `'en'` via `resolve_optional_locale` in `locale.py`/`dependencies.py`, added legacy-column `OperationalError` (`"no such column"`) `'en'` fallback in `reminders.py`, localized `showHome()` navigation and home shell labels in `miniapp.js` without altering `base.html`, moved `sync_user_bot_commands` in `PATCH /api/profile/locale` (`routes/profile.py`) to FastAPI `BackgroundTasks`, and added unit tests in `tests/test_i18n_unit.py`.
- [x] **STEP 5: Code Cleanup**
  - `ai-tasks/WISHENKA-33/40-code-cleanup.md` — проверены `make analyze` (Ruff lint/format + Mypy strict: 188 files clean), длина строк (<= 100), отсутствие debug-выводов/конфликтов, явные `pytest.mark.timeout` во всех изменённых/новых тестах и прогон `make test` (`1069 passed`).
- [x] **STEP 6: Observability**
  - `ai-tasks/WISHENKA-33/50-observability.md` — документированы структурированные события логирования (`locale_auto_resolved`, `locale_explicit_updated`, `locale_invalid_request`, `bot_commands_locale_synced`, `bot_commands_locale_sync_failed`, `i18n_missing_translation_key`, `notice_locale_resolved`), добавлено `DEBUG`-логирование `bot_commands_locale_synced` в `wishenka/bot/i18n.py` и тест `test_i18n_observability_structured_logs_and_no_pii` в `tests/test_i18n_unit.py`; `make analyze` и `make test` (`1070 passed`) зелёные.
- [x] **STEP 7: Technical Debt Analysis**
  - `ai-tasks/WISHENKA-33/60-tech-debt.md` — анализ технического долга, компромиссов, недостающих тестов и задач на доработку.
- [x] **STEP 8: Dev Docs**
  - `doc/dev/i18n.md` — создано руководство разработчика по подсистеме двуязычной локализации (`RU`/`EN`): архитектура, приоритеты `auto`/`explicit`, API/зависимости, HTTP-эндпоинты, конфигурация и troubleshooting.
  - `doc/dev/users.md` — обновлены статусы `WISHENKA-33` (Implemented), сигнатура `UserStore.set_locale`, расположение `LocaleMiddleware` (`wishenka/bot/i18n.py`) и ссылки на `doc/dev/i18n.md`.
  - `doc/dev/auth.md` — обновлены примечания по статусу `WISHENKA-33` (`UserStore.set_locale` и ссылка на `doc/dev/i18n.md`).
- [x] **COMMIT: Commit Changes**

## Status Legend

- `[ ]` — step not started
- `[/]` — step in progress
- `[x]` — step completed and accepted (acceptance gate passed)

See the `td-roadmap` skill for who writes which mark and when.

## Artifacts

### STEP 1: Requirements

- `ai-tasks/WISHENKA-33/10-requirements.md`

### STEP 2: Architecture

- `ai-tasks/WISHENKA-33/20-architecture.md`

### STEP 3: Failing Repro

- `tests/test_i18n_sync.py`

### STEP 4: Development

- Source code
- Tests
- Documentation updates

### STEP 5: Code Cleanup

- `ai-tasks/WISHENKA-33/40-code-cleanup.md`

### STEP 6: Observability

- `ai-tasks/WISHENKA-33/50-observability.md`

### STEP 7: Technical Debt

- `ai-tasks/WISHENKA-33/60-tech-debt.md`

### STEP 8: Dev Docs

- `doc/dev/i18n.md`
- `doc/dev/users.md`
- `doc/dev/auth.md`

### COMMIT

- No artifact recorded here beyond the `[x]` mark above. Branch name and commit hash are reported
  in chat only, never written to this file.
