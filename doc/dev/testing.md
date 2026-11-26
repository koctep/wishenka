# Browser UI-тесты: подготовка Chromium

## Overview

Тесты с маркером `browser` управляют настоящим Chromium/Chrome через Chrome DevTools Protocol (CDP):
`tests/test_wishlist_management_browser.py`, `tests/test_wishlist_sections_ui.py`, три модуля
поведенческих тестов списка желаний (раздел «Browser UI-тесты списка желаний (WISHENKA-110)» ниже)
и модули диалога получения `tests/test_receipt_modal_browser.py` (WISHENKA-24) и
`tests/test_receipt_accessibility_browser.py` (WISHENKA-161, раздел «Диалог получения
(WISHENKA-24, WISHENKA-161)»).
Для них нужен исполняемый браузер. Раньше его отсутствие приводило к пропуску тестов и «зелёному» прогону.

Теперь поведение такое:

- браузер ищется и проверяется в одном месте (`tests/browser_support.py`);
- если браузера нет, каждый браузерный тест завершается ошибкой на этапе setup, а `pytest`
  возвращает ненулевой код выхода;
- пропуск возможен только как явный локальный opt-out и никогда не действует в CI;
- `make deps-browser` готовит браузер, а CI вызывает эту цель перед `make check`.

Общие сведения о Makefile и CI: `doc/dev/infrastructure.md`.

Как устроен параллельный запуск всего набора (`make test`, xdist, `/dev/shm`) и как запускать
тесты последовательно: раздел «Параллельный запуск тестов (WISHENKA-166)» ниже.

## Architecture

| Компонент | Назначение |
| --- | --- |
| `tests/browser_support.py` | Единственное место, которое знает, как найти и проверить браузер. Только стандартная библиотека. Используется фикстурой и CLI. |
| `tests/conftest.py` | Сессионная фикстура `chromium_executable`: вызывает `check_chromium(os.environ)` и превращает результат в путь, `pytest.skip` или `pytest.fail`. |
| `python -m tests.browser_support` | CLI для `make deps-browser`. Строгий режим: `WISHENKA_SKIP_BROWSER_TESTS` не учитывает. |
| `Makefile`, цель `deps-browser` | Печатает найденный браузер; на Debian без браузера ставит пакет `chromium`. |
| `.github/workflows/ci.yml` | Шаг `make deps-browser` между `make deps` и `make check`. |
| `tests/test_browser_prerequisites.py` | Тесты самой подготовки: поиск, проба, политика fail/skip, CLI, `Makefile`, `ci.yml`, `pyproject.toml`. |
| `pyproject.toml` | Маркер `browser` и dev-зависимость `websockets>=13.0` (клиент CDP). |

Основные функции `tests/browser_support.py`:

- `find_candidates(env, path=None)` — список кандидатов (порядок ниже).
- `probe(executable, timeout=10.0)` — запускает `<браузер> --version`, никогда не бросает
  исключений, возвращает `ProbeResult(ok, version, detail)`.
- `check_chromium(env, path=None, probe_timeout=10.0)` — выбирает первый пригодный браузер и
  применяет политику fail/skip; возвращает `BrowserCheck` с действием `ok`, `skip` или `fail`.
- `missing_message(env, failures)` — текст ошибки: что не найдено или не запускается и как
  исправить.
- `main()` — точка входа CLI с кодами выхода `0`, `2`, `3`.

### Порядок поиска браузера

1. Если задана `WISHENKA_CHROMIUM_BIN` (непустая после обрезки пробелов): единственный кандидат —
   этот путь. Он должен быть обычным файлом с правом на выполнение, иначе кандидатов нет. Отката на
   `PATH` нет.
2. Иначе по `PATH` ищутся имена `chromium`, `chromium-browser`, `google-chrome-stable`,
   `google-chrome` (в этом порядке). Найденные пути приводятся к абсолютным (`abspath`) и
   дублирующиеся пути отбрасываются. Символические ссылки не разыменовываются (`realpath` не
   используется), поэтому ссылки на одну и ту же заглушку проверяются отдельно.

### Проба

Каждый кандидат запускается как `<браузер> --version` с ограничением 10 секунд
(`DEFAULT_PROBE_TIMEOUT`). Кандидат пригоден, если код завершения равен `0` и stdout не пуст. Первая
строка stdout становится версией. Таймаут, невозможность запуска и ненулевой код превращаются в
описание причины (текст stderr обрезается до 300 символов). Выбирается первый пригодный кандидат;
непригодные запоминаются для сообщения об ошибке.

### Коды выхода CLI

| Код | Значение |
| --- | --- |
| `0` | Браузер найден и запускается; в stdout печатаются путь и версия. |
| `2` | Кандидатов нет: ничего не найдено на `PATH` или `WISHENKA_CHROMIUM_BIN` указывает на непригодный файл. |
| `3` | Кандидаты есть, но ни один не прошёл пробу (заглушка, зависание, ошибка запуска). |

Сообщение при коде `2` и `3` печатается в stderr.

## Usage

Подготовка браузера:

```bash
make deps-browser
```

Цель независима от `make deps`: она требует только существующий `.venv/bin/python` (иначе печатает
подсказку выполнить `make venv` или `make deps` и завершается с кодом 1). `make test` и `make check`
цель `deps-browser` не вызывают, поэтому браузер нужно подготовить заранее.

Поведение `make deps-browser`:

- Браузер найден: печатает путь и версию, ничего не устанавливает.
- Код `2`, не задана `WISHENKA_CHROMIUM_BIN`, `ID=debian` в `/etc/os-release` и есть `apt-get`:
  выполняет `apt-get update` и `apt-get install -y chromium` (с `sudo`, если пользователь не root),
  затем повторяет проверку.
- Любой другой случай (Ubuntu, другие дистрибутивы, непригодная `WISHENKA_CHROMIUM_BIN`, код `3`):
  ничего не устанавливает, печатает сообщение и завершается с кодом проверки.

Запуск тестов:

```bash
make deps-browser
make test
```

Только браузерные тесты:

```bash
.venv/bin/pytest -m browser
```

## Configuration

| Переменная | Назначение |
| --- | --- |
| `WISHENKA_CHROMIUM_BIN` | Явный путь к Chromium/Chrome. Если задан и непригоден, откат на `PATH` не выполняется, `make deps-browser` ничего не устанавливает. |
| `WISHENKA_SKIP_BROWSER_TESTS` | Значение ровно `1` включает локальный opt-out: фикстура пропускает тесты с причиной (SKIPPED). Другие значения (`true`, `yes` и т. п.) opt-out не включают. |
| `CI` | Если непустая и после обрезки пробелов и приведения к нижнему регистру не равна `0`, `false`, `no`, считается признаком CI; тогда opt-out игнорируется. Значения вроде `off` также считаются CI. |

Параметры пробы (10 секунд, 300 символов stderr) и список имён браузеров в окружении не
настраиваются.

### Политика fail/skip

| Ситуация | Результат |
| --- | --- |
| Браузер найден | Тесты используют его путь. |
| Браузера нет, opt-out не задан | ERROR at setup у каждого браузерного теста, ненулевой код выхода `pytest`. |
| Браузера нет, `WISHENKA_SKIP_BROWSER_TESTS=1`, `CI` не задана | SKIPPED с причиной (текст содержит и описание проблемы). |
| Браузера нет, `WISHENKA_SKIP_BROWSER_TESTS=1`, `CI` задана | ERROR как без opt-out. |

CLI `python -m tests.browser_support` и `make deps-browser` opt-out не учитывают.

### Запрет скрывать браузерные тесты

Нельзя прятать браузерные тесты опциями `-m "not browser"`, `-k ...browser...`, `--deselect`,
`--ignore` (в `addopts` из `pyproject.toml`, в `Makefile` и `ci.yml`). Единственный разрешённый
локальный способ — `WISHENKA_SKIP_BROWSER_TESTS=1`, и он не работает в CI. Запрет проверяют
`test_addopts_do_not_deselect_tests` и `test_ci_and_makefile_do_not_hide_browser_tests` в
`tests/test_browser_prerequisites.py`.

### CI

В `.github/workflows/ci.yml` шаги идут в порядке `make deps`, `make deps-browser`, `make check`.
Отдельная установка браузера не выполняется: используется браузер, предустановленный в образе
`ubuntu-latest` (это подвижный алиас, набор ПО образа может измениться без коммита). Если на раннере
нет подходящего браузера, шаг `make deps-browser` завершается кодом `2` или `3` с сообщением.
Запасной вариант — шаг `browser-actions/setup-chrome` с передачей пути в `WISHENKA_CHROMIUM_BIN` —
пока не подключён.

## Troubleshooting

### Сообщение «Chromium is required for browser UI tests»

**Симптом:** браузерные тесты завершаются ERROR at setup, `make deps-browser` выходит с кодом `2`.  
**Решение:** выполните `make deps-browser` (на Debian пакет будет установлен). На других системах
установите Chromium или Google Chrome и либо добавьте его в `PATH`, либо задайте путь:

```bash
export WISHENKA_CHROMIUM_BIN=/path/to/chrome
```

### Найдена snap-заглушка (код `3`, подсказка про snap)

**Симптом:** `/usr/bin/chromium` существует, но `--version` завершается ошибкой, а в сообщении есть подсказка про snap.  
**Причина:** на Ubuntu пакет `chromium-browser`, по имеющимся данным (WISHENKA-135), лишь заглушка для snap; при
отсутствии snap она не запускается. Snap Chromium не поддерживается: confinement (приватный `/tmp`)
может скрыть профиль браузера в `tmp_path`.  
**Решение:** установите Chromium из Debian или Google Chrome (`.deb`) и задайте
`WISHENKA_CHROMIUM_BIN`. Если рабочий браузер найден по пути `/snap/...`, фикстура его
использует; предупреждение о confinement есть только в `BrowserCheck.message` и не выводится ни
фикстурой, ни `make deps-browser`. `make deps-browser` на Ubuntu браузер не ставит.

### Зависшая проба

**Симптом:** сообщение `--version did not finish within 10s`.  
**Решение:** проверьте браузер вручную (`<путь> --version`); возможные причины — медленный первый
запуск или повреждённая установка. Задайте другой браузер через `WISHENKA_CHROMIUM_BIN`. Таймаут пробы
не настраивается.

### Явный путь не работает

**Симптом:** `WISHENKA_CHROMIUM_BIN=... is not a usable Chromium/Chrome executable`.  
**Решение:** путь должен вести на исполняемый файл, который отвечает на `--version`. Исправьте путь
или снимите переменную (`unset WISHENKA_CHROMIUM_BIN`), чтобы использовать поиск по `PATH`.

### Нужно пропустить браузерные тесты локально

Выполните `WISHENKA_SKIP_BROWSER_TESTS=1 make test`. В CI это не действует; не используйте опции
отбора вроде `-m "not browser"` (см. выше).

## Browser UI-тесты списка желаний (WISHENKA-110)

Поведенческие тесты `wishlist.js` и карточек желаний: они запускают настоящий headless Chromium,
открывают страницы приложения и проверяют результат в DOM и в запросах к серверу. Они заменили
большую часть слабых строковых проверок скрипта и CSS (что осталось, см. ниже). Playwright не
используется, хотя в заголовке задачи он назван: драйвер собственный (решение и причины в
`ai-tasks/WISHENKA-110/20-architecture.md`, пересмотр: см. «Выбор: CDP вместо Playwright»).

### Что покрыто

Всего 53 теста в трёх модулях (модуль WISHENKA-24 описан ниже); в каждом
`pytestmark = [pytest.mark.timeout(45), pytest.mark.browser]`.

| Модуль | Тестов | Что проверяет |
| --- | --- | --- |
| `tests/test_wishlist_cards_browser.py` | 21 | Раскрытие карточек: клик, Enter и Space (у Space `preventDefault` и нет прокрутки), прочие клавиши не раскрывают, соседние карточки не затрагиваются, вложенные элементы из `TOGGLE_EXCLUSION` не раскрывают, раскрытие работает после замены списка через `htmx.ajax`, страница по общей ссылке (share page), офлайн-гарантия (`test_page_loads_offline_with_real_assets`). |
| `tests/test_wishlist_mouse_reorder_browser.py` | 13 | Нативный HTML5 drag-and-drop мышью: сброс до и после середины цели, один запрос `/items/reorder` с полным порядком, идентификатор списка берётся из `data-wishlist-id`, сброс на себя или вне списка ничего не делает, пропуск отправки с ровно одним `console.warn`, повторная перестановка без перезагрузки, на share page нет ручки и перестановки. |
| `tests/test_wishlist_touch_reorder_browser.py` | 19 | Перестановка касанием за ручку: перетаскивание и обратная связь, отмена (`pointercancel`, `lostpointercapture`, `blur`, `visibilitychange`, замена списка по `htmx:beforeSwap`, Escape), второй палец, вертикальный свайп вне ручки прокручивает страницу, один запрос на жест, следующий тап после окна подавления клика (400 мс) раскрывает карточку, вычисленные стили ручки. |

### Устройство

| Файл | Назначение |
| --- | --- |
| `tests/browser_cdp.py` | Собственный драйвер на `websockets.sync` без потоков: один читатель событий. `CdpBrowser` (запуск Chromium с временным профилем, `new_page(..., use_real_htmx=False)`, `stop`: terminate, `wait(5)`, kill) и `CdpPage` (навигация, `set_bearer`, `set_cookie` через `Network.setCookie`, `evaluate`, `wait_for`, клик, клавиши включая `Tab` и `Shift+Tab`, мышь и нативный drag-and-drop через `Input.setInterceptDrags`, касания с несколькими пальцами, `snapshot`, `screenshot`). Ожидания ограничены по времени; `PageWaitTimeout` наследует `AssertionError`. |
| `tests/browser_helpers.py` | Общие помощники модулей: `Seeded`, селекторы (`card`, `summary`, `title`, `handle`), `assert_order`, `assert_cards`, `assert_clean_console`, `assert_gesture_clean`, `begin_touch_drag`, `wait_suppression_window_over` и др.; для диалога получения (WISHENKA-24) добавлены `record_receipt`, `archive_item_rest`, `open_receipt_dialog`, `posts_to`, `scroll_to`. |
| `tests/browser_assets/htmx_stub.js` | Офлайн-заглушка htmx (собственный код): только `htmx.ajax`; расширена в WISHENKA-24 (раздел «Диалог получения (WISHENKA-24)»). |
| `tests/conftest.py` | Фикстуры (ниже). |

Фикстуры `tests/conftest.py`:

- `chromium_browser` (сессия): один Chromium на весь прогон; путь даёт `chromium_executable`, поэтому
  при отсутствии браузера тесты падают с сообщением WISHENKA-124.
- `migrated_db_template` (сессия): база с применёнными миграциями Alembic создаётся один раз;
  в каждый тест копируется только файл `.db`.
- `wishlist_server` (тест): `uvicorn.Server` в потоке на `127.0.0.1` со случайным портом и своей копией
  базы; передаёт `application_origin=f"http://127.0.0.1:{port}"` в `Settings(...)`, чтобы
  `BrowserSecurityMiddleware` принимал `Origin` локального браузера при cookie-мутациях;
  остановка ограничена по времени (`SERVER_STOP_TIMEOUT`).
- `seed_wishlist(titles, *, quantities=None)`: фабрика, создаёт список и желания через REST (httpx);
  возвращает `Seeded` с идентификаторами и токенами.
- `wishlist_page(seeded, *, as_user="owner" | "viewer", viewport=(412, 800), auth_mode="bearer" | "cookie", use_real_htmx=False)` и
  `share_page(seeded, *, as_user=None | "viewer", viewport=(412, 800))`: фабрики, открывают вкладку
  и страницу; при `auth_mode="cookie"` выставляется `HttpOnly`, `SameSite=Lax` cookie `session_id`
  через `CdpPage.set_cookie(...)` вместо заголовка `Bearer`, а при `use_real_htmx=True` отдаются
  вендорные файлы `htmx@1.9.12` вместо заглушки; касания включаются вызовом `page.enable_touch()`.
- `_browser_pages` (тест): закрывает вкладки; при падении пишет диагностику (см. ниже).

### Запуск

```bash
make deps-browser
.venv/bin/pytest tests/test_wishlist_cards_browser.py \
  tests/test_wishlist_mouse_reorder_browser.py \
  tests/test_wishlist_touch_reorder_browser.py
.venv/bin/pytest -m browser   # все браузерные тесты
```

`make test` и `make check` запускают их вместе с остальными тестами. Три модуля занимают около
35-40 с, в CI это добавляется к шагу `make check`.

### Офлайн-гарантия

Тесты не ходят в сеть. `base.html` подключает три внешних адреса, драйвер перехватывает их через
`Fetch.enable` и отвечает локально: по умолчанию (`use_real_htmx=False`)
`https://unpkg.com/htmx.org@1.9.12` отдаётся заглушкой `htmx_stub.js`, а `.../dist/ext/json-enc.js`
и `https://telegram.org/js/telegram-web-app.js` пустым телом (HTTP 200). При `use_real_htmx=True`
(`_real_htmx_bodies()`) отдаются вендорные файлы `tests/browser_assets/htmx-1.9.12.min.js` и
`tests/browser_assets/htmx-json-enc-1.9.12.js`, а `TELEGRAM_URL` остаётся пустым телом. Любой другой
внешний запрос блокируется (`BlockedByClient`) и попадает в `page.external_requests`;
`test_page_loads_offline_with_real_assets` и `test_real_htmx_move_button_with_cookie_and_csrf`
проверяют, что список пуст. Запросы к `127.0.0.1` и `localhost` проходят и записываются в
`page.requests` со статусом ответа. Адреса продублированы в `tests/browser_cdp.py` (`HTMX_URL`,
`JSON_ENC_URL`, `TELEGRAM_URL`) и должны совпадать с `wishenka/web/templates/base.html`:
синхронность проверяет статический гард `test_browser_cdp_urls_match_base_template()` в
`tests/test_browser_prerequisites.py`. Смена версии htmx требует правки в обоих местах и обновления
вендорных файлов в `tests/browser_assets/`.

### Пределы достоверности

- Заглушка htmx не обрабатывает атрибуты `hx-*`, не вызывает `htmx:configRequest`, делает
  `innerHTML`-замену (значение `swap` записывается в `window.__ajaxCalls`; единственное
  исключение `swap: 'none'`, добавленное в WISHENKA-24; внеполосные элементы применяются
  отдельно). Поэтому 53 теста `WISHENKA-110` и тесты диалога получения, которым нужна замена
  списка, вызывают `window.htmx.ajax(...)` явно, а не нажимают кнопки перемещения. Реальный путь
  `hx-post`, `htmx:configRequest`, cookie-сессии и CSRF-проверки покрыт отдельным дымовым тестом
  `tests/test_wishlist_htmx_smoke_browser.py` (`WISHENKA-145`).
- По умолчанию используется аутентификация через Bearer (`Network.setExtraHTTPHeaders`), а не
  cookie-сессия; проверка cookie + CSRF включается параметром `auth_mode="cookie"` в
  `wishlist_page`.
- Касания синтезируются через `Input.dispatchTouchEvent`; это не настоящий стек касаний устройства.
  Поведение в Telegram WebView, автопрокрутка у краёв и порядок вызовов Telegram SDK не
  проверяются (чек-лист на устройствах: WISHENKA-143). `visibilitychange` и `blur` тесты
  отправляют как синтетические события окна.
- `label` не входит в `TOGGLE_EXCLUSION` (`a, button, input, select, textarea, [data-no-toggle]`);
  `test_nested_controls_do_not_toggle` проверяет реальный набор и `label` не утверждает.
- Константа окна подавления клика `CLICK_SUPPRESS_MS = 400` продублирована в
  `tests/browser_helpers.py`; если окно в `wishlist.js` вырастет, тест следующего тапа упадёт, если
  уменьшится, тест просто будет ждать дольше.

### Диалог получения (WISHENKA-24, WISHENKA-161)

Модуль `tests/test_receipt_modal_browser.py` (`pytestmark = [pytest.mark.timeout(45),
pytest.mark.browser]`, девять тестов B-1 - B-6) проверяет настоящие `receipt.js`, `wishlist.js`,
разметку и CSS страницы; htmx заменён заглушкой. Заглушка не обрабатывает `hx-*`, поэтому тесты
сами вызывают `htmx.ajax` (клик по `hx-get` кнопки карточки покрыт тестами разметки). Тесты:
сводка количества и закрытие без запроса; частичное и полное получение обновляют страницу; второй
тап не шлёт второй запрос; отказ, затем общая фраза об ошибке; `busy` оставляет диалог и
выбранное количество; переопределение `beforeSwap` закрытое (только заголовок
`X-Receipt-Refusal` из закрытого набора); устаревшая карточка дарителя; устаревшая перестановка
(`X-Reorder-Refusal`); ошибка без маркера не даёт уведомления и перезагрузки (ожидание 2 с).
Охранный тест `test_new_browser_modules_declare_marker_and_timeout` проверяет и этот модуль
(по маске `test_*_browser.py`), но множество `NEW_BROWSER_MODULES` по-прежнему содержит только три
модуля WISHENKA-110.

Что добавлено в заглушку (`htmx_stub.js`): `htmx:beforeSwap` получает `detail.xhr` (`status`,
`responseText`, `getResponseHeader`), `shouldSwap` и `isError`, обработчики могут их менять;
непринятый ответ отбрасывается, а при `isError` вызывается `htmx:responseError`; `swap: 'none'`;
внеполосные (`hx-swap-oob`) замены принятого ответа. Расхождения с настоящим htmx 1.9.12, которые
остаются: ворота запроса в тесте второго тапа держат `window.fetch`, а настоящий htmx использует
XHR; проверки `assert_clean_console` упали бы под настоящим htmx, который пишет `console.error`
на каждый непринятый 4xx; заглушка не принимает ничего со статусом от 400, поэтому слова её
заголовка «all additive» не вполне верны; `hx-get` кнопки, классы `htmx-request` и заголовок CSRF
не проверяются. Закрывают WISHENKA-145 и WISHENKA-162.

Серверные тесты слоя страниц (без браузера): `tests/test_receipt_ui_routes.py`,
`test_receipt_card_ui.py`, `test_gifted_section_ui.py`, `test_cabinet_received_marker.py`,
`test_receipt_static_script.py`, `test_receipt_ui_observability.py`,
`test_receipt_undo_correction_repro.py`, `test_receipt_undo_correction_edge_cases.py`, помощник
`tests/receipt_ui_support.py`; описание: `doc/dev/gift-receipt.md`, раздел «Mini App UI
(WISHENKA-24)». Отсутствие встроенных `<script>` и `on*`-атрибутов в страницах и фрагментах
(`base.html`, модалки и preview), а также раздача `/static/app.js` и `/static/settings.js` и
порядок `defer`-скриптов проверяются тестами `tests/test_csp_inline_removal_repro.py` и
`tests/test_receipt_static_script.py` (WISHENKA-140).

Модуль `tests/test_receipt_accessibility_browser.py` (`pytestmark = [pytest.mark.timeout(45),
pytest.mark.browser]`, 5 тестов, мобильный viewport `390x844`) проверяет доработки
`WISHENKA-161` с использованием `Tab`/`Shift+Tab` в `tests/browser_cdp.py`:

1. `test_modal_semantics_background_isolation_and_tab_trap`: `aria-modal="true"`, `inert` и
   `aria-hidden="true"` на фоновых элементах (`#items-list`, `#quick-add-bar`, `nav.top-nav`),
   замыкание `Tab` / `Shift+Tab` внутри `#item-receipt-modal`.
2. `test_focus_return_partial_full_and_refusal`: возврат фокуса на `.item-card-summary` после
   частичного получения, на `#list-notice` после полного получения и удержание на
   `#receipt-feedback` при отказе (`InventoryBusyError` 503).
3. `test_gifted_section_open_state_preserved`: сохранение `details.gifted-items-details.open`
   после out-of-band обновления `#gifted-items-section`.
4. `test_large_quantity_stepper_updates_summary_and_submits`: при `remaining = 500` рендерится
   `.quantity-control` (`input[type="number"]` + `[data-receipt-step]`) вместо `<select>`,
   кнопка `+` обновляет сводку и отправляет выбранное количество.
5. `test_mobile_touch_targets_and_quick_add_overlay`: размеры интерактивных элементов диалога не
   менее `44x44` px и `document.elementFromPoint` попадает в кнопки диалога поверх `#quick-add-bar`.

### Дымовой тест с настоящим htmx и cookie/CSRF (WISHENKA-145)

Модуль `tests/test_wishlist_htmx_smoke_browser.py` (`pytestmark = [pytest.mark.timeout(45),
pytest.mark.browser]`) содержит офлайн smoke-тест `test_real_htmx_move_button_with_cookie_and_csrf`,
который проверяет реальную связку декларативного `hx-post`, вендорного `htmx.org@1.9.12` +
`json-enc`, cookie-сессии и `BrowserSecurityMiddleware` без обращения в сеть:

- **Инициализация страницы (`tests/conftest.py` и `tests/browser_cdp.py`):**
  `wishlist_page(seeded, auth_mode="cookie", use_real_htmx=True)` открывает вкладку через
  `CdpBrowser.new_page(viewport, use_real_htmx=True)`, выставляет `HttpOnly` / `SameSite=Lax`
  cookie `session_id` через `CdpPage.set_cookie("session_id", token, url)` (`Network.setCookie`)
  вместо `Authorization: Bearer`, а локальный сервер `wishlist_server` настроен с
  `application_origin=f"http://127.0.0.1:{port}"`, чтобы `BrowserSecurityMiddleware` принимал
  заголовок `Origin` от Chromium.
- **Офлайн-подмена реальных ассетов:** при `use_real_htmx=True` перехват `Fetch.enable` отдаёт
  `_real_htmx_bodies()` — `tests/browser_assets/htmx-1.9.12.min.js` и
  `tests/browser_assets/htmx-json-enc-1.9.12.js` (и пустое тело для `TELEGRAM_URL`), проверяя
  `window.htmx.version == "1.9.12"` и `page.external_requests == []`.
- **Синхронность URL:** `tests/test_browser_prerequisites.py::test_browser_cdp_urls_match_base_template`
  сверяет внешние `<script src="https://...">` из `wishenka/web/templates/base.html` с
  `HTMX_URL`, `JSON_ENC_URL` и `TELEGRAM_URL` в `tests/browser_cdp.py`.
- **Сценарий теста:** дожидается `GET /api/auth/csrf` (статус `200`, `window.csrfToken`), раскрывает
  первую карточку и нажимает реальную кнопку `.btn-move-down` (`hx-post=".../move?direction=down"`),
  подтверждает отправку `X-CSRF-Token` через `htmx:configRequest`, обновление `#items-list` в DOM,
  статус `200` для `POST .../move`, сохранение порядка после перезагрузки страницы и чистую консоль
  (`assert_clean_console`).

Запуск отдельно и вместе с гардом URL:

```bash
make test-serial PYTEST_ARGS="tests/test_wishlist_htmx_smoke_browser.py tests/test_browser_prerequisites.py"
```

### E2E-тесты переходов из меню бота в Mini App (WISHENKA-177)

Модуль `tests/test_bot_menu_miniapp_e2e_browser.py` (`pytestmark = [pytest.mark.timeout(45),
pytest.mark.browser]`, 12 параметризованных тестов) проверяет границу между главным меню Telegram-бота
и экраном Mini App в headless Chromium (`tests/browser_cdp.py`):

- **Переходы `create`, `collection`, `home` (`en` и `ru`, 6 тестов):** диспетчеризует `/start` через
  `wishenka.bot.entry.create_router`, извлекает `WebAppInfo` query-параметры `startapp` и открывает
  страницу Mini App с cookie-сессией `session_id`; проверяет локализованный заголовок домашнего
  экрана, отображение существующего списка, фокус на кнопке создания вишлиста для `create` и
  отсутствие неявного создания вишлистов.
- **Восстановление при невалидном `startapp` (`en` и `ru`, 6 тестов):** для значений
  `unknown_action`, `bad!param` и `x_not_a_token` проверяет отображение локализованного экрана
  недоступности без утечки названий вишлиста и подарков, переход на главный экран по кнопке возврата
  и неизменность числа вишлистов.

Запуск модуля:

```bash
make test-serial PYTEST_ARGS="tests/test_bot_menu_miniapp_e2e_browser.py"
```

### Тесты единого визуального стиля (WISHENKA-288)

Модуль `tests/test_visual_identity_browser.py` (`pytestmark = [pytest.mark.timeout(45),
pytest.mark.browser]`, 5 тестов, мобильный viewport `412x800`) проверяет общую визуальную
идентичность и контраст в `wishenka/web/static/miniapp.css`, `wishenka/web/static/miniapp.js` и
серверных шаблонах (описание токенов и классов:
[miniapp.md](miniapp.md#shared-visual-identity-and-palette-tokens)):

- **`test_both_shells_use_coherent_light_canvas_and_surfaces`:** проверяет на `/`
  (`.wishlist-section`) и `/settings` (`#language-heading`) непрозрачный светлый фон
  (`min(rgb) >= 225`), отличие поверхности `section` от фона и согласованность каналов (`<= 16`).
- **`test_home_primary_action_is_visually_distinct_from_history`:** проверяет визуальное отличие
  основного действия создания вишлиста (`.btn-primary`) от кнопки истории в `.top-nav` на `/`.
- **`test_settings_actions_and_selection_have_distinct_visual_states`:** проверяет на `/settings`
  визуальное отличие кнопки сохранения (`.btn-primary`) и удаления аккаунта (`.btn-danger`) от
  кнопки очистки, отличие `.locale-option[aria-pressed="true"]` от `false`, изменение стиля
  `#birthdate-clear-btn` при `disabled = true` и видимый контур `:focus-visible` после `Tab`.
- **`test_dark_theme_modal_heading_and_focus_outline_contrast`:** проверяет при fallback
  (`None`, `None`) и тёмных `--tg-theme-bg-color: #202020` / `--tg-theme-text-color: #f5f5f5`
  контраст `>= 4.5` для `h2` и `:focus-visible` контура внутри `#item-archive-modal .modal-sheet`
  и `#item-receipt-modal .receipt-sheet`.
- **`test_invite_preview_primary_link_has_button_geometry_and_touch_target`:** проверяет, что на
  `/invite/nonexistent-invite-token` ссылка `a.btn.btn-primary` имеет геометрию кнопки
  (`>= 44x44` px, `inline-flex`, `border-box`, без подчёркивания, `fontWeight >= 600`, контраст
  `>= 4.5`) и видимый `:focus-visible` контур после `Tab`.

Интеграция с браузерным набором: модуль использует общие `tests/browser_cdp.py`,
`tests/browser_helpers.py` (`Seeded`, `focus`, `js_str`, `open_receipt_dialog`, `settle`) и
фикстуры `tests/conftest.py`, работает полностью офлайн, проходит AST-проверку маркера и
таймаута `tests/test_browser_prerequisites.py::test_new_browser_modules_declare_marker_and_timeout`
и дополняет `tests/test_receipt_theme_browser.py` и `tests/test_receipt_accessibility_browser.py`.

Запуск модуля:

```bash
make test-serial PYTEST_ARGS="tests/test_visual_identity_browser.py"
```

### Тесты обзора и навигации домашнего экрана Mini App (WISHENKA-289)

Два модуля проверяют структуру домашнего экрана `#app`, дедупликацию секций по приоритету ролей
`owner > admin > member > favorite`, карточку `.reservations-card`, иерархию действий карточек
(`.wishlist-card-open` и `.wishlist-card-remove`), двухчастные пустые состояния `.empty-state`,
условную секцию `.deleted-section.wishlist-section--deleted` и мобильную геометрию в `en` и `ru`
(описание архитектуры и ключей:
[miniapp.md](miniapp.md#6-categorized-home-screen-overview-navigation--card-anatomy-wishenka-289)):

- **`tests/test_home_overview_ui.py`** (`pytestmark = pytest.mark.timeout(20)`, 13 тест-кейсов в
  7 тестовых функциях: 1 непараметризованная и 6 с `@pytest.mark.parametrize("locale", ["en",
  "ru"])`, изолированный Node VM harness с `timeout=10`):
  1. `test_home_overview_i18n_keys_and_bilingual_parity` (1 кейс): проверяет наличие и двуязычную
     симметрию всех 13 новых ключей `miniapp.home.*` и сохранённых ключей в `CATALOG`,
     `miniapp_catalog()` и встроенном `<script id="miniapp-i18n">`, совпадение плейсхолдеров и
     префиксы `aria-label` по WCAG 2.5.3 Label in Name.
  2. `test_home_section_grouping_and_role_precedence_deduplication` (`en`, `ru` — 2 кейса):
     проверяет заголовок `#app h1`, `.home-lead`, `.top-nav.home-top-nav` (2 `<button>` и
     `a.settings-link[href="/settings"]`), 3 прямых `.wishlist-section` (`--owned`, `--collab`,
     `--favorites`), заголовки `.wishlist-section-header` с `.section-count`, `.section-subtitle`
     и отсутствие дублирования списков соавтора/администратора в секции **Favorites**.
  3. `test_home_cards_scannability_action_hierarchy_and_favorites_removal` (`en`, `ru` — 2 кейса):
     проверяет `<h3 class="wishlist-card-title">` (включая fallback без названия),
     `.wishlist-card-meta` (`event_title` и `formatDate(event_date)`), `.wishlist-card-open` и
     подчинённую кнопку `.wishlist-card-remove` (без `.btn-primary` и `.btn-danger`), переход по
     `Open` (`GET /api/wishlists/42`) и удаление закладки (`DELETE /api/favorites/42`).
  4. `test_home_empty_states_two_part_guidance_and_hidden_deleted_section` (`en`, `ru` — 2 кейса):
     проверяет рендеринг `.empty-state` (`.empty-notice` + `.empty-hint`) при `0` элементов в трёх
     основных секциях и скрытие `.deleted-section`, когда список удалённых пуст.
  5. `test_home_recently_deleted_section_restore_and_error_states` (`en`, `ru` — 2 кейса):
     проверяет условную секцию `.deleted-section.wishlist-section--deleted`, карточку
     `.deleted-wishlist-card` и сценарии `POST /api/wishlists/77/restore-deleted` со статусами
     `200`, `410` (`miniapp.deleted.expired`) и `500` (`miniapp.deleted.restore_failed` с
     повторным включением кнопки).
  6. `test_home_reservations_card_rendering_and_non_blocking_fallback` (`en`, `ru` — 2 кейса):
     проверяет вставку `a.reservations-card` (`.reservations-card-main`, `.reservations-title`,
     `.reservations-card-hint`, `.reservations-badge`) перед первой `.wishlist-section` и
     неблокирующий fallback при HTTP 500 от `/web/reservations/card`.
  7. `test_home_navigation_startapp_create_focus_and_preserved_script_contracts` (`en`, `ru` —
     2 кейса): проверяет контракт `test_reservations_cabinet_ui.home_script_problems(js_source)`,
     фокус на кнопке создания при `startapp=create` без `POST /api/wishlists`, что клик на создание
     открывает форму (`form`) и не отправляет `POST /api/wishlists` (WISHENKA-296: раньше уходил
     `{}`; заглушка теперь возвращает имя из тела запроса), и переход в `showHistory()` (`GET
     /api/history`).
- **`tests/test_home_overview_browser.py`** (`pytestmark = [pytest.mark.timeout(45),
  pytest.mark.browser]`, 6 тест-кейсов в 3 тестовых функциях в настоящем headless Chromium через
  `tests/browser_cdp.py`):
  1. `test_home_overview_sections_dedup_cards_nav_and_mobile_geometry` (`("en", (412, 800))`,
     `("ru", (412, 800))`, `("ru", (360, 800))` — 3 кейса): проверяет отсутствие горизонтального
     скролла (`scrollWidth <= innerWidth`), 2 кнопки в `.top-nav.home-top-nav` с кнопкой создания
     на верхнем ряду, `a.reservations-card` со счётчиком `1` перед первой секцией, различные левые
     границы секций, дедупликацию списков соавтора/администратора из **Favorites**, отсутствие
     перекрытий и обрезки длинных заголовков, интерактивные цели `>= 44x44` px, контур
     `:focus-visible` после `Tab` и соблюдение Surprise Invariant.
  2. `test_home_overview_empty_states_deleted_restore_and_single_step_navigation` (`"en"`, `"ru"`
     на `412x800` — 2 кейса): проверяет спокойные светлые `.empty-state` (`min(rgb) >= 240`, без
     `.alert-error`), одношаговую навигацию в историю просмотров, `/settings` и
     `/web/reservations`, фокус при `startapp=create` без создания вишлиста, а также условную
     секцию `.deleted-section.wishlist-section--deleted` с восстановлением списка при HTTP 500 от
     `/web/reservations/card`.
  3. `test_home_overview_favorites_remove_and_open_wishlist_browser` (`"en"` на `412x800` —
     1 кейс): проверяет, что клик по `.wishlist-card-remove` убирает вишлист только из
     **Favorites** без удаления самого списка у владельца, а клик по `.wishlist-card-open`
     открывает детальный экран вишлиста.

Запуск модулей:

```bash
make test-serial PYTEST_ARGS="tests/test_home_overview_ui.py tests/test_home_overview_browser.py"
```

### Тесты экрана личных настроек (WISHENKA-291)

Архитектура, id и селекторы экрана:
[miniapp.md](miniapp.md#personal-settings-screen-wishenka-291).

- **`tests/test_personal_settings_browser.py`** (настоящий Chromium через `tests/browser_cdp.py`,
  изолированные пользователи, принудительные HTTP-ошибки, обрывы сети и задержки ответов):
  видимые состояния on/off и бейджи inherited/override, pending, saved, error и unknown,
  сверка чтением после `5xx` и кнопка Retry, откат только после `401/403/404/422`, сериализация
  по категориям, черновик даты рождения, смена языка, предпросмотр и подтверждение удаления без
  повторов, мобильная геометрия 320/375 px и цели не менее 44 px. Внешний вид переключателей
  (роль `switch`, дорожка и бегунок, состояния pending/unknown/disabled) проверяет отдельный
  модуль WISHENKA-307, см. ниже; общие помощники (`_api`, `_click`, `_intercept`, `_open`) он
  импортирует отсюда, поэтому правка их сигнатур ломает оба модуля.
- **`tests/test_personal_settings_observability.py`** (`caplog`, таймаут 30 с): события успеха
  вызываются один раз на мутацию, отклонённые запросы дают WARNING без события успеха, в логах нет
  дат рождения, названий списков и токенов.

```bash
make test PYTEST_JOBS=2 PYTEST_ARGS='tests/test_personal_settings_browser.py -q'
make test PYTEST_JOBS=2 PYTEST_ARGS='tests/test_personal_settings_observability.py -q'
```

### Тесты переключателей экрана настроек (WISHENKA-307)

Разметка, состояния и CSS: [miniapp.md](miniapp.md#settings-switches-wishenka-307).

**`tests/test_settings_switch_browser.py`** (33 теста, настоящий Chromium через
`tests/browser_cdp.py`, `pytestmark` с таймаутом 45 с и маркером `browser`). Проверки R1-R10 по
пяти переключателям `input[data-global-category]`. Параметризация: R1, R2, R5, R7 идут по
`CASES` (en и ru на 320 и 375 px); R3 и R4 только по `STATE_CASES` (en 375, ru 320); R6 по
локали (en, ru); R8 и R10 в одной конфигурации (en 375; R8 pending ещё по начальному значению
вкл/выкл); R9 на 320, 360 и 375 px:

- R1 роль `switch`; R2 `appearance: none`; R3 геометрия дорожки (`::before`) и бегунка
  (`::after`); R4 состояние по положению и цвету бегунка, контраст рамки не ниже 3:1;
- R5 цель не менее 44 px, клик по подписи переключает; R6 кольцо фокуса и Space;
- R7 дерево доступности: переключатель объявляется один раз, имя равно подписи, `checked`
  совпадает с `input.checked`, `.toggle-state` скрыт через `aria-hidden`;
- R8 pending, unknown и обычный disabled различимы по рамке, глифу, курсору и `opacity`;
- R9 нет горизонтального переполнения при длинной русской подписи;
- R10 переход объявлен только при `no-preference`, при `reduce` он равен `0s`, при
  `forced-colors: active` используются системные цвета.

Правила измерений:

- Перед чтением геометрии и цветов псевдоэлементов включается эмуляция
  `prefers-reduced-motion: reduce` (`Emulation.setEmulatedMedia` через `CdpPage._send`, helper
  `_emulate`), иначе переход .15 с оставляет бегунок на полпути. Исключение: проверка объявления
  перехода под `no-preference`.
- Дерево доступности читается через `Accessibility.getFullAXTree` (`CdpPage._send`); учитываются
  узлы `switch` без `ignored`.
- `forced-colors` тоже включается эмуляцией; ожидаемые цвета берутся из проб-элементов с
  `Highlight`, `ButtonText` и `Canvas`, токены (`--accent`, `--danger`, ...) читаются через
  пробу `var(--name)`, а не литералами.

Состояния достигаются так: pending держит ответ `PUT /api/profile/notifications/global`
переопределением `window.fetch` (`_PENDING_OVERRIDE`, копия приёма из
`test_personal_settings_browser.py`; перед завершением теста обязателен
`window.releaseGlobal()`); unknown создаёт `_intercept(..., "commit", fail_read=True)` и клик,
после чего тест ждёт `data-unknown="1"`, снятый `aria-busy`, `disabled` и скрытое сообщение
pending; обычный disabled задаётся через `el.disabled = true`.

```bash
make test PYTEST_JOBS=2 PYTEST_ARGS='tests/test_settings_switch_browser.py -q'
```

Пределы: проверено только в Chromium
([WISHENKA-313](https://pypost.atlassian.net/browse/WISHENKA-313): iOS Safari, Firefox,
речевое управление); `forced-colors` для отмеченного pending/unknown и
перенос подписи на 320 px в `ru`
([WISHENKA-314](https://pypost.atlassian.net/browse/WISHENKA-314)); общие помощники вместо
приватного импорта ([WISHENKA-315](https://pypost.atlassian.net/browse/WISHENKA-315)).

### Тесты удаления вишлиста владельцем (WISHENKA-295)

Контракт и экран: [wishlists.md](wishlists.md#owner-delete-route-delete-apiwishlistsid),
[miniapp.md](miniapp.md#wishlist-delete-zone-wishenka-295). Всего 117 тестов в четырёх модулях
(сбор `.venv/bin/pytest --collect-only -q -n 0`).

| Модуль | Тесты | Таймаут / маркер | Что проверяет |
| --- | --- | --- | --- |
| `tests/test_wishlist_delete_api.py` | 31 | `timeout(30)` | маршрут `DELETE /api/wishlists/{id}`: коды и тело, идемпотентность без сдвига окна, 410 после окна, 409 архивного, одинаковый 404 для не владельца и неизвестного id, CSRF/Origin, `data-retention-days`, ключи каталога и ограничения текстов |
| `tests/test_wishlist_delete_ui.py` | 57 | `timeout(20)` | реальный `showList` в Node-стенде (`_NODE_HARNESS` из `tests/test_miniapp_i18n_repro.py`, патчится заменой строк): зона, права, подтверждение, повтор, сбой, 410 с возвратом на главный экран, фокусом на его заголовке и объявлением той же ошибки, доступное имя Cancel, Escape |
| `tests/test_wishlist_delete_browser.py` | 21 | `timeout(45)`, `browser` | настоящий Chromium: геометрия на узких экранах, фокус, один запрос, восстановление из «Недавно удалённых», возврат при 410 (фокус на заголовке главного экрана и то же сообщение об ошибке), разные доступные имена Cancel удаления и настроек, одинаковые тексты |
| `tests/test_wishlist_delete_observability.py` | 8 | `timeout(30)` | события и уровни по каждому пути, отсутствие названий, токенов и данных дарителя в логах |

- Браузерный модуль подпадает под охранный тест маркеров (см. «Таймауты и маркеры»).
- Chromium нужен только модулю `browser`; остальные три модуля его не требуют (UI-модуль требует
  `node`).
- Запуск: `make test PYTEST_JOBS=2 PYTEST_ARGS='tests/test_wishlist_delete_api.py -q'`.
  Набор сужает только `PYTEST_ARGS` (в `Makefile` нет переменной `ARGS`); для `make test-serial`
  тоже `PYTEST_ARGS="tests/x.py::t"`. `make test-serial ARGS=...` ничего не сужает и запустит
  весь набор; полный набор долгий, `make test` останавливается по `TEST_WALL_LIMIT` (`Makefile:10`, 600 с).
- Известные ограничения: тесты используют приватные помощники (`_NODE_HARNESS`, `page._send`,
  `service._reservations`) (WISHENKA-319); только Chromium, без речевого движка
  (WISHENKA-313). Фокус и объявление после 410, и отдельное доступное имя Cancel, проверяют
  интерфейсный и браузерный модули на русском и английском.
- Заведомо падающие тесты вне задачи: `tests/test_receipt_modal_browser.py`
  (`test_stale_giver_card_is_neutral`, WISHENKA-265;
  `test_unmarked_error_neither_shows_notice_nor_reloads`, WISHENKA-220) и остальной список в
  `ai-tasks/WISHENKA-292/60-tech-debt.md`.

### Тесты формы создания вишлиста (WISHENKA-296)

Контракт и экран: [wishlists.md](wishlists.md) (`POST /api/wishlists`),
[miniapp.md](miniapp.md#wishlist-creation-form-wishenka-296). Всего 105 тестов в четырёх модулях
(счёт по `.venv/bin/pytest --collect-only -q -n 0`).

| Модуль | Тесты | Таймаут / маркер | Что проверяет |
| --- | --- | --- | --- |
| `tests/test_wishlist_create_validation_api.py` | 25 | `timeout(30)` | `POST /api/wishlists`: обязательное имя, обрезка пробелов, 1-255 кодовых точек, форма `422`, необязательные поля, неразбираемая дата, `401` и CSRF без создания, `PATCH` отказывает в пустом и слишком длинном имени и позволяет опустить уже годное сохранённое имя, одиночный сигнал `wishlist_mutation_committed`, отсутствие текста пользователя в логах |
| `tests/test_wishlist_create_form_ui.py` | 27 | `timeout(20)` | реальный `showCreate` в Node-стенде (`_NODE_HARNESS`): поля и подписи, отмена, ошибки без запроса, один обрезанный `POST`, дата как UTC, сбой, ключи каталога (восемь `miniapp.create.*`) |
| `tests/test_wishlist_create_form_browser.py` | 42 | `timeout(45)`, `browser` | настоящий Chromium: открытие формы без запроса, уход (перезагрузка, навигация, Назад) ничего не создаёт, ошибки в полях, `422` по полю и неизвестному `loc`, серия нажатий и Enter дают один `POST`, сбой и повтор, сбой загрузки списка после создания, медленная загрузка главного экрана и защита `homeRenderToken`, deep link, геометрия на узких экранах, фокус, дерево доступности, порядок Tab |
| `tests/test_wishlist_create_observability.py` | 11 | `timeout(30)` | события по каждому пути (201, 422, 401, 403, 500) и отсутствие названий и токенов в логах |

- Браузерный модуль подпадает под охранный тест маркеров (см. «Таймауты и маркеры»).
- Исправлены на шаге 4 три новых теста (заведомо неверные ожидания, смысл сохранён): в UI-модуле
  после успеха исчезает только `wishlist-create-form` (на экране владельца есть своя форма
  настроек); в браузерном модуле для `back` не ждём главный экран (`history.back()` не меняет
  экран, запись в историю не добавляется); в проверке порядка Tab подряд идущие остановки одного
  `datetime-local` схлопываются.
- Обновлены существующие тесты: `test_home_overview_ui.py` (клик на создание открывает форму,
  без `POST`), `test_home_overview_browser.py` (уже сохранённое пустое имя записывается
  в базу, а не очисткой через `PATCH`; открытие не переименовывает список),
  `test_cross_screen_comfort_browser.py` (серия нажатий и сбой идут через кнопку
  «Создать» формы), `test_wishlist_api.py` и `test_wishlist_management_ui.py` (создание с именем;
  принудительная `500` сохранена).
- Запуск: `make test PYTEST_JOBS=2 PYTEST_ARGS='tests/test_wishlist_create_validation_api.py -q'`.
  Набор сужает только `PYTEST_ARGS`; `make test-serial ARGS=...` ничего не сужает.
- Известные ограничения: приватный вызов `page._send("Accessibility.getFullAXTree")`
  ([WISHENKA-319](https://pypost.atlassian.net/browse/WISHENKA-319)); только Chromium
  ([WISHENKA-313](https://pypost.atlassian.net/browse/WISHENKA-313)); дублирующиеся помощники
  каталога и слабое ожидание в `tests/test_history_screen_browser.py` (500), из-за которого
  `api()` разбирает тело только для `422`
  ([WISHENKA-321](https://pypost.atlassian.net/browse/WISHENKA-321));
  идемпотентность ([WISHENKA-322](https://pypost.atlassian.net/browse/WISHENKA-322)).
- Тесты с `caplog` падают при запуске с `-p no:logging`; настроенные запуски плагин не отключают.
- Заведомо падающие тесты вне задачи: те же, что в разделе WISHENKA-295.

### Тесты контракта имени вишлиста (WISHENKA-320)

Создание и правка делят одно правило имени. Описание и название события без нового
потолка длины; пустое или из одних пробелов значит «не задано».

- `tests/test_wishlist_name_contract_api.py` (`timeout(30)`): на `POST` и `PATCH`
  отсутствующее, пустое или составленное только из невидимых знаков имя —
  `wishlist_name_required`, а имя длиннее 255 кодовых точек —
  `wishlist_name_too_long`. Уже сохранённое пустое имя остаётся
  читаемым, и следующее сохранение обязано прислать настоящее имя. Опущенное
  сохранённое имя, которое уже длиннее 255, — отказ «слишком длинное», а не «имя
  обязательно». Такое имя сеется через домен, не через `PATCH`.
- `tests/test_wishlist_settings_name_contract_ui.py` (`timeout(20)`) и
  `tests/test_wishlist_settings_name_contract_browser.py` (`timeout(45)`, `browser`):
  форма настроек на английском и русском. Негодное имя не сохраняется. Принятое имя
  в теле — одна нормализованная строка, и крайний U+FEFF рядом с видимым знаком в ней
  остаётся. У описания и названия события нет `maxlength`. Пустое сохранённое имя
  по-прежнему показывает подпись без названия.
- Модули формы создания (`test_wishlist_create_form_ui.py`,
  `test_wishlist_create_form_browser.py`) покрывают те же три случая на создании,
  включая крайний U+FEFF в теле `POST` без второго `trim`.

Полный набор для этой заметки не запускался.

### Тесты экрана истории просмотров (WISHENKA-292)

Архитектура, состояния и селекторы:
[miniapp.md](miniapp.md#8-viewing-history--automated-tracking).

- **`tests/test_history_screen_browser.py`** (32 теста, настоящий Chromium через CDP, реальный
  сервер; подмена `fetch` на странице для отказов, задержек и фиксированных времён): карточки
  и порядок, открытие записи, относительное и абсолютное время по локали, двухшаговое
  подтверждение очистки (Cancel, Escape и фокус, ровно один `DELETE`, состояние clearing,
  отказ и повтор), пустое состояние, ошибка загрузки и Retry, `aria-busy`, 320 px без
  переполнения, клавиатура и заголовки; 5 контрольных тестов `test_control_*` (лимит 20,
  удалённый список, область очистки, приватность).
- **`tests/test_wishlist_sections_observability.py`** (`caplog`): жизненный цикл истории
  проверяет ровно одно событие `view_history_cleared` с `removed_count`.

```bash
make test PYTEST_JOBS=2 PYTEST_ARGS='tests/test_history_screen_browser.py -q'
make test PYTEST_JOBS=2 PYTEST_ARGS='tests/test_wishlist_sections_observability.py -q'
```

### Сквозные тесты комфорта и надёжности экранов (WISHENKA-294)

Архитектура слоя и поведение страницы недоступности:
[miniapp.md](miniapp.md#cross-screen-comfort-and-reliability-layer-wishenka-294).

- **`tests/test_cross_screen_comfort_browser.py`** (48 тестов, `timeout(45)`, `browser`; ширины 320,
  360, 375, 390 и 412 px, RU и EN; один сервер и одна страница на тест, ширину меняет
  `CdpPage.set_viewport`; хуки перечислены в докстринге модуля). Утверждения:
  - **A1/A2** нет горизонтальной прокрутки, длинные значения видны целиком (детальная и публичная
    страницы, диалоги);
  - **A3** главные действия достижимы, последний блок выше панели быстрого добавления;
  - **A4** все кнопки, ссылки, поля и `summary` не меньше 44 px;
  - **A5** `#quick-add-input` не уже 10rem;
  - **A6** `#status` виден, имеет `data-kind` и `aria-live`; один `POST` за серию нажатий на
    создание; защита избранного и сброса публичной ссылки; ошибка создания слышна как `error`;
  - **A7** страницы недоступности: `text/html`, код 404/401, `lang`, заголовок, ссылка на `/`,
    одинаковый ответ для отсутствующего и удалённого списка; JSON остаётся JSON для `*/*`,
    JSON, htmx и `/api`;
  - **A8** контраст и фокус на всех экранах; **A9** корневой шрифт относительный и не меняется
    по умолчанию; **A10** htmx: `aria-busy` и блокировка отправки, `#feedback` при сетевой ошибке.
  - Контрольные `test_control_*` (параметризованы) зелёные и на исходном коде: на нём были
    зелёными 16 из 48 тестов, красными 32 (дефекты D1-D9 из `20-architecture.md`).
- **`tests/browser_screens.py`**: общие помощники нескольких экранов: `provision_user`,
  `open_miniapp`, `telegram_init_data` (перенесены из `test_home_overview_browser.py`, старые
  имена там остались псевдонимами), `GEOMETRY_JS`/`CONTRAST_JS` и `assert_*` (проверки по
  странице), `seed_comfort_wishlist`, `open_path`, фикстура `configured_server` (сервер с
  именем бота, чтобы панели шеринга показывали ссылку и кнопку копирования).
- **`CdpPage.set_viewport(width, height)`** меняет эмулируемую ширину открытой вкладки;
  **`CdpPage.clear_cookies()`** (вызывается из `open_path`) очищает cookie общего профиля Chromium:
  cookie не различают порты, поэтому сессия предыдущего сервера делала анонимные случаи
  авторизованными.
- **`tests/test_unavailable_page_observability.py`** (`caplog`, 2 теста): один INFO-ивент
  `unavailable_page_rendered` на HTML-ответ с ожидаемыми `route_kind` и `status_code`, без токена
  и идентификатора в JSON-строке; JSON, `*/*`, htmx и `/api` событий не создают. Значение `locale`
  пока не проверяется (WISHENKA-308).

```bash
make test-serial PYTEST_ARGS="tests/test_cross_screen_comfort_browser.py -q"
make test-serial PYTEST_ARGS="tests/test_unavailable_page_observability.py -q"
```

Правила запуска:

- Тяжёлые браузерные наборы параллельно запускайте осторожно: под нагрузкой воркеров растут
  таймауты, а не число ошибок поведения. Эталонный прогон: `make test-serial PYTEST_ARGS="<файлы>
  -q"`. Переменная `TESTS=` игнорируется, файлы передаёт только `PYTEST_ARGS`.
- Известные тесты, чувствительные к нагрузке (падают только параллельно, поодиночке и
  последовательно проходят): `test_cross_screen_comfort_browser.py::
  test_htmx_pending_request_marks_the_form_busy` (ожидание `WAIT = 3.0` с) и
  `test_history_screen_browser.py::
  test_control_opening_an_entry_moves_it_to_the_top_and_navigation_works`. Стабилизация:
  [WISHENKA-311](https://pypost.atlassian.net/browse/WISHENKA-311).
- Ограничения набора: контрольный тест D4 пропускает неточно подобранные «подозреваемые»
  селекторы (`D4_SUSPECTS`, WISHENKA-308); защита кнопки создания и утверждение A6 после
  WISHENKA-296 относятся к кнопке «Создать» формы (тесты в
  `tests/test_wishlist_create_form_browser.py` и `test_create_wishlist_burst_sends_a_single_post`);
  остаток (повтор после потерянного ответа) в
  [WISHENKA-312](https://pypost.atlassian.net/browse/WISHENKA-312) и
  [WISHENKA-322](https://pypost.atlassian.net/browse/WISHENKA-322); устойчивость `:has()` и
  скрытого `#feedback`: [WISHENKA-309](https://pypost.atlassian.net/browse/WISHENKA-309);
  дублирование логики pending: [WISHENKA-310](https://pypost.atlassian.net/browse/WISHENKA-310).

### Изолированная диагностика поддержки и единый principal приватного бота (WISHENKA-182)

Модуль `tests/test_wishenka_182_repro.py` (`pytestmark = pytest.mark.timeout(30)`, 4 теста: 3 async, 1 sync)
проверяет устранение полнотабличного сканирования токенов в поддержке, чтение без `BEGIN IMMEDIATE`
и унификацию инициализации пользователя приватного бота:

- **`test_support_diagnostic_context_avoids_full_table_scans_and_write_tx`:** проверяет через
  SQLAlchemy `before_cursor_execute`, что `collect_diagnostic_context` и проверка rate-limit при
  отправке `/support ...` выполняются через `WishlistStore.execute_read` (отложенный `BEGIN`,
  без `BEGIN IMMEDIATE`), не сканируют чужие токены в `wl_lists` / `wl_tokens` / `wl_invite_tokens`
  и при этом редактируют собственные capability-токены пользователя и любые regex-совпадения чужих
  токенов (`[REDACTED]`).
- **`test_principal_helper_exists_and_routers_delegate_without_duplication`:** проверяет наличие
  `wishenka.bot.principal.ensure_private_bot_user` и делегирование инициализации из `entry.py`,
  `support.py`, `birthdays.py` и `capture.py` без дублирующего вызова `upsert_from_bot`.
- **`test_all_private_routers_preserve_stored_language_and_activate_destination`:** проверяет, что
  обработчики `entry.py`, `support.py`, `birthdays.py` и `capture.py` через единый helper
  `wishenka.bot.principal.ensure_private_bot_user` сохраняют уже заданный в `users.language_code`
  язык пользователя и активируют `bot_destinations`.
- **`test_ensure_private_bot_user_suppresses_user_identifier_logs`:** проверяет подавление
  логирования `user_created` / `user_updated` с Telegram ID и именем профиля через фильтр
  `_private_bot_user` при создании пользователя в `ensure_private_bot_user`.

Запуск модуля:

```bash
.venv/bin/pytest tests/test_wishenka_182_repro.py -v
```

### Диагностика при падении

- В отчёт pytest падающего теста добавляется секция `Page N diagnostics` со снимком
  `CdpPage.snapshot()`: адрес, `scrollY`, порядок и состояние карточек, классы, вызовы `ajax`,
  последние 20 записей консоли и запросов, внешние запросы, ошибки драйвера.
- В `tmp_path` теста записываются `diagnostics-N.txt` (тот же снимок) и `failure-N.png`
  (скриншот), где `N` номер вкладки. Пути не печатаются; найдите их в
  `/dev/shm/wishenka-pytest-<uid>-<pid>/` (после падающего прогона каталог остаётся, см.
  «Параллельный запуск тестов (WISHENKA-166)») либо задайте `--basetemp`.
- В CI эти файлы не выгружаются, снимок есть только в логе (WISHENKA-147).

### Таймауты и маркеры

Три новых модуля объявляют `pytestmark = [pytest.mark.timeout(45), pytest.mark.browser]`; это
договорённость для браузерных тестов (по инфраструктурному контракту обычные модули используют 10 или
30 с, см. `infrastructure.md`, раздел 4.1). Охранный тест
`tests/test_browser_prerequisites.py::test_new_browser_modules_declare_marker_and_timeout` разбирает
AST каждого `tests/test_*_browser.py`: маркер `browser` на модуле или на каждом тесте и модульный
`timeout(45)`; он же требует наличия трёх модулей, поэтому переименование модуля нужно
отразить в `NEW_BROWSER_MODULES`. `tests/test_wishlist_sections_ui.py` (таймаут 60 с) под
шаблон имени не попадает. Внутри драйвера есть свои пределы: команда CDP 10 с (`COMMAND_TIMEOUT`),
загрузка страницы 10 с, `wait_for` по умолчанию 5 с; цепочка ожиданий может превысить 45 с, и тогда
pytest-timeout сработает раньше, чем появится сообщение `PageWaitTimeout`.

### Проверка стабильности

Один раз, не как гейт CI: три модуля прогнаны 10 раз подряд, 10 из 10 `53 passed`, без падений и
нестабильных тестов; время одного прогона 34.9-39.6 с (в среднем около 37 с), после прогонов процессов
Chromium и uvicorn не осталось. Среда: Chromium 156, Debian 13, Python 3.13. В CI прогон ещё не
выполнялся (WISHENKA-135).

### Проверка чувствительности (mutation proof)

Метод: временная правка `wishenka/web/static/wishlist.js` одной мутацией, прогон трёх модулей,
откат командой `git checkout -- wishenka/web/static/wishlist.js` в `finally`; после серии
`git diff --exit-code -- wishenka/` пуст. Каждая мутация ловится утверждением (упавшим тестом).

| Мутация | Результат |
| --- | --- |
| M1: сравнение с серединой `>` на `<` | 12 красных |
| M2: идентификаторы собираются до `insertBefore` | 11 красных |
| M3: убран ранний выход по `TOGGLE_EXCLUSION` | 8 красных |
| M4a: отключён обработчик Escape | 2 красных |
| M5: второй `submitReorder` в `pointerup` | 4 красных |
| M6: убран `console.warn` | 3 красных |
| M7-M14 (`details.hidden = !expanded`, `preventDefault` у клавиши, `lostpointercapture`, `visibilitychange`, `blur`, проверка `target === dragged`, сброс флага подавления таймером, отмена вторым пальцем) | по 1-14 красных |
| M4b: убран слушатель `pointercancel` | выжила (19 зелёных) |
| M11: убран слушатель `htmx:beforeSwap` | выжила (19 зелёных) |

Выжившие M4b и M11 объясняются кодом, а не слабостью теста: после `touchCancel` и после замены списка
браузер всё равно доставляет `lostpointercapture`, а его слушатель вызывает тот же `cancelTouchDrag`.
Комбинации (`pointercancel` с `lostpointercapture`, `beforeSwap` с `lostpointercapture`) ловятся
(5 и 2 красных теста), но изолировать один слушатель нельзя без тестового шва в `wishlist.js`.
Решение о комментарии или шве: WISHENKA-144. Метод можно повторить при существенной правке
`wishlist.js`.

### Что осталось от строковых проверок

Слабые проверки содержимого скрипта и CSS заменены поведенческими тестами. Сохранены
(они проходят и на комментарии): `test_wishlist_script_contains_sdk_token` (четыре токена SDK:
`disableVerticalSwipes`, `enableVerticalSwipes`, `isVersionAtLeast`, `HapticFeedback`, которых
браузерные тесты не видят из-за пустого SDK), `-webkit-touch-callout: none`,
`test_css_summary_does_not_block_touch_scroll`,
`test_wishlist_script_has_single_reorder_submit_point`, проверки разметки, ответ 200 и тип
`javascript` для `/static/wishlist.js`, `test_cards_have_no_inline_event_handlers`.

### Выбор: CDP вместо Playwright

Драйвер на CDP выбран, чтобы не тянуть зависимость (колесо около 53 МБ, greenlet) и пару версий
Playwright с системным Chromium; тесты уже использовали CDP напрямую. Цена: около 670 строк
собственного кода, экспериментальный метод `Input.setInterceptDrags`, обходные решения для
инерции касаний Chromium и момента доставки `lostpointercapture` (описаны в комментариях драйвера).
Поводы пересмотреть:

- число браузерных тестов выросло примерно за 100 или появился второй тип страниц, которому нужна
  настоящая навигация htmx;
- понадобилась возможность, которую Playwright даёт из коробки (трассировка, видео, подмена сети);
- `websockets` удалит параметр `legacy`. Драйвер подключается через
  `websockets.sync.client.connect(..., legacy=True)`, а `pyproject.toml` требует только
  `websockets>=13.0`; диапазон версий нужно согласовать с этим параметром (WISHENKA-146).

### Устранение неполадок набора

- **Chromium не найден:** тесты падают на setup с сообщением «Chromium is required for browser UI
  tests» (WISHENKA-124); см. раздел «Troubleshooting» выше.
- **`PageWaitTimeout: ...`:** это `AssertionError` с описанием ожидаемого условия; снимок страницы
  в секции `Page N diagnostics` показывает порядок карточек, вызовы `ajax`, консоль и запросы. Если
  в `external requests` есть адрес, проверьте совпадение адресов с `base.html`.
- **Нестабильные касания:** в синтезированных касаниях драйвер делает паузы (16 мс после каждого
  движения, 60 мс перед `touchEnd`), иначе Chromium запускает инерцию и «съедает» следующий тап;
  в `wait_for` для опущенных пальцев отправляется смещение на 0.01 px, чтобы Chromium доставил
  `lostpointercapture`. Не убирайте паузы; на медленном раннере проверьте тесты
  `test_next_tap_after_suppression_window_toggles` и `test_vertical_swipe_outside_handle_scrolls_not_reorders`.
- **Остались процессы или занят порт:** порт сервера выбирается случайным, процессы закрываются в
  `finally`. После убитого (SIGKILL) прогона может остаться Chromium с временным профилем:
  `pkill -f chromium` завершит такие процессы; профили лежат на диске в каталогах
  `wk-chromium-<pid>-*` (временный каталог или `WISHENKA_TEST_DISK_TMPDIR`), их можно удалить
  вручную, следующий запуск чистит каталоги завершённых процессов. Запуск браузера через
  `launch_chromium` (`setpriv --pdeathsig KILL`, отдельная группа процессов) снижает этот риск;
  подробности в разделе про параллельный запуск.

## Параллельный запуск тестов (WISHENKA-166)

### Overview

`make test` (а значит и `make check`) запускает полный набор параллельно через `pytest-xdist`.
Зачем: последовательный прогон 798 тестов занимал 971.7 с (16 мин 11 с). Причина не в вычислениях:
каждый тест создаёт SQLite-базу и применяет миграции, а `fsync` на виртуальной файловой системе
`/tmp` стоит 11 мс в одиночку и 75 мс при шести писателях (фаза setup дала 56 % времени, call 40 %).
Параллельный запуск прямо на диске не помогает: `-n 6` на диске дал 981 с, 28 упавших тестов и
9 ошибок (`Timeout`). Ускорение даёт перенос файлов тестов на tmpfs плюс несколько воркеров.

Измерения на эталонной машине (6 ядер, 5909 MiB ОЗУ по `nproc` и `free -m`, Linux):

| Режим | Время | Результат |
| --- | --- | --- |
| Последовательно, диск (до задачи) | 971.7 с | 798 passed |
| Последовательно, tmpfs (`make test-serial`) | около 114 с | 814 passed |
| `make test`, 6 воркеров (6 прогонов) | 49-55 с общее время (включая `make deps`), около 44-49 с время pytest (47.5-48.9 с в серии из 3 прогонов, 44.1 с в более позднем прогоне) | 814 passed в каждом, наборы совпадают |

814 тестов = 798 прежних + 16 контрактных `tests/test_parallel_run_contract.py`. Пик памяти в
использовании 2.7-2.9 GiB, минимум `MemAvailable` 1908 MiB, OOM не было, после прогона `/dev/shm`
пуст и процессов Chromium нет. Бюджет 120 с подтверждён только на эталонной машине: на CI
(`ubuntu-latest`) и на медленном хранилище он не измерялся (см. «Известные пределы»).

Подробности: `ai-tasks/WISHENKA-166/20-architecture.md`, `21-baseline-data.md`, `40-development.md`.

### Architecture

| Компонент | Назначение |
| --- | --- |
| `Makefile`, цель `test` | `pytest -n $(PYTEST_JOBS) --dist loadfile $(PYTEST_ARGS)` под защитой по времени (`timeout -k 30 $(TEST_WALL_LIMIT)`, если команда `timeout` есть). |
| `pyproject.toml` | Зависимость `pytest-xdist>=3.6` в `dev` и `tmp_path_retention_policy = "failed"`. |
| `tests/xdist_support.py` | Чистые функции без импорта pytest: выбор каталога и числа воркеров, проба `fsync`, чистка устаревших каталогов, `disk_mkdtemp`. |
| `tests/conftest.py` | Хуки `pytest_xdist_auto_num_workers`, `pytest_configure`, `pytest_sessionfinish`, `pytest_unconfigure`, `pytest_terminal_summary`; фикстуры `_isolated_default_database`, `chromium_profile_dir`, `chromium_browser`, `migrated_db_template`. |
| `tests/browser_cdp.py` | `launch_chromium`, `stop_chromium`, `read_debug_port`, `CdpBrowser`. |
| `tests/bench_suite.py` | `make test-bench`: замер времени и памяти, сравнение множеств пройденных тестов. |
| `tests/test_parallel_run_contract.py` | Контракт: Makefile, pyproject, помощники `xdist_support`, ожидание файла порта CDP. |

Решения:

- **xdist.** `-n auto --dist loadfile`: все тесты одного файла идут в одном воркере, поэтому
  модульные фикстуры и браузер модуля остаются в одном процессе. `loadfile` выбран по медиане
  трёх прогонов (46.2 с против 49.4 с у `load`); разница в пределах шума (D-8).
- **Число воркеров** задаёт хук `pytest_xdist_auto_num_workers`, а не сам `auto`:
  `max(1, min(CPU, (MemAvailable - 1200) // 600))` (`choose_workers`). CPU берётся из
  `os.sched_getaffinity(0)`; `MemAvailable` из `/proc/meminfo` в MiB, при конечном значении
  `/sys/fs/cgroup/memory.max` берётся меньшее. На эталонной машине получается 6. На медленном
  хранилище всегда 1 воркер. Хук работает только при `-n auto`.
- **Быстрое хранилище.** Контроллер (`pytest_configure`, воркеры не повторяют выбор) создаёт
  `/dev/shm/wishenka-pytest-<uid>-<pid>` как `--basetemp` (там живёт `tmp_path`) и
  `/dev/shm/wishenka-pytest-<uid>-<pid>-tmp` как `TMPDIR` и `tempfile.tempdir`. Воркеры и их дочерние
  процессы наследуют окружение. Если `/dev/shm` недоступен (нет каталога, нет прав записи, меньше
  48 MiB свободно), проверяется скорость `fsync` во временном каталоге по умолчанию: быстрый
  остаётся как есть, медленный даёт один воркер. Опция `--basetemp` пользователя не переопределяется.
- **Два временных каталога.** `/dev/shm` смонтирован `noexec` и в Docker по умолчанию 64 MiB.
  Поэтому профили Chromium (до 100 MiB) и исполняемые заглушки браузеров в
  `test_browser_prerequisites.py` лежат на диске: `xdist_support.disk_mkdtemp(kind)` создаёт
  `wk-<kind>-<pid>-*` в `WISHENKA_TEST_DISK_TMPDIR` (по умолчанию исходный временный каталог).
  Фикстура `tmp_path` в `test_browser_prerequisites.py` переопределена именно для этого.
- **Браузер.** Фикстуры `chromium_browser` (один headless Chromium на воркер, профиль на диске) и
  `migrated_db_template` (база с применёнными миграциями, создаётся один раз на воркер и копируется
  в каждый тест) имеют область `session`: в xdist это «на воркер». `launch_chromium` запускает
  браузер через `setpriv --pdeathsig KILL` (если `setpriv` найден: ядро убьёт Chromium даже при
  `SIGKILL` воркера), с `start_new_session=True`; `stop_chromium` делает `terminate`, ожидание до
  5 с, затем `os.killpg` на всю группу; хук `atexit` убивает группы живых браузеров. Без `setpriv`
  убитый `SIGKILL` воркер может оставить Chromium-сироту. `preexec_fn` не используется (небезопасен
  с потоками).
- **Ожидание порта CDP.** Chromium создаёт `DevToolsActivePort` до того, как запишет порт, поэтому
  недостаточно проверить существование файла: `read_debug_port` возвращает порт, только если первая
  строка состоит из цифр; ожидание ограничено 10 с.
- **База по умолчанию.** Автоматическая фикстура `_isolated_default_database` задаёт
  `WISHENKA_DATABASE_URL` и `WISHENKA_SQLITE_DB_PATH` на файл в каталоге сессии, поэтому тест,
  создающий `Settings()` без аргументов, не пишет в `data/wishenka.db` репозитория. Явный
  `database_url=` сильнее.
- **Тест, который нельзя запускать одновременно.** Берите исключительный ресурс из фикстуры
  теста (`tmp_path`, порт 0, `xdist_support.disk_mkdtemp`). Если это невозможно, пометьте тест
  `@pytest.mark.xdist_group(name=...)` и переключите Makefile на `--dist loadgroup`. Таких тестов
  сейчас нет, первый - проектное решение, его надо записать в артефактах задачи.

### Usage

```bash
make test                                    # параллельно, быстрое хранилище
make test PYTEST_ARGS="--durations=20"       # 20 самых медленных тестов
make test PYTEST_ARGS="-k receipt"           # отбор тестов
make test PYTEST_ARGS="tests/test_booking_ceiling_r5.py"
make test PYTEST_JOBS=3                      # три воркера вместо auto
make test-serial                             # строго последовательно (-n 0)
make test-serial PYTEST_ARGS="tests/test_x.py::test_name"   # один тест, отладка
make test-bench                              # замер: nproc, free -m, время, память, бюджет 120 с
make check                                   # make analyze + параллельный make test
```

- `make test-serial` выполняется `-n 0` в одном процессе, без хука числа воркеров, но каталоги всё
  равно размещаются на быстром хранилище (около 114 с). Используйте его для одного теста,
  отладки и чтения трассировок.
- `PYTEST_ARGS` попадает в конец команды pytest в обеих целях (`-v` и `--strict-markers` уже есть в
  `addopts`).
- `make test-bench` запускает `make test` с `--junitxml`, печатает `nproc`, `free -m`, время,
  минимум `MemAvailable`, пик `/dev/shm`, число пройденных, упавших и пропущенных тестов; код выхода
  1, если есть упавшие или пропущенные тесты, множество пройденных тестов при `--compare`
  отличается от более раннего файла или время больше 120 с. Для сравнения наборов:
  `python -m tests.bench_suite --budget 120 --junit run1.xml --compare run0.xml`.
- Для отладки тайм-аутов используйте `make test-serial PYTEST_ARGS="--timeout=120 <id>"`: при
  зависании pytest-timeout печатает стеки.

### Configuration

| Параметр | Значения | По умолчанию | Действие |
| --- | --- | --- | --- |
| `WISHENKA_TEST_TMPDIR` | путь к каталогу или `disk` | не задан (`/dev/shm`) | Каталог для быстрых файлов. Путь заменяет `/dev/shm` (нужны права записи и 48 MiB свободно). `disk` отключает tmpfs: используется временный каталог по умолчанию с пробой `fsync`. |
| `WISHENKA_TEST_DISK_TMPDIR` | путь к каталогу | исходный `tempfile.gettempdir()` | Диск с правом исполнения для профилей Chromium и заглушек браузеров. Контроллер экспортирует его для воркеров. |
| `WISHENKA_TEST_WORKERS` | положительное целое | не задан | Явное число воркеров вместо расчёта (только при `-n auto`, предупреждение медленного хранилища не печатается). Нецелое значение и `0` молча игнорируются. |
| `PYTEST_JOBS` | `auto`, число, `0` | `auto` | Значение `-n`. Число отключает хук ограничения; `0` без xdist. |
| `PYTEST_ARGS` | любые аргументы pytest | пусто | Добавляются к команде. |
| `TEST_WALL_LIMIT` | секунды | `600` | Предел времени всего `make test` (`timeout -k 30`). Это защита от зависания, не тайм-аут теста. Если команды `timeout` нет, защиты нет. |

Пороги в коде (не настраиваются, `tests/xdist_support.py`, `tests/conftest.py`):

| Порог | Значение | Где |
| --- | --- | --- |
| Быстрый `fsync` | медиана пяти записей по 4 КБ не больше 2 мс | `FSYNC_SAMPLES`, `FSYNC_FAST_SECONDS` |
| Минимум свободного места в каталоге | 48 MiB | `MIN_FREE_MB` |
| Резерв памяти и память на воркер | 1200 MiB и 600 MiB | `RESERVE_MB`, `PER_WORKER_MB` |
| Таймер дампа стеков в конце сессии | 120 с (`faulthandler`, только печать) | `SESSION_END_DUMP_SECONDS` |
| Ожидание порта Chromium | 10 с (литерал) | `tests/browser_cdp.py`, `CdpBrowser._launch` |
| Завершение браузера | 5 с, дважды | `tests/browser_cdp.py`, `TERMINATE_TIMEOUT` |

### Медленное хранилище

Если `/dev/shm` недоступен, а во временном каталоге по умолчанию медиана `fsync` больше 2 мс,
используется один воркер, и в stderr печатается:
`WARNING: slow test storage: running with one worker; expected about 16 minutes; set
WISHENKA_TEST_TMPDIR to a fast directory (for example /dev/shm)`. Прогон занимает около 16 минут:
шесть воркеров на таком хранилище не быстрее и дают ошибки `Timeout` (981 с, 28 упавших, 9
ошибок). Что сделать: указать быстрый каталог (`export WISHENKA_TEST_TMPDIR=/path/to/tmpfs`; он
должен быть записываемым и иметь 48 MiB), смонтировать `/dev/shm` или запустить контейнер с
`--shm-size`. Если проба ошиблась из-за временной нагрузки, перезапустите прогон. Принудительно
задать число воркеров можно через `WISHENKA_TEST_WORKERS`, но на медленном диске это даёт ошибки.

### Troubleshooting

- **`Timeout` на тестах под нагрузкой.** Машина занята другой работой или воркеров слишком много.
  Перезапустите при свободной машине; уменьшите число: `make test PYTEST_JOBS=3` или
  `WISHENKA_TEST_WORKERS=3`. Не поднимайте тайм-ауты тестов и не добавляйте повторные запуски.
- **Прогон завис, код 124 или 137.** Сработала защита `TEST_WALL_LIMIT`. Цель печатает подсказку.
  Найдите зависший тест по последним строкам, воспроизведите последовательно:
  `make test-serial PYTEST_ARGS="--timeout=120 <id теста>"`; pytest-timeout напечатает стеки.
  Через 120 с после конца сессии `faulthandler` печатает стеки потоков (зависание в завершении).
- **Строка «test files kept for diagnosis: ...».** После прогона с кодом выхода не 0 каталоги
  `/dev/shm/wishenka-pytest-<uid>-<pid>` и `...-tmp` остаются для разбора (в `tmp_path` упавших
  браузерных тестов лежат `diagnostics-N.txt` и `failure-N.png`). Следующий запуск удаляет каталоги
  завершённых процессов того же пользователя. Вручную: `rm -rf /dev/shm/wishenka-pytest-*` и
  `rm -rf /tmp/wk-*` (каталоги профилей и заглушек на диске; следующий запуск тоже чистит
  `wk-<kind>-<pid>-*` мёртвых процессов, но каталог с суффиксом `wk-contract-` не чистится).
- **Ложное сообщение «kept», код 5.** Если ни один тест не выбран (`-k` без совпадений, опечатка в
  id), код выхода 5, и сообщение печатается, а каталог остаётся: в нём нет данных, следующий запуск
  его удалит (D-6).
- **Остался Chromium.** Проверьте `pgrep -af chromium`. Без `setpriv` убитый `SIGKILL` прогон мог
  оставить браузер: `pkill -f chromium`; профили лежат в `wk-chromium-*` на диске.
- **OOM или убитые воркеры.** Уменьшите число воркеров (`PYTEST_JOBS`, `WISHENKA_TEST_WORKERS`).
  На воркер приходится около 450-480 MiB вместе с Chromium; формула резервирует 600 MiB.
- **macOS и Windows не поддерживаются.** `os.sched_getaffinity` отсутствует на macOS, поэтому
  `make test` падает при `-n auto`. Поддерживается Linux (WSL подходит). Обходной путь:
  `make test-serial` или `make test PYTEST_JOBS=2` (число без `auto` хук не вызывает).
- **Как отключить параллельность.** `make test-serial` или `make test PYTEST_JOBS=0`;
  напрямую: `.venv/bin/pytest -n 0`. Прямой `pytest` без `-n` тоже работает последовательно.
- **Контрактные тесты.** `test_fsync_probe_is_fast_on_tmpfs` требует быстрый `/dev/shm`; при его
  отсутствии он падает, а не пропускается (D-10).

### Известные пределы

Список долга: `ai-tasks/WISHENKA-166/60-tech-debt.md`, пункты D-1..D-18 (тикеты созданы). Главное:

- Скорость даёт tmpfs, а не удешевление setup: на медленном хранилище набор идёт около 16 мин
  (D-7, WISHENKA-170).
- Бюджет 120 с проверен только на эталонной машине; для CI и для 2-4 ядер это оценка (D-9, WISHENKA-172).
  Критический путь: `test_shared_inventory_multiprocess` (около 25 с) и `test_booking_ceiling_r5`
  (около 20 с) целиком в одном воркере при `loadfile` (D-8, WISHENKA-171).
- Нет тестов на завершение процессов Chromium, чистку устаревших каталогов, откат на медленное
  хранилище и сообщения Makefile (D-1..D-5, WISHENKA-167, WISHENKA-168).
- Пороги не настраиваются (D-11), `faulthandler_timeout` не задан (D-12): WISHENKA-174.
- Ложное сообщение «kept» при коде 5 (D-6): WISHENKA-169.
- Только Linux, `test-bench` без зависимости `deps` и Linux-команды в нём (D-10, D-18):
  WISHENKA-173. Не проверено на Python 3.12 (D-17): WISHENKA-175.
- Устаревший каталог чужого процесса в общем `/dev/shm` с другими пространствами pid может быть
  удалён (D-3): WISHENKA-168. Покрытие тестами Chromium и Makefile (D-1, D-2, D-5, D-13):
  WISHENKA-167.
- D-16 (файл `core`): существующий WISHENKA-126. D-14 (эта документация) выполнен, D-15
  исправлен в артефакте.

## Стресс-тесты конкурентного жизненного цикла желаний (WISHENKA-102)

### Overview

Модуль `tests/test_wish_lifecycle_stress.py` проверяет конкурентную корректность операций жизненного
цикла желаний в `WishlistService` (`add_wish_item`, `reorder_wish_items`, `archive_wish_item`) поверх
файловой SQLite БД в режиме WAL с транзакциями `BEGIN IMMEDIATE`.

Покрытые сценарии:

- `test_concurrent_reorders_single_store_preserve_permutation` — 24 параллельных `reorder_wish_items`
  через один `WishlistStore` (роли `OWNER`, `ADMIN`, `MEMBER`).
- `test_concurrent_reorders_multiple_stores_preserve_permutation` — 20 параллельных
  `reorder_wish_items` через 4 независимых экземпляра `WishlistStore` на одном файле БД.
- `test_concurrent_add_and_reorder_preserve_all_items` — одновременные `add_wish_item` (8 задач) и
  `reorder_wish_items` (10 задач) с проверкой атомарного отклонения устаревших снимков через
  `ValueError`.
- `test_concurrent_archive_and_reorder_exclude_archived_items` — одновременные `archive_wish_item`
  (3 задачи), `add_wish_item` (4 задачи) и `reorder_wish_items` (8 задач).
- `test_mixed_lifecycle_waves_owner_and_coauthors` — 3 последовательные волны смешанных операций
  через 2 экземпляра `WishlistStore` от имени владельца и соавторов.
- `test_concurrent_lifecycle_isolation_across_wishlists` — параллельные мутации на 3 независимых
  вишлистах без взаимного влияния.

### Architecture

- `_open_wal_store(db_path)` — инициализирует `WishlistStore(f"sqlite+aiosqlite:///{db_path}")`,
  проверяет `PRAGMA journal_mode == "wal"`, `PRAGMA foreign_keys == 1` и `PRAGMA busy_timeout == 5000`,
  гарантирует `await store.dispose()` в `finally`.
- `_run_barrier_tasks(factories, ...)` — синхронизирует старт всех корутин через общий барьер
  (`asyncio.Event`), ограничивает ожидание барьера и пакета через `asyncio.wait_for` и отменяет
  незавершённые задачи в `finally`.
- `_assert_wishlist_invariants(store, ...)` — сверяет инварианты из двух источников: прямым SQL к
  таблице `wl_items` и через `WishlistService.get_wishlist_view()`. Проверяются точные множества
  активных и архивных `id`, отсутствие пересечений, уникальность `display_order` среди активных
  желаний (и непрерывность `0..N-1`, если `require_contiguous_order=True`).

### Usage

Запуск только стресс-набора:

```bash
.venv/bin/pytest tests/test_wish_lifecycle_stress.py
```

Запуск через `Makefile` в составе полного набора или последовательно:

```bash
make test-serial PYTEST_ARGS="tests/test_wish_lifecycle_stress.py"
```

### Configuration

- Маркер таймаута модуля: `pytestmark = pytest.mark.timeout(120)`.
- Внутренние ограниченные ожидания: `_BARRIER_TIMEOUT_SECONDS = 15.0`,
  `_BATCH_TIMEOUT_SECONDS = 45.0`.
- Временные файлы БД создаются в `tmp_path` (наследуют `WISHENKA_TEST_TMPDIR`, по умолчанию
  `/dev/shm` при наличии быстрого tmpfs).

### Troubleshooting

- **Таймаут или `InventoryBusyError` на медленном диске.** Если `tmp_path` расположен на медленном
  хранилище с высоким `fsync`, задайте быстрый каталог: `export WISHENKA_TEST_TMPDIR=/dev/shm`.
- **`ValueError` в `reorder_wish_items`.** Ожидаемое поведение при конкурентном `add_wish_item` или
  `archive_wish_item`: перестановка со старым набором активных `item_ids` атомарно отклоняется до
  записи в БД и не должна приводить к частичному изменению `display_order`.

## Тесты доставки уведомлений: живой smoke и гонка воркеров (WISHENKA-156)

### `tests/test_telegram_notice_smoke.py` (маркер `telegram_smoke`)

Модуль (`pytestmark = pytest.mark.timeout(60)`) объединяет opt-in smoke-тесты реальной отправки в
Telegram Bot API и офлайн-проверки безопасности:

- **Офлайн-проверки (всегда выполняются в `make test`):**
  - `test_build_sender_rejects_placeholder_and_invalid_tokens` — проверяет, что `build_sender`
    возвращает `None` для пустого токена, `PLACEHOLDER_TOKEN` и некорректного токена.
  - `test_notice_text_truncates_titles_and_preserves_plain_text` — проверяет ограничение длины
    названий (`TITLE_LIMIT = 100`), сохранение спецсимволов (`<script>&"'>`) в открытом тексте и
    соблюдение лимита Telegram (`4096` символов).
- **Живые smoke-тесты (`@pytest.mark.telegram_smoke`, зарегистрирован в `pyproject.toml`):**
  - Автоматически пропускаются (`pytest.mark.skipif`), если не заданы
    `WISHENKA_TELEGRAM_SMOKE_TOKEN` и целочисленный `WISHENKA_TELEGRAM_SMOKE_CHAT_ID`.
  - `test_telegram_smoke_delivers_plain_text_with_special_chars_and_truncation` — отправляет
    реальное уведомление со спецсимволами и длинными названиями (`>100` символов) через
    `AiogramNoticeSender.send` и ожидает `SendOutcome.DELIVERED`.
  - `test_telegram_smoke_rejects_invalid_chat` — отправляет сообщение в
    `WISHENKA_TELEGRAM_SMOKE_INVALID_CHAT_ID` (по умолчанию `0`) и ожидает `SendOutcome.REJECTED` с
    непустым `error_class`.

Запуск живых smoke-тестов и ручной чек-лист проверки описаны в
[`doc/dev/notifications.md`](notifications.md#live-telegram-smoke-test--manual-verification-checklist).

### `tests/test_notice_worker_concurrency.py` (гонка двух процессов воркера)

Модуль (`pytestmark = pytest.mark.timeout(120)`) проверяет межпроцессное соревнование двух
независимых процессов ОС за одну очередь `notification_outbox` поверх файловой WAL SQLite БД:

- **Инициализация:** засевает `10` (`_GIVER_COUNT = 10`) отложенных уведомлений для разных
  дарителей (`users`, активные `bot_destinations`, `wl_lists`, `wl_items`, `wl_reservations`,
  `record_item_fulfillment`), чтобы исключить пер-чатовый интервал ограничения скорости.
- **Конкурентный запуск:** запускает 2 дочерних процесса через `multiprocessing.get_context("spawn")`,
  синхронизирует их старт на `ctx.Barrier(2)` (`_BARRIER_TIMEOUT = 10`, `_JOIN_TIMEOUT = 15`) и в
  каждом процессе открывает собственный `WishlistStore` / `NoticeStore` и вызывает
  `NoticeWorker.run_once(now=...)` с `FakeNoticeSender(sleep=0.01)` для перекрытия I/O.
- **Инварианты:** нулевые коды выхода, отсутствие ошибок БД и блокировок, ровно `10` доставок без
  дубликатов и потерь, а все строки `notification_outbox` переходят в `status = 'sent'` с
  `claim_token IS NULL`, `claimed_at IS NULL` и `attempts = 1`.

Запуск модуля:

```bash
.venv/bin/pytest tests/test_notice_worker_concurrency.py
```

## Атомарная транзакционная граница захвата бота (WISHENKA-179)

Модуль `tests/test_bot_capture_atomic_store_repro.py` (`pytestmark = pytest.mark.timeout(15)`)
проверяет публичный интерфейс `WishlistStore.execute_with_connection` и миграцию
`wishenka/bot/capture.py:mutate`:

- `test_execute_with_connection_commits_service_and_sql_atomically` — совместный коммит доменного
  вызова `WishlistService.add_wish_item` и SQL-обновления `bot_drafts` на одном `AsyncConnection`.
- `test_execute_with_connection_rolls_back_service_and_sql_on_error` — одновременный откат
  доменной записи и SQL-изменения при исключении внутри колбэка.
- `test_bot_capture_save_uses_execute_with_connection_and_preserves_replay` — подтверждает вызов
  `store.execute_with_connection` при сохранении черновика и идемпотентный повторный ответ.
- `test_bot_capture_does_not_access_private_store_read_write` — AST-проверка того, что
  `wishenka/bot/capture.py` не обращается к приватным атрибутам `_read` и `_write`.

Запуск модуля:

```bash
make test PYTEST_JOBS=0 PYTEST_ARGS="tests/test_bot_capture_atomic_store_repro.py"
```

## Публичная транзакционная граница NoticeStore (WISHENKA-180)

Модуль `tests/test_notice_store_transaction_repro.py` (`pytestmark = pytest.mark.timeout(30)`)
проверяет публичный интерфейс `NoticeStore.transaction` и отсутствие обращений к приватному
атрибуту `_store` в пакете `wishenka/notices/`:

- `test_notice_store_exposes_public_transaction` — проверяет, что `NoticeStore.transaction(work)`
  выполняет `work(conn)` в транзакции и возвращает результат.
- `test_notice_store_transaction_rolls_back_on_error` — проверяет откат незафиксированных
  изменений при исключении внутри `NoticeStore.transaction`.
- `test_notices_package_has_no_private_store_access` — AST-проверка того, что модули в
  `wishenka/notices/` (кроме `store.py`) не обращаются к приватному атрибуту `._store`.

Запуск модуля:

```bash
make test PYTEST_JOBS=0 PYTEST_ARGS="tests/test_notice_store_transaction_repro.py"
```

## Пакетная очистка outbox и `reminder_outbox.updated_at` (WISHENKA-183)

Два модуля (`pytestmark = pytest.mark.timeout(30)`) проверяют ограниченную по размеру пакета
очистку `NoticeStore.purge_finished` и миграцию/проставление `reminder_outbox.updated_at`:

### `tests/test_wishenka_183_repro.py`

- `test_purge_finished_validates_non_positive_batch_size` — отклоняет `batch_size <= 0` (`0`, `-1`)
  через `ValueError`.
- `test_purge_finished_drains_both_outboxes_and_preserves_protected_rows` — проверяет поэтапное
  удаление (`LIMIT :batch_size` в отдельных транзакциях) просроченных терминальных строк из
  `notification_outbox` и `reminder_outbox` с сохранением нетерминальных (`pending`, `uncertain`),
  свежих и активных по циклу (`event_date >= today_utc`) записей.
- `test_reminder_outbox_has_updated_at_column_index_and_coalesce_retention` — проверяет наличие
  колонки `reminder_outbox.updated_at`, индекса `idx_reminder_outbox_status_updated` и фильтрацию
  хранения по `COALESCE(updated_at, next_attempt_at)`.

### `tests/test_wishenka_183_updated_at.py`

- `test_alembic_reminder_outbox_updated_at_upgrade_backfill_and_downgrade` — проверяет миграцию
  `add_reminder_outbox_updated_at` (`upgrade` с backfill `COALESCE(claimed_at, next_attempt_at)` и
  созданием `idx_reminder_outbox_status_updated`, а также обратимый `downgrade` к
  `add_bot_capture_order_retention`).
- `test_reminder_outbox_writers_stamp_updated_at` — проверяет проставление `updated_at` всеми
  источниками записи в `reminder_outbox`: `ReminderScheduler`, `EventProducer`,
  `NoticeWorker.run_once` (`settle_reminder`), восстановлением зависших захватов в `claim_reminder`
  и операторским `resolve`.
- `test_purge_finished_logs_batch_count_and_batch_size` — проверяет поля `batches` и `batch_size`
  в событии `notice_outbox_purged`.

Запуск модулей:

```bash
make test PYTEST_JOBS=0 PYTEST_ARGS="tests/test_wishenka_183_repro.py tests/test_wishenka_183_updated_at.py"
```

## Известные ограничения

Тесты удаления вишлиста WISHENKA-295: см. раздел «Тесты удаления вишлиста владельцем
(WISHENKA-295)» (WISHENKA-316..319).

Тесты формы создания WISHENKA-296: см. раздел «Тесты формы создания вишлиста (WISHENKA-296)»
(WISHENKA-312, 313, 319..322).

Тесты переключателей настроек WISHENKA-307: см. раздел «Тесты переключателей экрана настроек
(WISHENKA-307)» (WISHENKA-313..315).

Сквозные тесты WISHENKA-294: см. конец раздела «Сквозные тесты комфорта и надёжности экранов
(WISHENKA-294)» (WISHENKA-308..312).

Пункты отслежены в Jira (источники: `ai-tasks/WISHENKA-124/60-tech-debt.md` и `ai-tasks/WISHENKA-110/60-tech-debt.md`):

- [WISHENKA-135](https://pypost.atlassian.net/browse/WISHENKA-135): браузер на раннере CI не
  проверен реальным прогоном (имя и путь в образе `ubuntu-latest` не подтверждены); запасной шаг
  `browser-actions/setup-chrome` не подключён.
- [WISHENKA-136](https://pypost.atlassian.net/browse/WISHENKA-136): ветка `apt` цели
  `deps-browser` не выполнялась на чистой Debian и не покрыта тестами (путь `/etc/os-release`
  зашит в рецепт; нет теста на охрану `WISHENKA_CHROMIUM_BIN` и правило «только Debian»).
- [WISHENKA-137](https://pypost.atlassian.net/browse/WISHENKA-137): нет теста, что оба браузерных
  теста помечены `browser`; проверка объявления маркера мягкая; внутренний таймаут 60 с в
  `_nested_pytest` недостижим из-за маркера 30 с.
- [WISHENKA-138](https://pypost.atlassian.net/browse/WISHENKA-138): проба устойчива не полностью:
  таймаут нельзя настроить, до четырёх зависших кандидатов могут занять 40 с из 45 с лимита теста,
  stderr обрезается до 300 символов, определение snap идёт по подстроке.
- [WISHENKA-145](https://pypost.atlassian.net/browse/WISHENKA-145): заглушка htmx не покрывает
  настоящий htmx, `hx-*` и путь CSRF; **закрыто** дымовым тестом
  `tests/test_wishlist_htmx_smoke_browser.py` (`use_real_htmx=True`, `auth_mode="cookie"`),
  существующие 53 теста `WISHENKA-110` по-прежнему используют `htmx_stub.js` и `Bearer`.
- [WISHENKA-146](https://pypost.atlassian.net/browse/WISHENKA-146): два старых браузерных модуля не
  используют общий драйвер `tests/browser_cdp.py`; диапазон версий `websockets` не согласован с
  `legacy=True`.
- [WISHENKA-147](https://pypost.atlassian.net/browse/WISHENKA-147): скриншоты и `diagnostics-N.txt`
  не выгружаются из CI, один и тот же снимок выводится дважды.
- [WISHENKA-126](https://pypost.atlassian.net/browse/WISHENKA-126): неотслеживаемый файл `core` в
  корне репозитория (не в `.gitignore`); при коммите добавляйте файлы по явным путям.

Прочие осознанные ограничения: поддерживается только Linux; автоматическая установка только на
Debian (`ID=debian`, пакет `chromium`); код CDP остаётся дублированным в двух старых браузерных модулях (`test_wishlist_management_browser.py`,
`test_wishlist_sections_ui.py`); общий драйвер `tests/browser_cdp.py` для них не применён
(миграция: WISHENKA-146);
`candidate_names()` дублируется в этом документе.
