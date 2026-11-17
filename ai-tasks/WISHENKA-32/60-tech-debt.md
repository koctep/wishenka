# WISHENKA-32: Technical Debt Analysis

> **Контекст скоупа:** `WISHENKA-32` — задача декомпозиции, архитектуры, функциональной спецификации (`in-docs/spec.md`) и контрактов наблюдаемости (`ai-tasks/WISHENKA-32/50-observability.md`). Изменения в runtime-коде Python и автотестах в рамках `WISHENKA-32` не выполнялись (`N/A` для live-правок кода). Ниже зафиксированы архитектурные компромиссы, допущения, пограничные случаи передачи контрактов в задачи реализации спринта 2112 (`WISHENKA-33`, `WISHENKA-34`, `WISHENKA-35`) и вынесенный технический долг.

## Shortcuts Taken

1. **Сохранение исторического расщепления ключей пользователя (`users.telegram_id` vs `users.id`) и отсутствующих FK-каскадов (`20-architecture.md` §1.2, §1.4, §4.2, Q&A Q1):**
   - Таблицы домена вишлистов, настроек уведомлений и outbox (`wl_lists.owner_id`, `wl_members.user_id`, `wl_items.recipient_user_id`, `wl_reservations.user_id`, `wl_favorites.user_id`, `wl_view_history.user_id`, `wl_idempotency_records.actor_id`, `notification_outbox.giver_user_id`, `notice_receipt_keys.giver_user_id`, `user_notification_settings.user_id`, `wl_list_notification_settings.user_id`, `reminder_outbox.user_id`) используют `users.telegram_id` без `FOREIGN KEY` на `users`, тогда как `bot_destinations.user_id`, `birthday_entries.owner_id`, `birthday_input.owner_id`, `support_input.owner_id` ссылаются на автоинкрементный PK `users.id` (а `support_tickets` хранит оба столбца `owner_id` и `telegram_id`).
   - В `wl_tokens`, `wl_invite_tokens` и `reminder_outbox` нет `FOREIGN KEY ... ON DELETE CASCADE` на `wl_lists`.
   - **Компромисс:** вместо масштабного рефакторинга схемы БД в `WISHENKA-35` каскадное удаление компенсирует это вручную внутри `BEGIN IMMEDIATE`, резолвя оба ключа (`tg_id`, `internal_user_id`, `chat_id`) и явно удаляя строки из каждой таблицы. Любая новая таблица с привязкой к пользователю без FK-каскада должна быть явно добавлена в `AccountDeletionService`, иначе в БД останутся осиротевшие ПДн.

2. **Двойное поддержание DDL таблицы `users` в Alembic и `UserStore.initialize()` (`20-architecture.md` §1.1, §2.3):**
   - Миграция `users` (включая `avatar_url`, `birthday`, `birthday_source`, `locale`, `locale_source`) и `deleted_session_revocations` добавляется в цепочку `wishenka/wishlists/alembic/versions/` от ревизии `add_idempotency_records` (при сохранении `_adopt_known_schema` для старых БД без `alembic_version`), а `UserStore.initialize()` сохраняет идемпотентный `CREATE TABLE IF NOT EXISTS users` и проверку `PRAGMA table_info(users)` для изолированных unit-тестов без запуска `WishlistStore`.
   - **Компромисс:** схема `users` поддерживается в двух местах, что создаёт риск расхождения DDL при последующих миграциях.

3. **Обратно-совместимый обход проверки `users` в `get_optional_current_user` (`20-architecture.md` §4.2.6):**
   - Если `claims.user_id is not None`, но таблица `users` в БД отсутствует, проверка существования пользователя пропускается ради изолированных маршрутных тестов без `UserStore`. В ошибочно сконфигурированной среде это тихо отключит проверку живости аккаунта через `users` (дополнительно к проверке `deleted_session_revocations`).

4. **Точечное сохранение `is_collaborative = 1` при передаче владения вместо рефакторинга `WishlistAccessPolicy` (`20-architecture.md` §1.4, §4.2.3.C, Q&A Q2):**
   - `WishlistService.remove_member()` сбрасывает `wl.is_collaborative = len(wl.members) > 0`, однако при удалении владельца совместного списка с одним оставшимся участником сброс `is_collaborative` в `0` заставил бы `WishlistAccessPolicy.is_recipient_id` считать нового владельца получателем *всех* желаний списка. Поэтому `AccountDeletionService` (`WISHENKA-35`) сознательно оставляет `is_collaborative = 1`, даже если `wl_members` становится пустым.

5. **Обезличивание `wl_items` без поля `created_by` и денормализация `wl_lists.owner_name` (`20-architecture.md` §1.2, §2.1, §4.2.4):**
   - Таблица `wl_items` хранит `recipient_user_id` и `recipient_name`, но не имеет столбца `created_by`. Обезличивание авторства (`FR-12`, `FR-13`) сводится к занулению `recipient_user_id = NULL, recipient_name = NULL` для желаний, где получателем был удаляемый пользователь; если `created_by` появится позже, каскад удаления придётся дорабатывать.
   - `wl_lists.owner_name` заполняется при создании списка и при передаче владения, но не актуализируется при последующих изменениях имени пользователя в Telegram (`FR-4`), в отличие от вычисляемого `UserRecord.display_name` в списке участников.

6. **Best-effort обновление меню команд бота и полная перезагрузка Mini App при смене языка (`20-architecture.md` §3.2.1, §3.2.2):**
   - При `PATCH /api/profile/locale` вызов `bot.set_my_commands(..., scope=BotCommandScopeChat)` выполняется в режиме best-effort (только если сконфигурирован `Bot` и существует запись в `bot_destinations`) без очереди повторных попыток.
   - Обновление открытого экрана Mini App опирается на заголовок `HX-Refresh: true` (полная перерисовка вместо точечного swap фрагментов).

7. **Отзыв stateless-сессий через `deleted_session_revocations` и зависимость от фоновой очистки (`20-architecture.md` §2.2, §4.2.6):**
   - Использование `HMAC-SHA256(settings.secret_key, f"deleted:{telegram_id}")` исключает ПДн из таблицы отзывов, но завязано на неизменность `settings.secret_key` (что консистентно, так как смена `secret_key` сама по себе инвалидирует старые HMAC-токены) и требует регулярного запуска `wishenka/wishlists/cleanup.py`.

8. **Log-only метрики до подключения экспортера Prometheus/OpenTelemetry (`50-observability.md`):**
   - Поскольку в текущей кодовой базе экспортер Prometheus/OTel не подключён, инструментация `WISHENKA-33/34/35` опирается на структурированные поля JSON-логов `JsonFormatter` (`extra`), а подключение `/metrics`, дашбордов Grafana и правил алертинга оставлено опциональным/внешним шагом.

## Code Quality Issues

1. **Неоднозначность сигнатуры `UserStore.upsert_from_bot` vs `UserStore.upsert_user(sync_avatar=...)` (`WISHENKA-33`, `WISHENKA-34`, `20-architecture.md` §3.2.2 vs §5.1):**
   - В §3.2.2 middleware бота вызывает `UserStore.upsert_from_bot(event.from_user)` (передавая `aiogram.types.User`), тогда как в §5.1 описан только `UserStore.upsert_user(user: TelegramUser, *, sync_avatar: bool = True) -> UserRecord`.
   - При реализации в `WISHENKA-33`/`WISHENKA-34` необходимо явно определить единый адаптер `upsert_from_bot` поверх `upsert_user(..., sync_avatar=False)`, чтобы бот-апдейты гарантированно не затирали `avatar_url`.

2. **Неподтверждённые ключи таблиц состояния бота и токенов приглашений (`WISHENKA-35`, `20-architecture.md` §4.2.3.B, §4.2.5):**
   - В `20-architecture.md` явно оставлены на уточнение в коде при реализации `WISHENKA-35`: точный ключ `owner_id` для `support_input` (`bot/support.py`), точные ключи `owner`/`chat` для `bot_drafts` и `bot_capture_order` (`bot/capture.py`), а также предположение об очистке `wl_invite_tokens` по одному `:invite_token`.

3. **Координация единой схемы `users` и миграции Alembic между `WISHENKA-33`, `WISHENKA-34` и смежными задачами (`20-architecture.md` §2.3, таблица декомпозиции):**
   - И `WISHENKA-33`, и `WISHENKA-34` затрагивают `UserRecord`, `UserStore` и ветку миграций от `add_idempotency_records`. Также в `20-architecture.md` отмечены смежные задачи `WISHENKA-73` и `WISHENKA-89`, которые должны использовать общую схему `users` без конкурирующих таблиц и параллельных веток Alembic.

4. **Несоответствие словаря ролей `coauthor` / `collaborator` между `spec.md` §3 и `20-architecture.md` (`WISHENKA-35`):**
   - В `10-requirements.md` (`FR-12`), `in-docs/spec.md` (§11.2, §16) и `20-architecture.md` (§4.2.3.C) предусмотрен уровень приоритета «соавтор» (`coauthor` / `collaborator` -> `role_rank = 2` *при наличии роли*), однако в `in-docs/spec.md` §3 и enum `WishlistRole` (`wishenka/wishlists/models.py`) сейчас присутствуют только `owner`, `admin`, `member`. Требуется аккуратное маппирование строковых ролей без рассинхронизации с `WishlistRole` и тестовыми фикстурами.

5. **Переходное сосуществование `users.language_code` и `users.locale` (`WISHENKA-33`, `20-architecture.md` §1.3, §3.2.3):**
   - В кодовой базе `wishenka/notices/store.py` (fallback `"ru"`), `wishenka/notices/reminders.py` (неявный fallback на русский) и `wishenka/bot/entry.py` ранее читали `language_code` с несогласованным fallback. Все потребители в `WISHENKA-33` должны быть полностью переведены на `u.locale` с единым fallback `'en'`.

6. **Единая валидация и сериализация `Birthday` (`YYYY-MM-DD` и `--MM-DD`, включая `--02-29`) (`WISHENKA-34`, `20-architecture.md` §1.2, §2.1):**
   - `ChatFullInfo.birthdate` возвращает структуру `Birthdate(day, month, year | None)`. Необходимо выделить общую функцию форматирования и календарной валидации без дублирования между бот-синхронизацией и `PATCH /api/profile`.

## Missing Tests

- **Для `WISHENKA-32`:** `N/A — no behavioral change` (код Python и тестовый набор в этой задаче не изменялись; новых тестов без маркеров таймаута — блокеров согласно `do-testing` — не добавлялось).
- **Обязательное покрытие, запланированное в `20-architecture.md` (Step 3 failing-repro матрица) и `50-observability.md` (критерии `caplog` / `JsonFormatter`) для задач реализации — каждый Python-тест должен иметь явный `@pytest.mark.timeout(...)` / `pytestmark` и полную изоляцию от сети Telegram:**
  - **`WISHENKA-33` (`tests/test_i18n_sync.py` и проверки наблюдаемости):**
    - Автоопределение локали при первом входе (`ru*` → `ru`, `en*`/иные/`None` → `en`, `locale_source="auto"`).
    - Автообновление локали при смене языка клиента в режиме `auto` и сохранение выбора после `PATCH /api/profile/locale` (`locale_source="explicit"`).
    - Мгновенная синхронизация после переключения в Mini App: SSR-рендер, ответы бота на всех роутерах (`entry`, `capture`, `birthdays`, `support`), уже поставленные `pending`-записи в `notification_outbox` и `reminder_outbox`.
    - Полнота ключей каталога переводов (`ru` ↔ `en`) и проверка `caplog`: `locale_explicit_updated`, `i18n_missing_translation_key`, `bot_commands_locale_sync_failed` (без падения HTTP `200` и без утечки токена бота).
  - **`WISHENKA-34` (`tests/test_profile_settings.py` и проверки наблюдаемости):**
    - Очистка `username` и `avatar_url` при удалении/скрытии в `initData`, но сохранение `avatar_url` при бот-апдейтах (`sync_avatar=False`).
    - Блокировка небезопасных схем и URL вида `https://api.telegram.org/file/bot<TOKEN>/...` в `photo_url` + проверка `caplog` (`profile_avatar_rejected` без токена и URL).
    - Матрица переходов `birthday` / `birthday_source` (`YYYY-MM-DD`, `--MM-DD`, `--02-29`, заполнение и очистка из `ChatFullInfo.birthdate`, абсолютный приоритет ручного ввода и ручной очистки `birthday_source="manual"`) + проверка отсутствия значения даты в `caplog.text`.
    - CRUD для `user_notification_settings` и `wl_list_notification_settings` с приоритетом настроек вишлиста и отображение `display_name`/аватара участников вместо `User <id>`.
  - **`WISHENKA-35` (`tests/test_account_deletion.py` и проверки наблюдаемости):**
    - Удаление личных, soft-deleted и пустых совместных вишлистов с освобождением `available_quantity` и без уведомлений получателям (`FR-15`).
    - Детерминированный выбор преемника (`role_rank` → `joined_at` → `users.created_at` → `telegram_id`), сохранение `is_collaborative = 1` и нейтральное уведомление `membership_changed`.
    - Выход из чужого совместного вишлиста с обезличиванием `wl_items` и сохранением чужих активных/купленных броней.
    - Полная очистка всех таблиц ПДн и состояния бота, откат при искусственном сбое внутри `BEGIN IMMEDIATE` (`NFR-1`), идемпотентность повторного вызова (`NFR-3`), немедленный отзыв старых сессий (как с `user_id`, так и без `user_id`) даже при повторной регистрации (`FR-17`), отмена доставки в `refresh_claim` / `refresh_reminder`, очистка `deleted_session_revocations` и негативные проверки `caplog` / `JsonFormatter` на отсутствие ПДн, токенов и связок `(reservation_id, giver, recipient, item_id)`.

## Performance Concerns

1. **Неопределённая частота опроса `ChatFullInfo.birthdate` через `bot.get_chat` (`WISHENKA-34`):**
   - `20-architecture.md` фиксирует best-effort синхронизацию `ChatFullInfo.birthdate`, но не задаёт политику троттлинга (например, только на `/start`, по TTL раз в N часов или при открытии профиля). Вызов `getChat` на каждом входящем апдейте бота создаст лишнюю сетевую задержку и риск rate-limit Telegram Bot API, а опрос только на `/start` оставляет `birthday` устаревшим (в том числе при скрытии даты в Telegram).

2. **Длительность блокировки записи `BEGIN IMMEDIATE` при каскадном удалении аккаунта (`WISHENKA-35`):**
   - Атомарное удаление охватывает ~15+ таблиц в SQLite WAL (`PRAGMA busy_timeout = 5000`), сериализуя конкурентные бронирования и доставку уведомлений (`NoticeStore`, `ReminderScheduler`). Для предотвращения table-scan и сокращения времени удержания write-lock критично наличие индексов на ключевых столбцах удаления (`wl_lists(owner_id)`, `wl_members(user_id)`, `wl_reservations(user_id)`, `wl_items(recipient_user_id)`, `idx_deleted_session_revocations_expires`).

3. **Дополнительные запросы к `users` на каждом HTTP-запросе (`WISHENKA-33`, `WISHENKA-35`):**
   - Чтение актуальной `users.locale` в `get_request_locale` (`WISHENKA-33`) и проверка существования `users.id` в `get_optional_current_user` (`WISHENKA-35`) происходят на каждом авторизованном запросе Mini App. Во избежание дублирования запросов целесообразно читать строку `UserRecord` по `telegram_id` один раз в рамках request-контекста (FastAPI dependency cache).

4. **Таймаут/асинхронность `bot.set_my_commands` в `PATCH /api/profile/locale` (`WISHENKA-33`):**
   - Чтобы сбой или высокая задержка Telegram Bot API не блокировали HTTP-ответ пользователю Mini App, best-effort вызов `set_my_commands` должен выполняться с жёстким таймаутом или в фоновой задаче (`BackgroundTasks`).

5. **Накопление записей в `deleted_session_revocations` (`WISHENKA-35`):**
   - Без регулярного запуска `wishenka/wishlists/cleanup.py` таблица отзывов будет расти по одной строке на каждое удаление аккаунта.

## Follow-up Tasks

### Уточнения и работы в рамках существующих задач Sprint 2112 (уже заведены в Jira)

Следующие задачи **уже созданы в Jira (Sprint 2112)** — выявленные по ним детали из разделов выше относятся к их прямому скоупу реализации и не требуют создания отдельных Debt-тикетов:

- **`WISHENKA-33` (existing Story — i18n `RU`/`EN`):** зафиксировать явный адаптер `UserStore.upsert_from_bot` → `upsert_user(..., sync_avatar=False)`, перевести все чтения с `language_code` на `u.locale` с fallback `'en'`, выполнить best-effort `bot.set_my_commands` без блокировки HTTP-ответа (и синхронизацию меню при `/start`), объединить чтение пользователя в request-зависимости, реализовать автотесты синхронизации i18n, паритета ключей и `caplog` с `@pytest.mark.timeout(...)`.
- **`WISHENKA-34` (existing Story — расширенный профиль и настройки уведомлений):** определить политику троттлинга/триггера `bot.get_chat` для `ChatFullInfo.birthdate`, вынести единый валидатор/форматтер `YYYY-MM-DD` / `--MM-DD` (`--02-29`), скоординировать общую ревизию Alembic `users` с `WISHENKA-33`, реализовать автотесты профиля, защиты `photo_url` и настроек уведомлений с `@pytest.mark.timeout(...)`.
- **`WISHENKA-35` (existing Story — удаление аккаунта, передача владения и отзыв сессий):** подтвердить в коде точные ключи удаления для `support_input` (`bot/support.py`), `bot_drafts` / `bot_capture_order` (`bot/capture.py`) и `wl_invite_tokens`, обеспечить сохранение `is_collaborative = 1` при передаче владения и корректный маппинг ролей с учётом `WishlistRole`, проверить индексы таблиц под `BEGIN IMMEDIATE`, реализовать автотесты каскада, отката, идемпотентности, отзыва сессий и негативные `caplog`-проверки ПДн/тайны сюрприза с `@pytest.mark.timeout(...)`.

### Новые follow-up задачи техдолга (вне скоупа `WISHENKA-33` / `WISHENKA-34` / `WISHENKA-35`)

1. **Унификация пользовательских ключей БД (`telegram_id` vs `users.id`), добавление каскадных FK и консолидация DDL `users` в Alembic**
   - **Priority:** `Medium`
   - **Jira:** [WISHENKA-188](https://pypost.atlassian.net/browse/WISHENKA-188) (8 SP)
   - **Scope:** устранить историческое расщепление внешних ключей между `users.telegram_id` (таблицы `wl_*`, `notice_*`, `reminder_outbox`) и `users.id` (`bot_destinations`, `birthday_*`, `support_*`), добавить недостающие `FOREIGN KEY ... ON DELETE CASCADE` для `wl_tokens`, `wl_invite_tokens` и `reminder_outbox`, а также перенести управление DDL `users` исключительно в Alembic (исключив дублирование в `UserStore.initialize()`).

2. **Подключение Prometheus/OpenTelemetry экспортера метрик, дашбордов Grafana и правил алертинга**
   - **Priority:** `Low`
   - **Jira:** [WISHENKA-189](https://pypost.atlassian.net/browse/WISHENKA-189) (8 SP)
   - **Scope:** реализовать экспортер метрик (`/metrics` endpoint или OTel-коллектор) поверх контракта счётчиков и гистограмм из `ai-tasks/WISHENKA-32/50-observability.md`, настроить дашборды Grafana и правила алертинга (`account_deletion_failed`, `bot_token_url_blocked`, `i18n_missing_translation_key`, всплески `telegram_best_effort_sync_errors`).

3. **Синхронизация или устранение денормализованного столбца `wl_lists.owner_name`**
   - **Priority:** `Low`
   - **Jira:** [WISHENKA-190](https://pypost.atlassian.net/browse/WISHENKA-190) (3 SP)
   - **Scope:** исключить устаревание отображаемого имени владельца в `wl_lists.owner_name` при смене `first_name`/`last_name` в Telegram (актуализировать `owner_name` при `UserStore.upsert_user` либо вычислять имя владельца динамически через `users` / `UserRecord.display_name`).

4. **Разделение семантики флага `is_collaborative` и выравнивание ролевой модели (`coauthor`)**
   - **Priority:** `Low`
   - **Jira:** [WISHENKA-191](https://pypost.atlassian.net/browse/WISHENKA-191) (5 SP)
   - **Scope:** устранить расхождение между `WishlistService.remove_member()` (сбрасывающим `is_collaborative`) и сохранением `is_collaborative = 1` при передаче владения в `AccountDeletionService`, отделив признак наличия других участников от режима персональной привязки `recipient_user_id` в `WishlistAccessPolicy.is_recipient_id`; при продуктовом решении о введении роли `coauthor` синхронизировать `in-docs/spec.md` §3 и enum `WishlistRole`.
