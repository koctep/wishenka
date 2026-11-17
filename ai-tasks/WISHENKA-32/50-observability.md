# WISHENKA-32: Observability Design & Contracts

> **Статус реализации (Scope Note):** `WISHENKA-32` — задача `[Декомпозиция]`, архитектуры и спецификации. В рамках `WISHENKA-32` **изменения в runtime-коде Python и тестах не вносятся (`N/A` для live-правок кода)**. Ниже зафиксированы обязательные контракты логирования, метрик, защиты ПДн / тайны сюрприза и критерии верификации для задач реализации:
> - **`WISHENKA-33`** — мультиязычность `RU`/`EN` (Mini App ↔ Bot ↔ Outbox);
> - **`WISHENKA-34`** — синхронизация профиля (`avatar_url`, `birthday`) и настроек уведомлений;
> - **`WISHENKA-35`** — транзакционное удаление аккаунта, передача владения и отзыв сессий.

---

## Logging Implementation

### Added Logs

В приложении используется единая конфигурация логирования из [`wishenka/logging.py`](file:///home/src/wishenka/logging.py) (`configure_logging`, `JsonFormatter`). Все события используют стандартные уровни Python `logging` (`CRITICAL`, `ERROR`, `WARNING`, `INFO`, `DEBUG`).

Соответствие syslog-уровням из `td-50-observability`:
- **EMERG / ALERT / CRIT (`CRITICAL`)**: `N/A` для штатных операций подсистемы профиля/i18n/удаления; зарезервировано на уровне старта приложения для невосстановимой несовместимости схемы БД при миграции.
- **ERR (`ERROR`)**: сбои атомарных транзакций и критические ошибки записи/целостности данных.
- **WARNING**: отклонение некорректных/небезопасных входных данных, отказы best-effort вызовов Telegram API, отсутствие ключа перевода, отказ авторизации по отозванной или удалённой сессии.
- **NOTICE**: в Python `logging` отдельный уровень отсутствует; значимые бизнес-переходы фиксируются на уровне `INFO`.
- **INFO**: подтверждённые изменения состояния (явное переключение локали, ручное обновление/очистка даты рождения, изменение настроек уведомлений, передача владения совместным списком, завершение/идемпотентный повтор удаления аккаунта, очистка истёкших записей отзыва).
- **DEBUG**: высокочастотные операции (автоопределение локали при входе/апдейте, синхронизация профиля из Telegram, предпросмотр удаления, отмена отправки уведомления удалённому пользователю).

#### Контракт событий по подсистемам (`WISHENKA-33`, `WISHENKA-34`, `WISHENKA-35`)

| Задача | Уровень | Logger (`logging.getLogger`) | Событие (`message`) | Безопасные поля (`extra`) | Запрещённые поля (PII / Secrets / Surprise) |
| ------ | ------- | ---------------------------- | ------------------- | ------------------------- | ------------------------------------------- |
| `WISHENKA-33` | `DEBUG` | `wishenka.i18n` / `wishenka.users.store` | `locale_auto_resolved` | `channel` (`miniapp_auth` \| `bot_update` \| `public_share`), `resolved_locale` (`ru` \| `en`), `locale_source` (`auto` \| `explicit`), `changed` (`bool`), `fallback_used` (`bool`) | `initData`, `username`, `first_name`, `last_name`, `display_name`, session token |
| `WISHENKA-33` | `INFO` | `wishenka.web.profile` / `wishenka.users.store` | `locale_explicit_updated` | `user_id` (`users.id`), `previous_locale` (`ru` \| `en`), `new_locale` (`ru` \| `en`), `previous_source` (`auto` \| `explicit`), `locale_source` (`explicit`) | `username`, `display_name`, cookie/CSRF token |
| `WISHENKA-33` | `WARNING` | `wishenka.web.profile` | `locale_invalid_request` | `user_id`, `status_code` (`400` \| `422`) | Сырой payload, `username`, `display_name`, cookie |
| `WISHENKA-33` | `WARNING` | `wishenka.i18n` | `i18n_missing_translation_key` | `i18n_key` (`str`), `locale` (`ru` \| `en`), `fallback_locale` (`en` \| `key`) | Пользовательские тексты и ПДн |
| `WISHENKA-33` | `WARNING` | `wishenka.bot.i18n` | `bot_commands_locale_sync_failed` | `user_id`, `target_locale` (`ru` \| `en`), `error_type` (`type(exc).__name__`) | Токен бота, URL Bot API, текст исключения с секретами, `chat_id` с ПДн |
| `WISHENKA-33` | `DEBUG` | `wishenka.notices.store` / `wishenka.notices.reminders` | `notice_locale_resolved` | `channel` (`notice_outbox` \| `reminder_outbox`), `locale` (`ru` \| `en`), `fallback_used` (`bool`) | `giver_user_id`, `recipient_user_id`, `item_id`, `reservation_id`, `birthday` |
| `WISHENKA-34` | `WARNING` | `wishenka.auth.models` / `wishenka.users.store` | `profile_avatar_rejected` | `reason` (`invalid_scheme` \| `bot_token_url_blocked` \| `exceeds_max_length`) | Само значение `avatar_url` / `photo_url` (может содержать токен бота или ПДн) |
| `WISHENKA-34` | `DEBUG` | `wishenka.users.store` | `profile_telegram_synced` | `user_id`, `sync_avatar` (`bool`), `has_username` (`bool`), `has_avatar` (`bool`), `username_cleared` (`bool`), `avatar_cleared` (`bool`) | `first_name`, `last_name`, `display_name`, `username`, `avatar_url` |
| `WISHENKA-34` | `DEBUG` | `wishenka.users.store` | `profile_birthday_synced` | `user_id`, `outcome` (`updated` \| `cleared` \| `skipped_manual_override`), `birthday_source` (`telegram` \| `manual` \| `none`), `has_year` (`bool`) | Значение `birthday` (`YYYY-MM-DD`, `--MM-DD`, день/месяц/год) |
| `WISHENKA-34` | `WARNING` | `wishenka.bot` | `profile_birthday_telegram_fetch_failed` | `user_id`, `error_type` (`type(exc).__name__`) | Токен бота, `birthday`, `username`, `display_name` |
| `WISHENKA-34` | `INFO` | `wishenka.web.profile` / `wishenka.users.store` | `profile_birthday_manual_updated` | `user_id`, `action` (`set` \| `cleared`), `birthday_source` (`manual`), `has_year` (`bool`) | Значение `birthday`, `username`, `display_name` |
| `WISHENKA-34` | `WARNING` | `wishenka.web.profile` | `profile_birthday_invalid` | `user_id`, `error_code` (`invalid_birthday_format` \| `invalid_calendar_date`) | Сырое значение `birthday`, `username`, `display_name` |
| `WISHENKA-34` | `INFO` | `wishenka.web.profile` | `notification_settings_updated` | `scope` (`global` \| `wishlist`), `user_id`, `wishlist_id` (`int \| None`), `event_type` (`gift_received` \| `wishlist_changes` \| `reservation_changes` \| `reminders`), `enabled` (`bool`) | `username`, `display_name`, содержимое желаний и броней |
| `WISHENKA-35` | `DEBUG` | `wishenka.wishlists.deletion` | `account_deletion_previewed` | `user_id`, `personal_lists_count` (`int`), `collaborative_transferred_count` (`int`), `collaborative_deleted_count` (`int`), `reservations_count` (`int`) | Названия списков, ID желаний, получатели и дарители |
| `WISHENKA-35` | `INFO` | `wishenka.wishlists.deletion` | `account_deletion_started` | `subject_hash_prefix` (`str`, 12 hex-символов `HMAC-SHA256`), `confirmed` (`True`) | `telegram_id`, `users.id`, `username`, `display_name`, `avatar_url`, `birthday` |
| `WISHENKA-35` | `INFO` | `wishenka.wishlists.deletion` | `collaborative_wishlist_ownership_transferred` | `subject_hash_prefix`, `wishlist_id` (`int`), `wishlist_status` (`active` \| `archived`), `selected_role_rank` (`1` \| `2` \| `3`), `tie_breaker_level` (`role_rank` \| `joined_at` \| `user_created_at` \| `telegram_id`), `is_collaborative` (`True`) | `telegram_id` удаляемого/преемника, `username`, `display_name`, `item_id`, `reservation_id` |
| `WISHENKA-35` | `INFO` | `wishenka.wishlists.deletion` | `account_deletion_completed` | `subject_hash_prefix`, `already_deleted` (`bool`), `deleted_lists_count` (`int`), `transferred_lists_count` (`int`), `cancelled_reservations_count` (`int`), `anonymized_items_count` (`int`), `revocation_recorded` (`bool`), `duration_ms` (`float`) | `telegram_id`, `users.id`, `chat_id`, `username`, `display_name`, `avatar_url`, `birthday`, связки `(reservation_id, giver, recipient)` |
| `WISHENKA-35` | `ERROR` | `wishenka.wishlists.deletion` | `account_deletion_failed` | `subject_hash_prefix`, `stage` (`reservations` \| `owned_lists` \| `member_exit` \| `pii_purge` \| `revocation` \| `transaction`), `error_type` (`type(exc).__name__`), `rolled_back` (`True`), `duration_ms` (`float`) | `telegram_id`, SQL-параметры с ПДн, токены, связки броней |
| `WISHENKA-35` | `WARNING` | `wishenka.auth.dependencies` | `session_rejected_revoked_or_deleted` | `reason` (`user_not_found` \| `session_revoked`), `subject_hash_prefix`, `has_user_id_claim` (`bool`) | Значение cookie/Bearer-токена, `secret_key`, `telegram_id`, `username`, `display_name` |
| `WISHENKA-35` | `DEBUG` | `wishenka.notices.store` / `wishenka.notices.reminders` | `notice_aborted_user_deleted` | `channel` (`notice_outbox` \| `reminder_outbox`), `reason` (`user_or_destination_deleted`) | `giver_user_id`, `recipient_user_id`, `wishlist_id`, `item_id`, `birthday` |
| `WISHENKA-35` | `INFO` (при `purged_count > 0`) / `DEBUG` (при `0`) | `wishenka.wishlists.cleanup` | `session_revocations_purged` | `purged_count` (`int`), `duration_ms` (`float`) | Полный `subject_hash` / `telegram_id` |

### Log Structure

Формат логов определяется [`wishenka/logging.py`](file:///home/src/wishenka/logging.py):

- **Structured logs**: `yes` — при `json_logs=True` (`JsonFormatter`) каждая запись выводится как JSON-строка с ключами `timestamp`, `level`, `logger`, `message`, опциональным `exception` и словарём `extra` для всех прикладных атрибутов, переданных через `extra={...}`. При `json_logs=False` используется консольный формат `%(asctime)s [%(levelname)s] %(name)s: %(message)s`.
- **Includes context**: `yes` — контекст передаётся плоскими скалярными полями в `extra` (`str`, `int`, `float`, `bool`) без вложенных структур, дампов DTO/ORM, списков SQL-строк и HTML/JSON-тел запросов.
- **Log levels**: `ERROR`, `WARNING`, `INFO`, `DEBUG` (`CRITICAL` — только при фатальном сбое инициализации приложения).

#### Жёсткие правила санитизации и инварианты приватности

1. **Запрет ПДн в логах (`FR-16`):** поля `first_name`, `last_name`, `display_name`, `username`, `avatar_url` / `photo_url`, `birthday` (`YYYY-MM-DD`, `--MM-DD`, day/month/year), содержимое `support_tickets`, `bot_drafts` и названия желаний/списков **никогда** не логируются.
2. **Корреляция удаления без следов ПДн:** в событиях `WISHENKA-35` (`account_deletion_*`, `collaborative_wishlist_ownership_transferred`, `session_rejected_revoked_or_deleted`) вместо `telegram_id` используется `subject_hash_prefix` — первые 12 hex-символов `HMAC-SHA256(settings.secret_key, f"deleted:{telegram_id}")`. Это гарантирует трассируемость транзакции без сохранения `telegram_id` в агрегаторах логов после удаления аккаунта.
3. **Запрет секретов:** никогда не логируются `initData`, cookie/Bearer токены `SessionTokenService`, `settings.secret_key`, CSRF-токены, токен Telegram-бота (включая URL вида `api.telegram.org/file/bot<TOKEN>/...`), токены `wl_tokens` / `wl_invite_tokens`.
4. **Тайна сюрприза (`FR-15`):** запрещено логировать связки `(reservation_id, giver_user_id, recipient_user_id, item_id)` или детали отменённых/сохранённых броней при удалении аккаунта и передаче владения — фиксируются только агрегированные счётчики (`cancelled_reservations_count`, `anonymized_items_count`).

---

## Metrics Implementation (if applicable)

В текущей кодовой базе экспортер Prometheus/OpenTelemetry не зафиксирован; метрики ниже задают канонический контракт для инструментовки в `WISHENKA-33/34/35` (через реестр метрик при его наличии либо агрегацией структурированных полей `JsonFormatter` в системе сбора логов). Все метки (labels) имеют строго низкую кардинальность — **без `user_id`, `telegram_id`, `wishlist_id` и `subject_hash_prefix`**.

### Performance Metrics

- **Account deletion transaction latency**: `wishenka_account_deletion_duration_seconds` (Histogram, labels: `outcome` ∈ `{completed, already_deleted, error}`) — `AccountDeletionService.delete_account` (`wishenka/wishlists/deletion.py`, `WISHENKA-35`). Соответствует полю лога `duration_ms` в `account_deletion_completed` / `account_deletion_failed`.
- **Deletion preview latency**: `wishenka_deletion_preview_duration_seconds` (Histogram) — `AccountDeletionService.preview_account_deletion` (`WISHENKA-35`).
- **Revocation cleanup latency**: `wishenka_revocation_cleanup_duration_seconds` (Histogram) — очистка `deleted_session_revocations` в `wishenka/wishlists/cleanup.py` (`WISHENKA-35`).
- **Error rate**: вычисляется по `wishenka_account_deletions_total{outcome="error"} / wishenka_account_deletions_total` и доле `account_deletion_failed` среди `account_deletion_started`.

### Business Metrics

- `wishenka_i18n_locale_switches_total` (Counter, labels: `from_locale` ∈ `{ru, en}`, `to_locale` ∈ `{ru, en}`) — явные переключения локали через `PATCH /api/profile/locale` (`WISHENKA-33`).
- `wishenka_i18n_auto_resolutions_total` (Counter, labels: `locale` ∈ `{ru, en}`, `channel` ∈ `{miniapp_auth, bot_update, public_share}`) — автоматические определения локали (`WISHENKA-33`).
- `wishenka_profile_birthday_updates_total` (Counter, labels: `source` ∈ `{manual, telegram}`, `action` ∈ `{set, cleared, skipped_manual_override}`) — обновления и приоритет ручной даты рождения (`WISHENKA-34`).
- `wishenka_notification_settings_updates_total` (Counter, labels: `scope` ∈ `{global, wishlist}`, `event_type` ∈ `{gift_received, wishlist_changes, reservation_changes, reminders}`, `enabled` ∈ `{true, false}`) — изменения пользовательских и списочных настроек уведомлений (`WISHENKA-34`).
- `wishenka_account_deletions_total` (Counter, labels: `outcome` ∈ `{completed, already_deleted, error}`) — итоги вызовов удаления аккаунта (`WISHENKA-35`).
- `wishenka_account_deletion_entities_total` (Counter, labels: `entity` ∈ `{deleted_lists, transferred_lists, cancelled_reservations, anonymized_items}`) — агрегированное количество затронутых сущностей при удалении (`WISHENKA-35`).

### System Health Metrics

- **Component status (i18n catalog integrity)**: `wishenka_i18n_missing_keys_total` (Counter, labels: `locale` ∈ `{ru, en}`) — пропуски ключей в `wishenka/i18n/` (`WISHENKA-33`).
- **Component status (Telegram best-effort sync)**: `wishenka_telegram_best_effort_sync_errors_total` (Counter, labels: `operation` ∈ `{set_my_commands, get_chat_birthdate}`) — сбои фоновых вызовов Telegram API, не блокирующих основной поток (`WISHENKA-33`, `WISHENKA-34`).
- **Security & Auth hygiene**:
  - `wishenka_profile_avatar_rejections_total` (Counter, labels: `reason` ∈ `{invalid_scheme, bot_token_url_blocked, exceeds_max_length}`) — срабатывания защиты URL аватара (`WISHENKA-34`).
  - `wishenka_auth_revoked_rejections_total` (Counter, labels: `reason` ∈ `{user_not_found, session_revoked}`) — отказы `401` для токенов удалённых пользователей (`WISHENKA-35`).
- **Database / Outbox hygiene**:
  - `wishenka_notices_aborted_deleted_user_total` (Counter, labels: `channel` ∈ `{notice_outbox, reminder_outbox}`) — отмены отправки в `refresh_claim`/`refresh_reminder` после удаления аккаунта (`WISHENKA-35`).
  - `wishenka_revocation_table_expired_purged_total` (Counter) — удалённые истёкшие записи из `deleted_session_revocations` (`WISHENKA-35`).
- **Resource usage**: CPU, memory, disk — `N/A` на уровне прикладного контракта `WISHENKA-32` (собирается базовым рантаймом контейнера/ОС).

---

## Monitoring Integration

Целевая интеграция (реализуется и проверяется в `WISHENKA-33`, `WISHENKA-34`, `WISHENKA-35`; в `WISHENKA-32` не применимо к коду):

- [ ] Prometheus metrics (опционально при подключении экспортера к FastAPI/worker; базовый сбор гарантирован через поля JSON-логов)
- [ ] Grafana dashboards (панели: `account_deletions` latency/outcomes, `i18n` switch ratio & missing keys, `revoked_sessions` rejections)
- [ ] Alerting rules:
  - Любое событие `account_deletion_failed` (`ERROR`, `rolled_back=True`) → критический алерт на расследование сбоя атомарности / SQLite lock.
  - Любое событие `profile_avatar_rejected` с `reason="bot_token_url_blocked"` → алерт безопасности.
  - Ненулевой темп `i18n_missing_translation_key` после релиза → предупреждение о рассинхронизации словарей `RU`/`EN`.
  - Всплеск `bot_commands_locale_sync_failed` или `profile_birthday_telegram_fetch_failed` → предупреждение о деградации Telegram API.
- [x] Log aggregation (контракт полностью совместим с `JsonFormatter` в [`wishenka/logging.py`](file:///home/src/wishenka/logging.py) для ELK / Loki / stdout-коллекторов)

---

## Validation Results

Поскольку `WISHENKA-32` не изменяет Python-код, ниже приведены статус в `WISHENKA-32` и **обязательные критерии приёмки (log & metric assertions)** для автоматических тестов (`pytest` + `caplog` + `JsonFormatter`) в `WISHENKA-33`, `WISHENKA-34` и `WISHENKA-35`:

- [x] Контракт формата логов согласован с `JsonFormatter` (`timestamp`, `level`, `logger`, `message`, `extra`) и консольным форматтером [`wishenka/logging.py`](file:///home/src/wishenka/logging.py).
- [x] В спецификации исключено логирование крупных структур, ПДн, секретов и связок, нарушающих Surprise Invariant (`FR-15`, `FR-16`).
- [ ] Runtime-верификация в `WISHENKA-33` (выполняется при реализации `WISHENKA-33`):
  - `caplog` при `PATCH /api/profile/locale` фиксирует `INFO` `locale_explicit_updated` (`previous_locale`, `new_locale`, `locale_source="explicit"`) без ПДн и токенов.
  - `caplog` при обращении к отсутствующему ключу `t(...)` фиксирует `WARNING` `i18n_missing_translation_key` с `i18n_key`.
  - При имитации ошибки `bot.set_my_commands` фиксируется `WARNING` `bot_commands_locale_sync_failed` (`error_type`), HTTP-ответ остаётся `200`, токен бота отсутствует в `caplog.text`.
  - Вывод через `JsonFormatter().format(record)` парсится `json.loads(...)` без ошибок и содержит блок `extra`.
- [ ] Runtime-верификация в `WISHENKA-34` (выполняется при реализации `WISHENKA-34`):
  - Передача Bot API URL (`https://api.telegram.org/file/bot<TOKEN>/...`) в `photo_url` вызывает `WARNING` `profile_avatar_rejected` (`reason="bot_token_url_blocked"`), и ни токен, ни URL не встречаются в `caplog.text`.
  - `PATCH /api/profile` с датой `--05-14` фиксирует `INFO` `profile_birthday_manual_updated` (`action="set"`, `birthday_source="manual"`, `has_year=False`), при этом строка даты (`--05-14` / `05-14`) отсутствует в `caplog.text` и JSON-строках.
  - Повторная синхронизация Telegram при `birthday_source="manual"` фиксирует `DEBUG` `profile_birthday_synced` (`outcome="skipped_manual_override"`).
  - Обновление общих и списочных настроек уведомлений фиксирует `INFO` `notification_settings_updated` с корректными `scope`, `event_type`, `enabled`.
- [ ] Runtime-верификация в `WISHENKA-35` (выполняется при реализации `WISHENKA-35`):
  - Успешное удаление аккаунта фиксирует `INFO` `account_deletion_started`, `INFO` `collaborative_wishlist_ownership_transferred` (при передаче списка; с `selected_role_rank` и `tie_breaker_level`) и `INFO` `account_deletion_completed` (`already_deleted=False`, точные счётчики сущностей, `revocation_recorded=True`, `duration_ms >= 0`).
  - Негативные проверки приватности (`caplog.text` и сериализованный `JsonFormatter`): ни в одном событии удаления/передачи/отзыва не содержатся `telegram_id`, `first_name`, `last_name`, `username`, `avatar_url`, `birthday`, значения cookie/Bearer-токенов, а также `reservation_id` / `item_id` / `recipient_user_id` других пользователей (`FR-15`, `FR-16`).
  - Искусственный сбой внутри `BEGIN IMMEDIATE` фиксирует `ERROR` `account_deletion_failed` (`rolled_back=True`, `stage`, `error_type`), а повторный вызов удаления фиксирует `INFO` `account_deletion_completed` (`already_deleted=True`).
  - Запрос с отозванным токеном после удаления фиксирует `WARNING` `session_rejected_revoked_or_deleted` без раскрытия токена; прерванная отправка воркером фиксирует `DEBUG` `notice_aborted_user_deleted`; чистка `deleted_session_revocations` фиксирует `session_revocations_purged` (`purged_count`).

---

## Notes

- В [`wishenka/logging.py`](file:///home/src/wishenka/logging.py) словарь `standard_fields` в `JsonFormatter` отсекает служебные поля `LogRecord` и сериализует остальные публичные поля в `log_data["extra"]` через `json.dumps(..., default=str)`. Поэтому в `WISHENKA-33/34/35` все поля контракта должны передаваться через параметр `extra={...}` и иметь имена, не конфликтующие со `standard_fields` (например, избегать ключа `name` — использовать `event` или плоские доменные ключи вроде `user_id`, `wishlist_id`, `locale`, `subject_hash_prefix`).
- `WISHENKA-32` не содержит runtime-изменений; проверка соблюдения данного документа должна входить в code review и Step 6 (`50-observability.md`) каждой дочерней задачи (`WISHENKA-33`, `WISHENKA-34`, `WISHENKA-35`).
