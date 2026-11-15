# Browser UI-тесты: подготовка Chromium

## Overview

Тесты с маркером `browser` управляют настоящим Chromium/Chrome через Chrome DevTools Protocol (CDP):
`tests/test_wishlist_management_browser.py`, `tests/test_wishlist_sections_ui.py`, три модуля
поведенческих тестов списка желаний (раздел «Browser UI-тесты списка желаний (WISHENKA-110)» ниже)
и модуль диалога получения `tests/test_receipt_modal_browser.py` (WISHENKA-24, раздел «Диалог
получения (WISHENKA-24)»).
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
| `tests/browser_cdp.py` | Собственный драйвер на `websockets.sync` без потоков: один читатель событий. `CdpBrowser` (запуск Chromium с временным профилем, `new_page`, `stop`: terminate, `wait(5)`, kill) и `CdpPage` (навигация, `evaluate`, `wait_for`, клик, клавиши, мышь и нативный drag-and-drop через `Input.setInterceptDrags`, касания с несколькими пальцами, `snapshot`, `screenshot`). Ожидания ограничены по времени; `PageWaitTimeout` наследует `AssertionError`. |
| `tests/browser_helpers.py` | Общие помощники модулей: `Seeded`, селекторы (`card`, `summary`, `title`, `handle`), `assert_order`, `assert_cards`, `assert_clean_console`, `assert_gesture_clean`, `begin_touch_drag`, `retarget_touch_drag`, `wait_suppression_window_over` и др.; для диалога получения (WISHENKA-24) добавлены `record_receipt`, `archive_item_rest`, `open_receipt_dialog`, `posts_to`, `scroll_to`. |
| `tests/browser_assets/htmx_stub.js` | Офлайн-заглушка htmx (собственный код): только `htmx.ajax`; расширена в WISHENKA-24 (раздел «Диалог получения (WISHENKA-24)»). |
| `tests/conftest.py` | Фикстуры (ниже). |

Фикстуры `tests/conftest.py`:

- `chromium_browser` (сессия): один Chromium на весь прогон; путь даёт `chromium_executable`, поэтому
  при отсутствии браузера тесты падают с сообщением WISHENKA-124.
- `migrated_db_template` (сессия): база с применёнными миграциями Alembic создаётся один раз;
  в каждый тест копируется только файл `.db`.
- `wishlist_server` (тест): `uvicorn.Server` в потоке на `127.0.0.1` со случайным портом и своей копией
  базы; остановка ограничена по времени (`SERVER_STOP_TIMEOUT`).
- `seed_wishlist(titles, *, quantities=None)`: фабрика, создаёт список и желания через REST (httpx);
  возвращает `Seeded` с идентификаторами и токенами.
- `wishlist_page(seeded, *, as_user="owner" | "viewer", viewport=(412, 800))` и
  `share_page(seeded, *, as_user=None | "viewer", viewport=(412, 800))`: фабрики, открывают вкладку
  и страницу; касания включаются вызовом `page.enable_touch()`.
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
`Fetch.enable` и отвечает локально: `https://unpkg.com/htmx.org@1.9.12` отдаётся заглушкой
`htmx_stub.js`, `.../dist/ext/json-enc.js` и `https://telegram.org/js/telegram-web-app.js` пустым
телом (HTTP 200). Любой другой внешний запрос блокируется (`BlockedByClient`) и попадает в
`page.external_requests`; `test_page_loads_offline_with_real_assets` проверяет, что список пуст.
Запросы к `127.0.0.1` и `localhost` проходят и записываются в `page.requests` со статусом ответа.
Адреса продублированы в `tests/browser_cdp.py` (`HTMX_URL`, `JSON_ENC_URL`, `TELEGRAM_URL`) и должны
совпадать с `base.html`: при расхождении запрос блокируется, и тесты падают со снимком страницы.
Смена версии htmx требует правки в обоих местах.

### Пределы достоверности

- Заглушка htmx не обрабатывает атрибуты `hx-*`, не вызывает `htmx:configRequest`, делает
  `innerHTML`-замену (значение `swap` записывается в `window.__ajaxCalls`; единственное
  исключение `swap: 'none'`, добавленное в WISHENKA-24; внеполосные элементы применяются
  отдельно). Поэтому тесты,
  которым нужна замена списка, вызывают `window.htmx.ajax(...)` явно, а не нажимают кнопки
  перемещения. Ошибка в `hx-post`/`hx-target` кнопок или изменение событий htmx при обновлении
  библиотеки тестами не поймаются (WISHENKA-145).
- Аутентификация через Bearer (`Network.setExtraHTTPHeaders`), а не cookie-сессия: путь CSRF не
  проверяется.
- Касания синтезируются через `Input.dispatchTouchEvent`; это не настоящий стек касаний устройства.
  Поведение в Telegram WebView, автопрокрутка у краёв и порядок вызовов Telegram SDK не
  проверяются (чек-лист на устройствах: WISHENKA-143). `visibilitychange` и `blur` тесты
  отправляют как синтетические события окна.
- `label` не входит в `TOGGLE_EXCLUSION` (`a, button, input, select, textarea, [data-no-toggle]`);
  `test_nested_controls_do_not_toggle` проверяет реальный набор и `label` не утверждает.
- Константа окна подавления клика `CLICK_SUPPRESS_MS = 400` продублирована в
  `tests/browser_helpers.py`; если окно в `wishlist.js` вырастет, тест следующего тапа упадёт, если
  уменьшится, тест просто будет ждать дольше.

### Диалог получения (WISHENKA-24)

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
`test_receipt_static_script.py`, `test_receipt_ui_observability.py`, помощник
`tests/receipt_ui_support.py`; описание: `doc/dev/gift-receipt.md`, раздел «Mini App UI
(WISHENKA-24)». Хеш SHA-256 встроенного скрипта `base.html` закреплён тестом
`test_inline_script_is_unchanged_and_free_of_receipt_code`: осознанная правка скрипта
(WISHENKA-140) требует обновить хеш.

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

## Известные ограничения

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
  настоящий htmx, `hx-*` и путь CSRF; нужен один дымовой тест на реальной библиотеке без сети.
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
