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
  - `PRAGMA journal_mode = WAL;` (параллельное чтение без блокировки писателей)
  - `PRAGMA foreign_keys = ON;` (каскадная целостность)
  - `PRAGMA busy_timeout = 5000;`
- **ORM и миграции:** SQLAlchemy 2.0 (Async) + Alembic
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
Суммарное количество забронированных штук не может превышать требуемое:
- `reserved_quantity = sum(r.quantity for r in reservations if r.status in (ACTIVE, PURCHASED))`
- `sum(active + purchased) <= wish_item.quantity`
- Доступный остаток: `available_quantity = max(0, quantity - received_quantity - reserved_quantity)`
- Запрет уменьшения желаемого количества ниже уже заблокированного (`reserved + fulfilled`).
- Контролируется доменными инвариантами, координатором конкурентности (`ItemConcurrencyCoordinator` / KeyedMutex) и транзакциями в SQLite при бронировании (см. [`doc/dev/reservations.md`](reservations.md) и [`doc/dev/items.md`](items.md)).

### 2.3. Аутентификация в Telegram Mini App
1. TMA при открытии передает `window.Telegram.WebApp.initData`.
2. Бэкенд проверяет криптографическую подпись HMAC-SHA256 с токеном бота.
3. Выставляется защищенная `HttpOnly` `SameSite=None` Secure session cookie.
4. Все последующие HTMX-запросы автоматически аутентифицируются по cookie без оверхеда на повторную проверку подписи.

---

## 3. Схема данных (SQLite)

Основные таблицы:
- `users` — пользователи Telegram (id, telegram_id, username, first_name, language_code, birthday).
- `wishlists` — списки желаний (id, owner_id, title, event_title, event_date, is_collaborative, is_archived, public_slug).
- `wishlist_members` — соавторы совместных вишлистов (wishlist_id, user_id, role).
- `wish_items` — элементы вишлиста (id, wishlist_id, recipient_user_id, title, link, price, currency, quantity, received_quantity, is_archived).
- `reservations` — бронирования дарителей (id, wish_item_id, user_id, quantity, status: active/purchased/cancelled/completed).
- `user_wishlist_favorites` — избранные списки дарителя.
- `user_wishlist_views` — история недавних просмотров.
- `user_notification_settings` — настройки оповещений.
- `notification_outbox` — очередь отправки сообщений ботом.

---

## 4. Документация подсистем и доменов

- [`doc/dev/wishlists.md`](wishlists.md) — Домен вишлистов: ролевая модель (RBAC/ABAC), жизненный цикл, Surprise Invariant, бронирование и токены шеринга.
- [`doc/dev/reservations.md`](reservations.md) — Домен бронирования подарков: жизненный цикл броней (ACTIVE, PURCHASED, CANCELLED, FULFILLED), гарантия Surprise Invariant, координатор конкурентного доступа (KeyedMutex), штучный учет и личный кабинет дарителя «Мои бронирования».
- [`doc/dev/items.md`](items.md) — Домен элементов желаний: универсальный ввод (текст, ссылки, шеринг), каскадный парсинг метаданных (JSON-LD, OpenGraph, Microdata), graceful fallback при антибот-защите и штучный учет подарков.
- [`doc/dev/auth.md`](auth.md) — Аутентификация Telegram Mini App, валидация initData и
  сессионные токены.
- [`doc/dev/miniapp.md`](miniapp.md) — Telegram Mini App (TMA): интерфейс управления вишлистами,
  администрирование участников, флоу инвайтов, шеринг и CSRF-защита.
- [`doc/dev/infrastructure.md`](infrastructure.md) — Окружение разработки, Makefile, линтеры,
  форматирование и CI.
