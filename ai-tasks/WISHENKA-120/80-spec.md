# Спецификация: WISHENKA-120 — Проверка HTTP-ответов 503 при занятости желания

**Задача в Jira:** WISHENKA-120 (источник: технический долг `ai-tasks/WISHENKA-57/60-tech-debt.md` — покрытие маршрутов HTTP 503)  
**Статус:** реализовано и принято (добавление регрессионного покрытия и документации без изменения продакшн-поведения)  
**Язык реализации:** Python 3.12+ (`pytest`, FastAPI `TestClient`, `BeautifulSoup`)  
**Связанные артефакты:** `ai-tasks/WISHENKA-120/` (`00-roadmap.md`, `10-requirements.md`, `20-architecture.md`, `40-code-cleanup.md`, `50-observability.md`, `60-tech-debt.md`), `tests/test_item_busy_responses.py`, `doc/dev/items.md`

---

## 1. Назначение и бизнес-цель

### 1.1. Постановка проблемы

В задаче `WISHENKA-57` для операций с инвентарём желаний на базе SQLite WAL (`BEGIN IMMEDIATE`) была добавлена обработка конкурентной блокировки записи: при истечении `PRAGMA busy_timeout` хранилище выбрасывает `InventoryBusyError`, а маршруты сохранения элементов преобразуют его в повторяемый отказ `HTTP 503 Service Unavailable`.

При завершении `WISHENKA-57` исключение `InventoryBusyError` было покрыто только на уровне хранилища (`tests/test_shared_inventory_multiprocess.py`), тогда как оба HTTP-обработчика — `wishenka/web/routes/items.py::execute` и `wishenka/web/routes/items_ui.py::submit_edit_item` — оставались без маршрутных регрессионных тестов. Без автоматизированного контроля любое последующее изменение маршрутов, локализации, шаблонов или маппинга исключений могло привести к возврату ложного успеха, необработанной ошибки `500`, потере заполненных пользователем полей формы или утечке сведений о дарителе.

### 1.2. Цели и бизнес-ценность

**Цель задачи** — защитить надёжность и приватность редактирования желаний при временной занятости за счёт автоматического регрессионного покрытия существующих маршрутов REST API и UI Mini App с явным ограничением времени выполнения.

Бизнес-ценность и системный эффект:

- **Для пользователя, редактирующего желание:** гарантия того, что временный конфликт блокировки не выглядит как успешное сохранение, а модальное окно остаётся открытым со всеми введёнными полями и понятным сообщением для повторной отправки.
- **Для дарителя (тайна сюрприза и приватность):** подтверждение отсутствия идентификатора дарителя и любых упоминаний о нём в ответах об ошибке при отказе сохранения.
- **Для потребителей API и команды разработки:** гарантированный контракт `503 Service Unavailable` с ожидаемым `detail`, позволяющий отличать повторяемый временный отказ от успешной мутации и выявлять регрессии до попадания в эксплуатацию.

### 1.3. Границы задачи (Scope и Non-Goals)

В рамки `WISHENKA-120` **входят**:

- регрессионная проверка ответа HTTP `503` на маршруте API-мутации элемента (`items.py::execute`) с валидацией JSON `detail` и приватности ответа;
- регрессионная проверка ответа HTTP `503` на маршруте сохранения модального окна редактирования (`items_ui.py::submit_edit_item`) с проверкой открытого модального окна, сохранения всех отправленных полей, текста сообщения для локалей по умолчанию (`en`) и `ru`, приватности и неизменности сохранённого элемента в БД;
- задание явного ограниченного таймаута (`pytest.mark.timeout(30)`) для добавленных проверок;
- документирование регрессионных проверок и команды запуска в `doc/dev/items.md`.

В рамки `WISHENKA-120` **не входят**:

- изменение продакшн-кода, контракта маршрутов, шаблонов, логирования или схемы хранилища;
- воспроизведение реальной конкурентной файловой блокировки SQLite через HTTP-клиент (блокировки проверяются на уровне хранилища в `tests/test_shared_inventory_multiprocess.py`);
- добавление новых логов, метрик или тестовых ассертов по записям `caplog`;
- написание падающего теста на Шаге 3 (отмечен как `N/A`, так как оба обработчика уже реализуют требуемый контракт).

---

## 2. Функциональные требования и пользовательские сценарии

### 2.1. Сущности и роли

| Сущность / роль | Назначение в рамках задачи |
| --- | --- |
| **Желание (`WishItem`)** | Редактируемая позиция вишлиста (`title`, `quantity` и дополнительные атрибуты), по которой имеется активное бронирование. |
| **Редактор / владелец (`OWNER`)** | Аутентифицированный участник с правами редактирования, отправляющий изменения желания через API или форму модального окна. |
| **Даритель (`GIFTER`)** | Пользователь с открытой бронью на целевое желание; его идентификатор (`GIFTER_ID`) и роль не должны раскрываться при отказе по занятости. |
| **Потребитель API / HTMX UI** | Клиент, выполняющий `PATCH` к REST API или отправку формы `POST` из модального окна редактирования. |

### 2.2. Функциональные требования

1. **Контракт занятости REST API (`items.py::execute`):**
   - При возникновении `InventoryBusyError` внутри `execute_wish` запрос `PATCH /api/wishlists/{wishlist_id}/items/{item_id}` должен возвращать HTTP-статус `503 Service Unavailable`.
   - Тело ответа должно представлять собой JSON `{"detail": "The wish was busy and the attempt changed nothing"}`.
   - Тело ответа не должно содержать идентификатор дарителя (`GIFTER_ID`) или подстроку `"gifter"` (без учёта регистра).
2. **Контракт занятости UI-формы редактирования (`items_ui.py::submit_edit_item`):**
   - При возникновении `InventoryBusyError` в `execute_wish` отправка `POST /web/wishlists/{wishlist_id}/items/{item_id}/edit` должна возвращать HTTP-статус `503 Service Unavailable` с `Content-Type`, содержащим `text/html`.
   - Ответ должен содержать отрендеренное модальное окно `partials/item_edit_modal.html` (`#item-edit-sheet` и форму `#item-detailed-form` с атрибутом `hx-post`, равным пути редактирования элемента) и заголовки HTMX-перенаправления замены (`HX-Retarget: #item-modal-container`, `HX-Reswap: innerHTML`).
   - Блок оповещения `[role="alert"]` должен отображать локализованное сообщение о занятости без раскрытия дарителя:
     - для локали `en` (по умолчанию): `"The wish was busy, the edit was not saved, and it can be submitted again."`
     - для локали `ru`: `"Желание было занято, изменения не сохранены — попробуйте отправить снова."`
   - HTML-ответ не должен содержать `GIFTER_ID` и подстроку `"gifter"`, а текст `[role="alert"]` не должен содержать корень `"дарител"`.
   - Все отправленные пользователем значения полей формы должны сохраняться в соответствующих элементах DOM:
     - поля `<input>` (`title`, `link`, `price`, `quantity`, `image_url`, `category`) — в атрибуте `value`;
     - многострочное поле `<textarea name="description">` — в текстовом содержимом;
     - выпадающие списки `<select>` (`currency`, `priority`) — через `option[selected]` с соответствующим `value`.
3. **Неизменность сохранённых данных:**
   - При отказе сохранения с `InventoryBusyError` исходное желание в хранилище остаётся нетронутым: последующий запрос `GET /api/wishlists/{wishlist_id}/items/{item_id}` возвращает статус `200` и исходное название (`"Original"`).
4. **Неизменность runtime-поведения и ограничение времени проверок:**
   - Проверки тестируют существующую реализацию и не меняют поведение приложения.
   - На весь тестовый модуль задан явный ограниченный таймаут `30` секунд (`pytest.mark.timeout(30)`).

### 2.3. Пользовательские сценарии

- **UC-120-01. Временная занятость при API-редактировании желания:** владелец вишлиста (при наличии брони другого дарителя на то же желание) отправляет `PATCH /api/wishlists/{wishlist_id}/items/{item_id}` в момент конфликта записи (`InventoryBusyError`). API возвращает `503` с повторяемым JSON-описанием без идентификатора или упоминания дарителя.
- **UC-120-02. Временная занятость при сохранении формы редактирования в Mini App (`en` и `ru`):** владелец отправляет заполненную форму на `POST /web/wishlists/{wishlist_id}/items/{item_id}/edit` и сталкивается с `InventoryBusyError`. Модальное окно остаётся открытым на экране с понятным предупреждением на языке профиля пользователя, сохраняет все 9 введённых полей (включая `select` и `textarea`) для немедленной повторной отправки, не раскрывает дарителя и не изменяет сохранённое желание.

### 2.4. Входные и выходные данные, инварианты

- **Входные данные тестовых сценариев:**
  - изолированное приложение `app_env(tmp_path)` с реальным `WishlistStore` на SQLite;
  - созданные через `WishlistService` вишлист, желание (`quantity=5`, `title="Original"`) и бронь дарителя `GIFTER` (`quantity=1`);
  - заголовки аутентификации владельца `bearer(sessions, OWNER_ID)` и настройка локали пользователя (`None`/`en` либо `ru`);
  - подмена `app.state.wishlist_store.execute_wish` на заглушку, выбрасывающую `InventoryBusyError()`;
  - полезная нагрузка `PATCH` (`{"title": "Updated"}`) или данные формы редактирования (`title`, `link`, `price`, `currency`, `quantity`, `description`, `image_url`, `priority`, `category`).
- **Выходные данные:**
  - HTTP-ответы со статусом `503` (JSON `detail` в API и HTML-фрагмент `partials/item_edit_modal.html` в UI);
  - контрольный ответ `GET /api/wishlists/{wishlist_id}/items/{item_id}` (`200 OK`, `title == "Original"`).
- **Ключевые инварианты:**
  1. **Тайна сюрприза:** отказ по занятости ни в JSON, ни в HTML-уведомлении не раскрывает личность или факт участия дарителя.
  2. **Атомарность и сохранность ввода:** при `503` БД не меняется, а UI не теряет введённые пользователем данные.
  3. **Проверка реального HTTP-стека:** запросы проходят через штатную маршрутизацию FastAPI, аутентификацию, локализацию, рендеринг Jinja2 и реальные обработчики исключений.

---

## 3. Архитектура, компоненты и интерфейсы

### 3.1. Архитектурная схема и выбор тестового шва

```text
pytest + TestClient (bearer OWNER_ID)
    |
    +-- PATCH /api/wishlists/{wishlist_id}/items/{item_id}
    |       |
    |       v
    |   items.execute (wishenka/web/routes/items.py)
    |       |
    |       +---> app.state.wishlist_store.execute_wish (stub -> InventoryBusyError)
    |       |         |
    |       |         v
    |       +---< HTTP 503 JSON detail (без данных дарителя)
    |
    +-- POST /web/wishlists/{wishlist_id}/items/{item_id}/edit
            |
            v
        items_ui.submit_edit_item (wishenka/web/routes/items_ui.py)
            |
            +---> app.state.wishlist_store.execute_wish (stub -> InventoryBusyError)
            |         |
            |         v
            +---< HTTP 503 partials/item_edit_modal.html (сохранённые поля, alert без дарителя)
```

После создания исходных сущностей в реальном `WishlistStore` на SQLite метод `app.state.wishlist_store.execute_wish` локально для каждого теста подменяется с помощью `monkeypatch.setattr` на асинхронную заглушку, выбрасывающую `InventoryBusyError()`. Инъектируемый `app.state.wishlist_service` не задаётся (`None`), благодаря чему оба маршрута идут через штатный путь `wishlist_store.execute_wish`. Подмена одного шва хранилища детерминированно достигает реальных HTTP-обработчиков ошибок без гонки блокировок, без внешнего сервиса и без ожидания таймаута SQLite (`5000` мс).

### 3.2. Модули, классы и функции

**Проверяемые компоненты приложения (без изменений):**

- `wishenka/web/routes/items.py` (`execute`):
  - принимает `request`, `action` и опциональный `item_id`;
  - при отсутствии `app.state.wishlist_service` и заданном `item_id` вызывает `request.app.state.wishlist_store.execute_wish(action, item_id=item_id, operation_name=operation or "wish_inventory")`;
  - перехватывает `InventoryBusyError`, записывает предупреждение `item_inventory_busy` и выбрасывает `HTTPException(status_code=503, detail=str(exc))`.
- `wishenka/web/routes/items_ui.py` (`submit_edit_item`, `_render_item_modal_error`):
  - разбирает форму через `_parse_item_modal_form`; при корректной форме выполняет `action` через `request.app.state.wishlist_store.execute_wish(action, item_id=item_id, operation_name="submit_edit_item")`;
  - при `InventoryBusyError` записывает предупреждение `ui_item_edit_busy` и возвращает `_render_item_modal_error` с шаблоном `partials/item_edit_modal.html`, `form_data=parsed.form_data`, `error_message=t("web.item.edit_busy_error", locale)`, `status_code=503` и заголовками `_RETARGET_MODAL_HEADERS`.
- `wishenka/wishlists/exceptions.py` (`InventoryBusyError`):
  - сообщение по умолчанию: `"The wish was busy and the attempt changed nothing"`.
- `wishenka/i18n/catalog.py` (`web.item.edit_busy_error`):
  - локализованные строки ошибки для `en` и `ru`.
- `wishenka/web/templates/partials/item_edit_modal.html`:
  - HTML-разметка модального окна редактирования (`#item-edit-sheet`, `#item-detailed-form`, `[role="alert"]`).

**Добавленный тестовый модуль и документация:**

- `tests/test_item_busy_responses.py`:
  - `pytestmark = pytest.mark.timeout(30)` — явный модульный таймаут 30 секунд;
  - `test_app(tmp_path)` — фикстура на базе `tests.receipt_support.app_env(tmp_path)`;
  - `_seed(service)` — создание желания (`quantity=5`, `title="Original"`) и брони `GIFTER` (`quantity=1`);
  - `_make_busy(monkeypatch, app)` — подмена `app.state.wishlist_store.execute_wish` заглушкой, поднимающей `InventoryBusyError()`;
  - `_set_owner_locale(app, locale)` — установка профиля и локали владельца через `app.state.user_store`;
  - `test_item_api_busy_response_hides_gifter` — тест API-ответа `503`;
  - `test_item_edit_busy_renders_submitted_fields` — параметризованный тест (`en-default`, `ru`) UI-ответа `503` с разбором HTML через `BeautifulSoup` и контрольным чтением элемента.
- `doc/dev/items.md`:
  - документированы регрессионные проверки HTTP `503` и команда запуска `make test PYTEST_ARGS='-n 0 tests/test_item_busy_responses.py'`.

### 3.3. Контракты данных и переходы состояний

| Точка входа | Условие | HTTP-статус и заголовки | Тело ответа | Состояние в БД |
| --- | --- | --- | --- | --- |
| `PATCH /api/wishlists/{wishlist_id}/items/{item_id}` | `InventoryBusyError` из `execute_wish` | `503 Service Unavailable`, `application/json` | `{"detail": "The wish was busy and the attempt changed nothing"}` | Без изменений (`Original`) |
| `POST /web/wishlists/{wishlist_id}/items/{item_id}/edit` | `InventoryBusyError` из `execute_wish` | `503 Service Unavailable`, `text/html`, `HX-Retarget: #item-modal-container`, `HX-Reswap: innerHTML` | Фрагмент `partials/item_edit_modal.html`: `#item-edit-sheet`, `#item-detailed-form`, `[role="alert"]`, заполненные поля | Без изменений (`Original`) |

В обработчике `submit_edit_item` при валидной форме (`parsed.validation_error is None`) переменные снимка до вызова `execute_wish` инициализируются безопасными значениями (`received_quantity_snapshot = 0`, `is_collaborative_snapshot = False`, `collaborative_members_snapshot = []`). Когда `execute_wish` выбрасывает `InventoryBusyError`, обратный рендер модального окна использует `min_quantity = max(1, 0) = 1` и полностью опирается на переданные пользователем `parsed.form_data`. После завершения каждого теста `monkeypatch` автоматически восстанавливает исходный `execute_wish`, а временный каталог `tmp_path` очищается.

---

## 4. Нефункциональные требования, безопасность и наблюдаемость

### 4.1. Производительность, таймауты и ограничения

- **Ограниченное время выполнения:** для модуля `tests/test_item_busy_responses.py` установлен явный таймаут `pytest.mark.timeout(30)`. Использование заглушки `execute_wish` исключает задержку в `5000` мс (`PRAGMA busy_timeout`) при каждом запуске теста.
- **Отсутствие влияния на runtime:** продакшн-код не изменялся; алгоритмическая сложность и задержка обработки запросов в работе сервиса остаются прежними.
- **Оформление тестового кода:** в новом модуле отсутствуют строки длиннее 100 символов, неиспользуемые импорты, отладочный вывод и маркёры конфликтов.

### 4.2. Безопасность и приватность

- **Защита тайны сюрприза:** ни ответ API `503`, ни HTML-ответ модального окна (включая `[role="alert"]`) не содержат `GIFTER_ID`, `"gifter"` или слов с корнем `"дарител"`.
- **Полноценная аутентификация:** тестовые запросы используют реальный bearer-токен владельца (`bearer(sessions, OWNER_ID)`), проходя штатную проверку авторизации без отключения защитных зависимостей.
- **Изоляция тестового воздействия:** подмена `execute_wish` ограничена рамками одного теста через `monkeypatch`.

### 4.3. Наблюдаемость: структурированное логирование и метрики

- **Структурированное логирование (не изменялось, подтверждено инспекцией):**
  - В `wishenka/web/routes/items.py` при `InventoryBusyError` используется событие уровня `WARNING` `item_inventory_busy` (логгер `wishenka.web.items`) с полями `extra`: `event="item_inventory_busy"`, `operation` и (когда известен) `item_id`. Идентификатор/имя дарителя и данные формы в лог не попадают.
  - В `wishenka/web/routes/items_ui.py` при `InventoryBusyError` используется событие уровня `WARNING` `ui_item_edit_busy` (логгер `wishenka.web.items_ui`) с полями `extra`: `event="ui_item_edit_busy"`, `wishlist_id`, `item_id`. Идентификатор/имя дарителя и данные формы в лог не попадают.
  - Новые события, уровни логирования или поля `extra` в рамках `WISHENKA-120` не добавлялись.
- **Метрики и мониторинг:**
  - Новые метрики, дашборды, алерты и экспортёры не добавлялись (`N/A`); на уровне развёртывания существующий мониторинг HTTP-статусов по-прежнему может отслеживать ответы `503`.
- **Ограничение проверки логирования:**
  - Модуль `tests/test_item_busy_responses.py` проверяет приватность HTTP-ответов, но не перехватывает и не проверяет записи логов (`caplog`); поля и безопасность существующих предупреждений подтверждены инспекцией исходного кода.

---

## 5. Верификация и критерии приёмки

### 5.1. Тестовые сценарии и результаты проверок

В файле `tests/test_item_busy_responses.py` (`pytestmark = pytest.mark.timeout(30)`) реализованы два сценария (три параметризованных тестовых кейса):

1. **`test_item_api_busy_response_hides_gifter`:**
   - Создаёт вишлист, желание (`quantity=5`, `title="Original"`) и бронь дарителя `GIFTER` (`quantity=1`).
   - Подменяет `execute_wish` заглушкой `InventoryBusyError` и отправляет `PATCH /api/wishlists/{wishlist_id}/items/{item_id}` с `{"title": "Updated"}`.
   - Проверяет статус `503`, тело `{"detail": "The wish was busy and the attempt changed nothing"}`, отсутствие `str(GIFTER_ID)` и `"gifter"` в ответе.
2. **`test_item_edit_busy_renders_submitted_fields` (`en-default` и `ru`):**
   - Подготавливает данные аналогично API-тесту; в варианте `ru` предварительно выставляет владельцу локаль `"ru"` в `user_store`.
   - Подменяет `execute_wish` заглушкой `InventoryBusyError` и отправляет `POST /web/wishlists/{wishlist_id}/items/{item_id}/edit` с 9 отличительными полями формы (`title`, `link`, `price`, `currency`, `quantity`, `description`, `image_url`, `priority`, `category`).
   - Проверяет статус `503`, заголовок `Content-Type: text/html`, наличие `#item-edit-sheet` и `#item-detailed-form[hx-post=...]`, точный текст `[role="alert"]` для обеих локалей, отсутствие `str(GIFTER_ID)`, `"gifter"` и `"дарител"`.
   - Разбирает HTML через `BeautifulSoup` и проверяет точное сохранение каждого поля формы: `value` у `input`-полей, текст внутри `textarea[name="description"]` и `option[selected]` у `currency` и `priority`.
   - Выполняет `GET /api/wishlists/{wishlist_id}/items/{item_id}` и подтверждает статус `200` и неизменное название `"Original"`.

**Зафиксированные результаты проверок из артефактов задачи:**

- `make test` (Шаг 4): **841 passed** (зафиксировано 6 предупреждений `StarletteDeprecationWarning`).
- `make analyze` (Шаг 5): прошёл без замечаний (Ruff lint, Ruff format check, `mypy`).
- `git diff --check` (Шаг 5): прошёл без замечаний и маркёров конфликта.
- Инспекция обработчиков (Шаг 6): подтверждена структура предупреждений `item_inventory_busy` и `ui_item_edit_busy` без данных дарителя и формы; код и логи на Шаге 6 не менялись.

### 5.2. Критерии приёмки (Definition of Done)

1. Покрыт ответ `503` существующего обработчика `items.py::execute`: проверяются статус `503`, установленное сообщение `detail` и отсутствие идентификатора дарителя.
2. Покрыт ответ `503` существующего обработчика `items_ui.py::submit_edit_item`: проверяются статус `503`, сохранение открытого модального окна и всех отправленных полей (включая `select` и `textarea`), установленный текст сообщения о занятости (для `en` по умолчанию и `ru`) и неизменность сохранённого элемента.
3. Добавленные автоматизированные проверки имеют явный ограниченный таймаут (`pytest.mark.timeout(30)`).
4. Продакшн-поведение не изменено; пройдены проверки `make test`, `make analyze`, `git diff --check`, а команда и описание проверок зафиксированы в `doc/dev/items.md`.

### 5.3. Известные ограничения и отложенные задачи (`60-tech-debt.md`)

- **Детерминированная заглушка вместо реального файлового конфликта SQLite:** тесты в `tests/test_item_busy_responses.py` изолируют HTTP-уровень путём подмены `execute_wish` после настройки БД и не моделируют реальную конкуренцию за блокировку SQLite.
- **Отсутствие проверок лог-записей в новом модуле:** тесты проверяют приватность HTTP-ответов, но не перехватывают события `item_inventory_busy` и `ui_item_edit_busy` через `caplog` (ограничение зафиксировано в `50-observability.md` и `60-tech-debt.md`; поля логов проверены инспекцией).
- **Предупреждения окружения при прогоне:** при выполнении `make test` (841 тест) зафиксировано 6 предупреждений `StarletteDeprecationWarning`.
- **Follow-up задачи:** новых задач техдолга в рамках `WISHENKA-120` не выявлено и не заведено.
