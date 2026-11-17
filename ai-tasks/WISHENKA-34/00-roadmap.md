# Roadmap: WISHENKA-34

## Task Metadata

- **Implementation language**: Python (with HTML/JS for Mini App templates)

## Step Status

- [x] **STEP 1: Requirements Gathering and Documentation**
  - `ai-tasks/WISHENKA-34/10-requirements.md` — бизнес-требования, пользовательские сценарии, функциональные/нефункциональные требования, сущности домена и критерии приёмки по настройкам уведомлений (глобальные, по вишлистам с приоритетом, напоминания о ДР) и персональным предпочтениям профиля в Mini App.
- [x] **STEP 2: High-Level Architecture Design**
  - `ai-tasks/WISHENKA-34/20-architecture.md` — архитектура настроек уведомлений (глобальных, по вишлистам, напоминаний о ДР) и персональных предпочтений профиля в Mini App.
- [x] **STEP 3: Failing Repro Test**
  - [x] `tests/test_wishenka_34_repro.py` — автоматизированные red-тесты для настроек уведомлений (глобальных, по вишлистам, `birthday_reminders`), даты рождения и инварианта тайны сюрприза.
- [x] **STEP 4: Development**
  - [x] Расширены `UserRecord` и `UserStore` полями `birth_day`, `birth_month`, `birth_year`, `birthdate_source`, валидацией календарных дат (включая 29 февраля без года) и методами `set_birthdate` / `clear_birthdate` с защитой от перезаписи при `upsert_user`.
  - [x] Реализован `NotificationPreferencesStore` (`wishenka/notices/preferences.py`) и обновлены `claim_reminder` / `refresh_reminder` в `wishenka/notices/reminders.py` для приоритетной проверки `birthday_reminders` с fallback на `reminders`.
  - [x] Добавлены эндпоинты `/api/profile/preferences`, `/api/profile/birthdate`, `/api/profile/notifications/global`, `/api/profile/notifications/wishlists/{id}`, ключи локализации `ru`/`en` в `wishenka/i18n/catalog.py`, все 5 red-тестов в `tests/test_wishenka_34_repro.py` стали зелёными.
  - [x] Обновлён шаблон `wishenka/web/templates/settings.html` (дата рождения, напоминания о ДР, глобальные переключатели и настройки по вишлистам на RU/EN) и добавлены комплексные unit/integration-тесты в `tests/test_wishenka_34_preferences.py`.
- [x] **STEP 5: Code Cleanup**
  - `ai-tasks/WISHENKA-34/40-code-cleanup.md` — отчёт по статическому анализу, форматированию, очистке кода и проверке тестов (`make analyze` и `make test` прошли успешно).
- [x] **STEP 6: Observability**
  - `ai-tasks/WISHENKA-34/50-observability.md` — отчёт по наблюдаемости (структурированное логирование и валидация).
- [x] **STEP 7: Technical Debt Analysis**
  - `ai-tasks/WISHENKA-34/60-tech-debt.md` — анализ технического долга, компромиссов, отсутствующих тестов, узких мест производительности и задач на доработку.
- [x] **STEP 8: Dev Docs**
  - `doc/dev/users.md` — актуализирована документация профиля пользователя (поля `birth_day`, `birth_month`, `birth_year`, `birthdate_source`, валидация дат, `set_birthdate`/`clear_birthdate`, реализованные эндпоинты `/api/profile/preferences` и `/api/profile/birthdate`).
  - `doc/dev/notifications.md` — добавлена документация по `NotificationPreferencesStore` (`wishenka/notices/preferences.py`), приоритету `birthday_reminders` в `wishenka/notices/reminders.py`, глобальным и списочным настройкам уведомлений и API `/api/profile/notifications/*`.
- [x] **COMMIT: Commit Changes**

## Status Legend

- `[ ]` — step not started
- `[/]` — step in progress
- `[x]` — step completed and accepted (acceptance gate passed)

See the `td-roadmap` skill for who writes which mark and when.

## Artifacts

### STEP 1: Requirements

- `ai-tasks/WISHENKA-34/10-requirements.md`

### STEP 2: Architecture

- `ai-tasks/WISHENKA-34/20-architecture.md`

### STEP 3: Failing Repro

- Automated red test(s) under `tests/` (or N/A note in roadmap)

### STEP 4: Development

- Source code
- Tests
- Documentation updates

### STEP 5: Code Cleanup

- `ai-tasks/WISHENKA-34/40-code-cleanup.md`

### STEP 6: Observability

- `ai-tasks/WISHENKA-34/50-observability.md`

### STEP 7: Technical Debt

- `ai-tasks/WISHENKA-34/60-tech-debt.md`

### STEP 8: Dev Docs

- `doc/dev/`

### COMMIT

- No artifact recorded here beyond the `[x]` mark above. Branch name and commit hash are reported
  in chat only, never written to this file.
