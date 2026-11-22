# Спецификация: WISHENKA-110 — Браузерные тесты раскрытия карточек и drag-and-drop списка желаний

**Задача:** WISHENKA-110 (`Debt`, 5 SP, приоритет `Low`, метка `tech-debt`)  
**Статус:** реализовано и принято (Steps 1–8)  
**Объект проверки:** клиентский скрипт `wishenka/web/static/wishlist.js` и серверные представления `/web/wishlists/{id}`, `/share/{token}`  
**Стек реализации:** Python (`pytest`), `websockets.sync` (Chrome DevTools Protocol), `httpx`, `uvicorn`, headless Chromium, `tests/browser_assets/htmx_stub.js`

## 1. Назначение и бизнес-цель

### 1.1. Постановка проблемы

Клиентское поведение страницы списка желаний — делегированное раскрытие и сворачивание карточек, синхронизация атрибутов доступности, перестановка карточек мышью (HTML5 Drag-and-Drop) и пальцем (Pointer Events), а также отправка нового порядка на сервер — сосредоточено в статическом скрипте `wishenka/web/static/wishlist.js` (один IIFE, 538 строк).

До реализации WISHENKA-110 в репозитории отсутствовали автоматические поведенческие тесты, исполняющие этот JavaScript в реальном браузере:

- существующие проверки ограничивались поиском строковых маркеров и CSS-деклараций в тексте файлов, что не выявляет поломки логики (например, ошибки расчёта середины цели, неверного порядка `item_ids`, потери отмены жеста или срабатывания раскрытия при клике по вложенным элементам);
- единственная ручная проверка касания в Chromium выполнялась разово и не была зафиксирована в автоматическом наборе тестов;
- регрессии на фронтенде (при выносе inline-JS, переходе на `data-reorder-url`, правках CSS или обновлении htmx) могли пройти `make check` незамеченными и проявиться только у пользователей Telegram Mini App.

### 1.2. Цели задачи

1. Защитить наблюдаемое браузерное поведение `wishlist.js` на настоящей HTML-разметке и настоящем CSS приложения автоматическими тестами в реальном headless Chromium.
2. Обеспечить автономность, детерминизм и полную изоляцию состояния каждого теста (собственные БД, данные и вкладка) без доступа к внешней сети и без скачивания браузера во время тестов.
3. Интегрировать новые тесты в стандартные гейты `make test`, `make check` и CI после шага `make deps-browser`.
4. Подтвердить чувствительность тестов к регрессиям с помощью выборочной мутационной проверки `wishlist.js` и удалить избыточные строковые проверки в устаревших тестовых модулях с фиксацией таблицы соответствия.

### 1.3. Ценность и границы решения

- **Для редакторов вишлиста (владелец, администратор, участник):** гарантия сохранности порядка желаний и корректной работы раскрытия карточек после любых изменений фронтенда.
- **Для посетителей публичной ссылки:** подтверждение работы раскрытия карточек и невозможности изменить порядок желаний.
- **Для пользователей вспомогательных технологий:** инвариантная синхронность состояния `aria-expanded` и видимости блока подробностей (`hidden`).
- **Для команды разработки и CI:** быстрая (около 35–40 с) воспроизводимая обратная связь на гейте `make check` и устойчивость тестов к рефакторингу/переформатированию кода.

#### Границы задачи (Scope и Out of Scope)

В объём WISHENKA-110 включены пункты Definition of Done 1–18 (поведение карточек, мышиное и сенсорное перетаскивание), 20–26 (изоляция, таймауты, офлайн-заглушки, диагностика), 27 (мутационная проверка) и 28–30 (чистка слабых строковых проверок и закрытие открытых пунктов из `ai-tasks/WISHENKA-108` и `ai-tasks/WISHENKA-109`). Производственный код `wishenka/` и сценарии двух ранее существовавших браузерных тестов (`tests/test_wishlist_management_browser.py`, `tests/test_wishlist_sections_ui.py`) не изменяются; перестановка в браузере проверяется для роли владельца (матрица прав ролей уже покрыта серверными тестами).

Вне объёма задачи (отдельные задачи и п. 19 требований):

- проверка на реальных мобильных устройствах и в Telegram WebView (iOS, Android, Telegram Web), автопрокрутка у краёв, порядок вызовов и деградация заглушки Telegram SDK, ветка `warnSdk` — [WISHENKA-143](https://pypost.atlassian.net/browse/WISHENKA-143);
- устранение скачка раскладки при сворачивании развёрнутой карточки в начале жеста — WISHENKA-142;
- перенос адреса перестановки в атрибут `data-reorder-url` — [WISHENKA-141](https://pypost.atlassian.net/browse/WISHENKA-141);
- вынос оставшегося inline-JS из `base.html`, тестирование CSRF-потока cookie-сессий и кэширование статики;
- поддержка браузеров кроме Chromium, платформ Windows/macOS и тесты производительности.

## 2. Функциональные требования и пользовательские сценарии

### 2.1. Роли и общие инварианты

| Контекст / роль | Маршрут | Доступное поведение в браузерных тестах |
| --- | --- | --- |
| Владелец активного вишлиста | `/web/wishlists/{id}` | Раскрытие/сворачивание карточек кликом и клавиатурой; наличие `[draggable="true"]` и `.item-drag-handle[data-no-toggle]`; перестановка мышью и касанием с сохранением на сервере |
| Авторизованный не-владелец (даритель) | `/share/{token}` (с Bearer-токеном) | Просмотр и раскрытие карточек; присутствие блока `.item-giver[data-no-toggle]` для проверки исключений клика |
| Анонимный посетитель | `/share/{token}` (без токена) | Раскрытие/сворачивание карточек кликом и клавиатурой; отсутствие `.item-drag-handle` и `[draggable="true"]`; невозможность перестановки любым жестом |

**Ключевые поведенческие инварианты:**

1. Атрибут `aria-expanded` на `.item-card-summary` и свойство/атрибут `hidden` на `.item-card-details` согласованы после каждого действия для всех карточек списка.
2. Запрос перестановки направляется на ресурс `/web/wishlists/<id>/items/reorder` строго один раз за завершённый валидный жест и содержит `item_ids` всех карточек списка в актуальном порядке DOM.
3. Отменённый или невалидный жест (отпускание на себя, вне списка, 6 путей отмены касания, второй палец, свайп вне ручки) не отправляет запрос перестановки и не оставляет артефактов состояния на карточках, `body` или `documentElement`.

### 2.2. Раскрытие и сворачивание карточек (пп. 1–6)

- **Клик мышью:** клик по сводке свёрнутой карточки выставляет `aria-expanded="true"` и снимает `hidden` у `.item-card-details`; повторный клик возвращает `aria-expanded="false"` и `hidden`.
- **Клавиатурное управление:** при фокусе на `.item-card-summary` клавиши `Enter` и `Space` переключают карточку аналогично клику. Для `Space` действие по умолчанию отменяется (`defaultPrevented === true`), вертикальная прокрутка `scrollY` на странице с полосой прокрутки не изменяется; клавиши `a`, `Escape` и `ArrowDown` карточку не переключают.
- **Независимость карточек:** переключение одной карточки не изменяет состояние остальных карточек списка.
- **Исключение вложенных интерактивных элементов:** клик по элементам из набора `TOGGLE_EXCLUSION` (`a, button, input, select, textarea, [data-no-toggle]`) — ручке `.item-drag-handle` на странице владельца, тексту блока `.item-giver`, `select` и кнопке «Забронировать» (с отменой `submit` в тесте во избежание навигации) на странице дарителя, а также вставленным в сводку `a[href="#x"]`, `input`, `textarea` — не переключает карточку.
  - *Уточнение по `<label>`:* элемент `label` («метки» в тексте требования п. 4) отсутствует в `TOGGLE_EXCLUSION` в `wishlist.js` и в тесте не проверяется; расхождение зафиксировано для продуктового уточнения.
- **Делегирование после htmx-подмены:** после замены содержимого `#items-list` настоящим HTML-фрагментом от сервера (вызов `window.htmx.ajax('POST', '.../items/<id>/move?direction=down', {target: '#items-list', swap: 'innerHTML'})`) обработчики раскрытия продолжают работать по клику и клавиатуре.
- **Публичная страница:** на анонимной странице `/share/{token}` карточки раскрываются и сворачиваются кликом, `Enter` и `Space`.

### 2.3. Перестановка карточек мышью (HTML5 Drag-and-Drop, пп. 7–11, 30)

- **Позиционирование относительно середины цели:** перетаскивание карточки на другую карточку с попаданием в верхнюю половину (`y_fraction = 0.25`) вставляет источник перед целью; попадание в нижнюю половину (`y_fraction = 0.75`) вставляет источник после цели (проверено в обоих направлениях: первая на третью и последняя на первую).
- **Сетевой контракт и сохранение на сервере:** при успешном перетаскивании регистрируется ровно один вызов `htmx.ajax` и ровно один HTTP `POST` на `/web/wishlists/<id>/items/reorder` с полным массивом `item_ids` в новом порядке DOM; повторное открытие страницы подтверждает сохранение порядка на сервере.
- **Источник идентификатора списка:** адрес запроса строится по атрибуту `data-wishlist-id` элемента `#items-list`, а не по `window.location` (проверено изменением `data-wishlist-id` на другое число перед жестом).
- **Негативные сценарии и ветки защиты:**
  - отпускание на саму перетаскиваемую карточку или за пределы списка (точка `(1.0, 1.0)`, также покрывающая `dragend` без `drop`) не отправляет запрос, не меняет порядок DOM, не пишет предупреждений/ошибок в консоль и оставляет страницу готовой к следующему жесту;
  - при отсутствии `data-wishlist-id`, нечисловом значении `data-wishlist-id="abc"` или удалённом `window.htmx` запрос не уходит, порядок DOM не меняется (проверка выполняется до перестановки элементов), а в консоль пишется ровно одно `console.warn` с подстрокой `reorder skipped` и причиной (`not numeric` или `not loaded`).
- **Повторные жесты и публичная страница:** последовательные перетаскивания без перезагрузки работают без «залипания» состояния `dragged` (в том числе после отпускания на себя и после `dragend` без `drop`). На `/share/{token}` отсутствуют `.item-drag-handle` и `[draggable="true"]`, а нативный DnD и синтетический `dragstart`+`drop` не вызывают `/items/reorder`.

### 2.4. Перестановка карточек касанием (Pointer Events, пп. 12–18, 30)

- **Перетаскивание за ручку:** удержание и перемещение за `.item-drag-handle` сверх порога активации (не менее двух шагов `touchMove`, порог 4 px) на верхнюю (`0.25`) или нижнюю (`0.75`) половину цели выставляет на карточке класс `is-touch-dragging`, на цели `drop-before` или `drop-after`, после `touchEnd` меняет порядок в DOM и отправляет ровно один запрос с полным списком `item_ids`.
- **Развёрнутая карточка:** развёрнутая карточка корректно переставляется касанием и сохраняет раскрытое состояние (`aria-expanded="true"`, без `hidden`) при отмене жеста через `touchCancel`.
- **Разделение tap и перетаскивания:** короткий `tap` по `.item-card-summary` переключает карточку; `tap` по `.item-drag-handle` не переключает карточку, не выставляет `is-touch-dragging` и не отправляет запрос.
- **Шесть путей отмены жеста (п. 14):** ни один из путей не отправляет `/items/reorder` и полностью очищает классы/трансформации жеста (`.is-touch-dragging`, `.drop-before`, `.drop-after`, `body.is-touch-reordering`, `html.is-touch-reordering`, `style.transform`):
  1. `pointercancel` (через CDP `Input.dispatchTouchEvent` `touchCancel`);
  2. `lostpointercapture` (через `handle.releasePointerCapture(pointerId)` во время жеста);
  3. `Escape` — проверен как до преодоления порога 4 px (вооружённый жест), так и после активации;
  4. `blur` окна (`window.dispatchEvent(new Event('blur'))`);
  5. `visibilitychange` (переопределение `document.hidden = true` и событие `visibilitychange`);
  6. `htmx:beforeSwap` — во время жеста через `htmx.ajax` выполняется реальный серверный `POST .../items/<id>/move?direction=down` в `#items-list`; в этом случае DOM после подмены отражает новый серверный порядок `[b, a, c]`, но `/items/reorder` не вызывается и состояние жеста очищается.
- **Многопальцевый ввод и прокрутка:** появление второго пальца (`touchStart` с двумя `TouchPoint`) на другой ручке во время жеста отменяет перетаскивание без запуска второго жеста и без запроса. Вертикальный свайп по тексту сводки `.item-title` вне ручки (8 карточек, viewport `412x500`) прокручивает страницу (`scrollY > 0`), сохраняет порядок и не отправляет запрос.
- **Кратность запросов и окно подавления клика:** за один жест уходит строго один запрос. По истечении окна подавления клика (`CLICK_SUPPRESS_MS = 400 мс` по `performance.now()` страницы, с запасом 50 мс) следующий `tap` по сводке переключает карточку — как после успешного drop, так и после отменённого активного жеста.
- **Вычисляемые стили (пп. 28–29):** в реальном CSS приложения проверяются `getComputedStyle(handle)`: `touchAction === 'none'`, `userSelect === 'none'`, ширина и высота ручки `>= 44 px`; в процессе активного жеста у `.is-touch-dragging` вычисленное `opacity < 1`, а у цели с `drop-before`/`drop-after` непустой `boxShadow`.

### 2.5. Пользовательские сценарии (UC)

- **UC-110-01. Просмотр и переключение деталей желания:** пользователь (владелец или посетитель публичной ссылки) раскрывает и сворачивает карточки кликом, `Enter` и `Space`, в том числе после серверного обновления списка, не задевая соседние карточки и не вызывая случайного переключения при нажатии вложенных кнопок, ссылок или формы дарителя.
- **UC-110-02. Сортировка вишлиста мышью:** владелец перетаскивает карточку выше или ниже середины цели, повторяет перестановку без перезагрузки, а система сохраняет полный порядок `item_ids` на сервере и игнорирует отпускание на себя или вне списка.
- **UC-110-03. Сортировка вишлиста касанием:** владелец перетаскивает карточку за ручку в мобильном viewport, отменяет жест любым прерыванием (`Escape`, потеря захвата, второй палец, скрытие вкладки, подмена списка) или прокручивает список свайпом по тексту карточки, а затем продолжает работу с карточками после окна подавления клика.
- **UC-110-04. Проверка невалидного состояния при отпускании:** при повреждённом/отсутствующем `data-wishlist-id` или отсутствии `window.htmx` скрипт безопасно отменяет отправку с единственным предупреждением в консоль.

## 3. Архитектура, компоненты и интерфейсы

### 3.1. Архитектурный выбор и схема модулей

- **Свой минимальный CDP-драйвер (`tests/browser_cdp.py`) вместо Playwright:** в проекте уже используются `websockets` и `httpx` для работы с системным Chromium (WISHENKA-124), тогда как `playwright` не установлен, добавляет колесо ~53,5 МБ с `greenlet` и не гарантирует совместимость с несовпадающей системной сборкой Chromium; низкоуровневые сценарии касания и отменяемого DnD в любом случае требуют прямых CDP-команд. Интерфейс `CdpPage` изолирует тесты от протокола CDP.
  - *Триггер пересмотра решения:* рост числа браузерных сценариев выше ~100 тестов, появление многобраузерных требований, второго типа страниц со сложной реальной htmx-навигацией, потребности в трассировках/видео или удаление `legacy=True` в `websockets`.
- **Офлайн-перехват на сетевой границе вкладки (`Fetch.enable`):** вместо изменения шаблонов или хранения копии `htmx.min.js` в git вкладка перехватывает запросы на внешние скрипты и подставляет локальные заглушки, пропуская весь локальный трафик к настоящему приложению.
- **Изоляция на уровне теста с разделяемым процессом Chromium:** единый процесс Chromium и однократно мигрированный шаблон БД на сессию сочетаются с отдельным сервером приложения, копией SQLite и вкладкой на каждый тест.

```text
tests/conftest.py ──(lazy)──> tests/browser_cdp.py ──> websockets.sync, httpx
   │  chromium_executable (WISHENKA-124)     CdpBrowser, CdpPage, PageWaitTimeout
   │  chromium_browser (session)  ───────────────────┘
   │  migrated_db_template (session)  ──> wishenka.web.app.create_app
   │  wishlist_server (function)      ──> uvicorn.Server in thread, copied SQLite
   │  seed_wishlist (function)        ──> httpx + Bearer -> REST API приложения
   │  wishlist_page / share_page      ──> CdpBrowser.new_page(), offline Fetch, Bearer
   └─ pytest_runtest_makereport       ──> секция диагностики и артефакты teardown
tests/browser_assets/htmx_stub.js        (подмена unpkg htmx через Fetch.fulfillRequest)
tests/browser_helpers.py                 (Seeded, селекторы, assert-хелперы, жесты)
tests/test_wishlist_cards_browser.py         (пп. 1–6, 22)
tests/test_wishlist_mouse_reorder_browser.py (пп. 7–11, 28, 30)
tests/test_wishlist_touch_reorder_browser.py (пп. 12–18, 28, 29, 30)
tests/test_browser_prerequisites.py          (AST-охранный тест маркеров и таймаутов)
```

### 3.2. Контракты данных и публичные интерфейсы драйвера

- **Типы и структуры в `tests/browser_cdp.py`:**
  - `TouchPoint = tuple[int, float, float]` — координаты касания `(finger_id, x, y)` в CSS-пикселях viewport.
  - `WindowEventKind = Literal["blur", "visibilitychange"]`.
  - `PageWaitTimeout(AssertionError)` — исключение истечения ограниченного ожидания; содержит описание ожидания, последнее вычисленное значение предиката и снимок `snapshot()`.
  - `ConsoleEntry(type: str, text: str)` и `ConsoleLog(list[ConsoleEntry])` с методом `.warnings()`; `type` принимает `"warning"` для `console.warn`, `"error"` или `"exception"` для `Runtime.exceptionThrown`.
  - `RecordedRequest(method: str, url: str, post_data: str | None = None, status: int | None = None)` со свойством `.path`.
- **`CdpBrowser` (`tests/browser_cdp.py`):**
  - `start(executable, profile_dir)` — запускает Chromium с флагами `--headless --no-sandbox --disable-gpu --disable-dev-shm-usage --remote-debugging-port=0 --user-data-dir=<dir>`, читает отладочный порт и отслеживает раннее падение процесса.
  - `ensure_alive()` — проверяет `proc.poll() is None` перед выдачей страницы и при необходимости перезапускает процесс, предотвращая каскадные отказы.
  - `new_page(viewport=(412, 800))` — создаёт вкладку (`PUT /json/new`), открывает синхронное соединение (`connect(..., legacy=True)` для совместимости с `websockets` 17.x), включает домены `Network`, `Page`, `Runtime`, `Fetch`, `Emulation` и настраивает viewport `412x800`, `mobile=False`.
  - `stop()` — `terminate()`, ожидание до 5 с, затем `kill()`.
- **`CdpPage` (`tests/browser_cdp.py`, однопоточный насос событий на `websockets.sync` без фоновых потоков):**
  - **Выполнение и ожидания:** `navigate(url)` (`Page.navigate` + `Page.loadEventFired`), `evaluate(expression, *, await_promise=False)` (исключения JS преобразуются в `AssertionError`), `wait_for(description, predicate_js, timeout=5.0)`.
  - **Ввод мыши, клавиатуры и DnD:** `click(selector)`, `press_key(key)` (`Enter`, `Space` с `text=" "`, `Escape`, `ArrowDown`, `Tab`, символы), `mouse_drag(source_selector, target_selector, *, y_fraction)` (нативный DnD через `Input.setInterceptDrags`, `mousePressed`, два `mouseMoved`, ожидание `Input.dragIntercepted`, серию `Input.dispatchDragEvent` для `dragEnter`/`dragOver`/`drop`, `mouseReleased`), `drop_outside(source_selector, point)`.
  - **Сенсорный ввод и события окна:** `enable_touch()`, `touch_start(points)` (повторный вызов с расширенным списком добавляет палец), `touch_move(points)` (передаёт все активные пальцы), `touch_end()` (завершает все активные пальцы; безопасный no-op, если ни один палец не опущен), `touch_cancel()`, `touch_tap(selector)`, `touch_drag(...)`, `dispatch_window_event(kind)`.
  - **Наблюдение и состояние:** свойства `console`, `requests`, `external_requests`; методы `ajax_calls()`, `order()`, `card_state(item_id)` (`{"expanded": "true"|"false"|None, "hidden": bool}`), `snapshot()`, `screenshot(path)`, `close()`.
- **Общие хелперы (`tests/browser_helpers.py`):**
  - `Seeded(wishlist_id, public_token, item_ids, owner_token, viewer_token)` — результат фабрики `seed_wishlist` (создание списка через `POST /api/wishlists`, где ответ возвращает `share_token`, и добавление желаний через REST).
  - Селекторы и действия: `card`, `summary`, `title`, `handle`, `center`, `point_in`, `focus`, `settle`, `reorder_requests`, `reorder_ajax_calls`, `request_item_ids`, `begin_touch_drag`, `wait_gesture_active`, `wait_suppression_window_over` (`CLICK_SUPPRESS_MS = 400`, `CLICK_SUPPRESS_MARGIN_MS = 50`).
  - Диагностические проверки: `assert_order`, `assert_cards`, `assert_no_reorder_sent`, `assert_clean_console`, `assert_gesture_clean`.

### 3.3. Контракт офлайн-перехвата и заглушки `htmx_stub.js`

Обработчик `Fetch.requestPaused` (шаблон `*`) маршрутизирует запросы следующим образом:

| Шаблон URL | Действие драйвера | Запись в журнал |
| --- | --- | --- |
| `https://unpkg.com/htmx.org@1.9.12` | `Fetch.fulfillRequest` (200, `text/javascript`, тело `tests/browser_assets/htmx_stub.js`) | — |
| `https://unpkg.com/htmx.org@1.9.12/dist/ext/json-enc.js` | `Fetch.fulfillRequest` (200, `text/javascript`, пустой JS) | — |
| `https://telegram.org/js/telegram-web-app.js` | `Fetch.fulfillRequest` (200, `text/javascript`, пустой JS) | — |
| Хосты `127.0.0.1`, `localhost` и внутренние схемы (`data`, `blob`, `about`, `chrome`, `chrome-error`) | `Fetch.continueRequest` (для локального сервера) | Локальные запросы фиксируются в `page.requests`, статус обновляется из `Network.responseReceived` |
| Любой другой внешний URL | `Fetch.failRequest(BlockedByClient)` | Фиксируется в `page.external_requests` |

Заглушка `tests/browser_assets/htmx_stub.js` (собственный код без вендоринга) в рамках WISHENKA-110 обеспечивает:

- присваивание `window.htmx = { version: 'stub', ajax }` как конфигурируемого свойства, что позволяет тестам выполнять `delete window.htmx`;
- запись каждого вызова `htmx.ajax(verb, url, {target, swap, values})` в `window.__ajaxCalls` и учёт незавершённых запросов в `window.__ajaxPending`;
- реальную пересылку запроса на сервер через `fetch` с заголовком `HX-Request: true` и телом `application/x-www-form-urlencoded` (массив `item_ids` кодируется повторяющимися полями);
- генерацию `htmx:beforeSwap` (с `detail.target`) на целевом элементе до обновления `target.innerHTML` и `htmx:afterSwap` после обновления.

*Пределы точности заглушки:* декларативные `hx-*` атрибуты на кнопках, событие `htmx:configRequest` (CSRF-заголовок), альтернативные режимы `swap` и расширение `json-enc` заглушкой WISHENKA-110 не обрабатываются.

### 3.4. Жизненный цикл фикстур и особенности взаимодействия с Chromium

1. **Сессионная подготовка (`chromium_browser`, `migrated_db_template`):** браузер запускается один раз; `migrated_db_template` один раз прогоняет миграции Alembic в `TestClient` и корректно закрывает движки SQLite без остатка `-wal`.
2. **Подготовка теста (`wishlist_server`, `seed_wishlist`, `wishlist_page` / `share_page`):** копируется `template.db` (около 0.03 с вместо 1.4 с), стартует `uvicorn.Server` в `daemon`-потоке на `127.0.0.1:0`, через `httpx` с Bearer-токеном заводятся список и желания, открывается вкладка браузера и загружается `/web/wishlists/{id}` или `/share/{token}`.
3. **Завершение теста (`_browser_pages`, `wishlist_server`):** при провале сохраняются диагностические файлы; вкладка и websocket закрываются, `uvicorn` останавливается через `should_exit = True` + `thread.join` в блоках `finally`.
4. **Особенности движка Chromium, учтённые в драйвере и тестах:**
   - *Подавление fling-инерции:* пауза `TOUCH_MOVE_INTERVAL = 0.016 s` после каждого `touchMove` и `TOUCH_REST_BEFORE_END = 0.06 s` перед `touchEnd` предотвращают распознавание высокой скорости отпускания как инерционного скролла, который в противном случае блокирует следующий `tap` дольше 1.2 с.
   - *Удержание пальцев для `lostpointercapture`:* Chromium доставляет `lostpointercapture` после `releasePointerCapture` только при очередном событии указателя; поэтому `CdpPage.wait_for` на каждом неуспешном шаге опроса отправляет микросдвиг `0.01 px` для удержанных пальцев (`_hold_fingers`).
   - *Перенаведение после схлопывания карточки:* при начале касания развёрнутая карточка схлопывается и смещает нижележащие карточки, поэтому в реализации WISHENKA-110 использовался вспомогательный пересчёт координат цели после активации жеста (`retarget_touch_drag` в `tests/browser_helpers.py`).

## 4. Нефункциональные требования, безопасность и наблюдаемость

### 4.1. Производительность, таймауты и бюджет времени

- **Маркеры модулей:** все три браузерных модуля объявляют `pytestmark = [pytest.mark.timeout(45), pytest.mark.browser]`; очищенные текстовые модули и охранный тест имеют `timeout(30)` (проверяется AST-тестом `test_new_browser_modules_declare_marker_and_timeout`).
- **Ограниченные ожидания без слепых пауз и без retry:**
  - `COMMAND_TIMEOUT = 10.0 s` — лимит ответа на любую команду CDP;
  - `LOAD_TIMEOUT = 10.0 s` — ожидание `Page.loadEventFired`;
  - `DRAG_INTERCEPT_TIMEOUT = 3.0 s` — ожидание `Input.dragIntercepted`;
  - `wait_for` — по умолчанию `5.0 s` с шагом опроса `POLL_STEP = 0.025 s` (ожидание истечения `CLICK_SUPPRESS_MS` ограничено `3.0 s` по `performance.now()`);
  - запуск/остановка `uvicorn` и HTTP-запросы засева — ограниченные таймауты (`httpx` `timeout=10`, остановка Chromium `terminate()` -> `wait(5)` -> `kill()`).
- **Бюджет времени (п. 25):** целевой ориентир ~60 с; фактическое время 53 новых тестов составило **34.9–39.6 с** (среднее ~37.3 с по 10 прогонам, ~39 с в финальном прогоне Step 5) — около 8% времени полного набора `make test` (589 тестов, 496.97 с).

### 4.2. Изоляция, автономность и политика доступности браузера

- **Изоляция состояния (п. 20):** каждый тест получает уникальный случайный порт `127.0.0.1:0` (отдельный Origin для cookie, `localStorage` и HTTP-кэша), собственную копию SQLite, свежие сущности и новую вкладку браузера. После 10 подряд прогонов зафиксировано 0 оставшихся процессов Chromium или `uvicorn`.
- **Сетевая изоляция (п. 22):** выход за пределы локального хоста и трёх перехватываемых URL блокируется и фиксируется в `external_requests`, что превращает любую скрытую сетевую зависимость в явный отказ теста.
- **Политика отсутствия браузера (WISHENKA-124, п. 23):** при отсутствии системного Chromium тесты завершаются ошибкой `ERROR` на setup с явным сообщением о `make deps-browser`; пропуск разрешён только при локальном флаге `WISHENKA_SKIP_BROWSER_TESTS=1`, который игнорируется в CI.

### 4.3. Безопасность, приватность и качество кода

- В тестах применяются фиксированные тестовые токены и идентификаторы (`OWNER_TELEGRAM_ID`, `VIEWER_TELEGRAM_ID`, `BROWSER_TEST_SECRET`); реальные учётные данные не задействованы.
- Публичная страница `/share/{token}` открывается без авторизации и не содержит элементов управления перестановкой.
- Аутентификация владельца и дарителя выполняется через `Network.setExtraHTTPHeaders` (`Authorization: Bearer`), поэтому запросы обходят `BrowserSecurityMiddleware` (проверка `Origin` и `X-CSRF-Token` остаётся в зоне серверных тестов и отложена для реального htmx smoke-теста в [WISHENKA-145](https://pypost.atlassian.net/browse/WISHENKA-145)).
- Качество кода тестов подтверждено статическими проверками: `ruff check`, `ruff format --check`, строгий `mypy` (103 файла без ошибок), `node --check tests/browser_assets/htmx_stub.js`; устранено предупреждение `DeprecationWarning` клиента `websockets` передачей `legacy=True`.

### 4.4. Наблюдаемость и диагностика падений (п. 26)

Производственный код (`wishenka/`) в рамках задачи не менялся, поэтому продакшн-логирование, Prometheus-метрики, дашборды и алерты не добавлялись (`N/A`); существующие журналы WISHENKA-108/109 остались без изменений. Наблюдаемость реализуется для разработчика и логов CI при падении тестов:

1. **Полный снимок состояния `CdpPage.snapshot()`:** включает текущий URL, `scrollY`, классы `body`, структурированную строку по каждой карточке (`data-item-id`, `aria-expanded`, `hidden`, классы — не усекается), `window.__ajaxCalls`, срез `#items-list outerHTML` (усечённый до 2000 символов во избежание раздувания логов), до 20 последних записей консоли, до 20 последних локальных запросов (метод, путь, статус, тело POST), список заблокированных `external_requests` и до 5 последних ошибок драйвера. При падении страницы выводит `(page state unavailable: ...)` и всё равно печатает консоль и сеть.
2. **Диагностические исключения:** `PageWaitTimeout` и хелперы (`assert_order`, `assert_cards`, `assert_gesture_clean`, `assert_no_reorder_sent`, `assert_clean_console`) выводят описание ожидания, последнее значение, ожидаемое и фактическое состояние и снимок `snapshot()`. Ошибки драйвера именуют проблемный метод CDP или URL.
3. **Явный контроль консоли:** тесты вызывают `assert_clean_console(page)` явно (без autouse-фикстуры под `--strict-markers`), а сценарии с ожидаемым `console.warn` проверяют `page.console.warnings()` точечно.
4. **Интеграция с отчётом pytest и файловые артефакты:** хук `pytest_runtest_makereport` добавляет секцию `Page N diagnostics` в вывод упавшего теста (попадает в лог GitHub Actions), а teardown `_browser_pages` сохраняет в `tmp_path` файлы `diagnostics-N.txt` и `failure-N.png` (`Page.captureScreenshot`) под защитой `contextlib.suppress`, чтобы сбой снятия скриншота не скрыл исходную ошибку.

## 5. Верификация и критерии приёмки

### 5.1. Покрытие тестами и чистка строковых проверок

#### Новые тестовые модули (53 теста, маркер `browser`, таймаут 45 с)

| Модуль | Кол-во тестов | Покрытие DoD | Ключевые проверяемые сценарии |
| --- | --- | --- | --- |
| `tests/test_wishlist_cards_browser.py` | 21 | пп. 1–6, 22 | Загрузка офлайн с реальными `wishlist.js`/`miniapp.css` и `htmx.version == 'stub'` (owner, share); клик туда и обратно; `Enter`/`Space` и отмена прокрутки для `Space`; игнор прочих клавиш; независимость карточек; 7 исключений вложенных элементов; делегирование после реального серверного `htmx.ajax`-обновления; анонимный `/share/{token}` |
| `tests/test_wishlist_mouse_reorder_browser.py` | 13 | пп. 7–11, 28, 30 | Позиционирование выше/ниже середины цели (4 комбинации); 1 вызов `htmx.ajax` + 1 `POST` с полным `item_ids` и сохранением в БД; чтение `data-wishlist-id`; no-op на себя и вне списка без консоли; ровно 1 `console.warn` для отсутствующего/нечислового id и без `window.htmx`; повторные жесты и `dragend` без `drop`; отсутствие ручек и запрет перестановки на `/share/{token}` |
| `tests/test_wishlist_touch_reorder_browser.py` | 19 | пп. 12–18, 28–30 | Перетаскивание за ручку (верх/низ/развёрнутая карточка); сохранение `aria-expanded` при отмене; tap по сводке vs tap по ручке; 6 путей отмены (`pointercancel`, `lostpointercapture`, `Escape`, `blur`, `visibilitychange`, `htmx:beforeSwap`); второй палец; `Escape` до и после порога; свайп вне ручки (`scrollY > 0`); 1 запрос за жест; tap после окна подавления клика; вычисляемые стили `touchAction`, `userSelect`, размеры `>= 44 px`, `opacity < 1`, `boxShadow` |

Дополнительно в `tests/test_browser_prerequisites.py` добавлен AST-тест `test_new_browser_modules_declare_marker_and_timeout`, проверяющий наличие маркера `browser` и `pytest.mark.timeout(45)` в модулях `tests/test_*_browser.py` (таймаут модуля 30 с).

#### Чистка устаревших строковых проверок (пп. 28–29)

После получения зелёных браузерных тестов выполнена адресная чистка трёх legacy-модулей (с 53 до 28 собранных тест-кейсов; уменьшение на 25 кейсов при сохранении защитных guard-проверок):

| Очищенный модуль | Удалено / сокращено | Заменяющий браузерный тест / причина | Что сохранено осознанно |
| --- | --- | --- | --- |
| `tests/test_wishlist_static_script.py` | Строковые маркеры `toggleWishCard`, `' '`, `'Enter'`, `.item-card-summary`, `EXCLUSION_SELECTOR`, `dragstart`/`dragover`/`drop`/`dragend`, `/items/reorder`, `wishlistId`/`data-wishlist-id`, отсутствие `location.pathname`/`window.location` в `test_static_wishlist_script_content` | Тесты раскрытия (пп. 1–4), мышиной перестановки (пп. 7–10) и `test_reorder_uses_data_wishlist_id_not_location` | Проверка HTTP 200 и MIME `javascript` для `/static/wishlist.js`; `test_cards_have_no_inline_event_handlers`; структурные тесты шаблонов |
| `tests/test_wishlist_touch_reorder.py` | 19 токенов жеста из `test_wishlist_script_contains_token`; `touch-action`, `user-select`, `min-width: 44px` из `test_css_drag_handle_declares_touch_rules`; `test_css_has_drag_feedback_rule` (3 параметра) | Сенсорные браузерные тесты (пп. 12–18) и `test_handle_and_feedback_computed_styles` | 4 SDK-токена (`test_wishlist_script_contains_sdk_token`); `-webkit-touch-callout: none` (свойство iOS); `test_css_summary_does_not_block_touch_scroll`; `test_wishlist_script_has_single_reorder_submit_point` |
| `tests/test_wish_items_list_reorder_ui.py` | Подстроки `"onclick" not in html` и `"toggleWishCard" in static_js.text` | `test_cards_have_no_inline_event_handlers` и `test_click_toggles_card_both_ways` | Проверка HTTP 200 для `/static/wishlist.js` и проверки разметки |

### 5.2. Результаты прогонов, стабильность и мутационное доказательство

- **Финальная проверка качества (Step 5):**
  - три новых браузерных модуля: **53 passed** (~39 с);
  - полный набор тестов (`PYTHONDONTWRITEBYTECODE=1 make test`): **589 passed, 0 failed** (496.97 с; баланс тестов: `560 + 53 - 25 + 1 = 589`);
  - `make analyze`: `ruff check`, `ruff format --check` (103 файла) и `mypy` (103 файла) — без замечаний; `node --check tests/browser_assets/htmx_stub.js` — OK;
  - `git diff --exit-code -- wishenka/` пуст (производственный код не затронут).
- **Проверка стабильности (п. 21, Step 4):** 10 последовательных запусков трёх модулей — **10/10 по 53 passed, 0 failed, 0 flaky** (время прогонов: 34.9–39.6 с, среднее ~37.3 с); после завершения 0 оставшихся процессов Chromium/uvicorn.
- **Мутационная проверка `wishlist.js` (п. 27, Step 4, с откатом после каждой мутации):**
  - *Обязательная выборка и дополнительные мутации — пойманы по утверждениям:*
    - `M1` (`isAfterMidpoint`: `>` -> `<`) — 12 тестов красные;
    - `M2` (`submitReorder`: сбор `item_ids` до `insertBefore`) — 11 красных;
    - `M3` (`toggleWishCard`: снята проверка `TOGGLE_EXCLUSION`) — 8 красных;
    - `M4a` (отключён слушатель `Escape`) — 2 красных;
    - `M5` (повторный `submitReorder` в `pointerup`) — 4 красных;
    - `M6` (удалён `console.warn` в `submitReorder`) — 3 красных;
    - дополнительные мутации `M7` (`details.hidden = !expanded`, 14 red), `M8` (снят `preventDefault` на `keydown`, 1 red), `M9` (`lostpointercapture`, 1 red), `M10a`/`M10b` (`visibilitychange` и `blur`, по 1 red), `M12` (`target === dragged`, 2 red), `M13` (несброшенное подавление клика, 2 red), `M14` (игнор второго пальца, 1 red) — все пойманы.
  - *Выжившие одиночные мутации (принятое ограничение изоляции):*
    - `M4b` (удаление только `pointercancel`) и `M11` (удаление только `htmx:beforeSwap`) оставляют 19 touch-тестов зелёными, поскольку браузер при отмене жеста или удалении карточки из DOM также доставляет `lostpointercapture`, вызывающий тот же `cancelTouchDrag`. Комбинированные мутации `M4c` (`pointercancel + lostpointercapture`, 5 red) и `M11b` (`beforeSwap + lostpointercapture`, 2 red) падают корректно, подтверждая проверку отмены как единого поведения.

### 5.3. Критерии приёмки

| Критерий | Статус | Подтверждение |
| --- | --- | --- |
| Раскрытие карточек, клавиатура, исключения, делегирование и `/share/{token}` (пп. 1–6) | Выполнено | 21 тест в `tests/test_wishlist_cards_browser.py` (`<label>` не проверяется, см. п. 2.2) |
| Перестановка мышью, единый POST, валидация и публичная недоступность (пп. 7–11, 30) | Выполнено | 13 тестов в `tests/test_wishlist_mouse_reorder_browser.py` |
| Перестановка касанием, 6 путей отмены, второй палец, скролл и подавление клика (пп. 12–18, 30) | Выполнено | 19 тестов в `tests/test_wishlist_touch_reorder_browser.py` |
| Изоляция, детерминизм 10/10, офлайн-работа, WISHENKA-124, `make check`, бюджет времени (пп. 20–25) | Выполнено | Фикстуры в `tests/conftest.py`, Fetch-перехват, 10/10 прогонов (~37.3 с), `make test` (589 passed) и `make analyze` |
| Диагностика падений и мутационное доказательство (пп. 26–27) | Выполнено | `snapshot()`, `PageWaitTimeout`, `pytest_runtest_makereport`, убиты M1–M4a, M5–M10b, M12–M14 (M4b/M11 отмечены как дублирующие пути отмены) |
| Чистка слабых строковых проверок и таблица соответствия (пп. 28–29) | Выполнено | Удалено/сокращено 25 слабых кейсов в 3 legacy-модулях с сохранением guard-проверок |
| Пункт 19 (реальные устройства, автопрокрутка, SDK-порядок, `warnSdk`) | Вне объёма | Осознанно отложено в [WISHENKA-143](https://pypost.atlassian.net/browse/WISHENKA-143) |

### 5.4. Известные ограничения и план доработок

Блокирующих дефектов (`BLOCKER`) при анализе технического долга не выявлено.

#### Известные ограничения реализации

1. **Ограниченная точность офлайн-заглушки и Bearer-аутентификации:** `htmx_stub.js` не проверяет декларативные `hx-*` атрибуты, `htmx:configRequest`, `json-enc` и путь cookie + CSRF; три внешних URL продублированы в `tests/browser_cdp.py` и `base.html`.
2. **Дублирующие пути отмены в `wishlist.js`:** одиночные мутации `pointercancel` (`M4b`) и `htmx:beforeSwap` (`M11`) маскируются событием `lostpointercapture`.
3. **Зависимость от заголовка `label` в требовании п. 4:** `<label>` отсутствует в `TOGGLE_EXCLUSION` и не входит в тестовый набор исключений.
4. **Зеркальная константа и синтетика касаний:** `CLICK_SUPPRESS_MS = 400` дублируется в `tests/browser_helpers.py`; `_hold_fingers` посылает субпиксельные `touchMove` (`0.01 px`) при опросе `wait_for`; тайминги защиты от fling (`16 ms`, `60 ms`) подобраны под headless Chromium 156 на Debian 13 и на момент закрытия задачи ещё не проверялись в CI (`ubuntu-latest`, Python 3.12).
5. **Артефакты падений в CI:** `failure-N.png` и `diagnostics-N.txt` пишутся в `tmp_path`, но в CI отсутствует `actions/upload-artifact` и пути файлов не печатаются в отчёт (текст `snapshot()` попадает в лог CI через секцию отчёта, дублируясь с текстом `PageWaitTimeout`).
6. **Специфика `websockets`:** вызов `connect(..., legacy=True)` опирается на флаг совместимости `websockets` 17.x при нижней границе `websockets>=13.0` в `pyproject.toml`.

#### Задачи дальнейшего развития (Follow-up из `60-tech-debt.md`)

- **[WISHENKA-146](https://pypost.atlassian.net/browse/WISHENKA-146) (Debt, ~3–4 SP):** перевести два старых браузерных модуля (`test_wishlist_management_browser.py`, `test_wishlist_sections_ui.py`) на общие `CdpBrowser`, `CdpPage`, `wishlist_server` и `chromium_browser`; расширить AST-охранный тест на все браузерные модули; согласовать ограничение версии `websockets` в `pyproject.toml` с API `legacy=True` (или перейти на контекстный менеджер).
- **[WISHENKA-147](https://pypost.atlassian.net/browse/WISHENKA-147) (Debt, 1–2 SP):** настроить фиксированный `--basetemp` и `actions/upload-artifact` с `if: failure()` для `failure-N.png` и `diagnostics-N.txt`, печатать пути артефактов в отчёт и убрать дублирование текста снимка.
- **[WISHENKA-145](https://pypost.atlassian.net/browse/WISHENKA-145) (Debt, ~3 SP, после выноса inline-JS):** добавить локальный smoke-тест с реальной vendored-копией htmx, реальным `hx-post`, cookie-сессией и CSRF (`htmx:configRequest`), а также охранную проверку совпадения трёх внешних URL между `tests/browser_cdp.py` и `base.html`.
- **Заметки в существующих задачах Jira:**
  - [WISHENKA-143](https://pypost.atlassian.net/browse/WISHENKA-143) — проверка реальных устройств и возможное расширение CDP-тестов для п. 19 (автопрокрутка, порядок вызовов SDK, `warnSdk`);
  - [WISHENKA-135](https://pypost.atlassian.net/browse/WISHENKA-135) — фиксация версии браузера, времени (+40 с) и стабильности touch-тестов на первом прогоне CI (`ubuntu-latest`);
  - [WISHENKA-137](https://pypost.atlassian.net/browse/WISHENKA-137) — расширение охвата AST-охранного теста на `test_wishlist_sections_ui.py` и снятие жёсткой привязки к именам трёх модулей;
  - [WISHENKA-138](https://pypost.atlassian.net/browse/WISHENKA-138) — согласование общего бюджета таймаутов драйвера и маркера `timeout(45)`, чтобы не терять `PageWaitTimeout` при последовательных ожиданиях;
  - [WISHENKA-144](https://pypost.atlassian.net/browse/WISHENKA-144) — решение по намеренности дублирующих путей отмены (`pointercancel`, `htmx:beforeSwap`, `lostpointercapture`);
  - [WISHENKA-141](https://pypost.atlassian.net/browse/WISHENKA-141) — совместное обновление `test_reorder_uses_data_wishlist_id_not_location` и теста предупреждений при переходе на `data-reorder-url`.
