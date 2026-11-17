# WISHENKA-34: Observability Implementation

## Logging Implementation

### Added Logs

Describe added logging:
- **EMERG**: none (not applicable for profile/preferences domain)
- **ALERT**: none (not applicable for profile/preferences domain)
- **CRIT**: none (not applicable for profile/preferences domain)
- **ERR**: none (all errors in this flow are client validation/not-found errors handled as 422/404)
- **WARNING**:
  - `wishenka/web/routes/profile.py` (`_read_json_dict`) — `event="profile_malformed_json"`, `status_code=422`: логирование некорректного или не-объектного JSON-тела запроса.
  - `wishenka/web/routes/profile.py` (`update_profile_birthdate`) — `event="birthdate_invalid_request"` (`user_id`, `status_code=422`) и `event="birthdate_user_not_found"` (`user_id`, `status_code=404`): ошибки валидации даты рождения или отсутствия профиля пользователя.
  - `wishenka/web/routes/profile.py` (`update_global_notifications`) — `event="notification_global_invalid_request"` (`user_id`, `status_code=422`): некорректный формат или неподдерживаемые категории в глобальных настройках уведомлений.
  - `wishenka/web/routes/profile.py` (`get_wishlist_notifications`, `update_wishlist_notifications`) — `event="notification_wishlist_not_found"` (`user_id`, `wishlist_id`, `status_code=404`) и `event="notification_wishlist_invalid_request"` (`user_id`, `wishlist_id`, `status_code=422`): обращение к несуществующему/недоступному вишлисту или некорректные переопределения уведомлений.
- **NOTICE**: none (Python `logging` uses `INFO`/`WARNING`)
- **INFO**:
  - `wishenka/notices/preferences.py` (`NotificationPreferencesStore.update_global_settings`) — `event="notification_global_updated"`, `updated_count`, `categories`: фиксация обновления глобальных настроек уведомлений.
  - `wishenka/notices/preferences.py` (`NotificationPreferencesStore.update_wishlist_overrides`) — `event="notification_wishlist_updated"`, `wishlist_id`, `role`, `updated_count`, `cleared_count`: фиксация обновления или сброса переопределений уведомлений по вишлисту.
  - `wishenka/users/store.py` (`UserStore.set_birthdate`, `UserStore.clear_birthdate`, добавлено ранее) — `event="birthdate_explicit_updated"` (`user_id`, `has_year`, `birthdate_source`) и `event="birthdate_explicit_cleared"` (`user_id`, `birthdate_source`): фиксация явного обновления или очистки даты рождения без логирования самой даты.
- **DEBUG**:
  - `wishenka/notices/reminders.py` (`claim_reminder`, уже существующее логирование) — `event="service_notice_skipped"`, `outbox_id`, `kind`, `reason`: диагностика пропуска напоминаний (в т.ч. `birthday` при отключённом `birthday_reminders` / `reminders`).

### Log Structure

Log format used:
- Structured logs: yes (`wishenka/logging.py` `JsonFormatter` с `extra={...}` скалярными полями; без PII — `telegram_id`, дата рождения и текстовые payload'ы не логируются)
- Includes context: yes (`event`, `user_id`, `wishlist_id`, `role`, `status_code`, `updated_count`, `cleared_count`, `categories`)
- Log levels: `WARNING`, `INFO`, `DEBUG`

## Metrics Implementation (if applicable)

### Performance Metrics

Added performance metrics:
- Not applicable — в проекте не используется отдельный сборщик метрик (Prometheus/StatsD); наблюдаемость строится на структурированных JSON-логах (`wishenka/logging.py`).

### Business Metrics

Business metrics:
- Not applicable — ключевые бизнес-события (`notification_global_updated`, `notification_wishlist_updated`, `birthdate_explicit_updated`, `birthdate_explicit_cleared`) фиксируются в структурированных логах с полем `event` для последующей агрегации.

### System Health Metrics

System health metrics:
- Not applicable (нет изменений системных ресурсов или фоновых воркеров).

## Monitoring Integration

Integration with monitoring systems:
- [ ] Prometheus metrics (N/A)
- [ ] Grafana dashboards (N/A)
- [ ] Alerting rules (N/A)
- [x] Log aggregation (structured JSON logs via `wishenka/logging.py` `JsonFormatter`)

## Validation Results

Validation results:
- [x] Logs are correctly formatted (verified `make analyze`: Ruff linter, Ruff format, Mypy strict check passed)
- [x] Metrics are collected correctly (N/A — structured event logs verified)
- [x] Logging works in error scenarios (422/404 branches in `wishenka/web/routes/profile.py` covered by `tests/test_wishenka_34_preferences.py` and `tests/test_wishenka_34_repro.py`)
- [x] Large data structures are not logged (only scalar `extra` fields: `str`, `int`, `bool`)
- [x] Metrics are available for monitoring (N/A)

## Notes

- Все добавленные поля `extra` в `wishenka/notices/preferences.py` и `wishenka/web/routes/profile.py` являются скалярными (`str`, `int`, `bool`) и не содержат персональных данных (PII: `telegram_id`, день/месяц/год рождения не попадают в логи).
- Статус Step 6 в `ai-tasks/WISHENKA-34/00-roadmap.md` оставлен `[/]` до прохождения review-gate.
