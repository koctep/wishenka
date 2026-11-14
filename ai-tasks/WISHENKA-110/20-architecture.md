# WISHENKA-110: Браузерные тесты для раскрытия карточек и drag-and-drop списка желаний

Тип: Debt, 5 SP. Язык реализации: Python (pytest) для тестов; проверяемый код: JavaScript
(`wishenka/web/static/wishlist.js`), производственный код не меняется. Требования:
`ai-tasks/WISHENKA-110/10-requirements.md` (30 пунктов Definition of Done, далее «п. N»).

## Research

### Что есть в репозитории (проверено на Step 2)

- `wishlist.js` (538 строк, один IIFE): делегированный `click`/`keydown` на `.item-card-summary`
  (`toggleWishCard`, исключения `a, button, input, select, textarea, [data-no-toggle]`), нативный
  HTML5 DnD для мыши (`dragstart`/`dragover`/`drop`/`dragend`), жест пальцем на Pointer Events
  (`pointerdown`/`move`/`up`/`cancel`, `lostpointercapture`, `Escape`, `blur`,
  `visibilitychange`, `htmx:beforeSwap`), единственная точка отправки `submitReorder` ->
  `window.htmx.ajax('POST', '/web/wishlists/<id>/items/reorder', {target, swap, values: {item_ids}})`,
  ветка `console.warn` при нечисловом `data-wishlist-id` или отсутствии `window.htmx`,
  `CLICK_SUPPRESS_MS = 400`.
- `base.html` грузит `telegram.org/js/telegram-web-app.js`, `unpkg.com/htmx.org@1.9.12`,
  `.../dist/ext/json-enc.js` (все три без `defer`) и `/static/wishlist.js` (`defer`, после htmx).
  Именно эти три URL должны быть доступны офлайн (п. 22).
- Разметка: `partials/item_card.html` (`.item-card[draggable=true]` только при
  `can_edit_wishlist`, `.item-card-summary[role=button][tabindex=0][aria-expanded]`,
  `.item-drag-handle[data-no-toggle]` внутри сводки, `.item-card-details[hidden]` вне сводки,
  блок `.item-giver[data-no-toggle]` с формой, `select` и кнопками внутри сводки для не-получателя),
  `wishlist_detail.html` и `share_wishlist.html` (`#items-list[data-wishlist-id]`).
- Аутентификация: `get_optional_current_user` принимает `Authorization: Bearer` ИЛИ cookie
  `session_id`; для небезопасных методов с cookie без Bearer `BrowserSecurityMiddleware` требует
  `Origin == application_origin` и `X-CSRF-Token`; запрос с Bearer CSRF-проверку обходит
  (`wishenka/web/security.py:28-35`). `/share/{token}` доступен анонимно (`OptionalUser`).
- Существующие два браузерных теста: сервер `uvicorn.Server` в потоке на `127.0.0.1:0`, Chromium
  `--headless --no-sandbox --disable-gpu --disable-dev-shm-usage --remote-debugging-port=0
  --user-data-dir=<tmp>`, вкладка через `PUT /json/new`, CDP по `websockets.sync`. Обе
  страницы SPA-корня `/`, `fetch` подменён скриптом `BRIDGE_MOCK`; серверные страницы `/web/...`
  и `/share/...` они не открывают, аутентификация серверных страниц в браузере не отрабатывалась.
  Хелперы CDP (`send_command`, `wait_for_load`) продублированы в каждом файле.
- Среда: Chromium 156.0.8078.79 (Debian 13, `/usr/bin/chromium`), `websockets` 17.4 (в `.venv`;
  проектный минимум `>=13.0`), `httpx`, `beautifulsoup4`; `playwright` не установлен и не объявлен.
  Сеть в среде разработки сейчас есть (`pypi.org` отвечает 200, `unpkg.com` 301), но правило
  WISHENKA-124 и п. 22 не должны от неё зависеть.

### Эмпирическая проверка (одноразовый спайк, не коммитится)

Скрипт в scratchpad (`websockets.sync` + `chromium`, минимальная страница с настоящим
`wishlist.js` и тремя карточками, заглушка htmx). Результаты:

| Что проверено | Результат |
| --- | --- |
| `Fetch.enable` с шаблоном `https://unpkg.com/*` + `Fetch.fulfillRequest` подменяет htmx | Работает: `typeof window.htmx === 'object'`, страница загрузилась без сети |
| Клик мышью (`Input.dispatchMouseEvent` pressed/released) по сводке | `aria-expanded="true"` |
| `Input.dispatchKeyEvent` `keyDown` с `key:" "`, `code:"Space"`, `text:" "` | карточка переключилась |
| Нативный DnD: `Input.setInterceptDrags{enabled:true}` + `mousePressed`, два `mouseMoved` -> событие `Input.dragIntercepted` -> `Input.dispatchDragEvent` `dragEnter`/`dragOver`/`drop` с `data` из события -> `mouseReleased` | Работает: ровно один вызов `htmx.ajax('POST','/web/wishlists/7/items/reorder', {..., values:{item_ids:["2","3","1"]}})`, DOM `[2,3,1]` |
| Касание: `Emulation.setTouchEmulationEnabled` + `Input.dispatchTouchEvent` `touchStart`/`touchMove`/`touchMove`/`touchEnd` на ручке | Приходят `pointerdown:touch`, `pointermove:touch`, `pointerup:touch`, `lostpointercapture:touch`; запрос `item_ids:["3","1","2"]` ушёл. Без CSS приложения (`.is-touch-dragging{pointer-events:none}`) жест молча не находил цель: перетаскиваемая карточка сама оказывалась под пальцем. Вывод: тесты обязаны идти на настоящем CSS приложения, а не на упрощённой странице. |
| Время запуска приложения: `create_app` + uvicorn на свежей SQLite | около 1,4 с (миграции Alembic при первом `initialize`) |
| То же на копии заранее мигрированного файла БД | около 0,03 с |
| Остановка сервера (`should_exit` + `join`) | около 0,25 с |

Не проверено спайком (проверить на Step 4): скролл страницы от синтезированного касания
(п. 17), `touchCancel` как источник `pointercancel`, второй палец одним `touchStart` с двумя
`touchPoints`, tap как источник `click`, влияние `touch-action: none` на синтезированный свайп,
потокобезопасность `ws.send` (в выбранном дизайне она не нужна, см. (a)).

### (a) Инструмент: свой CDP-драйвер или Playwright

Playwright для Python (актуальная версия на PyPI 1.65.2, `requires_python >=3.10`, зависимость
`greenlet`; колесо `manylinux1_x86_64` 53,5 МБ со встроенным node-драйвером, по метаданным PyPI
[pypi.org/pypi/playwright/json](https://pypi.org/pypi/playwright/json)). `pip install playwright`
ставит только библиотеку; браузеры качает отдельная команда `playwright install` с CDN Microsoft
([Playwright: Browsers](https://playwright.dev/python/docs/browsers)). Системный Chromium
подключается опцией `executable_path` ([BrowserType API](https://playwright.dev/python/docs/api/class-browsertype)),
но библиотека гарантированно работает только со своей закреплённой сборкой Chromium: с другой
версией «не гарантируется» (формулировка из документации старых версий, актуальная ли она для
1.65, проверить на Step 4 не планируется, так как вывод от этого не зависит). Системный
Chromium 156 на dev-боксе и «Chromium 157» на runner-е (WISHENKA-124, не перепроверено) заведомо
не совпадают с закреплённой сборкой.

| Критерий | Свой `CdpPage` поверх `websockets.sync` | Playwright + системный Chromium (`executable_path`) |
| --- | --- | --- |
| Новая зависимость | нет (`websockets`, `httpx` уже объявлены) | `playwright` в `dev`-extras: +53 МБ колесо при `make deps` (сеть), `greenlet`, node-драйвер внутри колеса |
| Скачивание браузера | нет | нет, если всегда задавать `executable_path`; но `playwright install` случайно запущенный разработчиком или CI скачает ~150 МБ, а без `executable_path` тесты упадут «Executable doesn't exist» |
| Совместимость с системным Chromium | прямой CDP, версия не важна (в протоколе используются стабильные методы `Input`, `Fetch`, `Runtime`, `Emulation`, `Page`) | не гарантирована, риск тихих расхождений при смене версии Chromium на runner-е |
| Правило WISHENKA-124 (политика fail-by-default, `check_chromium`, `chromium_executable`) | переиспользуется как есть | придётся передавать найденный путь в `launch(executable_path=...)`; политика та же, но второй слой запуска |
| Автоожидание, локаторы | нет: пишем `wait_for` с дедлайном (около 40 строк) | есть, но в этой задаче проверяются состояния DOM и порядок запросов, а не локаторы |
| Перехват запросов и ответов | `Fetch.enable`/`fulfillRequest`, около 30 строк | `page.route`, удобнее |
| Нативный DnD мышью | `Input.setInterceptDrags` + `dispatchDragEvent` (проверено спайком) | `page.drag_and_drop`/`mouse` (внутри тот же CDP) |
| Касание | `Input.dispatchTouchEvent` (проверено спайком); многопальцевый жест вручную | `page.touchscreen.tap` только тап; свайп и многопальцевые жесты всё равно через CDP-сессию `new_cdp_session` |
| Диагностика | свой журнал консоли, запросов, снимок DOM | трассировки, но зависят от пути браузера |
| Объём кода | `tests/browser_cdp.py` около 300-350 строк | тонкая обвязка, но синхронный API Playwright несовместим с `uvicorn` в потоке без осторожности (greenlet-цикл; проверить на Step 4) |
| Единообразие с двумя существующими браузерными тестами | да | нет (два разных способа управлять браузером в одном репозитории) |

**Решение: свой драйвер `CdpPage` (`tests/browser_cdp.py`), Playwright не добавляется.**
Обоснование: (1) единственное преимущество Playwright здесь автоожидание и локаторы, а задача
проверяет порядок `item_ids`, атрибуты и перехваты запросов, где нужен именно низкий уровень CDP
(`Input.dispatchTouchEvent`, `Input.dispatchDragEvent`, `Fetch`), и многопальцевый и отменяемый
жест Playwright всё равно делает через CDP-сессию; (2) Playwright с системным Chromium работает
вне гарантированной связки версий, а проект сознательно использует системный браузер без
скачиваний (WISHENKA-124); (3) 53 МБ зависимости и риск «случайного» `playwright install` для
5-очкового Debt несоразмерны. Заголовок Jira говорит «Playwright» как о намерении «браузерные
тесты» (требования, раздел Q&A); отступление от буквы заголовка осознанное, фиксируется в итогах
и в `doc/dev/testing.md`. Условие пересмотра: если число сценариев вырастет настолько, что
собственная обвязка станет дороже зависимости (многобраузерные тесты, трассировки), заводится
отдельная задача на миграцию; драйвер при этом скрыт за узким интерфейсом `CdpPage`, который
легко заменить.

### (b) Офлайн-страница для п. 22

Варианты:

| Вариант | Плюсы | Минусы |
| --- | --- | --- |
| A. `Fetch.enable` на уровне вкладки, три внешних URL отдаются локальными заглушками; всё остальное идёт на настоящий сервер | настоящая разметка, настоящий `wishlist.js` и CSS; ничего не меняется в приложении; одна точка конфигурации; блокировка любых других внешних запросов даёт защиту «нет сети» | заглушка htmx не повторяет семантику htmx |
| B. Флаг в приложении/шаблоне, отключающий внешние скрипты | не нужны перехваты | изменение производственного кода (запрещено допущениями), страница уже не настоящая |
| C. Закоммитить копию `htmx.min.js` в `tests/` | настоящая семантика htmx | сторонний бинарно-подобный файл ~47 КБ в git, скачать его можно только один раз вручную (нарушает дух «ничего не скачиваем и не коммитим артефакты установки»), версия расходится с `base.html` при обновлении |
| D. `Page.addScriptToEvaluateOnNewDocument` подставляет `window.htmx` | просто | запросы к unpkg всё равно уходят в сеть и висят до таймаута |

**Решение: вариант A.** Страница открывается с `Fetch.enable(patterns=[{urlPattern:"*"}])`;
обработчик `Fetch.requestPaused`:

- `https://unpkg.com/htmx.org@1.9.12` -> `fulfillRequest` содержимым `tests/browser_assets/htmx_stub.js`;
- `https://unpkg.com/htmx.org@1.9.12/dist/ext/json-enc.js` и
  `https://telegram.org/js/telegram-web-app.js` -> `fulfillRequest` пустым JavaScript (200,
  `content-type: text/javascript`); без заглушки Telegram `window.Telegram` отсутствует и скрипт
  идёт по ветке «SDK недоступен» (в объёме не проверяется, п. 19);
- запросы на `127.0.0.1:<port>` -> `continueRequest` и запись в `page.requests`
  (метод, URL, тело POST из `request.postData`);
- любой другой URL -> `failRequest(BlockedByClient)` и запись в `page.external_requests`;
  автоиспользуемая проверка в тестовом фикстуре-«стороже» падает, если список не пуст
  (так защищено от случайной зависимости от сети, например `image_url`).

Заглушка htmx (`tests/browser_assets/htmx_stub.js`, собственный код около 40 строк, не
скачанный):

- `window.htmx = {version: 'stub', ajax(verb, url, opts)}`;
- каждый вызов записывается в `window.__ajaxCalls` (verb, url, target, swap, values), чтобы тест
  проверял именно аргументы `htmx.ajax`, которые формирует `submitReorder` (устойчиво к
  WISHENKA-141: адрес берётся из записанного вызова и/или сетевого запроса, а не из исходника);
- затем **пересылает запрос настоящему серверу** через `fetch`: `application/x-www-form-urlencoded`,
  массив `values.item_ids` кодируется повторяющимся полем `item_ids` (как делает htmx), заголовок
  `HX-Request: true`; на ответ делает `innerHTML`-подмену `opts.target`, предварительно
  отправив на `document` событие `htmx:beforeSwap` с `detail.target` (как htmx), затем
  `htmx:afterSwap`; счётчик `window.__ajaxPending` позволяет дождаться завершения.

Вывод о точности. Реально проверяются: аргументы вызова `htmx.ajax`, содержимое и число
серверных запросов, принятие и сохранение порядка настоящим маршрутом (после перезагрузки
страницы порядок на сервере совпадает), настоящая перерисовка `#items-list` настоящим HTML
сервера, пост-подменная работоспособность делегированных обработчиков (п. 5). НЕ проверяются:
обработка `hx-*` атрибутов, `htmx:configRequest` (CSRF-заголовок из `base.html`), стратегии
`swap` кроме `innerHTML`, порядок и семантика реальных событий htmx (`htmx:beforeSwap` из
заглушки имитирует лишь форму события), `hx-ext="json-enc"`. Эти зоны вне пунктов 1-18 и
остаются на ручной проверке и WISHENKA-143. Заглушка ограничена: ни один тест не опирается на
то, чего настоящий htmx не гарантирует; правильность кодирования тела проверяет сам сервер
(он должен принять запрос и сохранить порядок). Реальный htmx в офлайне не используем
(вариант C отклонён).

Отдельно: тест `test_..._page_loads_offline_with_real_assets` проверяет, что `/static/wishlist.js`
и `/static/miniapp.css` отданы настоящим сервером (запись в `page.requests`, статус 200), что
`window.htmx.version === 'stub'` (заглушка действительно подставлена), и что `external_requests`
пуст.

### (c) Жизненный цикл, изоляция, аутентификация

Варианты изоляции (п. 20: у каждого теста своя БД, свои данные и своя вкладка обязательны):

| Вариант | Время (оценка по спайку) | Изоляция |
| --- | --- | --- |
| 1. Сервер и Chromium на сессию, БД общая | минимум | нарушает п. 20 (общая БД) |
| 2. Chromium на сессию, **сервер и БД на тест**, вкладка на тест | сервер 0,05-0,3 с + вкладка ~0,2 с | полная; процессы Chromium разделяются, но состояние нет |
| 3. Всё на тест (Chromium тоже) | + ~1-1,5 с на запуск Chromium на тест; около 50 тестов -> +60 с | максимальная, но съедает бюджет п. 25 |

**Решение: вариант 2.**

- Сессионная фикстура `chromium_browser` (в `tests/conftest.py`, ленивые импорты) зависит от
  `chromium_executable` (политика fail/skip WISHENKA-124 не дублируется) и запускает один headless
  Chromium с `--remote-debugging-port=0` и профилем в `tmp_path_factory`. Перед каждым тестом
  `ensure_alive()` проверяет `proc.poll() is None` и при смерти процесса перезапускает его
  (одна упавшая страница не должна валить 50 тестов каскадом). Завершение: `terminate()`,
  `wait(5)`, затем `kill()`, `wait(5)`; профиль удаляется.
- Сессионная фикстура `migrated_db_template`: один раз создаёт `create_app` на пустой SQLite,
  дожидается `lifespan` и сохраняет мигрированный файл. Экономия: 1,4 с -> 0,03 с на тест (спайк).
- Функциональная фикстура `wishlist_server`: копирует шаблон БД в `tmp_path`, `create_app(Settings(
  database_url=..., secret_key=<фиксированный тестовый>))`, слушающий сокет `127.0.0.1:0`,
  `uvicorn.Server` в потоке `daemon=True`, ожидание `server.started` с дедлайном 8 с, остановка
  `should_exit=True`, `thread.join(8)`, закрытие сокета, `assert not thread.is_alive()` как в
  существующих тестах. Все шаги остановки в `finally`, то есть при падении теста тоже.
- Заведение данных: через публичный REST приложения (`httpx` с Bearer владельца:
  `POST /api/wishlists`, `POST /api/wishlists/{id}/items`, см. `tests/test_wish_items_crud_api.py`),
  а не через `asyncio.run(service...)` в главном потоке: сервис живёт в событийном цикле потока
  uvicorn, и вызов сервиса из другого цикла с `aiosqlite` может дать межцикловые ошибки (проверить
  на Step 4; запасной вариант: засеять БД-шаблон копией до старта сервера отдельным `create_app`
  внутри `TestClient`). Фабрика `seed_wishlist(titles, quantities=...)` возвращает
  `Seeded(wishlist_id, public_token, item_ids, owner_token, viewer_token)`.
- Функциональная фикстура `wishlist_page`: новая вкладка `PUT /json/new` (как в существующих
  тестах), `CdpPage`, `Network.enable`, `Page.enable`, `Runtime.enable`, `Fetch.enable` (офлайн,
  (b)), `Emulation.setDeviceMetricsOverride` (412x800, `mobile=False`, чтобы раскладка не зависела
  от размера окна по умолчанию), включение касания только в сценариях касания. Закрытие вкладки
  `GET /json/close/<id>` с таймаутом 5 с и закрытие websocket в `finally`. Origin у каждого теста свой
  (случайный порт), поэтому `localStorage`, кэш и cookie между тестами не пересекаются.
- Аутентификация `/web/wishlists/{id}`: **заголовок `Authorization: Bearer <токен>` через
  `Network.setExtraHTTPHeaders`**, токен выпускает `SessionTokenService(settings.secret_key)
  .create_token(telegram_id, first_name)`. Почему не cookie: cookie потребовала бы
  `Origin == application_origin` и `X-CSRF-Token` для POST перестановки (`security.py`), то есть
  настройку `Settings.application_origin` под случайный порт и подстановку CSRF-токена, который
  в проде добавляет `base.html` через `htmx:configRequest` (событие заглушки не воспроизводит).
  Это отдельное поведение, к пунктам 1-18 не относится; CSRF уже покрыт серверными тестами.
  Побочное следствие, фиксируется как ограничение: браузерный POST идёт как Bearer-запрос
  и CSRF-путь не упражняется. Существующие браузерные тесты серверные страницы не открывают, то есть
  прецедента нет, решение новое. Для `/share/{token}` заголовок не ставится (анонимный посетитель,
  п. 6, 11); для проверки вложенных форм (п. 4) используется второй пользователь с Bearer, не
  владелец (у него `can_promise` и форма бронирования в сводке).
- Время: сессия (Chromium ~1 с + шаблон БД 1,4 с) один раз; на тест около 0,4 с накладных +
  само действие. Оценка 50-55 тестов около 45-60 с, укладывается в ориентир п. 25; фактическое
  значение измеряется на Step 4-5.

### Ограниченные ожидания (do-testing, п. 21)

- `CdpPage.wait_for(description, predicate, timeout=5.0)`: цикл `evaluate` до дедлайна
  `time.monotonic()+timeout`, шаг опроса 25 мс (это интервал опроса, не «слепая пауза»); при
  истечении `PageWaitTimeout` с описанием ожидания, последним значением, хвостом журнала консоли и
  запросов, снимком `#items-list`.
- Все `ws.recv` с таймаутом; каждый `send_command` ограничен 10 с; ожидание `Page.loadEventFired`
  и `Fetch.requestPaused` через тот же общий насос событий (`_pump(deadline)`) без потоков:
  один читатель, обработчик `Fetch.requestPaused` отвечает командой fire-and-forget (ответ придёт
  позже и будет учтён насосом). Потоки не нужны, гонок по `ws.send` нет.
- Отрицательные утверждения («запроса не было») не требуют ожидания: `submitReorder` синхронно
  вызывается внутри обработчика `pointerup`/`drop`, а `Input.dispatch*Event` возвращается после
  подтверждения рендерером; последующий `Runtime.evaluate` исполняется после него на главном
  потоке страницы (подтвердить на Step 4 десятикратным прогоном).
- Единственное ожидание по часам: окно подавления клика п. 18 (400 мс, `CLICK_SUPPRESS_MS`):
  `wait_for` до тех пор, пока `performance.now()` страницы не превысит момент конца жеста + 450 мс
  (дедлайн 3 с). Константа 400 дублируется в тесте с комментарием «зеркало
  `CLICK_SUPPRESS_MS` из wishlist.js»; значение читается из исходника нельзя (константа внутри IIFE).

## Implementation Plan

Пошагово (Step 3 пишет красные тесты на заглушке драйвера, Step 4 реализует драйвер и доводит до
зелёного; см. Failing Repro):

1. `tests/browser_cdp.py` (новый): `CdpBrowser` (запуск и остановка процесса, `new_page()`),
   `CdpPage` (интерфейс ниже), `PageWaitTimeout`. Только стандартная библиотека, `websockets`,
   `httpx`.
2. `tests/browser_assets/htmx_stub.js` (новый): заглушка (b).
3. `tests/conftest.py`: сессионные `chromium_browser`, `migrated_db_template`; функциональные
   `wishlist_server`, `seed_wishlist`, `wishlist_page`, `share_page`; хук
   `pytest_runtest_makereport` для диагностики при падении (ниже). Ленивые импорты, чтобы
   остальные тесты не платили за `uvicorn`/CDP.
4. Три модуля тестов (каталог ниже), каждый с
   `pytestmark = [pytest.mark.timeout(45), pytest.mark.browser]`.
5. Мутационная проверка (e), сопоставление чистки (f), десятикратный прогон п. 21, запись
   времени п. 25.
6. Чистка слабых строковых тестов (f) после зелёных замен.
7. Документация (i) на Step 8.

### Failing Repro (Step 3)

Задача добавляет тесты, а не производственный код, поэтому честное определение «красного»:
поведение приложения уже корректно (мы не меняем `wishlist.js`), и новые тесты против настоящего
драйвера сразу зелёные. Значит красный бывает двух видов, и они оба нужны.

1. **Структурный красный (Step 3, как требует td-25 и раздел «Stubs» `lsr-python`).**
   Пишутся полностью модули тестов и фикстуры с настоящими утверждениями (порядок `item_ids`,
   `aria-expanded`/`hidden`, число запросов, сообщения консоли), а `tests/browser_cdp.py` создаётся
   как заглушка с теми же сигнатурами: методы `CdpPage` и `CdpBrowser` бросают
   `NotImplementedError("CdpPage.<method> not implemented")` (стиль заглушек `lsr-python`).
   Результат: все новые тесты падают красными ровно из-за `NotImplementedError` на первом вызове
   драйвера, а не из-за `ImportError`, ошибки сбора или опечатки (рецензент проверяет причину по
   трейсу каждого падения; сбор тестов `pytest --collect-only` проходит чисто). Это красный «по
   причине отсутствия возможности наблюдать поведение», то есть именно та дыра, которую закрывает
   задача. Фикстуры, не требующие драйвера (`migrated_db_template`, `seed_wishlist`), уже
   реализуются на Step 3 только если без них тест нельзя написать; иначе тоже заглушка.
2. **Поведенческий красный (Step 4, мутационное доказательство п. 27).** Для каждой
   мутации из (e) показывается, что хотя бы один новый тест падает по утверждению о поведении
   (а не по таймауту или ошибке драйвера); результаты записываются в подпункты roadmap шагов 3-4.
   Именно это доказывает, что тесты ловят регрессию, а не пропускают всё подряд.

Последовательность: исследование (этот документ) -> тесты и заглушка драйвера (красные,
`NotImplementedError`) -> драйвер, фикстуры, заглушка htmx -> зелёные тесты -> мутации (красные
по поведению, затем откат) -> чистка слабых тестов -> десятикратный прогон -> `make check`.
Если тесты вскроют дефект `wishlist.js`, он заводится отдельным багом, тест остаётся красным
только по согласованной политике (xfail без ссылки на задачу запрещён).

## Architecture

### Модули и зависимости

```text
tests/conftest.py ──(lazy)──> tests/browser_cdp.py ──> websockets.sync, httpx
   │  chromium_executable (WISHENKA-124)     CdpBrowser, CdpPage, PageWaitTimeout
   │  chromium_browser (session)  ───────────────────┘
   │  migrated_db_template (session)  ──> wishenka.web.app.create_app
   │  wishlist_server (function)      ──> uvicorn.Server in thread, copied SQLite
   │  seed_wishlist (function)        ──> httpx + Bearer -> REST of the app
   │  wishlist_page / share_page      ──> CdpBrowser.new_page(), offline Fetch, auth header
   └ pytest_runtest_makereport        ──> failure diagnostics
tests/browser_assets/htmx_stub.js      (served by Fetch.fulfillRequest in place of unpkg htmx)
tests/test_wishlist_cards_browser.py        п. 1-6, 22
tests/test_wishlist_mouse_reorder_browser.py п. 7-11
tests/test_wishlist_touch_reorder_browser.py п. 12-18
```

Шаблон: «Page Object» минимального размера (`CdpPage`) + фабричные фикстуры (изоляция состояния
по тесту) + прокси-заглушка внешних ресурсов на границе сети (Fetch). Модули тестов не знают
о CDP-методах напрямую, только об интерфейсе `CdpPage`.

### Интерфейс `CdpPage` (основной контракт Step 3-4)

| Метод / свойство | Назначение |
| --- | --- |
| `navigate(url)` | `Page.navigate` + ожидание `Page.loadEventFired` (дедлайн 10 с) |
| `evaluate(expression, *, await_promise=False)` | `Runtime.evaluate` с `returnByValue`, исключение страницы превращается в `AssertionError` с текстом |
| `wait_for(description, predicate_js, timeout=5.0)` | ограниченный опрос выражения JS (см. выше) |
| `click(selector)` | центр элемента (`getBoundingClientRect`) -> `Input.dispatchMouseEvent` pressed/released |
| `press_key(key)` | `Input.dispatchKeyEvent` keyDown/keyUp (`Enter`, `Space` с `text:" "`, `Escape`, произвольная буква) |
| `mouse_drag(source_selector, target_selector, *, y_fraction)` | нативный DnD по CDP: `Input.setInterceptDrags`, `mousePressed`, два `mouseMoved`, ожидание `Input.dragIntercepted` (дедлайн 3 с), `dispatchDragEvent` dragEnter/dragOver/drop, `mouseReleased` |
| `drop_outside(source_selector, point)` | то же с точкой вне списка |
| `touch_start(points)`, `touch_move(points)`, `touch_end()`, `touch_cancel()` | `Input.dispatchTouchEvent` (id пальца, несколько `touchPoints`); `Emulation.setTouchEmulationEnabled` включается `enable_touch()` |
| `touch_tap(selector)`, `touch_drag(handle_selector, target_selector, y_fraction, *, steps=4)` | составные жесты на основе предыдущих |
| `dispatch_window_event(kind)` | синтетические `blur` и `visibilitychange` (с `document.hidden` через `Object.defineProperty`) |
| `console` | список сообщений `Runtime.consoleAPICalled` (тип, текст) и исключений `Runtime.exceptionThrown`; `console.warnings()` |
| `requests`, `external_requests` | записи Fetch (метод, URL, тело) и заблокированные внешние запросы |
| `ajax_calls()` | `window.__ajaxCalls` заглушки htmx |
| `order()` | `[data-item-id]` карточек `#items-list` в порядке DOM (строки) |
| `card_state(item_id)` | `{expanded: aria-expanded, hidden: details.hidden}` |
| `snapshot()` | текстовая сводка (порядок, состояния, классы жеста, хвост консоли и запросов, `outerHTML` списка) |
| `screenshot(path)` | `Page.captureScreenshot` |
| `close()` | закрыть websocket и вкладку (ограниченно) |

`CdpBrowser`: `start(executable, profile_dir)`, `ensure_alive()`, `new_page()`, `stop()`.
Типы: строгие аннотации (mypy `check_untyped_defs`, ruff `line-length = 100`), docstrings в стиле
Google по `lsr-python`.

### Нативный DnD мышью: решение и точность

Основной путь: настоящий DnD через CDP (`Input.setInterceptDrags` + `dispatchDragEvent`), потому
что он порождает доверенные (`isTrusted`) события `dragstart`/`dragover`/`drop`/`dragend` с
настоящим `DataTransfer` и настоящим `clientY`, а середина цели считается по реальной раскладке.
Спайк прошёл с первой попытки. Риск флакинесса: событие `Input.dragIntercepted` приходит
асинхронно; драйвер ждёт его с дедлайном 3 с и при отсутствии падает с понятным сообщением.
Критерий выбора: десятикратный прогон п. 21 без падений. **Запасной путь**, если на Step 4
наблюдается нестабильность: синтетические `DragEvent` (`new DragEvent('dragstart', {bubbles:true,
dataTransfer: new DataTransfer()})`, затем `dragover`, `drop` с `clientY`, `dragend`), посланные
скриптом. Он теряет `isTrusted` и работу нативного механизма, но проверяет логику `wishlist.js`
(середина, порядок, один запрос), то есть всё, что защищает п. 7-10; потеря фиксируется в итогах.

Отмена мышью (п. 14 последняя фраза отсылает к п. 14, отмена мышью — Escape во время нативного
DnD браузер сам завершает событием `dragend`): проверяется одним тестом `dragend` без `drop`
(состояние `dragged` не залипает, следующий жест работает) в `test_repeat_reorder_...`.

### Что делает каждый класс отмены в тестах касания (п. 14)

| Путь | Как вызывается | Реальность |
| --- | --- | --- |
| `pointercancel` | `Input.dispatchTouchEvent` type `touchCancel` | настоящее событие рендерера (подтвердить на Step 4) |
| потеря захвата | `handle.releasePointerCapture(pointerId)` из страницы во время жеста | настоящее `lostpointercapture` |
| Escape | `Input.dispatchKeyEvent` `Escape` | настоящий ввод |
| `blur` окна | `window.dispatchEvent(new Event('blur'))` | синтетическое: настоящая потеря фокуса окна в headless нестабильна |
| `visibilitychange` | `Object.defineProperty(document,'hidden',{value:true,configurable:true})` и `document.dispatchEvent(new Event('visibilitychange'))` | синтетическое по той же причине; `Emulation.setFocusEmulationEnabled` и `Page.setWebLifecycleState` не гарантируют это событие (проверить на Step 4) |
| `htmx:beforeSwap` | в середине жеста заглушка выполняет настоящий запрос `.../items/<id>/move?direction=up` с целью `#items-list` (событие `beforeSwap` отправляет сама заглушка, форма как у htmx) | промежуточная реальность: сервер и подмена настоящие, событие имитировано |

После отмены каждый тест продолжает жест (`touchEnd`) и убеждается, что запрос не ушёл, порядок
в DOM исходный, классы `is-touch-dragging`, `drop-before`/`drop-after`, `body.is-touch-reordering`
сняты, `transform` карточки пуст.

### Каталог тестов: сопоставление с пунктами 1-30

Параметризация описана в скобках; все тесты используют `wishlist_page` с тремя желаниями
(для п. 4 одно с `quantity=3` ради `select`), кроме отмеченных. Общий autouse-страж
`assert_clean_console` в конце теста проверяет, что в консоли нет предупреждений, ошибок и
необработанных исключений, кроме явно ожидаемых тестом (его `expected_warnings`).

#### `tests/test_wishlist_cards_browser.py` (п. 1-6, 22)

| Тест | Пункт | Что утверждает |
| --- | --- | --- |
| `test_page_loads_offline_with_real_assets` (owner, share) | 22 | `external_requests == []`; `/static/wishlist.js` и `/static/miniapp.css` получены с сервера (200); `htmx.version == 'stub'`; число `.item-card-summary` равно числу желаний |
| `test_click_toggles_card_both_ways` | 1 | клик: `aria-expanded="true"`, у `.item-card-details` нет `hidden`; второй клик: `"false"` и `hidden` |
| `test_enter_and_space_toggle` (Enter, Space) | 2 | фокус на сводке, клавиша переключает как клик |
| `test_space_default_prevented_and_page_does_not_scroll` | 2 | слушатель `keydown` на `window` записывает `defaultPrevented === true` для пробела; `scrollY` не меняется на высокой странице |
| `test_other_keys_do_not_toggle` (`a`, `Escape`, `ArrowDown`) | 2 | состояние не меняется |
| `test_toggle_one_card_leaves_others_untouched` | 3 | после каждого действия на трёх карточках пара `aria-expanded`/`hidden` согласована у всех, чужие не меняются |
| `test_nested_controls_do_not_toggle` (ручка на owner-странице; текст блока `.item-giver`, `select`, кнопка «Забронировать» с отменой `submit` на share-странице вошедшего не владельца; синтетически вставленные `a[href=#x]`, `input`, `textarea` в сводку) | 4 | клик не меняет состояние карточки; для кнопки в форме `submit` отменяется скриптом теста, чтобы не уйти нативной навигацией |
| `test_toggle_works_after_htmx_swap` | 5 | перестановка кнопкой `move`/`ajax` заменяет `#items-list` настоящим HTML сервера; новая карточка раскрывается кликом и клавишей (делегирование) |
| `test_share_page_toggles_cards` (click, Enter, Space) | 6 | то же на `/share/{token}` анонимно |

Замечание по п. 4: в требованиях перечислены «метки». В `TOGGLE_EXCLUSION` элемента `label`
нет, поэтому тест проверяет набор, который в коде реально есть (`a, button, input, select,
textarea, [data-no-toggle]`); `label` не проверяется, расхождение сообщается в итогах
(возможный дефект/уточнение требования, не блокирует).

#### `tests/test_wishlist_mouse_reorder_browser.py` (п. 7-11)

| Тест | Пункт | Что утверждает |
| --- | --- | --- |
| `test_mouse_drop_before_or_after_target_midpoint` (параметры: первая на третью верхняя половина -> `[2,1,3]`... и нижняя -> `[2,3,1]`; последняя на первую верхняя -> `[3,1,2]` и нижняя -> `[1,3,2]`) | 7 | порядок DOM соответствует до/после цели |
| `test_mouse_drop_sends_exactly_one_request_with_full_order` | 8 | ровно один вызов `htmx.ajax` и ровно один сетевой POST; метод, адрес `/web/wishlists/<id>/items/reorder`, `item_ids` = все карточки в порядке DOM (сравнение списков строк с ожидаемым, сообщение с обоими); после `navigate` порядок на сервере тот же (сервер принял и сохранил) |
| `test_reorder_uses_data_wishlist_id_not_location` | 8, 28 | перед жестом `data-wishlist-id` меняется на другое число: адрес запроса использует его (замена проверки `window.location`/`wishlistId` в строках) |
| `test_drop_on_self_or_outside_list_is_a_no_op` (self, outside) | 9 | нет `htmx.ajax`, нет POST, порядок прежний, консоль без предупреждений и исключений, страница отвечает (последующий корректный жест работает) |
| `test_reorder_skipped_with_exactly_one_warning` (id отсутствует, id `abc`, `window.htmx` удалён) | 9, 30 | жест на настоящей карточке: запроса нет, DOM прежний (в `submitReorder` вставка выполняется после проверки), ровно одно `console.warn`, текст содержит `reorder skipped` и причину (`not numeric` / `not loaded`) |
| `test_repeated_reorder_without_reload` | 10 | два жеста подряд без перезагрузки, у каждого один запрос и корректный порядок; после отпускания на себя следующий настоящий жест работает (`dragged` не залипает); `dragend` без `drop` тоже не залипает |
| `test_share_page_has_no_handle_and_cannot_reorder` (нативный DnD, синтетический dragstart+drop) | 11 | нет `.item-drag-handle` и `[draggable="true"]`; ни одного `/items/reorder` ни в `requests`, ни в `ajax_calls()` |

#### `tests/test_wishlist_touch_reorder_browser.py` (п. 12-18)

Все жесты через `Emulation.setTouchEmulationEnabled` и `Input.dispatchTouchEvent`, с шагами
`touchMove` (не менее двух перемещений, порог 4 px) на реальном CSS приложения.

| Тест | Пункт | Что утверждает |
| --- | --- | --- |
| `test_touch_drag_handle_reorders` (верхняя половина, нижняя половина, развёрнутая карточка) | 12 | до `touchEnd` на цели видны `drop-before`/`drop-after`, у карточки `is-touch-dragging`; после: порядок DOM, один запрос, `item_ids` равен DOM |
| `test_expanded_card_stays_expanded_after_cancelled_touch_drag` | 12 | развёрнутая карточка: жест + `touchCancel`, состояние `aria-expanded="true"`/без `hidden` сохранено, запроса нет |
| `test_tap_on_summary_toggles_tap_on_handle_does_nothing` | 13 | tap по сводке переключает; tap по ручке: нет переключения, нет запроса, нет `is-touch-dragging` |
| `test_touch_cancel_paths_send_nothing` (`pointercancel`, `lostpointercapture`, Escape, `blur`, `visibilitychange`, `htmx:beforeSwap`) | 14 | см. таблицу путей отмены |
| `test_second_finger_does_not_start_second_gesture` | 15 | второй `touchPoint` на другой ручке во время жеста: запросов нет (код отменяет жест), порядок прежний |
| `test_escape_cancels_armed_and_active_gesture` (до порога, после порога) | 16 | запроса нет, состояние чистое |
| `test_vertical_swipe_outside_handle_scrolls_not_reorders` | 17 | на странице с прокруткой (8 желаний, окно 412x500) свайп по тексту сводки: `scrollY` увеличился (если синтезированное касание скроллит; иначе утверждение ослабляется до «нет жеста, нет запроса» с записью причины), порядок прежний, запроса нет |
| `test_one_request_per_gesture` | 18 | число `htmx.ajax` и сетевых POST равно 1 за жест |
| `test_next_tap_after_suppression_window_toggles` (после drop, после отменённого активного жеста) | 18 | после жеста ждём конец окна по часам страницы, tap по сводке переключает (поведение, не флаг) |
| `test_handle_and_feedback_computed_styles` | 28, 29 | `getComputedStyle(handle).touchAction == 'none'`, `userSelect == 'none'`, ширина и высота ручки не менее 44 px; во время жеста у `.is-touch-dragging` `opacity < 1`, у цели `drop-before`/`drop-after` непустой `boxShadow` (замена строковых CSS-проверок; `touch-callout` не проверяется, в десктопном Chromium не поддерживается) |

Пункт 19 (автопрокрутка, заглушка Telegram SDK, `warnSdk`, WISHENKA-143): тестов нет сознательно.

#### Сводная таблица критериев

| Пункт | Покрытие |
| --- | --- |
| 1 | `test_click_toggles_card_both_ways` |
| 2 | `test_enter_and_space_toggle`, `test_space_default_prevented...`, `test_other_keys_do_not_toggle` |
| 3 | `test_toggle_one_card_leaves_others_untouched` |
| 4 | `test_nested_controls_do_not_toggle` |
| 5 | `test_toggle_works_after_htmx_swap` |
| 6 | `test_share_page_toggles_cards` |
| 7 | `test_mouse_drop_before_or_after_target_midpoint` |
| 8 | `test_mouse_drop_sends_exactly_one_request_with_full_order`, `test_reorder_uses_data_wishlist_id...` |
| 9 | `test_drop_on_self_or_outside_list_is_a_no_op`, `test_reorder_skipped_with_exactly_one_warning` |
| 10 | `test_repeated_reorder_without_reload` |
| 11 | `test_share_page_has_no_handle_and_cannot_reorder` |
| 12 | `test_touch_drag_handle_reorders`, `test_expanded_card_stays_expanded...` |
| 13 | `test_tap_on_summary_toggles_tap_on_handle_does_nothing` |
| 14 | `test_touch_cancel_paths_send_nothing` (6 параметров) |
| 15 | `test_second_finger_does_not_start_second_gesture` |
| 16 | `test_escape_cancels_armed_and_active_gesture` |
| 17 | `test_vertical_swipe_outside_handle_scrolls_not_reorders` |
| 18 | `test_one_request_per_gesture`, `test_next_tap_after_suppression_window_toggles` |
| 19 | вне объёма, тестов нет |
| 20 | фикстуры (c); `test_page_loads_offline_with_real_assets`; остановка в `finally` |
| 21 | ограниченные ожидания `wait_for`; `pytestmark timeout(45)`; десятикратный прогон на Step 4, результат в roadmap |
| 22 | (b) + `test_page_loads_offline_with_real_assets` |
| 23 | зависимость `chromium_browser` -> `chromium_executable`; охранный тест (ниже) |
| 24 | маркер `browser` в `pytestmark`; охранный тест; `make test`/`make check` без флагов |
| 25 | `timeout(45)` на модуль; измерение суммарного времени на Step 4-5 |
| 26 | диагностика (h) |
| 27 | мутационная проверка (e) |
| 28, 29 | таблица чистки (f) |
| 30 | `test_reorder_skipped_with_exactly_one_warning`, `test_drop_on_self_or_outside...`, пути отмены п. 14 |

Охранный тест `test_new_browser_modules_declare_marker_and_timeout` в
`tests/test_browser_prerequisites.py` (без Chromium): разбирает AST `tests/test_*_browser.py`
и проверяет, что `pytestmark` содержит `browser` и `timeout(45)` (п. 24, 25). Это единственная
правка существующего тестового файла.

### (e) Мутационное доказательство (п. 27)

Процедура на Step 4 (после зелёных тестов), для каждой строки: (1) копия оригинала
`wishlist.js` в scratchpad; (2) временная правка скриптом `python -I` (замена одной подстроки,
контроль, что замена сработала ровно один раз); (3) запуск `.venv/bin/pytest -m browser -q -x
tests/test_wishlist_*_browser.py` (без `-x`, если нужен полный список красных); (4) запись
в roadmap: мутация, список упавших тестов и причина (утверждение, не таймаут); (5) возврат
`git checkout -- wishenka/web/static/wishlist.js`; (6) проверка `git diff --exit-code -- wishenka/`
пуста после последней мутации. `wishlist.js` никогда не попадает в коммит (на td-99 файлы
стейджатся по именам). Скрипт мутаций не коммитится.

| № | Мутация (временная правка `wishlist.js`) | Ожидаемо красные |
| --- | --- | --- |
| M1 | `isAfterMidpoint`: `>` -> `<` | `test_mouse_drop_before_or_after...`, `test_touch_drag_handle_reorders` |
| M2 | `submitReorder`: собрать `ids` до `insertBefore` (старый порядок) | `test_mouse_drop_sends_exactly_one_request...`, `test_touch_drag_handle_reorders` |
| M3 | `toggleWishCard`: убрать `if (event.target.closest(TOGGLE_EXCLUSION)) return;` | `test_nested_controls_do_not_toggle`, `test_tap_on_summary...` (tap по ручке) |
| M4a | убрать слушатель `keydown` для `Escape` | `test_escape_cancels...`, параметр Escape п. 14 |
| M4b | убрать слушатель `pointercancel` | параметр `pointercancel` п. 14 |
| M5 | в `pointerup` вызывать `submitReorder` дважды (второй вызов после первого) | `test_one_request_per_gesture`, проверки «ровно один» п. 8 и 12 |
| M6 | удалить `console.warn(...)` в `submitReorder` | `test_reorder_skipped_with_exactly_one_warning` (все три параметра) |
| M7 | `details.hidden = expanded` -> `!expanded` | `test_click_toggles_card_both_ways`, `test_toggle_one_card...` |
| M8 | убрать `event.preventDefault()` на `keydown` | `test_space_default_prevented...` |
| M9 | убрать слушатель `lostpointercapture` | параметр п. 14 |
| M10 | убрать слушатели `visibilitychange` и `blur` (по одному) | соответствующие параметры п. 14 |
| M11 | убрать слушатель `htmx:beforeSwap` | параметр `htmx:beforeSwap` п. 14 |
| M12 | `drop`: убрать `target === dragged` из условия отпускания на себя | `test_drop_on_self_or_outside...` (self) |
| M13 | `armClickSuppression`: не сбрасывать флаг по таймеру | `test_next_tap_after_suppression_window_toggles` |
| M14 | `pointerdown`: при втором пальце не отменять жест | `test_second_finger_does_not_start_second_gesture` |

Обязательная выборка п. 27 (середина M1, порядок M2, исключения M3, Escape/`pointercancel` M4a/M4b,
второй запрос M5, удалённый `console.warn` M6) обязательна; M7-M14 желательны, красные записываются,
но непокрытая мутация из M7-M14 не блокирует задачу, а заводится как найденный пробел тестов.

### (f) Чистка слабых тестов (п. 28-29)

Удаление выполняется только после зелёных замен и мутаций, одним отдельным шагом Step 4.

| Что удаляется / сокращается | Содержание проверки | Чем заменено (браузерный тест) |
| --- | --- | --- |
| `test_static_wishlist_script_content` маркеры `toggleWishCard`, `' '`, `'Enter'`, `.item-card-summary`, `EXCLUSION_SELECTOR` | текст в исходнике | п. 1, 2, 4: `test_click_toggles...`, `test_enter_and_space_toggle`, `test_nested_controls_do_not_toggle` |
| то же: `dragstart`, `dragover`, `drop`, `dragend`, `/items/reorder` | текст | п. 7, 8, 10: тесты мышиной перестановки, адрес из записанного запроса |
| то же: `wishlistId`/`data-wishlist-id` и отсутствие `location.pathname`/`window.location` | текст | `test_reorder_uses_data_wishlist_id_not_location` |
| остаётся в `test_static_wishlist_script_content` | статус 200 и `javascript` в `content-type` `/static/wishlist.js` | не заменяется (сильная проверка отдачи) |
| `test_wishlist_script_contains_token`: `pointerdown`, `pointermove`, `pointerup`, `pointercancel`, `lostpointercapture`, `setPointerCapture`, `elementFromPoint`, `'touch'`, `'Escape'`, `requestAnimationFrame`, `visibilitychange`, `htmx:beforeSwap`, `pointerType`, `submitReorder`, `isAfterMidpoint`, `.item-drag-handle`, `is-touch-dragging`, `drop-before`, `drop-after` | текст | п. 12-18: `test_touch_drag_handle_reorders`, `test_touch_cancel_paths_send_nothing`, `test_escape_cancels...`, `test_second_finger...` |
| остаётся: `disableVerticalSwipes`, `enableVerticalSwipes`, `isVersionAtLeast`, `HapticFeedback` (сокращённый параметризованный `test_wishlist_script_contains_sdk_token`) | текст | не заменяется: Telegram SDK вне объёма (п. 19), WISHENKA-143; удалить при закрытии WISHENKA-143 |
| `test_css_drag_handle_declares_touch_rules`: `touch-action: none`, `user-select: none`, `min-width: 44px` | текст CSS | `test_handle_and_feedback_computed_styles` (вычисленные стили, переживают переформатирование) |
| остаётся: `-webkit-touch-callout: none` | текст CSS | не заменяется: свойство iOS, в десктопном Chromium недоступно |
| `test_css_has_drag_feedback_rule` (`.is-touch-dragging`, `.drop-before`, `.drop-after`) | наличие правила | вычисленные стили `opacity`/`boxShadow` в том же тесте и классы в тесте п. 12 |
| остаётся (guard): `test_css_summary_does_not_block_touch_scroll` | `.item-card-summary` без `touch-action: none` | дополняется (не заменяется) вертикальным свайпом п. 17; по п. 28 остаётся |
| остаётся (guard): `test_wishlist_script_has_single_reorder_submit_point` | один `htmx.ajax(` | остаётся как guard; поведение «один запрос» подтверждено п. 8, 12, 18 |
| `tests/test_wish_items_list_reorder_ui.py`: `assert "onclick" not in html` (около строки 137) | подстрока | сильная проверка отсутствия любых `on*` атрибутов уже есть: `test_cards_have_no_inline_event_handlers` в `test_wishlist_static_script.py` (остаётся) |
| то же место, строки 138-140: `"toggleWishCard" in static_js.text` (сверх списка Jira) | подстрока имени функции | `test_click_toggles_card_both_ways`; удаляется на тех же основаниях, статус 200 остаётся |

Остаются без изменений: `test_inline_script_no_longer_holds_toggle_or_dnd`,
`test_page_loads_wishlist_script_deferred_after_htmx`, `test_cards_have_no_inline_event_handlers`,
`test_items_list_declares_wishlist_id*`, `test_guard_no_swap_replaces_items_list_container`,
`test_no_new_third_party_scripts` (оба файла), все проверки разметки ручки и `draggable`.
Оценка снижения числа тестов: около 24 + 3 + 2 параметров заменены 53 браузерными; общее число
зелёных тестов проекта вырастет, а число слабых строковых уменьшится осознанно; точная цифра
фиксируется на Step 4 (п. 29).

### (h) CI, бюджет, диагностика

- Новый шаг CI не нужен: тесты помечены `browser`, лежат в `tests/`, выполняются
  в `make test`/`make check` без флагов; в CI Chromium готовит существующий шаг
  `make deps-browser`. Новых зависимостей нет (`websockets`, `httpx`, `uvicorn` уже в проекте),
  поэтому `pyproject.toml` и `Makefile` не меняются. Локальный opt-out
  `WISHENKA_SKIP_BROWSER_TESTS=1` и политика ERROR на setup работают через `chromium_executable`
  (п. 23, 24).
- Бюджет: оценка 53 теста, около 0,8-1,1 с на тест + сессия 3 с = 45-60 с (оценка по спайку, не
  измерена). Фактическое время записывается на Step 4-5 (`--durations=15`); превышение 60 с
  не блокирует, требует причины.
- Диагностика (п. 26): (1) `PageWaitTimeout` и `AssertionError` из хелперов включают
  `snapshot()` (ожидаемый и фактический порядок, `aria-expanded`/`hidden` каждой карточки, классы
  жеста, последние 20 сообщений консоли, последние 20 запросов `requests`, `ajax_calls()`,
  `outerHTML` `#items-list`); (2) хук `pytest_runtest_makereport` в `conftest.py` сохраняет
  результат фазы на `item`, фикстура `wishlist_page` при падении в teardown пишет
  `diagnostics.txt` и `failure.png` (`Page.captureScreenshot`) в `tmp_path` и добавляет их путь
  и текст в отчёт (`item.add_report_section`); (3) собственные ошибки драйвера содержат имя
  метода CDP и ответ. Скриншот желателен, не обязателен; его сбой не должен маскировать
  исходное падение (`try/except` вокруг с записью причины).

### (i) Документация для Step 8

- `doc/dev/testing.md`: в раздел Overview добавить три новых модуля и ссылку на новую
  подсекцию «Браузерные тесты списка желаний (WISHENKA-110)»: выбор CDP вместо Playwright и
  причина, `tests/browser_cdp.py` и интерфейс `CdpPage`, фикстуры (сессионный Chromium, шаблон
  БД, сервер и БД на тест), офлайн-заглушки трёх внешних URL и пределы точности заглушки htmx,
  Bearer-аутентификация и ограничение «CSRF-путь не упражняется», диагностика при падении,
  запуск `pytest tests/test_wishlist_*_browser.py -m browser`, процедура мутационной проверки,
  оценка времени. Обновить перечень «Тесты с маркером `browser`...» в начале файла.
- `doc/dev/miniapp.md` §9.8.1, пункт **Tests** (строки около 580-591): заменить абзацы про
  «brittle string matches» и «no behavioural test is committed» описанием браузерных тестов
  и оставшихся строковых проверок (SDK-токены, `-webkit-touch-callout`, guard-тесты, `single
  submit point`); сослаться на WISHENKA-143 для реального устройства; оговорка, что `label`
  не входит в набор исключений переключения (если подтвердится как факт).
- Требований к `specs/` и `in-docs/` нет (поведение продукта не меняется).

## Q&A

- **Почему не Playwright, раз он назван в заголовке Jira?** Заголовок выражает намерение
  «браузерные тесты» (раздел Q&A требований). Playwright с системным Chromium работает вне
  гарантированной связки версий ([Playwright: Browsers](https://playwright.dev/python/docs/browsers),
  [BrowserType](https://playwright.dev/python/docs/api/class-browsertype)), добавляет колесо
  53,5 МБ ([PyPI](https://pypi.org/pypi/playwright/json)) и вторую политику запуска браузера;
  а касание и перетаскивание на низком уровне всё равно идёт через CDP. Выбран
  собственный `CdpPage` на уже объявленных `websockets` и `httpx`.
- **Не слишком ли слабая заглушка htmx?** Она записывает аргументы `htmx.ajax` и пересылает
  запрос настоящему серверу, так что порядок и перерисовка проверяются на настоящих данных.
  Не проверяются `hx-*` атрибуты, `configRequest`, расширения: это вне пп. 1-18 (раздел (b)).
- **Почему Bearer, а не cookie?** Cookie требует `Origin` и CSRF-токен для POST (`security.py`);
  в этой задаче нужна логика перестановки, а не CSRF. Ограничение записано.
- **Почему сервер на каждый тест, а не на модуль?** П. 20 требует собственную БД на тест;
  копирование мигрированного шаблона делает запуск дешёвым (1,4 с -> 0,03 с в спайке).
- **Что если нативный DnD через CDP окажется нестабильным?** Запасной путь с синтетическими
  `DragEvent`, потеря фиксируется (раздел «Нативный DnD мышью»). Решает десятикратный
  прогон п. 21.
- **Нужно ли менять `wishlist.js` ради тестов?** Нет (вне объёма). Найденные дефекты (например,
  `label` в исключениях) оформляются отдельно.
- **Что проверить на Step 4 (непроверенное на Step 2)?** Скролл от синтезированного касания
  (п. 17), `touchCancel` -> `pointercancel`, второй палец одним `touchStart`, tap -> `click`,
  влияние `touch-action: none` на синтезированный свайп, порядок «диспетчеризация события
  завершена до следующего `evaluate`», заведение данных через REST из главного потока, поведение
  `visibilitychange`/`blur` без синтетики, совместимость с mypy/ruff, фактическое время
  модулей.
- Источники: `ai-tasks/WISHENKA-124/20-architecture.md`, `ai-tasks/WISHENKA-109/20-architecture.md`
  и `60-tech-debt.md`, `tests/browser_support.py`, `tests/conftest.py`, оба существующих
  браузерных теста, [CDP Input domain](https://chromedevtools.github.io/devtools-protocol/tot/Input/),
  [CDP Fetch domain](https://chromedevtools.github.io/devtools-protocol/tot/Fetch/) (методы
  использованы по спайку, содержание страниц на Step 2 не извлекалось, поведение подтверждено
  эмпирически), [Playwright: Browsers](https://playwright.dev/python/docs/browsers).
