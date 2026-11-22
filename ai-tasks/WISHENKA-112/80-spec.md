# Спецификация: WISHENKA-112 — Рефакторинг UI-маршрутов желаний и хранилища вишлистов

**Задача в Jira:** WISHENKA-112 (`Debt`, приоритет `Low`, `2 SP`, метка `tech-debt`)  
**Источник:** технический долг из `ai-tasks/WISHENKA-15/60-tech-debt.md` (актуализировано с учётом `WISHENKA-111`)  
**Язык реализации:** Python  
**Статус:** реализовано и верифицировано в рамках Top-Down workflow (без изменения внешнего поведения)

## 1. Назначение и бизнес-цель

### 1.1. Постановка проблемы

После завершения `WISHENKA-15` в коде веб-маршрутов управления желаниями (`wishenka/web/routes/items_ui.py`) и слоя загрузки вишлистов (`wishenka/wishlists/store.py`, `wishenka/wishlists/repository.py`) остались три внутренних дефекта читаемости и честности кода:

1. **Вводящее в заблуждение имя группы исключений:** кортеж доменных ошибок назывался `_NOT_FOUND_ERRORS`, хотя включал `WishlistArchivedError`, который транслируется клиенту как `409 Conflict` (`"Wishlist is archived"`), а не `404 Not Found`. Такое имя создавало риск ошибочного предположения о поведении архивных списков и неверного маппинга в новых маршрутах.
2. **Неиспользуемый аргумент в колбэке переупорядочивания:** общий обработчик `_reordered_response` требовал от вызывающих маршрутов (`reorder_items_ui`, `move_item_ui`) колбэк сигнатуры `Callable[[WishlistService, list[int]], list[int]]`, однако аргумент `WishlistService` нигде не использовался.
3. **Избыточные проверки наличия гарантированных колонок:** при преобразовании строк SQLAlchemy в доменные модели `store.py` и `repository.py` проверяли наличие атрибутов `warn_on_delete_reserved` и `display_order` через `hasattr`/`getattr`. После введения версионированных миграций Alembic в `WISHENKA-111` обе колонки гарантированы схемой с ограничениями `NOT NULL DEFAULT` и всегда выбираются во всех `SELECT`-запросах вызывающих методов.

### 1.2. Цели задачи

- Привести имя группы доменных ошибок в `wishenka/web/routes/items_ui.py` в соответствие с её реальным составом и логикой HTTP-маппинга.
- Упростить контракт колбэка в `_reordered_response`, оставив только реально используемый список идентификаторов активных желаний.
- Удалить мёртвый защитный код (`hasattr`/`getattr`) для гарантированных схемой колонок `warn_on_delete_reserved` и `display_order` в `wishenka/wishlists/store.py` и `wishenka/wishlists/repository.py`, сохранив при этом защиты от значения `NULL` (`None`).
- Зафиксировать правило прямого чтения гарантированных колонок в документации разработчика (`doc/dev/migrations.md`).
- Обеспечить стопроцентную сохранность внешнего поведения сервиса для пользователей и дарителей.

### 1.3. Ценность для пользователей и системы

- **Поддерживаемость:** имена символов и сигнатуры функций точно отражают контракт (принцип «имя должно описывать то, что оно содержит»), избавляя разработчиков от необходимости проверять внутреннюю реализацию на предмет скрытой логики.
- **Снижение когнитивного шума:** удаление неиспользуемого аргумента и недостижимых защитных веток делает критичные маршруты переупорядочивания и загрузки вишлистов прозрачнее.
- **Безопасность будущих изменений и диагностируемость:** снижается риск случайной регрессии при расширении маршрутов, а гипотетическая рассинхронизация схемы БД и `SELECT`-запросов проявляется явно (`AttributeError` и HTTP `500`), а не скрывается подстановкой тихих значений по умолчанию.
- **Неизменность для конечного пользователя:** владельцы, соавторы и дарители вишлистов не наблюдают никаких изменений в интерфейсе, ответах API, порядке желаний и уведомлениях.

## 2. Функциональные требования и пользовательские сценарии

### 2.1. Границы области изменений

#### Входит в область (In Scope)

- Переименование `_NOT_FOUND_ERRORS` в `_DOMAIN_ERRORS` в `wishenka/web/routes/items_ui.py` с добавлением поясняющего комментария и обновлением всех мест использования; проверка отсутствия старого имени во всём репозитории.
- Упрощение сигнатуры колбэка `reorder` в `_reordered_response` и адаптация обоих вызывающих маршрутов (`reorder_items_ui` и `move_item_ui`).
- Удаление проверок `hasattr` и `getattr` для колонок `warn_on_delete_reserved` и `display_order` в `wishenka/wishlists/store.py` (3 места, включая `display_order` в `_read` и `getattr` при загрузке одного желания) и в `wishenka/wishlists/repository.py` (2 места в `_row_to_wishlist` и `_row_to_item`).
- Актуализация `doc/dev/migrations.md` правилом работы с колонками, гарантированными ревизиями Alembic.
- Создание структурных тестов (проверяющих выполненный рефакторинг) и characterization-тестов (фиксирующих сохранность поведения).

#### Исключения (Non-Goals)

- Любые изменения бизнес-логики, HTTP-статусов, текстов `detail`, HTML-шаблонов, заголовков и событий логирования.
- Изменения схемы БД, миграций Alembic, перечня выбираемых колонок в `SELECT`-запросах и удаление value-level проверок на `None` (`is not None`, `or 0`).
- Удаление вызовов `hasattr`/`getattr`, относящихся к другим объектам вне целевых колонок строк вишлиста и желаний (исключения SQLAlchemy и имена сервиса в `store.py`, значения ролей в `sharing.py`, содержимое ответа в `items/fetcher.py`).
- Иные пункты технического долга из `WISHENKA-15` (например, `can_edit_wishlist=True`, разделение шаблона карточки, оптимизация рендеринга, i18n, CDN) и несвязанные задачи `WISHENKA-125`–`WISHENKA-147`.

### 2.2. Функциональные требования

- **FR-01. Корректное именование группы доменных ошибок:** в `wishenka/web/routes/items_ui.py` кортеж исключений носит имя `_DOMAIN_ERRORS`, содержит неизменный набор из пяти классов (`WishlistNotFoundError`, `WishlistDeletedError`, `ItemNotFoundError`, `PermissionDeniedError`, `WishlistArchivedError`) и сопровождается комментарием о маппинге (`archived -> 409`, остальные `-> 404`). Имя `_NOT_FOUND_ERRORS` полностью удалено из рабочего кода, тестов и `doc/dev/` (упоминается только в структурном тесте как запрещённый атрибут).
- **FR-02. Минимальная сигнатура колбэка переупорядочивания:** параметр `reorder` функции `_reordered_response` имеет аннотацию `Callable[[list[int]], list[int]]`. Вызывающий маршрут `reorder_items_ui` передаёт `lambda _current: item_ids`, а `move_item_ui` определяет `compute(current: list[int]) -> list[int]`. Список `current_ids` вычисляется внутри `_reordered_response` однократно и используется как для вызова `reorder(current_ids)`, так и для проверки `new_ids != current_ids`.
- **FR-03. Прямое чтение гарантированных колонок:** в `wishenka/wishlists/store.py` и `wishenka/wishlists/repository.py` поля строк результата `warn_on_delete_reserved` и `display_order` считываются напрямую через обращение к атрибуту строки без `hasattr` и `getattr`. Существующие проверки на `None` (`is not None`, `or 0`) сохраняются в неизменном виде.
- **FR-04. Перепроверка исходного долга:** все три исходных пункта долга перепроверены по актуальному состоянию кодовой базы после `WISHENKA-111`; дополнительно выявленные однотипные дефекты (`hasattr(ir, "display_order")` в `store.py` и два места в `repository.py`, а также `getattr` при загрузке одиночного желания в `store.py`) включены в область изменений явно и задокументированы.

### 2.3. Внешние входы, выходы и сохраняемые инварианты

В рамках `WISHENKA-112` внешнее поведение маршрутов управления желаниями остаётся строго неизменным:

| Маршрут и вход | Сценарий | HTTP-статус и тело / заголовок | Побочный эффект в БД |
| --- | --- | --- | --- |
| `POST /web/wishlists/{wishlist_id}/items/reorder` (`item_ids: list[int]`) | Корректная перестановка с изменением порядка | `200 OK`, HTML списка активных желаний | `1` вызов `WishlistService.reorder_wish_items` |
| `POST /web/wishlists/{wishlist_id}/items/reorder` (`item_ids: list[int]`) | Отправка текущего порядка без изменений | `200 OK`, HTML списка активных желаний | `0` вызовов записи (`new_ids == current_ids`) |
| `POST /web/wishlists/{wishlist_id}/items/reorder` (`item_ids: list[int]`) | Неполный список, дубликат или неизвестный `item_id` (`ValueError`) | `400 Bad Request`, `detail: "Invalid item order"`, заголовок `X-Reorder-Refusal: stale_order` | Порядок в БД не меняется |
| `POST /web/wishlists/{wishlist_id}/items/{item_id}/move?direction=up\|down` | Попытка сдвига первого элемента вверх или последнего вниз | `200 OK`, HTML списка активных желаний | `0` вызовов записи (`new_ids == current_ids`) |
| `POST /web/wishlists/{wishlist_id}/items/{item_id}/move?direction=up\|down` | Реальное перемещение на 1 позицию | `200 OK`, HTML обновлённого списка | `1` вызов `WishlistService.reorder_wish_items` |
| `POST .../move`, `GET .../archive-confirm`, `POST .../archive`, `POST .../restore` | Неизвестный `item_id` в пути (`ItemNotFoundError`) | `404 Not Found`, `detail: "Resource not found"` | Нет изменений |
| Все 5 маршрутов (`reorder`, `move`, `archive-confirm`, `archive`, `restore`) | Несуществующий/удалённый вишлист или не-участник списка | `404 Not Found`, `detail: "Resource not found"` | Нет изменений |
| Все 5 маршрутов (`reorder`, `move`, `archive-confirm`, `archive`, `restore`) | Архивный вишлист (`WishlistArchivedError`) | `409 Conflict`, `detail: "Wishlist is archived"` | Нет изменений |

> **Примечание о последующей эволюции:** в более поздних изменениях кодовой базы (вне рамок `WISHENKA-112`, после её завершения) модальные обработчики `archive_confirm_ui`, `archive_item_ui`, а также модальные маршруты редактирования `get_edit_item_modal` и `submit_edit_item` были переведены на `_modal_domain_error_response` с возвратом out-of-band HTML-уведомлений вместо JSON `HTTPException` при сохранении тех же статусов `409` и `404`.

Инварианты загрузки данных из SQLite:

- При наличии `warn_on_delete_reserved = NULL` в строке таблицы `wl_lists` доменная модель `Wishlist` получает значение `warn_on_delete_reserved=True`.
- При наличии `display_order = NULL` в строке таблицы `wl_items` доменная модель `WishItem` получает значение `display_order=0`.
- Значения `0`/`1` и целочисленные порядки преобразуются в `bool` и `int` идентично прежней реализации.

### 2.4. Пользовательские сценарии

- **UC-01. Безопасное сопровождение UI-маршрутов желаний:** разработчик, читающий `wishenka/web/routes/items_ui.py`, видит группу `_DOMAIN_ERRORS` с явным комментарием о маппинге `archived -> 409, all others -> 404` и чистую сигнатуру `reorder: Callable[[list[int]], list[int]]` в `_reordered_response`, что исключает неверные допущения о кодах ошибок и назначении колбэка.
- **UC-02. Безопасное сопровождение слоя хранения:** разработчик, работающий с `wishenka/wishlists/store.py` или `wishenka/wishlists/repository.py`, видит прямое чтение колонок `warn_on_delete_reserved` и `display_order` и опирается на зафиксированное в `doc/dev/migrations.md` правило гарантии колонок ревизиями Alembic.
- **UC-03. Переупорядочивание, архивация и восстановление желаний:** владелец или соавтор вишлиста меняет порядок карточек, сдвигает желание вверх/вниз, архивирует или восстанавливает его и получает точно те же UI-ответы, HTTP-статусы и сохранённое состояние списка, что и до рефакторинга.

## 3. Архитектура, компоненты и интерфейсы

### 3.1. Затронутые модули и структура взаимодействия

Рефакторинг не вводит новых модулей, классов, публичных маршрутов или внешних интерфейсов; изменения локализованы внутри двух слоёв приложения (веб-маршруты UI и слой чтения хранилища) и одного документа разработчика:

```text
wishenka/web/routes/items_ui.py
  reorder_items_ui / move_item_ui
        | reorder: Callable[[list[int]], list[int]]
        v
  _reordered_response
        |-- except _DOMAIN_ERRORS --> _raise_http (409 / 404)
        |-- except ValueError -------> 400 + ui_items_reorder_rejected
        v
  WishlistService (get_wishlist_by_id, list_wish_items, reorder_wish_items)

wishenka/wishlists/store.py & repository.py
  SQLAlchemy Row (SELECT гарантированных колонок) --> прямое чтение атрибутов --> Wishlist / WishItem
```

#### Изменения в `wishenka/web/routes/items_ui.py`

- **`_DOMAIN_ERRORS`:** кортеж из пяти доменных исключений (`WishlistNotFoundError`, `WishlistDeletedError`, `ItemNotFoundError`, `PermissionDeniedError`, `WishlistArchivedError`) с комментарием о трансляции (`archived -> 409`, остальные `-> 404`). В рамках `WISHENKA-112` заменил `_NOT_FOUND_ERRORS` в четырёх блоках `except` (`_reordered_response`, `archive_confirm_ui`, `archive_item_ui`, `restore_item_ui`), перенаправлявших исключение в `_raise_http(exc)`. В актуальном файле `_DOMAIN_ERRORS` используется также в модальных маршрутах `get_edit_item_modal` и `submit_edit_item` (всего 6 мест: 2 вызова `_raise_http` и 4 вызова `_modal_domain_error_response`).
- **`_raise_http(exc: Exception) -> NoReturn`:** транслятор доменных исключений без утечки деталей (`WishlistArchivedError` → `HTTPException(409, "Wishlist is archived")`, прочие исключения → `HTTPException(404, "Resource not found")`, с сохранением цепочки `from exc`). Сигнатура и логика функции не изменялись.
- **`_reordered_response(request, wishlist_id, user, reorder: Callable[[list[int]], list[int]], locale=DEFAULT_LOCALE) -> HTMLResponse`:** внутри вложенной корутины `action(svc: WishlistService)` вызывает `svc.get_wishlist_by_id`, `_ensure_member_and_active`, `svc.list_wish_items`, однократно вычисляет `current_ids = [it.id for it in current]`, получает `new_ids = reorder(current_ids)` и выполняет запись `svc.reorder_wish_items` только при `new_ids != current_ids`.
- **`reorder_items_ui`:** передаёт в `_reordered_response` колбэк `lambda _current: item_ids`.
- **`move_item_ui`:** определяет локальную функцию `compute(current: list[int]) -> list[int]`, которая при `item_id not in current` выбрасывает `ItemNotFoundError`, а иначе меняет местами `item_id` с соседним элементом в пределах допустимых границ `[0, len(result))` и возвращает новый список идентификаторов.

#### Изменения в `wishenka/wishlists/store.py`, `wishenka/wishlists/repository.py` и документации

- **`wishenka/wishlists/store.py`:** удалены три проверки существования колонок в методах `_read` (загрузка списка и загрузка желания) и загрузки одного желания (два `hasattr` и один `getattr`).
- **`wishenka/wishlists/repository.py`:** удалены две проверки в функциях преобразования строк `_row_to_wishlist` и `_row_to_item` (один `hasattr` и один `getattr`).
- **`doc/dev/migrations.md`:** после цепочки ревизий добавлен раздел «Column convention», закрепляющий правило: колонки, созданные ревизиями Alembic, гарантированы после `upgrade_to_head()`, поэтому код читает их напрямую без `hasattr`/`getattr` и без тихих значений по умолчанию, сохраняя `None`-проверки только для допускающих `NULL` полей.

### 3.2. Контракты данных и соответствие SELECT-запросов

Все пять очищенных мест преобразования строк результата SQLAlchemy гарантированы контрактом «каждый вызывающий `SELECT` включает колонку + колонка определена в миграции с `NOT NULL DEFAULT`»:

| Модуль и место | Удалённая проверка | Текущая реализация | Источник в SELECT и схеме |
| --- | --- | --- | --- |
| `store.py`, `_read` (списки) | `hasattr(r, "warn_on_delete_reserved")` | `bool(r.warn_on_delete_reserved) if r.warn_on_delete_reserved is not None else True` | `l_stmt` (`FROM wl_lists`); ревизия `add_warn_on_delete_reserved` (`INTEGER NOT NULL DEFAULT 1`) |
| `store.py`, `_read` (желания) | `hasattr(ir, "display_order")` | `int(ir.display_order) if ir.display_order is not None else 0` | `i_stmt` (`FROM wl_items`); ревизия `add_display_order` (`INTEGER NOT NULL DEFAULT 0`) |
| `store.py`, загрузка 1 желания | `getattr(wishlist_row, "warn_on_delete_reserved", None)` | `warn_raw = wishlist_row.warn_on_delete_reserved` и `True if warn_raw is None else bool(warn_raw)` | `SELECT ... FROM wl_lists WHERE id = :id`; та же колонка схемы |
| `repository.py`, `_row_to_wishlist` | `hasattr(row, "warn_on_delete_reserved")` | `bool(row.warn_on_delete_reserved) if row.warn_on_delete_reserved is not None else True` | Единственный вызов `get_wishlist` включает `warn_on_delete_reserved` |
| `repository.py`, `_row_to_item` | `getattr(row, "display_order", 0)` | `int(row.display_order or 0)` | Вызовы `get_wishlist` и `get_item` включают `display_order` |

Фейковые объекты строк (`SimpleNamespace`, `namedtuple`, `Mock`) в тестах для обхода указанных полей не используются: модули тестирования хранилища и UI работают с реальной БД SQLite, прошедшей `upgrade_to_head()`.

### 3.3. Обработка исключений и переходы состояний

Поток выполнения `_reordered_response` имеет следующие переходы:

1. **Проверка существования, удаления и доступа:** `get_wishlist_by_id` и `_ensure_member_and_active` при отсутствии вишлиста, удалённом списке или отсутствии прав выбрасывают `WishlistNotFoundError`, `WishlistDeletedError` или `PermissionDeniedError` → блок `except _DOMAIN_ERRORS` вызывает `_raise_http(exc)` → HTTP `404`. Если список в архиве — выбрасывается `WishlistArchivedError` → HTTP `409`.
2. **Вычисление нового порядка:** вызов `reorder(current_ids)`. В `move_item_ui` при отсутствии `item_id` среди активных желаний `compute` выбрасывает `ItemNotFoundError` внутри `action` → перехватывается `_DOMAIN_ERRORS` → HTTP `404`.
3. **Запись изменений или no-op:**
    - При `new_ids == current_ids` вызов `svc.reorder_wish_items` не выполняется; функция сразу запрашивает актуальный список и возвращает `200 OK`.
    - При `new_ids != current_ids` вызывается `svc.reorder_wish_items`; если сервис отвергает перестановку с `ValueError`, перехват возвращает `400 Bad Request` (`detail="Invalid item order"`, заголовок `X-Reorder-Refusal: stale_order`).
4. **Нарушение контракта схемы БД (нештатная ошибка):** при отсутствии колонки `warn_on_delete_reserved` или `display_order` в строке `Row` прямое обращение к атрибуту немедленно выбрасывает `AttributeError` (не маскируемый значением по умолчанию), что приводит к HTTP `500` через общий обработчик исключений приложения.

## 4. Нефункциональные требования, безопасность и наблюдаемость

### 4.1. Производительность и ресурсные ограничения

- **Запросы к БД:** рефакторинг не изменяет количество SQL-запросов и обращений к сервису; удалённые вызовы `hasattr`/`getattr` выполнялись исключительно в памяти над уже загруженными строками.
- **Снижение аллокаций в памяти:** в `_reordered_response` список `current_ids` строится однократно вместо двух раз за запрос, что незначительно снижает накладные расходы без изменения поведения.
- **Отсутствие лишних записей:** инвариант `0` записей при неизменном порядке (`reorder` с тем же порядком, сдвиг первого элемента вверх или последнего вниз) и ровно `1` запись при реальном изменении сохранён.
- **Инициализация БД:** запуск миграций `upgrade_to_head()` по-прежнему выполняется при старте приложения под межпроцессной блокировкой в `asyncio.to_thread` с выбором режима `PRAGMA journal_mode=WAL` и без блокировки цикла событий.

### 4.2. Безопасность и инварианты приватности

- **Сокрытие деталей ресурсов и прав доступа:** `_raise_http` возвращает унифицированный ответ `404` с текстом `"Resource not found"` для отсутствующего/удалённого списка, отсутствующего желания и `PermissionDeniedError`. Это не позволяет постороннему пользователю определить факт существования чужого вишлиста или элемента по разнице статусов и сообщений.
- **Защита тайны сюрприза:** логика контроля доступа (`_ensure_member_and_active`, `WishlistAccessPolicy`) и фильтрация данных дарителей/бронирований не затрагивались.
- **Предотвращение тихой порчи данных:** отказ от тихой подстановки `display_order=0` или `warn_on_delete_reserved=True` при отсутствии колонки в сломанном запросе гарантирует, что дефект схемы не перезапишет порядок карточек и не подменит пользовательскую настройку предупреждения об удалении.

### 4.3. Наблюдаемость: структурированное логирование и метрики

Поскольку рефакторинг не меняет функционального поведения, новые события логирования и метрики не добавлялись, а существующие вызовы логгера `wishenka.web.items_ui` остались неизменными:

| Событие (`extra.event`) | Уровень | Точка генерации | Поля `extra` | Условие и гарантии |
| --- | --- | --- | --- | --- |
| `ui_items_reorder_rejected` | `WARNING` | `_reordered_response` (`except ValueError`) | `wishlist_id`, `actor_id`, `user_id`, `reason="invalid_permutation"` | Генерируется при ответе `400 Invalid item order` |
| `ui_items_reordered` | `INFO` | `reorder_items_ui` | `wishlist_id`, `actor_id`, `user_id`, `item_count` | Генерируется только после успешного возврата `_reordered_response`; никогда при `400`/`404`/`409` |
| `ui_item_moved` | `INFO` | `move_item_ui` | `wishlist_id`, `item_id`, `actor_id`, `user_id`, `direction` | Генерируется только после успешного возврата `_reordered_response`; никогда при `400`/`404`/`409` |

Дополнительные правила наблюдаемости:

- **Обработка `404`/`409` в `_raise_http`:** функция не пишет отдельный лог; трассировка выполняется только access-логом HTTP middleware в `wishenka/web/app.py` (метод, путь, `status_code`, `duration_ms`), что не раскрывает чувствительных подробностей.
- **Обработка `AttributeError` (`500`):** при отсутствии колонки неперехваченный `AttributeError` перехватывается HTTP middleware (`except Exception` в `wishenka/web/app.py`), который логирует событие через `logger.exception` на уровне `ERROR` с полным traceback (указывающим имя отсутствующего атрибута) и полями `method`, `path`, `duration_ms`.
- **Ограничение объёма логов:** в `extra` передаются только скалярные идентификаторы, направление и счётчик `item_count`; крупные структуры данных не логируются.
- **Метрики и мониторинг:** специализированный экспорт метрик (Prometheus/Grafana) в проекте отсутствует; измерение времени ответа (`duration_ms`) обеспечивается существующим HTTP middleware без изменений.

## 5. Верификация и критерии приёмки

### 5.1. Тестовые сценарии и результаты проверок

В дополнение к существующему набору тестов для `WISHENKA-112` добавлены два тестовых модуля с явными ограничениями времени выполнения (`pytestmark = pytest.mark.timeout(30)`):

#### Структурные тесты (`tests/test_wishenka_112_structure.py`, 3 теста)

Служили красным воспроизведением (RED) до внесения правок и перешли в зелёный статус (GREEN) после завершения разработки; закрепляют внутренние имена и форму кода от случайного отката:

1. `test_domain_errors_group_replaces_not_found_errors` — проверяет отсутствие атрибута `_NOT_FOUND_ERRORS` в `items_ui`, наличие `_DOMAIN_ERRORS` и точное совпадение множества из пяти доменных исключений.
2. `test_reorder_callback_takes_only_current_ids` — проверяет через `typing.get_type_hints(items_ui._reordered_response)["reorder"]`, что тип колбэка равен `Callable[[list[int]], list[int]]`.
3. `test_no_column_presence_checks_for_guaranteed_columns` — выполняет AST-анализ (`ast.parse`) модулей `wishenka/wishlists/store.py` и `wishenka/wishlists/repository.py` и подтверждает отсутствие вызовов `hasattr` или `getattr` со вторым строковым аргументом `"warn_on_delete_reserved"` или `"display_order"`.

#### Characterization-тесты поведения (`tests/test_items_ui_error_mapping.py`, 24 кейса)

Оставались зелёными как до, так и после рефакторинга, фиксируя внешне наблюдаемое поведение маршрутов `reorder`, `move`, `archive-confirm`, `archive` и `restore`:

1. **Матрица ошибок `409`/`404` (`test_archived_wishlist_gives_409`, `test_unknown_wishlist_gives_404`, `test_non_member_gives_404`, `test_unknown_item_gives_404`):** подтверждают `409 "Wishlist is archived"` на всех 5 маршрутах для архивного списка, `404 "Resource not found"` на всех 5 маршрутах для неизвестного списка и постороннего пользователя, а также `404 "Resource not found"` для неизвестного `item_id` на маршрутах `move`, `archive-confirm`, `archive`, `restore`.
2. **Невалидная перестановка (`test_invalid_permutation_gives_400_event_and_keeps_order`):** проверяет укороченный список и список с неизвестным `item_id` в форме `reorder`: оба возвращают `400 "Invalid item order"`, порядок в БД не меняется, в `caplog` фиксируются 2 записи `WARNING` (`ui_items_reorder_rejected`, `reason="invalid_permutation"`) без события `ui_items_reordered`.
3. **Защита от холостой записи (`test_unchanged_order_performs_no_write`):** с помощью `monkeypatch`-шпиона над `WishlistService.reorder_wish_items` подтверждает `0` вызовов записи при неизменном порядке, попытке сдвига первого элемента вверх и последнего вниз, при статусе `200` и генерации событий `ui_items_reordered` (1) и `ui_item_moved` (2).
4. **Штатное изменение порядка (`test_real_move_writes_once_and_logs_events`):** подтверждает `1` вызов записи на реальный сдвиг (`move`) и `1` на полную перестановку (`reorder`), фактическое изменение порядка и наличие INFO-событий `ui_item_moved` (`direction="up"`, `item_id`) и `ui_items_reordered` (`item_count=3`).
5. **Отсутствие ложных логов успеха (`test_error_paths_emit_no_success_events`):** подтверждает для `reorder` и `move`, что при `404` и `409` события `ui_items_reordered` и `ui_item_moved` не записываются.

#### Итоги приёмки по отчётам задачи (`00-roadmap.md`, `40-code-cleanup.md`)

- **Статический анализ (`make analyze`):** Ruff linter («All checks passed»), Ruff format check («105 files already formatted») и Mypy («no issues found in 105 source files») пройдены без замечаний.
- **Полный прогон тестов (`make test`):** зафиксировано прохождение `616 passed, 0 failed` (589 существовавших тестов + 3 структурных + 24 characterization-теста, за `504.19 s`, 1 предупреждение сторонней библиотеки `httpx`/`starlette`); ни один существующий тест не был пропущен (`skip`), ослаблен или помечен как `xfail`.

### 5.2. Критерии приёмки

Задача считается принятой при выполнении всех следующих условий:

1. **Группа ошибок переименована:** в `wishenka/web/routes/items_ui.py` используется имя `_DOMAIN_ERRORS` с поясняющим комментарием; старое имя `_NOT_FOUND_ERRORS` отсутствует в коде, тестах (кроме отрицательной проверки в структурном тесте) и `doc/dev/`; состав из пяти исключений не изменён.
2. **Сигнатура колбэка упрощена:** `_reordered_response` принимает `Callable[[list[int]], list[int]]`; неиспользуемый аргумент `WishlistService` удалён из `_reordered_response`, `reorder_items_ui` и `move_item_ui`.
3. **Избыточные проверки колонок удалены:** в `wishenka/wishlists/store.py` (3 места) и `wishenka/wishlists/repository.py` (2 места) убраны `hasattr`/`getattr` для `warn_on_delete_reserved` и `display_order` с сохранением защит от `None` (`is not None`, `or 0`); правило зафиксировано в `doc/dev/migrations.md`.
4. **Поведение полностью сохранено:** HTTP-статусы, тексты ответов, HTML-разметка, семантика пропуска записи при неизменном порядке, структура и условия логирования, а также значения по умолчанию при `NULL` идентичны исходным.
5. **Исходные пункты долга актуализированы:** каждый пункт перепроверен по коду после `WISHENKA-111`, а обнаруженные сиблинги в `store.py` и `repository.py` включены и закрыты явно.
6. **Ворота качества пройдены:** `make analyze` и `make test` завершаются успешно без ослабления утверждений в существующих тестах.

### 5.3. Известные ограничения и последующие задачи из `60-tech-debt.md`

Блокирующего технического долга (`BLOCKER`) не выявлено. Оставшиеся наблюдения и ограничения заведены в Jira как отдельные неблокирующие задачи (`NON-BLOCKER`, приоритет `Low`):

1. **Отсутствие серверного лога при маппинге `404`/`409` и неполные проверки полей в `caplog` (`WISHENKA-148`, ~2 SP):**
    - Ограничение: `_raise_http` не логирует класс исходного доменного исключения (затрудняя различение причин `404` по access-логам), а `tests/test_items_ui_error_mapping.py` проверяет имена событий, уровни, `reason`, `direction`, `item_id` и `item_count`, но не сверяет `actor_id`, `user_id`, `wishlist_id` и отсутствие лога в `_raise_http`.
    - Задача: [WISHENKA-148 в Jira](https://pypost.atlassian.net/browse/WISHENKA-148).
2. **Два источника правды для ошибок и повторение `try/except _DOMAIN_ERRORS` (`WISHENKA-149`, ~3 SP):**
    - Ограничение: список `_DOMAIN_ERRORS` и условное ветвление в `_raise_http` разделены, а блок перехвата повторяется в нескольких обработчиках `items_ui.py`; предлагается единая таблица маппинга и общий helper.
    - Задача: [WISHENKA-149 в Jira](https://pypost.atlassian.net/browse/WISHENKA-149).
3. **Хрупкость структурных тестов и отсутствие теста на громкий отказ при пропавшей колонке (`WISHENKA-150`, ~3 SP суммарно):**
    - Ограничение: `test_domain_errors_group_replaces_not_found_errors` и `test_reorder_callback_takes_only_current_ids` закрепляют имена и аннотацию типов (будут падать при легитимных переименованиях), тогда как целевое поведение `AttributeError` / HTTP `500` при отсутствии колонки в строке не закреплено отдельным тестом.
    - Задача: [WISHENKA-150 в Jira](https://pypost.atlassian.net/browse/WISHENKA-150).
4. **Дублирование тестовых хелперов и длительность прогона матрицы (`WISHENKA-151`, ~5 SP):**
    - Ограничение: `make_user` и `auth_header` определены локально в `tests/test_items_ui_error_mapping.py` (по аналогии с другими тестовыми модулями), а 24 кейса выполняются ~42 с из-за инициализации отдельного приложения и SQLite на каждый вызов.
    - Задача: [WISHENKA-151 в Jira](https://pypost.atlassian.net/browse/WISHENKA-151).
5. **Незафиксированный в продуктовой спецификации контраст `400` vs `404` для неизвестного `item_id` при `reorder` (`WISHENKA-152`, ~1 SP):**
    - Ограничение: передача несуществующего `item_id` в списке `item_ids` маршрута `reorder` возвращает `400 Invalid item order`, тогда как на маршрутах `move`/`archive-confirm`/`archive`/`restore` неизвестный `item_id` даёт `404 Resource not found`. Поведение унаследовано и охарактеризовано тестами, но требует отдельного решения команды (закрепить в `doc/dev/` или унифицировать).
    - Задача: [WISHENKA-152 в Jira](https://pypost.atlassian.net/browse/WISHENKA-152).
