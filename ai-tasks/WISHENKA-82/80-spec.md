# Спецификация: WISHENKA-82 — Стресс-покрытие конкурентного бронирования в SQLite

**Задача:** WISHENKA-82  
**Статус:** реализовано и верифицировано (этапы 1–8 завершены)  
**Язык реализации:** Python  
**Характер изменений:** расширение регрессионного и стресс-покрытия без изменения продакшн-кода

## 1. Назначение и бизнес-цель

### 1.1. Постановка проблемы

При высокой одновременной активности дарителей вокруг желания с ограниченным остатком (в частности, с единственным доступным экземпляром) возникает риск состояния гонки и двойного бронирования (overbooking). Существующий тест `tests/test_booking_ceiling_r5.py` проверял конкуренцию 5 пользователей, однако в наборе тестов отсутствовали:

- автоматизированная проверка инварианта доступного количества под конкурентной нагрузкой от 50 независимых дарителей на персистентном SQLite-хранилище;
- явная проверка конфигурации SQLite (`journal_mode = wal`, `busy_timeout = 5000`) в сценарии массовой конкуренции;
- изолированная проверка того, что второе подключение корректно ожидает освобождения удерживаемой пишущей блокировки SQLite в пределах `busy_timeout`, а не падает преждевременно или не обходит блокировку.

### 1.2. Цели задачи

- Обеспечить воспроизводимую, ограниченную по времени (bounded) проверку инварианта бронирования при 50 одновременных попытках разных дарителей зарезервировать последний доступный экземпляр.
- Проверить реальный производственный путь сериализации записей через `WishlistStore.execute_wish` и транзакции `BEGIN IMMEDIATE` на файловом SQLite без in-memory моков и искусственных глобальных блокировок.
- Отделить допустимые доменные отказы (`InsufficientQuantityError`) от непредвиденных сбоев хранилища и таймаутов, не допуская маскировки ошибок БД под бизнес-отказы.
- Зафиксировать поведение ожидания блокировки записи SQLite и границы применимости новых тестов в документации разработчика.

### 1.3. Пользовательская и системная ценность

- **Для дарителя:** уверенность в предсказуемом поведении системы — при исчерпании остатка другим пользователем система выдаёт однозначный отказ без создания конфликтующих обязательств.
- **Для получателя:** соблюдение запрошенного количества желания даже при одновременном спросе со стороны большого числа дарителей.
- **Для команды сопровождения:** детерминированная и быстрая регрессионная проверка в составе `tests/test_wishlists_sqlite_repo.py` без изменения продуктового поведения и без накладных расходов в продакшн-среде.

## 2. Функциональные требования и пользовательские сценарии

### 2.1. Область действия и ограничения

- Задача добавляет исключительно интеграционное тестовое покрытие в `tests/test_wishlists_sqlite_repo.py` и обновляет раздел документации разработчика `doc/dev/reservations.md`.
- Политика бронирования, публичные HTTP-маршруты, доменная логика `WishlistService` и производственный код `WishlistStore` не изменяются; этап падающего воспроизведения (Step 3) неприменим, поскольку проверяется уже существующий инвариант.
- Задача не устанавливает требований к пропускной способности (throughput) или целевых показателей задержек (latency SLA) для продакшн-нагрузки.

### 2.2. Бизнес-сущности сценария

| Сущность | Описание в рамках сценария |
| --- | --- |
| Вишлист (`Wishlist`) | Активный список владельца (`telegram_id = 1`), содержащий тестируемое желание |
| Желание (`WishItem`) | Элемент вишлиста с запрошенным количеством `quantity = 1` и доступным остатком `available_quantity = 1` |
| Даритель (`AuthenticatedUser`) | Независимый пользователь, не являющийся получателем: 50 пользователей (`telegram_id` `100..149`) в сценарии гонки и отдельный даритель (`telegram_id = 2`) в сценарии ожидания блокировки |
| Бронирование (`Reservation`) | Принятое обязательство на 1 экземпляр в статусе `active` (`ReservationStatus.ACTIVE`); в сценарии с 1 единицей допускается не более одной такой записи |
| Доменный отказ (`Refusal`) | Ожидаемое исключение `InsufficientQuantityError`, возвращаемое при отсутствии свободного остатка |

### 2.3. Сценарии поведения

**UC-01. Конкурентное бронирование последнего экземпляра 50 дарителями (`test_fifty_concurrent_reservations_do_not_overbook`)**

- **Входные условия:** временная файловая БД SQLite (`race.db`), инициализированная через `WishlistStore.initialize()`; созданы вишлист владельца (`telegram_id = 1`) и одно желание с `quantity = 1`; подтверждены `PRAGMA journal_mode == "wal"` и `PRAGMA busy_timeout == 5000`.
- **Выполнение:** формируются 50 корутин дарителей (`user_id` от `100` до `149`). Каждая корутина инкрементирует счётчик готовности; при достижении 50 готовых задач поднимается событие `ready`, после чего главный поток открывает общий стартовый барьер `gate`. Все 50 попыток одновременно вызывают `store.execute_wish(reserve, item_id=item_id)` с `service.create_reservation(item_id=item_id, user=user, quantity=1)`.
- **Выходной результат:**
  - Ровно 1 попытка возвращает `("success", reservation_id)`.
  - Ровно 49 попыток завершаются с исключением `InsufficientQuantityError` и классифицируются как `("refused", user_id)`.
  - В таблице `wl_reservations` для `wish_item_id = item_id` сохранена ровно 1 строка с `id == successes[0]`, `quantity == 1` и `status == "active"`.
  - Любые иные исключения (включая `InventoryBusyError`, ошибки SQLite и таймауты) не перехватываются как отказ и приводят к падению теста.

**UC-02. Ожидание освобождения удерживаемой блокировки записи SQLite (`test_reservation_waits_for_sqlite_writer`)**

- **Входные условия:** общая файловая БД SQLite (`wait.db`) и два независимых хранилища `holder` и `waiter`; созданы вишлист и желание с `quantity = 1`. На движок `waiter.engine.sync_engine` подключён обработчик `before_cursor_execute`, фиксирующий отправку инструкции `BEGIN IMMEDIATE`.
- **Выполнение:** `holder` открывает соединение и начинает транзакцию (`await conn.begin()`), удерживая эксклюзивную блокировку писателя. Запускается корутина `waiter.execute_wish(reserve, item_id=item_id)` для дарителя (`telegram_id = 2`). После срабатывания события `begin_attempted` тест ожидает `0.2` с (`asyncio.wait({pending}, timeout=0.2)`) и проверяет, что задача ещё не завершена. Затем транзакция `holder` откатывается (`await transaction.rollback()`) до истечения `busy_timeout = 5000` мс.
- **Выходной результат:** задача `waiter` получает освободившуюся блокировку, успешно завершается и возвращает идентификатор созданной брони `reservation.id > 0`.

### 2.4. Продуктовые и тестовые инварианты

1. **Инвариант лимита бронирований:** для желания с `quantity = 1` и `received_quantity = 0` суммарное забронированное количество (`reserved_quantity`) по завершении гонки строго равно `1`; перебронирование невозможно.
2. **Строгая классификация отказов:** единственным допустимым бизнес-отказом считается `InsufficientQuantityError`; любые ошибки блокировок (`InventoryBusyError`) и сбои драйвера БД считаются провалом проверки.
3. **Использование продакшн-пути:** тесты обязаны проходить через `WishlistStore.execute_wish` на файловой SQLite без подмены на in-memory заглушки или внешние тестовые блокировки.
4. **Изоляция и очистка ресурсов:** по завершении или при ошибке незавершённые задачи отменяются и ожидаются через `asyncio.gather(..., return_exceptions=True)`, удерживаемые транзакции откатываются, а движки БД закрываются через `dispose()`.

## 3. Архитектура, компоненты и интерфейсы

### 3.1. Задействованные модули и компоненты

| Компонент / файл | Назначение в рамках задачи |
| --- | --- |
| `tests/test_wishlists_sqlite_repo.py` | Реализует тесты `test_fifty_concurrent_reservations_do_not_overbook` и `test_reservation_waits_for_sqlite_writer` (изменённый файл задачи) |
| `wishenka/wishlists/store.py` | Класс `WishlistStore` и настройка SQLite (`_configure_immediate_transactions`, `initialize`, `_immediate`, `execute_wish`, `_load_wish`, `_persist_wish`, `_raise_for_storage_error`) |
| `wishenka/wishlists/service.py` | Класс `WishlistService` и метод `create_reservation`, выполняющий проверку остатка и создание записи `Reservation` |
| `wishenka/wishlists/models.py` | Модели `WishItem`, `Reservation`, `ReservationStatus` и вычисляемые свойства `reserved_quantity`, `available_quantity` |
| `wishenka/wishlists/exceptions.py` | Исключения `InsufficientQuantityError` (доменный отказ) и `InventoryBusyError` (превышение `busy_timeout`) |
| `wishenka/wishlists/concurrency.py` | Класс `ItemConcurrencyCoordinator`; при каждом вызове `execute_wish` создаётся новый `WishlistService.in_memory()`, поэтому внутрипроцессный `asyncio.Lock` не разделяется между вызовами и не заменяет сериализацию SQLite |
| `doc/dev/reservations.md` | Документация разработчика с описанием запуска и ограничений тестов конкурентности (обновлённый файл задачи) |

### 3.2. Поток выполнения в сценарии конкуренции

```text
50 корутин дарителей -> стартовый барьер (ready / gate) -> WishlistStore.execute_wish
    -> _immediate (SQLite BEGIN IMMEDIATE + PRAGMA busy_timeout=5000)
    -> _load_wish -> WishlistService.create_reservation
    -> проверка available_quantity -> _persist_wish
    -> 1 коммит (wl_reservations) и 49 откатов с InsufficientQuantityError
    -> проверка персистентного состояния в wl_reservations
```

### 3.3. Контракты данных и интерфейсы

- **`WishlistStore.__init__(database_url)`** (`wishenka/wishlists/store.py`):
  - Создаёт асинхронный движок SQLAlchemy с `connect_args={"timeout": 5}` и `hide_parameters=True`.
  - Подключает `_configure_immediate_transactions`:
    - На событии `connect`: устанавливает `dbapi_connection.isolation_level = None`, выполняет `PRAGMA foreign_keys=ON` и `PRAGMA busy_timeout=5000`.
    - На событии `begin`: перед открытием транзакции выполняет `PRAGMA busy_timeout=5000`, затем запускает `BEGIN` при `read_only=True` или `BEGIN IMMEDIATE` во всех остальных случаях.
- **`WishlistStore.initialize()`**:
  - Применяет миграции Alembic (`upgrade_to_head(self.database_url)`), устанавливающие в том числе режим журналирования WAL.
- **`WishlistStore.execute_wish(operation, *, item_id=None, reservation_id=None, operation_name="wish_inventory")`**:
  - Принимает ровно один идентификатор (`item_id` или `reservation_id`, иначе `ValueError`).
  - Внутри `_immediate(work)` в одной транзакции `BEGIN IMMEDIATE` определяет `resolved_item_id`, загружает состояние одного желания через `_load_wish(conn, resolved_item_id)`, вызывает `operation(service)`, сохраняет изменения через `_persist_wish(conn, service, snapshot)` (вставка/обновление строк в `wl_reservations` и обновление счётчика `wl_counters`) и фиксирует транзакцию.
  - При ошибке SQLAlchemy вызывает `_raise_for_storage_error`: если `_is_sqlite_busy(exc)` истинно (`SQLITE_BUSY`, `"database is locked"` или `"database is busy"`), выбрасывает `InventoryBusyError`.
- **`WishlistService.create_reservation(item_id, user, quantity=1, *, wishlist_id=None)`** (`wishenka/wishlists/service.py`):
  - Вычисляет `available_qty = item.available_quantity` по формуле:
    `available_quantity = max(0, quantity - received_quantity - reserved_quantity)`, где `reserved_quantity` суммирует `r.quantity` для броней в статусах `ReservationStatus.ACTIVE` и `ReservationStatus.PURCHASED`.
  - При `quantity > available_qty` выбрасывает `InsufficientQuantityError`.
  - При наличии остатка создаёт `Reservation` со статусом `ReservationStatus.ACTIVE` и добавляет его в агрегат желания.

### 3.4. Переходы состояний в рамках сценария

- **Состояния бронирования (`ReservationStatus`):**
  - В сценариях задачи используется переход `[отсутствует] -> ACTIVE` через `create_reservation` для победившего дарителя.
  - Для 49 отклонённых попыток запись в `wl_reservations` не создаётся, изменение счётчика `wl_counters` откатывается вместе с транзакцией.
- **Состояния транзакции записи SQLite:**
  1. **Ожидание блокировки:** при занятом писателе второе подключение ожидает на `BEGIN IMMEDIATE` в пределах `PRAGMA busy_timeout = 5000`.
  2. **Захват и валидация:** после получения блокировки транзакция загружает уже зафиксированный остаток из `wl_reservations` и `wl_items`.
  3. **Завершение:** либо `COMMIT` (для первого писателя при `available_quantity == 1`), либо `ROLLBACK` при `InsufficientQuantityError` (для последующих 49 попыток при `available_quantity == 0`), либо `ROLLBACK` с `InventoryBusyError` при превышении `busy_timeout`.
- **Ограничение сериализации SQLite WAL:** режим WAL допускает параллельное чтение одновременно с одним писателем, но всегда сериализует операции записи; пул соединений и блокировка БД сериализуют доступ 50 корутин последовательно на уровне транзакций.

## 4. Нефункциональные требования, безопасность и наблюдаемость

### 4.1. Производительность, таймауты и ограничения

- Оба теста явно переопределяют модульный маркер `pytestmark = pytest.mark.timeout(10)` и не используют произвольные `asyncio.sleep`:
  - `test_fifty_concurrent_reservations_do_not_overbook`: `@pytest.mark.timeout(60)`, барьер готовности `asyncio.wait_for(ready.wait(), timeout=5)`, сбор результатов конкурентных задач `asyncio.wait_for(asyncio.gather(*tasks), timeout=40)`.
  - `test_reservation_waits_for_sqlite_writer`: `@pytest.mark.timeout(30)`, ожидание попытки `BEGIN IMMEDIATE` с `timeout=5`, проверка удержания блокировки через `asyncio.wait({pending}, timeout=0.2)`, ожидание завершения после отката с `timeout=5`.
- Конфигурация SQLite: `PRAGMA journal_mode = wal`, `PRAGMA busy_timeout = 5000` (5000 мс), `connect_args={"timeout": 5}`.
- Накладные расходы в продакшне отсутствуют: задача не изменяет код приложения. Во время прогона тестов создаются 50 асинхронных задач и временные файлы SQLite в `tmp_path`.
- Ограничение `0.2` с в тесте блокировки служит исключительно доказательством факта ожидания освобождения блокировки записи и не является замером задержки.

### 4.2. Безопасность и приватность

- При откате по нехватке количества (`InsufficientQuantityError`) вызывающая сторона не получает сведений о других дарителях или их бронированиях.
- Движок в `WishlistStore` создаётся с `hide_parameters=True`, а логгер `aiosqlite` принудительно ограничен уровнем `WARNING`, чтобы исключить попадание SQL-параметров и токенов в журналы.
- Существующее логирование `WishlistStore.execute_wish` при откатах (`wishlist_inventory_rolled_back`, `wishlist_inventory_busy`) включает только тип ошибки и идентификаторы операции/желания, но не содержит идентификаторов дарителей (`user_id`), дампов строк БД и текста ошибок драйвера.

### 4.3. Наблюдаемость: логирование, метрики и мониторинг

- **Новые логи, метрики и алерты в задаче WISHENKA-82:** не добавлялись, так как изменения ограничены тестами и документацией, а новых runtime-компонентов не вводилось. Новые тесты не проверяют записи логов через `caplog` и не измеряют производственную конкуренцию.
- **Существующие структурированные события на исполняемом в тестах пути:**

| Логгер | Событие (`extra["event"]`) | Уровень | Контекстные поля | Назначение |
| --- | --- | --- | --- | --- |
| `wishenka.wishlists.store` | `wishlist_inventory_committed` | `INFO` | `event`, `item_id`, `operation`, `reservations_written` | Фиксация успешной транзакции в `execute_wish` |
| `wishenka.wishlists.store` | `wishlist_inventory_rolled_back` | `WARNING` / `ERROR` | `event`, `error_type`, опционально `item_id`, `reservation_id`, `operation` | Откат транзакции (`WARNING` для доменных отказов `WishlistError \| ValueError`, включая `InsufficientQuantityError`; `ERROR` для не-busy сбоев БД) |
| `wishenka.wishlists.store` | `wishlist_inventory_busy` | `WARNING` | `event`, `item_id` / `reservation_id`, `operation` | Откат из-за истечения `busy_timeout` в SQLite (преобразуется в `InventoryBusyError`) |
| `wishenka.wishlists` | `item_reserved` | `INFO` | `event`, `wishlist_id`, `reservation_id`, `item_id`, `quantity`, `user_id`, `gifter_id` | Создание брони (отложенный лог сбрасывается после коммита через `flush_pending_commit_logs`) |
| `wishenka.wishlists` | `insufficient_quantity_blocked` | `WARNING` | `event`, `wishlist_id`, `item_id`, `user_id`, `gifter_id`, `requested_quantity`, `available_quantity` | Блокировка попытки бронирования при превышении `available_quantity` |

## 5. Верификация и критерии приёмки

### 5.1. Сценарии проверки и фактические результаты

Оба сценария реализованы в `tests/test_wishlists_sqlite_repo.py` и запускаются автономно командой из `doc/dev/reservations.md`:

```bash
make test PYTEST_ARGS='-n 0 tests/test_wishlists_sqlite_repo.py'
```

| Тест / проверка | Проверяемый аспект | Зафиксированный результат |
| --- | --- | --- |
| `test_fifty_concurrent_reservations_do_not_overbook` | Режимы `wal` и `busy_timeout = 5000`; 50 конкурентных попыток; 1 успех и 49 `InsufficientQuantityError`; 1 активная запись в `wl_reservations` с `quantity = 1` | Пройден (в составе `make test`) |
| `test_reservation_waits_for_sqlite_writer` | Ожидание вторым `WishlistStore` освобождения удерживаемого `BEGIN IMMEDIATE` на первом `WishlistStore` (`0.2` с) и успешное бронирование после `rollback()` | Пройден (в составе `make test`) |
| `make test` (Шаг 4) | Полный набор тестов репозитория | 843 теста пройдено (с 6 предупреждениями об устаревании Starlette) |
| `make analyze` (Шаг 5) | Ruff lint, Ruff format check и `mypy` для 143 исходных файлов; длина строк не более 100 символов | Пройден без ошибок и замечаний |
| `git diff --check` (Шаг 5) | Отсутствие конфликтов слияния и проблем с пробелами | Пройден |

### 5.2. Критерии приёмки

1. При 50 одновременных попытках разных дарителей зарезервировать 1 доступный экземпляр желания ровно 1 попытка завершается успешно, а 49 получают `InsufficientQuantityError`.
2. В таблице `wl_reservations` для тестируемого желания присутствует ровно 1 запись со статусом `active`, количеством `1` и идентификатором, совпадающим с победившим результатом; перебронирование отсутствует.
3. Неожиданные ошибки (включая `InventoryBusyError`, сбои SQLite и таймауты) не считаются валидным бизнес-отказом и приводят к падению теста.
4. Подтверждены конфигурация `PRAGMA journal_mode = wal`, `PRAGMA busy_timeout = 5000` и ожидание освобождения блокировки удерживаемого писателя другим подключением в пределах таймаута.
5. Новые тесты размещены в `tests/test_wishlists_sqlite_repo.py`, имеют явные таймауты (`60` с и `30` с), ограниченные внутренние ожидания и гарантированное освобождение задач и соединений.
6. Продуктовый код и существующее поведение сервиса сохранены без изменений, `doc/dev/reservations.md` обновлён, а `make analyze` и `make test` пройдены полностью.

### 5.3. Известные ограничения и дальнейшие шаги (`60-tech-debt.md`)

- **Однопроцессное исполнение конкуренции:** сценарий использует 50 скоординированных корутин в одном процессе; SQLite и пул соединений сериализуют запись, поэтому тест подтверждает корректность инварианта бронирования под конкуренцией, а не пропускную способность одновременной физической записи (межпроцессная конкуренция покрыта отдельно в `tests/test_booking_ceiling_r5.py`).
- **Синтетическое окно ожидания (`0.2` с):** ожидание `0.2` с при удержании блокировки подтверждает лишь сам факт ожидания со стороны второго подключения и не является бенчмарком задержек.
- **Границы охвата:** тесты не оценивают реальный продакшн-трафик, другие конфигурации пула соединений и межпроцессную производительность; они также не задают целевых SLA по throughput или latency.
- **Последующие задачи (Follow-up Tasks):** по итогам анализа технического долга в `ai-tasks/WISHENKA-82/60-tech-debt.md` проблем качества кода и новых задач техдолга не выявлено.
