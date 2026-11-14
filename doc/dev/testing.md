# Browser UI-тесты: подготовка Chromium

## Overview

Тесты с маркером `browser` управляют настоящим Chromium/Chrome через Chrome DevTools Protocol (CDP):
`tests/test_wishlist_management_browser.py` и `tests/test_wishlist_sections_ui.py`. Для них нужен
исполняемый браузер. Раньше его отсутствие приводило к пропуску тестов и «зелёному» прогону.

Теперь поведение такое:

- браузер ищется и проверяется в одном месте (`tests/browser_support.py`);
- если браузера нет, каждый браузерный тест завершается ошибкой на этапе setup, а `pytest`
  возвращает ненулевой код выхода;
- пропуск возможен только как явный локальный opt-out и никогда не действует в CI;
- `make deps-browser` готовит браузер, а CI вызывает эту цель перед `make check`.

Общие сведения о Makefile и CI: `doc/dev/infrastructure.md`.

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

## Известные ограничения

Пункты отслежены в Jira (источник: `ai-tasks/WISHENKA-124/60-tech-debt.md`):

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
- [WISHENKA-126](https://pypost.atlassian.net/browse/WISHENKA-126): неотслеживаемый файл `core` в
  корне репозитория (не в `.gitignore`); при коммите добавляйте файлы по явным путям.

Прочие осознанные ограничения: поддерживается только Linux; автоматическая установка только на
Debian (`ID=debian`, пакет `chromium`); код CDP остаётся дублированным в двух браузерных тестах;
`candidate_names()` дублируется в этом документе.
