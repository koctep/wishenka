# Архитектура сервиса Telegram Wishlist Service

Данный документ описывает общую техническую архитектуру сервиса **Wishlist Service («Вишенка»)**, согласованную в задаче [WISHENKA-2](https://pypost.atlassian.net/browse/WISHENKA-2) на основе спецификаций `specs/00-high.md` и `in-docs/spec.md`.

Полная детальная спецификация со схемами и DDL доступна в [`ai-tasks/WISHENKA-2/20-architecture.md`](../../ai-tasks/WISHENKA-2/20-architecture.md).

---

## 1. Технологический стек

- **Язык разработки:** Python 3.12+
- **Web-фреймворк:** FastAPI (ASGI)
- **Telegram Bot:** aiogram v3 (асинхронный бот)
- **Интерфейс Mini App (TMA):** Server-Side Rendering (FastAPI + Jinja2 + HTMX / Alpine.js) + Telegram WebApp JS script
- **СУБД:** Встраиваемая SQLite с `aiosqlite`
  - `PRAGMA journal_mode = WAL;` (параллельное чтение без блокировки писателей) — постоянное состояние файла БД: выбирается один раз при старте миграций вишлистов, а не на каждом соединении
  - `PRAGMA foreign_keys = ON;` (каскадная целостность; задаётся на каждом соединении)
  - `PRAGMA busy_timeout = 5000;` (на каждом соединении)
  - общая настройка транзакций вынесена в `wishenka/sqlite.py`:
    - `configure_immediate_transactions(sync_engine, *, busy_timeout_ms=5000)` выставляет `isolation_level = None`, `PRAGMA foreign_keys=ON` и `PRAGMA busy_timeout` на `connect`, а на `begin` пропускает `AUTOCOMMIT`, применяет `PRAGMA busy_timeout` и открывает `BEGIN` при `execution_options(read_only=True)` либо `BEGIN IMMEDIATE` для записи; используется в `WishlistStore` и `UserStore`
    - `is_sqlite_busy(exc)` рекурсивно проверяет `exc`, `.orig` и `.__cause__` на `SQLITE_BUSY` (`sqlite_errorcode` или сообщение `database is locked` / `database is busy`)
  - запись инвентаря одного желания и операции записи `UserStore` стартуют с `Connection.begin()`; слушатель `begin` выполняет `BEGIN IMMEDIATE` при `isolation_level = None`
- **ORM и миграции:** SQLAlchemy 2.0 (Async) + Alembic
  - Схема таблиц `wl_*` хранилища вишлистов создаётся и меняется только версионными ревизиями Alembic (`wishenka/wishlists/alembic/versions/`); ad-hoc `ALTER TABLE` в коде хранилища нет.
  - Таблица `users` в текущем baseline создаётся императивно в `UserStore.initialize()` вне цепочки Alembic; в согласованной целевой архитектуре `WISHENKA-32` (к реализации в `WISHENKA-33`/`WISHENKA-35`) эволюция `users` и таблица `deleted_session_revocations` переводятся на линейную ревизию Alembic (от `add_idempotency_records`) при сохранении строго согласованного DDL в `UserStore.initialize()`.
  - `WishlistStore.initialize()` при старте приводит БД к head: распознаёт и штампует legacy-схему без изменения данных, применяет `upgrade head`, выбирает WAL. Параллельный старт нескольких процессов сериализуется файлом `<db>.migrate.lock` (`fcntl`, только POSIX, ожидание до 60 с).
  - Для `:memory:` хранилище использует изолированный временный файл, который удаляется в `WishlistStore.dispose()`.
  - **DI-слой веб-маршрутов (`WISHENKA-80`):** HTTP-маршруты (`wishenka/web/routes/wishlists.py`, `items.py`, `sharing.py`, `receipts.py`, `items_ui.py`, `receipts_ui.py`) не вызывают `WishlistStore.execute(...)` с полной гидратацией БД; они инжектируют транзакционный `WishlistRepo` (`Annotated[WishlistRepository, Depends(get_wishlist_repository)]`) из `wishenka/web/dependencies.py` и выполняют точечные запросы/мутации через `RepoWishlistOps` (`wishenka/wishlists/repo_ops.py`), тогда как мутации инвентаря/броней/получений по одному желанию по-прежнему используют `WishlistStore.execute_wish` / `execute_wish_idempotent`. Подробнее: [`doc/dev/wishlists.md`](wishlists.md#web-route-di--repowishlistops-wishenka-80).
  - Подробности, добавление ревизии и диагностика: [`doc/dev/migrations.md`](migrations.md).
- **Парсинг ссылок:** httpx + BeautifulSoup4 (с защитой от SSRF)
- **Очередь сообщений:** Встроенный Transactional Outbox в SQLite + асинхронный воркер

---

## 2. Ключевые архитектурные инварианты

### 2.1. Тайна сюрприза (Surprise Invariant)
Получатель подарка ни при каких условиях не должен видеть информацию о бронировании, личности дарителя или факте покупки.
- **Реализация:** Двухуровневая изоляция.
  - На сервисном уровне DTO маскируются: для получателя отдается `WishItemRecipientViewDTO` (без полей бронирования).
  - Для дарителя отдается `WishItemGifterViewDTO` (с доступным остатком и признаком собственной брони).
  - В интерфейсе используются раздельные Jinja2 макросы для владельца и дарителя.
  - Детальная документация ролевой модели, DTO и инвариантов представлена в [`doc/dev/wishlists.md`](wishlists.md) и [`doc/dev/reservations.md`](reservations.md).

### 2.2. Предотвращение овербукинга и штучный учет

Несколько копий сервиса пишут один файл SQLite. Исключение записи инвентаря одного желания — wish-scoped транзакция WAL на движке вишлистов: `Connection.begin()`, слушатель `begin` выполняет `BEGIN IMMEDIATE`, у соединения `isolation_level = None`. `busy_timeout` равен 5000 мс. Redis в этом пути нет. `asyncio.Lock` внутри `ItemConcurrencyCoordinator` остаётся внутрипроцессным координатором и не виден другой копии процесса. Аналогично `UserStore` (`wishenka/users/store.py`) использует `configure_immediate_transactions`: мутации выполняются через `_immediate` (`BEGIN IMMEDIATE` с отображением `SQLITE_BUSY` в `UserStoreBusyError` → HTTP 503), а чтения `get_by_telegram_id` и `get_by_id` — через `_read` (`execution_options(read_only=True)`), не блокируясь на пишущей транзакции (см. [`doc/dev/users.md`](users.md)).

Занятые штуки (`occupied`) — сумма `quantity` броней в статусах `ACTIVE` и `PURCHASED`. Правила одного желания считаются внутри этой транзакции:

- Приход добавляет полученные штуки, пишет запись в `wl_receipts` и ограничен
  `requested − received`; при нуле остатка отклоняется (`NothingRemainingError`).
  Он не отменяет бронь и не ставит `ReservationStatus.COMPLETED`. Статуса
  `FULFILLED` нет. Обещание остаётся открытым. После успешного прихода
  `occupied + received` может превысить запрошенное количество.
- Новое или увеличенное обещание берёт свободный остаток `max(0, requested − received − occupied)`.
- Снижение запрошенного количества ниже `occupied + received` отклоняется. Строки остаются на последнем коммите.
- `SQLITE_BUSY` после `busy_timeout` становится `InventoryBusyError`: транзакция откатывается и ничего не меняет.

Запись изменившихся строк, HTTP 503 и журналы — в [`doc/dev/items.md`](items.md). Жизненный цикл броней — в [`doc/dev/reservations.md`](reservations.md).

### 2.3. Аутентификация в Telegram Mini App
1. TMA при открытии передает `window.Telegram.WebApp.initData`.
2. Бэкенд проверяет криптографическую подпись HMAC-SHA256 с токеном бота.
3. Выставляется защищенная `HttpOnly` `SameSite=None` Secure session cookie.
4. Все последующие HTMX-запросы автоматически аутентифицируются по cookie без оверхеда на повторную проверку подписи.

### 2.4. Профиль пользователя, i18n (`RU`/`EN`) и удаление аккаунта (целевой контракт `WISHENKA-32`)

> [!NOTE]
> В текущем baseline реализована базовая запись `users` (`id`, `telegram_id`, `first_name`, `last_name`, `username`, `language_code`, `is_premium`). Описанные ниже контракты декомпозированы в `WISHENKA-32` для реализации в `WISHENKA-33`, `WISHENKA-34` и `WISHENKA-35`.

- **Профиль (`WISHENKA-34`):** `avatar_url` принимается только из проверенного `https://` `WebAppUser.photo_url` (без Bot API proxy-URL с токеном бота) и очищается при `photo_url=None` в `initData`; `birthday` поддерживает форматы `YYYY-MM-DD` и `--MM-DD` с безусловным приоритетом ручного ввода (`birthday_source = 'manual'`) над синхронизацией `ChatFullInfo.birthdate`; `display_name` вычисляется из `first_name`/`last_name`.
- **Локализация `RU`/`EN` (`WISHENKA-33`):** `users.locale` (`'ru'` | `'en'`, fallback `'en'`) и `locale_source` (`'auto'` | `'explicit'`) в SQLite WAL служат единым источником истины для Mini App (SSR/HTMX без кеширования локали в `SessionClaims`), Telegram-бота (`aiogram` `LocaleMiddleware`) и воркеров `NoticeStore`/`ReminderScheduler` (замена чтения `u.language_code` на `u.locale`).
- **Удаление аккаунта и отзыв сессий (`WISHENKA-35`):** выполняется `AccountDeletionService` в единой транзакции `BEGIN IMMEDIATE` с `PRAGMA foreign_keys = ON`, учитывает историческое разделение таблиц по `users.telegram_id` (`wl_*`, `notification_outbox`, `reminder_outbox`, `user_notification_settings`) и `users.id` (`bot_destinations`, `birthday_entries`, `support_tickets`), детерминированно передаёт владение совместными вишлистами с сохранением `is_collaborative = 1` (для сохранения Surprise Invariant в `WishlistAccessPolicy.is_recipient_id`), обезличивает `wl_items.recipient_user_id` и отзывает все stateless-сессии через проверку живости `users.id` (`AUTOINCREMENT`) и таблицу `deleted_session_revocations` без хранения ПДн. Подробнее см. [`doc/dev/users.md`](users.md).

---

## 3. Схема данных (SQLite)

Основные таблицы:
- `users` — пользователи Telegram (реализованный baseline: `id`, `telegram_id`, `first_name`, `last_name`, `username`, `language_code`, `is_premium`, `created_at`, `updated_at`; целевой контракт `WISHENKA-33/34` добавляет `avatar_url`, `birthday`, `birthday_source`, `locale`, `locale_source`).
- `deleted_session_revocations` *(целевая таблица `WISHENKA-35`)* — хэшированные (`HMAC-SHA256`) маркеры отзыва stateless-сессий без `user_id` и без хранения ПДн (`subject_hash`, `revoked_before`, `expires_at`).
- `wishlists` — списки желаний (id, owner_id, title, event_title, event_date, is_collaborative, is_archived, public_slug).
- `wishlist_members` — соавторы совместных вишлистов (wishlist_id, user_id, role).
- `wish_items` — элементы вишлиста (id, wishlist_id, recipient_user_id, title, link, price, currency, quantity, received_quantity, is_archived).
- `reservations` — бронирования дарителей (id, wish_item_id, user_id, quantity, status: active/purchased/cancelled/completed).
- `user_wishlist_favorites` — избранные списки дарителя.
- `user_wishlist_views` — история недавних просмотров.
- `user_notification_settings` — настройки оповещений уровня пользователя (создана ревизией
  `add_notice_outbox`).
- `wl_list_notification_settings` — настройки оповещений уровня вишлиста (та же ревизия).
- `notification_outbox` — очередь отправки сообщений ботом (та же ревизия).
- `wl_receipts` — история получений желаний: количество и дата, без дарителя (ревизия
  `add_gift_receipts`).
- `wl_idempotency_records` — клиентские ключи идемпотентности для мутаций бронирования и получения
  подарков (ревизия `add_idempotency_records`, см. [`doc/dev/idempotency.md`](idempotency.md)).
- `receipt_delivery_fence` и `receipt_delivery_fence_audit` — долговечный межпроцессный барьер
  доставки уведомлений о получении (`in_flight` / `uncertain`) по ключу `(wish_item_id, user_id)` и
  аудит его ручного разрешения (ревизия `add_receipt_delivery_fence`, см.
  [`doc/dev/notifications.md`](notifications.md)).

Реализовано (WISHENKA-23): уведомление дарителям о получении подарка — производитель в
`notification_outbox` внутри транзакции прихода, настройки действуют на двух уровнях (вишлист,
затем пользователь, по умолчанию включено), отправку выполняет воркер в lifespan каждого
веб-процесса и только при настоящем токене бота. Экрана настроек пока нет (WISHENKA-34).

Реализовано (WISHENKA-24): интерфейс получения в Mini App — диалог «Получено» на карточке
(`routes/receipts_ui.py`, `static/receipt.js`), раздел «Подаренные» для участников
(`web/gifted_view.py`), метка «Желание получено владельцем» в кабинете. Слой страниц вызывает
доменный сервис напрямую и не меняет домен, хранилище и JSON-интерфейсы. См.
[`doc/dev/gift-receipt.md`](gift-receipt.md#mini-app-ui-wishenka-24).

Реализовано (WISHENKA-29): сервис уведомлений и напоминаний с защитой тайны сюрприза
(`wishenka/notices/`, `wishenka/bot/birthdays.py`) — транзакционные интенты изменений списков и
opt-in подтверждений собственной брони (`reminder_outbox`), приватные дни рождения (`/birthdays`,
`birthday_entries`, `birthday_input`), подтверждённые чаты (`bot_destinations`), UTC-планировщик
напоминаний (`ReminderScheduler`), общий межпроцессный rate limiter (`notice_rate_slots`),
карантин неопределённых отправок (`status = 'uncertain'`) и операторский CLI
(`python -m wishenka.notices.operator`). См. [`doc/dev/notifications.md`](notifications.md).

Дополнено (WISHENKA-60): сохранение отложенного уведомления `gift_received` при архивировании
остатка частично полученного желания (`received_quantity > 0`), уведомление дарителей с открытыми
бронями при `list_archived`, `list_restored` и `list_updated` (включая `PATCH`-маршруты и передачу
владения), строгое исключение получателя при проверках по брони и единая очистка терминальных
строк `notification_outbox` и `reminder_outbox` в `NoticeStore.purge_finished`.

Реализовано (WISHENKA-30): канал обратной связи и обращений в поддержку в Telegram-боте
(`wishenka/bot/support.py`, ревизия `add_support_channel`) — команды `/help` и `/support`,
изоляция сессии ввода (`support_input`) от захвата желаний и дней рождения, редактирование
секретных capability-токенов (`redact_capabilities`), безопасный метаданный контекст
(`DiagnosticContext`), sliding-window rate limit (`support_tickets`) и пересылка в чат поддержки /
администраторам. См. [`doc/dev/bot-support.md`](bot-support.md).

Реализовано (WISHENKA-219): явное завершение купленной брони (`PURCHASED` -> `COMPLETED`) после
полного получения желания (`WishlistService.complete_reservation`,
`POST /api/wishlists/{wishlist_id}/items/{item_id}/reservations/{reservation_id}/complete`,
кнопка «Завершено» в кабинете «Мои бронирования», в том числе для архивных списков). Завершение
освобождает занятые единицы, исключает бронь из активных счётчиков, атомарно подавляет ожидающие
уведомления о получении в `notification_outbox` и `reminder_outbox` при отсутствии других открытых
броней того же дарителя на это желание и координируется с воркером доставки через `delivery_lock`
и `receipt_delivery_fence`. См. [`doc/dev/reservations.md`](reservations.md) и
[`doc/dev/notifications.md`](notifications.md).

Согласованный целевой контракт (`WISHENKA-32`, к реализации в `WISHENKA-33/34/35`, в коде пока не реализовано):
единая ревизия Alembic от `add_idempotency_records` (эволюция `users`: `avatar_url`, `birthday`,
`birthday_source`, `locale`, `locale_source`; таблица отзыва сессий `deleted_session_revocations`
без ПДн), синхронизация локали `RU`/`EN` между Mini App, ботом (`LocaleMiddleware`) и
воркерами уведомлений, экран настроек профиля и уведомлений (`GET /settings`, `/api/profile*`,
CRUD настроек `user_notification_settings` / `wl_list_notification_settings`) и транзакционное
удаление аккаунта (`AccountDeletionService` в `BEGIN IMMEDIATE` с передачей владения совместными
вишлистами и отзывом сессий). См. [`doc/dev/users.md`](users.md).

---

## 4. Документация подсистем и доменов

- [`doc/dev/users.md`](users.md) — Домен пользователей и целевые контракты `WISHENKA-32`
  (к реализации в `WISHENKA-33`, `WISHENKA-34`, `WISHENKA-35`): модель профиля и дельта Alembic,
  протокол синхронизации локали `RU`/`EN` (TMA ↔ бот ↔ outbox), транзакционное удаление аккаунта
  в `BEGIN IMMEDIATE`, `deleted_session_revocations` и контракты наблюдаемости.
- [`doc/dev/wishlists.md`](wishlists.md) — Домен вишлистов: ролевая модель (RBAC/ABAC), жизненный цикл, Surprise Invariant, бронирование, токены шеринга и rate limiting публичных ссылок (`PublicLinkRateLimitMiddleware`).
- [`doc/dev/notifications.md`](notifications.md) — Сервис уведомлений и напоминаний (WISHENKA-29):
  защита тайны сюрприза и live-проверки получателей, приватное отслеживание `/birthdays`,
  UTC-планировщик событий, межпроцессный rate limiter, карантин `uncertain` и CLI оператора.
- [`doc/dev/gift-receipt.md`](gift-receipt.md) — Получение подарков и раздел «Подаренные»
  (WISHENKA-23, WISHENKA-24): доменная модель, UI и очередь уведомлений о получении.
- [`doc/dev/idempotency.md`](idempotency.md) — Клиентские ключи идемпотентности для мутаций
  бронирования и получения подарков (WISHENKA-61): заголовок `Idempotency-Key`, таблица
  `wl_idempotency_records`, атомарность `BEGIN IMMEDIATE` и TTL-очистка.
- [`doc/dev/bot-scenarios.md`](bot-scenarios.md) — Точка входа Telegram-бота (`/start`, `/help`),
  навигация в Mini App и создание желаний из сообщений чата.
- [`doc/dev/bot-support.md`](bot-support.md) — Канал обратной связи и обращений в поддержку в
  Telegram-боте (WISHENKA-30): `/help`, `/support`, приоритет роутеров, изоляция сессий
  `support_input`, редактирование capability-токенов, rate limiting (`support_tickets`) и
  диагностика.
- [`doc/dev/reservations.md`](reservations.md) — Домен бронирования подарков:
  жизненный цикл броней (`ACTIVE`, `PURCHASED`, `CANCELLED`, `COMPLETED`). Приход
  добавляет полученные штуки и оставляет обещание открытым: статуса
  `FULFILLED` нет, и `record_item_fulfillment` не ставит
  `ReservationStatus.COMPLETED`; в `COMPLETED` переводит только явное действие дарителя
  (`complete_reservation`) для купленной брони после полного получения желания. Гарантия
  Surprise Invariant и личный кабинет дарителя «Мои бронирования». Исключение записи —
  wish-scoped транзакция SQLite, а не `asyncio.Lock` (плюс `delivery_lock` для координации
  завершения с отправкой уведомлений о получении).
- [`doc/dev/migrations.md`](migrations.md) — Миграции БД вишлистов (Alembic): ревизии, усыновление legacy-схемы, межпроцессная блокировка, выбор WAL, журналирование, диагностика и ограничения (WISHENKA-111).
- [`doc/dev/items.md`](items.md) — Домен элементов желаний: универсальный ввод (текст, ссылки, шеринг), каскадный парсинг метаданных (JSON-LD, OpenGraph, Microdata), защита от SSRF и DNS rebinding с in-memory TTL/LRU кэшированием DNS (`DNSCache`, single-flight coalescing), graceful fallback при антибот-защите (включая русскоязычные заглушки Яндекс SmartCaptcha, Авито, Ozon, Wildberries, Мегамаркет), VCR-совместимый стенд сетевых кассет маркетплейсов (`wishenka.items.cassettes`, `tests/cassettes/marketplaces/`, CLI `python -m wishenka.items.cassettes`), штучный учет и wish-scoped запись инвентаря.
- [`doc/dev/auth.md`](auth.md) — Аутентификация Telegram Mini App, валидация initData и
  сессионные токены.
- [`doc/dev/miniapp.md`](miniapp.md) — Telegram Mini App (TMA): интерфейс управления вишлистами,
  администрирование участников, флоу инвайтов, шеринг и CSRF-защита; общий слой комфорта и
  обратной связи и HTML-страница недоступности (WISHENKA-294); удаление вишлиста владельцем (WISHENKA-295).
- [`doc/dev/infrastructure.md`](infrastructure.md) — Окружение разработки, Makefile, линтеры,
  форматирование и CI.
- [`doc/dev/verification-matrix.md`](verification-matrix.md) — Verification
  matrix for surprise exits, the free-remainder ceiling, and anonymous
  share-link access (WISHENKA-37). S5, S6, and S8 are closed by
  `test_recipient_walk_hides_booking_in_response_log_and_notice`, and
  A3 by `test_share_link_visit_creates_no_account`, both in
  `tests/test_surprise_role_context.py`. R5 is the six checks in
  `tests/test_booking_ceiling_r5.py`.
