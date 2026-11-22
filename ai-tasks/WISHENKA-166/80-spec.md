# Спецификация: WISHENKA-166 — Параллельный запуск тестов (полный прогон не более 2 минут)

**Задача:** WISHENKA-166 («[Техдолг] Параллельный запуск тестов: полный прогон не более 2 минут»)  
**Контур изменений:** тестовая инфраструктура (`tests/`, `Makefile`, `pyproject.toml`); продуктовый код `wishenka/` не изменяется  
**Платформа и стек:** Linux, Python 3.12+ (верифицировано в `.venv` на Python 3.13.5), `pytest`, `pytest-xdist>=3.6`, GNU Make  
**Статус:** реализовано, документировано и проверено (DoD 1–10 выполнены)

## 1. Назначение и бизнес-цель

### 1.1. Постановка проблемы

До реализации задачи полный набор из 798 автоматических тестов (`make test`) выполнялся строго последовательно в одном процессе и занимал на эталонной машине (6 ядер `nproc`, 5909 MiB ОЗУ без swap, Linux 6.8) **971.70 с** (16 мин 11 с; оценочно 17 мин 20 с по предварительному прогону).

Инструментальный замер фаз показал, что основным узким местом является дисковый ввод-вывод временной файловой системы `/tmp` (`virtiofs`), а не вычисления CPU:

- На фазу `setup` приходилось **536.8 с (56.0 %)** из 957.7 с отчётных фаз, на `call` — 384.5 с (40.1 %), на `teardown` — 36.5 с (3.8 %).
- Каждый тест создаёт отдельную базу данных SQLite (режим `synchronous=FULL`) и применяет все ревизии миграций Alembic. Одиночный `fsync` блока 4 КБ на `/tmp` (`virtiofs`) занимает **11.3 мс**, а при 6 одновременных писателях — **75.4 мс** из-за сериализации на уровне хоста (на `/dev/shm` с `tmpfs` — **0.0–0.1 мс**).
- Простой перевод на параллельный запуск `-n 6` без смены хранилища усугубляет проблему: замер на диске дал **981 с**, **28 упавших тестов, 9 ошибок** и 31 сообщение `Timeout`.

Из-за 16-минутного ожидания разработчики избегали запуска полного набора перед коммитом, ограничивались частичными прогонами и поздно обнаруживали регрессии, что кратно замедляло итерации в рабочем процессе.

### 1.2. Цели задачи

- Обеспечить выполнение полного набора тестов по умолчанию (`make test` и `make check`) на эталонной машине за **не более 120 с** общего настенного времени (wall-clock), включая этап `make deps`.
- Сохранить **100 % тестового покрытия** без удаления, пропуска, ослабления проверок или использования автоматических повторов упавших тестов.
- Сохранить документированный последовательный режим запуска (`make test-serial`) для отладки отдельных тестов и воспроизведения сбоев.
- Устранить все источники нестабильности при конкурентном выполнении: общую БД по умолчанию, гонку чтения порта Chromium CDP, исполнение заглушек и хранение крупных профилей браузера на `noexec`/ограниченном `tmpfs`, а также утечки процессов и временных каталогов.
- Ввести безопасный откат к одному воркеру на машинах без быстрого временного хранилища, чтобы не маскировать и не провоцировать ложные таймауты.

### 1.3. Ценность для пользователей и системы

- **Быстрая обратная связь:** время прогона перед коммитом сокращается с ~16 минут до 44–55 с (~18–20x ускорение), позволяя выполнять полный `make check` на каждой итерации.
- **Предсказуемость и доверие к результату:** множество пройденных тестов в параллельном и последовательном прогонах полностью совпадают; прогон на слабом или медленном диске остаётся зелёным за счёт честного отката до 1 воркера.
- **Гигиена окружения:** тестовые прогоны не модифицируют файл базы данных репозитория `data/wishenka.db`, не оставляют «осиротевших» процессов Chromium и очищают временные каталоги.

### 1.4. Границы задачи (Scope и Non-Goals)

| Аспект | Решение | Обоснование |
| --- | --- | --- |
| Изменение поведения продукта `wishenka/` | Исключено (Out of scope) | Задача относится к тестовой инфраструктуре; продуктовые швы не требуются |
| Ослабление или удаление тестовых утверждений | Запрещено (C-1) | Скорость достигается инфраструктурой, а не ценой качества проверок |
| Исключение медленных тестов из `make test` | Запрещено (F-5) | Все тесты, включая браузерные и многопроцессные, остаются в основном прогоне |
| Изменение/увеличение таймаутов и автоповторы | Запрещено (N-4, D8) | Маркеры `pytest.mark.timeout` сохраняются; нестабильность устраняется по первопричине |
| Аппаратный апгрейд или настройка внешнего CI | Исключено (Out of scope) | Бюджет 120 с нормирован на эталонную машину (6 ядер, 5909 MiB ОЗУ); CI использует ту же схему без гарантированного порога |
| Устранение продуктовых багов, выявленных параллелизмом | Выносится отдельно (Q-4) | По итогам верификации новых продуктовых дефектов не обнаружено |

## 2. Функциональные требования и пользовательские сценарии

### 2.1. Пользовательские сценарии

- **UC-01. Быстрый прогон перед коммитом:** разработчик запускает `make test` или `make check` без дополнительных аргументов; полный набор из 814 тестов (798 исходных и 16 контрактных) выполняется параллельно через `pytest-xdist` в быстром хранилище и выдаёт вердикт не позднее 120 с на эталонной машине.
- **UC-02. Отладка в последовательном режиме:** разработчик запускает `make test-serial` или `make test-serial PYTEST_ARGS="tests/test_x.py::test_name"`; тесты идут строго последовательно (`-n 0`) с прямым пошаговым выводом, но используют быстрое хранилище (~114 с на весь набор). Прямой вызов `.venv/bin/pytest` без `-n` также работает последовательно.
- **UC-03. Контроль времени, памяти и совпадения вердиктов:** разработчик или инженер запускает `make test-bench` (или `python -m tests.bench_suite --budget 120 --junit run1.xml --compare run0.xml`), получая сводку с `nproc`, `free -m`, настенным временем, минимумом `MemAvailable`, пиком `/dev/shm` и сверкой множества пройденных тестов.
- **UC-04. Автоматический откат при медленном хранилище:** при запуске `make test` (`-n auto`) на среде без подходящего `tmpfs`, где системный временный каталог не проходит пробу `fsync` (медиана `> 2 мс`), контроллер автоматически выбирает **1 воркер** и выводит в `stderr` предупреждение `WARNING: slow test storage: ...` с подсказкой задать `WISHENKA_TEST_TMPDIR`.
- **UC-05. Добавление новых тестов:** новый тестовый модуль автоматически включается в параллельный прогон без дополнительной регистрации (F-8). Если тесту требуется исключительный ресурс, он обязан использовать пер-тестовую фикстуру (`tmp_path`, порт `0`, `xdist_support.disk_mkdtemp`), а при невозможности — явный маркер `@pytest.mark.xdist_group(name=...)` с переводом `Makefile` на `--dist loadgroup`.
- **UC-06. Диагностика сбоя или зависания:** при ненулевом коде выхода прогона каталоги в `/dev/shm` сохраняются, а в конце сводки pytest печатается путь к ним (`test files kept for diagnosis: ...`). При срабатывании общего лимита `TEST_WALL_LIMIT` (600 с) `Makefile` завершается с кодом 124 или 137 и печатает команду последовательного воспроизведения с `--timeout=120`.

### 2.2. Функциональные требования

| ID | Требование | Поведение и реализация |
| --- | --- | --- |
| F-1 | Быстрый путь по умолчанию | `make test` запускает `pytest -n $(PYTEST_JOBS) --dist loadfile $(PYTEST_ARGS)` под защитой `TEST_TIMEOUT`; `make check` вызывает `analyze test` |
| F-2 | Опора на измерения | Проведён базовый замер `pytest --durations=0` до оптимизаций (`21-baseline-data.md`) и замеры после внедрения |
| F-3 | Последовательный режим | Цель `make test-serial` (`-n 0`) и прямой вызов `pytest` без `-n` выполняют тесты в одном процессе; поддерживается передача конкретных node id через `PYTEST_ARGS` |
| F-4 | Сохранение покрытия | Все 814 тестов (798 исходных + 16 контрактных) собираются и проходят в обоих режимах без новых `skip`, `xfail` или `--deselect` |
| F-5 | Отсутствие исключений медленных тестов | Все медленные, браузерные и многопроцессные модули выполняются в основном `make test` |
| F-6 | Межтестовая изоляция | Изолированы `tmp_path` и `TMPDIR` (быстрое хранилище), профили Chromium и исполняемые заглушки (дисковый каталог), БД по умолчанию (`_isolated_default_database`), порты (`127.0.0.1:0` и `--remote-debugging-port=0`) |
| F-7 | Безопасность подпроцессов и вложенного `make` | Многопроцессные тесты (`spawn`, `tmp_path`) безопасны под нагрузкой; `test_browser_prerequisites.py` работает на исполняемом дисковом каталоге `disk_mkdtemp("prereq")` |
| F-8 | Подключение новых тестов по умолчанию | Распределение `--dist loadfile` автоматически распределяет новые файлы по воркерам без реестров; задокументировано правило для несовместимых тестов |
| F-9 | Прозрачный отчёт об ошибках | При падении теста или крахе воркера xdist печатает имя теста, вывод, трассировку с префиксом `[gwN]` и возвращает ненулевой код выхода |

### 2.3. Разделение временных областей и параметры управления

Система явно разделяет временные файлы на две области, чтобы совместить скорость `tmpfs` с ограничениями Docker (`/dev/shm` по умолчанию 64 MiB и смонтирован с `noexec`):

1. **Быстрое хранилище (`tmpfs`):**
   - `basetemp` для `tmp_path` и `tmp_path_factory`: `/dev/shm/wishenka-pytest-<uid>-<pid>`.
   - `TMPDIR` и `tempfile.tempdir`: `/dev/shm/wishenka-pytest-<uid>-<pid>-tmp` (используется в том числе для `:memory:`-хранилища через `tempfile.mkstemp` в `wishenka/wishlists/store.py`).
2. **Исполняемое дисковое хранилище:**
   - Передаётся через `WISHENKA_TEST_DISK_TMPDIR` (контроллер фиксирует исходный `tempfile.gettempdir()` до подмены `TMPDIR`).
   - Используется для профилей Chromium (до ~100 MiB на воркер) и исполняемых фейковых скриптов браузера в `tests/test_browser_prerequisites.py` (и в контрактном тесте CDP).

### 2.4. Продуктовые и тестовые инварианты

1. **Тождественность вердиктов:** при одинаковом коде множество пройденных тестов при `make test` и `make test-serial` совпадает (814 = 814).
2. **Неизменность БД репозитория:** `Settings()` внутри любого теста без явного `database_url=` указывает на изолированный файл во временном каталоге сессии; `data/wishenka.db` никогда не изменяется.
3. **Запрет скрытия браузерных тестов:** `addopts`, `Makefile` и `.github/workflows/ci.yml` не содержат `-m "not browser"`, `-k ...browser`, `--deselect` или `--ignore` (проверяется существующими тестами в `tests/test_browser_prerequisites.py`).
4. **Отсутствие автоповторов:** плагины повтора тестов (`reruns`, `flaky`) не используются; случайный порядок (`pytest-randomly`) в конфигурации отсутствует.

## 3. Архитектура, компоненты и интерфейсы

### 3.1. Компонентная схема и состав модулей

```mermaid
flowchart TD
    M["Makefile: test / test-serial / test-bench / check"] -->|"pytest -n PYTEST_JOBS --dist loadfile"| P["pytest controller"]
    P -->|"pytest_xdist_auto_num_workers (optionalhook)"| W["xdist_support.plan_workers"]
    P -->|"pytest_configure (tryfirst)"| T["xdist_support.plan_storage + cleanup"]
    P --> G0["worker gw0 .. gwN"]
    T -.->|"basetemp & TMPDIR (/dev/shm)" .-> G0
    G0 --> F1["session: chromium_executable, chromium_browser, migrated_db_template"]
    G0 --> F2["function: tmp_path (tmpfs), _isolated_default_database, uvicorn :0"]
    F1 -.->|"profile on disk (WISHENKA_TEST_DISK_TMPDIR), setpriv pdeathsig"| C["Chromium per worker"]
```

Состав изменённых и добавленных файлов тестовой инфраструктуры:

| Модуль / файл | Назначение | Тип изменения |
| --- | --- | --- |
| `Makefile` | Цели `test`, `test-serial`, `test-bench`, `check`; переменные `PYTEST_JOBS`, `PYTEST_ARGS`, `TEST_WALL_LIMIT`, обёртка `TEST_TIMEOUT` | Изменён |
| `pyproject.toml` | Зависимость `pytest-xdist>=3.6` в `dev`, `tmp_path_retention_policy = "failed"`, сохранение `addopts = "-v --strict-markers"` без `-n` | Изменён |
| `tests/xdist_support.py` | Чистые stdlib-функции выбора воркеров, хранилища, пробы `fsync`, очистки устаревших каталогов и создания дисковых каталогов | Новый |
| `tests/conftest.py` | Хуки контроллера/сессии, фикстуры изоляции БД по умолчанию, дисковых профилей Chromium и их очистки | Изменён |
| `tests/browser_cdp.py` | Ожидание непустого `DevToolsActivePort`, безопасный запуск и принудительная очистка группы процессов Chromium | Изменён |
| `tests/bench_suite.py` | CLI-инструмент замера времени, памяти, использования `/dev/shm` и сравнения JUnit-множеств | Новый |
| `tests/test_browser_prerequisites.py` | Переопределение фикстуры `tmp_path` на исполняемый дисковый каталог `disk_mkdtemp("prereq")` | Изменён |
| `tests/test_wishlist_management_browser.py` | Перевод собственного запуска Chromium на `chromium_profile_dir`, `launch_chromium`, `read_debug_port`, `stop_chromium` | Изменён |
| `tests/test_wishlist_sections_ui.py` | Перевод собственного запуска Chromium на `chromium_profile_dir`, `launch_chromium`, `read_debug_port`, `stop_chromium` | Изменён |
| `tests/test_parallel_run_contract.py` | 13 контрактных тестов (16 параметризованных кейсов) на API, конфигурацию, гонку CDP, БД и запуск без xdist | Новый |

### 3.2. Контракты модулей и интерфейсов

#### Конфигурация `Makefile` и `pyproject.toml`

- Переменные `Makefile`:
  - `PYTEST_JOBS ?= auto`
  - `PYTEST_ARGS ?=`
  - `TEST_WALL_LIMIT ?= 600`
  - `TEST_TIMEOUT := $(shell command -v timeout >/dev/null 2>&1 && echo "timeout -k 30 $(TEST_WALL_LIMIT)")`
- Цели `Makefile`:
  - `test: deps` — запускает `$(TEST_TIMEOUT) $(PYTEST) -n $(PYTEST_JOBS) --dist loadfile $(PYTEST_ARGS)` и при коде возврата `124` или `137` печатает диагностическую подсказку в `stderr`, сохраняя исходный код возврата.
  - `test-serial: deps` — запускает `$(PYTEST) -n 0 $(PYTEST_ARGS)`.
  - `test-bench` — запускает `$(PYTHON) -m tests.bench_suite --budget 120`.
  - `check: analyze test` — без изменений.
- Настройки `pyproject.toml`:
  - `[project.optional-dependencies].dev` включает `"pytest-xdist>=3.6"`.
  - `[tool.pytest.ini_options]`: `addopts = "-v --strict-markers"` (без `-n`), `tmp_path_retention_policy = "failed"`.

#### Модуль `tests/xdist_support.py` (без импорта `pytest`)

- Константы по умолчанию: `DEFAULT_FAST_BASE = Path("/dev/shm")`, `MIN_FREE_MB = 48`, `RESERVE_MB = 1200`, `PER_WORKER_MB = 600`, `FSYNC_SAMPLES = 5`, `FSYNC_FAST_SECONDS = 0.002`, `BASE_PREFIX = "wishenka-pytest-"`.
- Переменные окружения: `ENV_FAST_TMPDIR = "WISHENKA_TEST_TMPDIR"`, `ENV_DISK_TMPDIR = "WISHENKA_TEST_DISK_TMPDIR"`, `ENV_WORKERS = "WISHENKA_TEST_WORKERS"`, `ENV_DISK_VALUE = "disk"`.
- Структура данных `StoragePlan` (`@dataclass(frozen=True)`): поля `basetemp: Path | None`, `tmpdir: Path | None`, `fast: bool`.
- Публичные функции:
  - `choose_workers(cpu: int, mem_mb: int, fast_storage: bool, reserve_mb: int = 1200, per_worker_mb: int = 600) -> int` — при `fast_storage=False` возвращает `1`; иначе `max(1, min(cpu, (mem_mb - reserve_mb) // per_worker_mb))`.
  - `pick_fast_basetemp(candidate: Path = DEFAULT_FAST_BASE, min_free_mb: int = 48) -> Path | None` — проверяет существование каталога, права `os.W_OK | os.X_OK` и свободное место (`>= min_free_mb` MiB); возвращает путь `<candidate>/wishenka-pytest-<uid>-<pid>` (без создания на диске) либо `None`.
  - `fsync_is_fast(path: Path) -> bool` — выполняет 5 записей по 4096 байт во временный файл с `flush()` и `os.fsync()`, возвращает `True`, если медианное время `<= 0.002` с.
  - `available_memory_mb(meminfo: Path = Path("/proc/meminfo"), cgroup_max: Path = Path("/sys/fs/cgroup/memory.max")) -> int` — считывает `MemAvailable` в MiB и при конечном числе в `memory.max` берёт минимум; при недоступности возвращает `10**6`.
  - `cpu_count() -> int` — возвращает `len(os.sched_getaffinity(0))`.
  - `plan_storage(environ: Mapping[str, str]) -> StoragePlan` — проверяет `$WISHENKA_TEST_TMPDIR` (если не `"disk"`) или `/dev/shm` через `pick_fast_basetemp`; при успехе задаёт `basetemp` и `tmpdir` (`<basetemp>-tmp`) с `fast=True`, иначе выполняет `fsync_is_fast(Path(tempfile.gettempdir()))` и возвращает `StoragePlan(None, None, fast)`.
  - `plan_workers(environ: Mapping[str, str]) -> tuple[int, str | None]` — при положительном числовом значении `WISHENKA_TEST_WORKERS` возвращает `(int(override), None)` (невалидные или `0` игнорируются); иначе рассчитывает `choose_workers(...)` и при `not storage.fast` возвращает `SLOW_STORAGE_WARNING`.
  - `remove_stale(base: Path) -> list[Path]` и `remove_stale_disk_dirs(base: Path) -> list[Path]` — удаляют каталоги текущего `uid` вида `wishenka-pytest-<uid>-<pid>*` и `wk-<kind>-<pid>-*`, чей процесс не отвечает на `os.kill(pid, 0)` (`ProcessLookupError`).
  - `disk_mkdtemp(kind: str) -> Path` — создаёт каталог `wk-<kind>-<pid>-*` в `WISHENKA_TEST_DISK_TMPDIR` или `tempfile.gettempdir()`.

#### Хуки и фикстуры `tests/conftest.py`

- `pytest_xdist_auto_num_workers(config)` (`@pytest.hookimpl(optionalhook=True)`) — вызывается при `-n auto` до `pytest_configure`; при наличии предупреждения от `plan_workers` выводит `WARNING: ...` в `stderr`; `optionalhook=True` гарантирует работу без установленного или при отключённом `xdist` (`-p no:xdist`).
- `pytest_configure(config)` (`@pytest.hookimpl(tryfirst=True)`) — исполняется только в контроллере (`not hasattr(config, "workerinput")`):
  - экспортирует `WISHENKA_TEST_DISK_TMPDIR`;
  - вызывает `remove_stale_disk_dirs`;
  - при наличии быстрого плана и отсутствии пользовательского `--basetemp` вызывает `remove_stale`, создаёт `plan.tmpdir`, задаёт `TMPDIR`, `tempfile.tempdir`, `config.option.basetemp` и сохраняет оба пути в `config.stash[_RUN_DIRS]`.
- `pytest_sessionfinish(session, exitstatus)` — сохраняет `_EXIT_STATUS` и взводит `faulthandler.dump_traceback_later(120, exit=False)`.
- `pytest_unconfigure(config)` — отменяет таймер `faulthandler`; при `_EXIT_STATUS == 0` удаляет каталоги из `_RUN_DIRS`.
- `pytest_terminal_summary(terminalreporter, exitstatus, config)` — в контроллере при `_RUN_DIRS` и `exitstatus != 0` выводит строку сохранённого пути диагностики.
- Фикстуры:
  - `_default_db_dir` (`session`) и `_isolated_default_database` (`autouse=True`, `function`) — выставляют `WISHENKA_DATABASE_URL` и `WISHENKA_SQLITE_DB_PATH` на уникальный файл `<uuid4>.db`.
  - `chromium_profile_dir` (`function`) и `chromium_browser` (`session`) — размещают профили Chromium на диске через `disk_mkdtemp("chromium")` с очисткой в `finally`.
  - `migrated_db_template` (`session`) — создаёт один предмигрированный файл БД на воркер в `tmp_path_factory`.

#### Помощники CDP и управление процессами в `tests/browser_cdp.py`

- `read_debug_port(port_file: Path) -> int | None` — читает `DevToolsActivePort` и возвращает порт как `int` только тогда, когда первая строка не пуста и после `.strip()` состоит из цифр (`isdigit()`).
- `launch_chromium(command: Sequence[str]) -> subprocess.Popen[bytes]` — запускает Chromium через `setpriv --pdeathsig KILL` (если `setpriv` найден в `PATH`), с `start_new_session=True` и без `preexec_fn`; регистрирует процесс в `_LIVE_BROWSERS`.
- `stop_chromium(process)` — исключает из `_LIVE_BROWSERS`, выполняет `terminate()` с ожиданием до `TERMINATE_TIMEOUT = 5.0` с, затем `kill()` (до 5.0 с) и `os.killpg(process.pid, signal.SIGKILL)`.
- `_kill_live_browsers()` — зарегистрирован в `atexit`, прибивает группы процессов всех незакрытых браузеров.
- `CdpBrowser._launch()` — вызывает `self.stop()`, ждёт готовности порта через `read_debug_port` с шагом `0.05` с в пределах `10` с и проверяет досрочное завершение процесса.

#### Инструмент замеров `tests/bench_suite.py`

- `JunitResult(passed: frozenset[str], failed: frozenset[str], skipped: int)` и `parse_junit(path: Path) -> JunitResult`.
- `Sampler(threading.Thread)` — раз в `1.0` с фиксирует минимум `MemAvailable` и пик использования `/dev/shm`.
- `main(argv)` — принимает `--budget` (по умолчанию `120.0`), `--junit`, `--compare`, `--target` (по умолчанию `test`); запускает `make <target> PYTEST_ARGS=--junitxml=<junit>` и возвращает ненулевой код при ошибке `make`, падениях, пропусках, несовпадении множеств в `--compare`, отсутствии JUnit-файла или превышении бюджета.

### 3.3. Жизненный цикл прогона и переходы состояний

1. **Инициализация контроллера (`pytest_xdist_auto_num_workers` → `pytest_configure`):** определяется число воркеров (при `-n auto`), фиксируется дисковый каталог для профилей/заглушек, очищаются старые каталоги завершённых процессов, контроллер переключает `basetemp` и `TMPDIR` на `tmpfs` (если доступен и не передан `--basetemp`).
2. **Подъём воркеров (`gw0..gwN`):** воркеры наследуют `TMPDIR` и `WISHENKA_TEST_DISK_TMPDIR` от контроллера; распределение `--dist loadfile` назначает каждому воркеру целые тестовые модули. На первом тесте, требующем браузерной инфраструктуры, воркер однократно поднимает `chromium_browser` и создаёт `migrated_db_template`.
3. **Исполнение тестов:** каждый тест получает собственный каталог `tmp_path` на `tmpfs` (кроме `test_browser_prerequisites.py`, где `tmp_path` переопределён на `disk_mkdtemp("prereq")`), изолированный путь БД по умолчанию и случайные порты `127.0.0.1:0` / `--remote-debugging-port=0`.
4. **Штатное завершение или сбой:**
   - При `exitstatus == 0` контроллер удаляет каталоги `_RUN_DIRS` в `pytest_unconfigure`; `tmp_path` удаляется по политике `tmp_path_retention_policy = "failed"`.
   - При `exitstatus != 0` быстрые каталоги сохраняются, а `pytest_terminal_summary` печатает путь для разбора.
   - При зависании завершения сессии через 120 с срабатывает `faulthandler.dump_traceback_later`.
   - При внешнем `SIGKILL` или срабатывании `TEST_WALL_LIMIT` ядро Linux через `setpriv --pdeathsig KILL` завершает дочерние процессы Chromium, а оставшиеся каталоги в `/dev/shm` и `/tmp/wk-*` автоматически удаляются при следующем старте контроллера.

## 4. Нефункциональные требования, безопасность и наблюдаемость

### 4.1. Производительность, ресурсы и ограничения

- **Временной бюджет (N-1):** на эталонной машине (6 ядер, 5909 MiB ОЗУ, `/dev/shm` 64 MiB `noexec`) полный прогон `make test` укладывается в **≤ 120 с** общего времени (измерено: **48.9–55.3 с** wall-clock в 6 параллельных прогонах при **44.1–48.9 с** времени pytest).
- **Потребление памяти (N-3):**
  - Формула ограничения воркеров `min(cpu, (MemAvailable - 1200) // 600)` гарантирует резерв ОЗУ 1200 MiB и закладывает 600 MiB на воркер с Chromium.
  - Фактический расход при 6 воркерах: снижение `MemAvailable` на **2.7–2.9 GiB** (~450–519 MiB на воркер), минимальный остаток `MemAvailable` — **1908 MiB** в финальной серии (0 срабатываний OOM-killer).
  - Пиковое использование `/dev/shm`: **3.8–5.6 MiB** при доступном минимуме `MIN_FREE_MB = 48` MiB и дефолте Docker 64 MiB.
- **Таймауты и ограниченные ожидания (N-4):**
  - Все 814 тестов имеют явный маркер `pytest.mark.timeout` (0 тестов без маркера).
  - Все новые ожидания ограничены константными дедлайнами: `10` с на порт CDP в `CdpBrowser._launch`, `8` с на старт сервера/порта в двух браузерных тестах, `TERMINATE_TIMEOUT = 5.0` с (максимум дважды) в `stop_chromium`, `10` с для служебных подпроцессов в `bench_suite.py`.
  - Максимальное зафиксированное отношение `duration / timeout` при параллельном прогоне составило **0.174** (`test_receipt_is_not_capped_by_occupied_units`, 10.5 с из 60 с).
- **Пороги в коде (не настраиваются переменными окружения):** `FSYNC_SAMPLES = 5`, `FSYNC_FAST_SECONDS = 0.002`, `MIN_FREE_MB = 48`, `RESERVE_MB = 1200`, `PER_WORKER_MB = 600`, `SESSION_END_DUMP_SECONDS = 120`, `TERMINATE_TIMEOUT = 5.0`. Настраивается только `TEST_WALL_LIMIT` (по умолчанию `600` с).
- **Платформенные ограничения:** целевая платформа для параллельного запуска — **Linux** (включая Docker и WSL). На macOS отсутствует `os.sched_getaffinity`, на нативной Windows отсутствуют `os.getuid`, `os.killpg` и `os.sched_getaffinity`.

### 4.2. Безопасность, приватность и гигиена среды

- **Отсутствие утечек секретов и персональных данных:** в путях диагностики `/dev/shm/wishenka-pytest-<uid>-<pid>` и `wk-<kind>-<pid>-*` фигурируют только числовые `uid` и `pid` (без имени пользователя и домашнего каталога). `BROWSER_TEST_SECRET` в диагностические журналы не выводится.
- **Безопасный спаун процессов:** в `launch_chromium` принципиально не используется `preexec_fn` (небезопасный при активных потоках uvicorn/asyncio); вместо него применяются `setpriv --pdeathsig KILL` и `start_new_session=True`.
- **Отсутствие остаточных артефактов (N-6):** после успешного прогона `/dev/shm` пуст, каталоги `wk-*` отсутствуют, процессы Chromium не запущены, файл `data/wishenka.db` не изменён.

### 4.3. Наблюдаемость и диагностика

Продуктовый экспортёр метрик или агрегатор логов к тестовой инфраструктуре не применяется; диагностика поступает в вывод терминала (`stdout`/`stderr`), отчёты `pytest` и отчёт `make test-bench`.

| Канал и источник | Условие срабатывания | Сообщение / метрика и уровень |
| --- | --- | --- |
| `stderr`, `tests/conftest.py` (`pytest_xdist_auto_num_workers`) | `-n auto` и медленное хранилище | `WARNING`: `WARNING: slow test storage: running with one worker; expected about 16 minutes; set WISHENKA_TEST_TMPDIR to a fast directory (for example /dev/shm)` |
| `stdout`, шапка `pytest-xdist` | Любой параллельный запуск | `NOTICE`: `created: N/N workers` — фактическое число воркеров после ограничения |
| `pytest_terminal_summary`, `tests/conftest.py` | Контроллер, `exitstatus != 0` и активен быстрый `basetemp` | `NOTICE` в конце отчёта: `test files kept for diagnosis: <path> (the next run removes it once this process is gone)` |
| `stderr`, `tests/conftest.py` (`faulthandler`) | Зависание завершения сессии `> 120` с | `ERR`: дамп стеков всех потоков в `stderr` |
| `stderr`, `Makefile` (`test`) | Прерывание по `TEST_WALL_LIMIT` (`124`) или `SIGKILL` (`137`) | `ERR`: сообщение об остановке и команда воспроизведения `make test-serial PYTEST_ARGS=--timeout=120 ...` с сохранением кода выхода |
| Отчёт падения браузерного теста | Сбой в браузерном тесте | `ERR`: секция `Page N diagnostics`, файлы `diagnostics-N.txt` и `failure-N.png` в сохраняемом `tmp_path` |
| `stdout`, `tests/bench_suite.py` (`make test-bench`) | Явный запуск бенчмарка | `INFO` / `RESULT`: `nproc`, `free -m`, команда, `exit code`, `wall time` против бюджета, минимум `MemAvailable`, пик `/dev/shm`, счётчики тестов, до 10 `FAILED: <id>`, причина при `skipped`, итог `--compare`, `RESULT: OK/FAIL` |

## 5. Верификация и критерии приёмки

### 5.1. Тестовые сценарии и проверки

1. **Контрактный набор `tests/test_parallel_run_contract.py` (16 кейсов, ~0.5 с, без Chromium и сети):**
   - Проверка команд `Makefile`: `make -n test` содержит `-n` и `--dist`; `make -n test-serial` содержит `-n 0`, объявлена `.PHONY` и присутствует в `make help`; `check` зависит от `analyze test`.
   - Проверка `pyproject.toml`: `pytest-xdist` указан в `dev`, `tmp_path_retention_policy == "failed"`, `addopts` не содержит `-n`.
   - Проверка `tests/xdist_support.py`: `choose_workers` для `(6, 4900, True) in {5, 6}`, `(6, 1500, True) == 1`, `(2, 8000, True) == 2`, `(6, 4900, False) == 1`; `pick_fast_basetemp` отклоняет отсутствующий, переполненный или недоступный для записи каталог и формирует уникальное имя с `pid`; `fsync_is_fast(Path("/dev/shm"))` возвращает `True` быстрее `1.0` с.
   - Проверка гонки CDP (`test_cdp_launch_waits_for_complete_port_file`): фейковый Chromium в исполняемом каталоге `disk_tmp_path` создаёт пустой `DevToolsActivePort`, ждёт `0.3` с и затем дописывает порт `45678`; `CdpBrowser.start` не падает с `IndexError` и получает `http://127.0.0.1:45678`.
   - Проверка изоляции БД (`test_default_settings_do_not_point_at_repository_database`): `Settings().database_url` и `Settings().sqlite_db_path` не указывают на `data/wishenka.db`.
   - Проверка опциональности хука (`test_worker_cap_hook_is_registered_as_optional` и `test_pytest_collects_without_xdist`): `pytest -p no:xdist --collect-only -q tests/test_infra.py` завершается с кодом `0`.
2. **Интеграционные и нагрузочные сценарии модулей зоны риска (C-4):**
   - `tests/test_browser_prerequisites.py` (36 тестовых функций; 13 в отчёте фаз > 5 мс базового замера, 2.0 с на `tmpfs`), `tests/test_shared_inventory_multiprocess.py` (13 тестов, до 25.2 с под 6 воркерами), `tests/test_booking_ceiling_r5.py` (6 тестов, до 19.6 с под 6 воркерами), `tests/test_wishlist_migrations_concurrency.py` (2 теста, до 10.8 с под 6 воркерами), `tests/test_receipt_concurrency.py` (3 теста, 2.2 с на `tmpfs`), а также все браузерные модули успешно проходят в параллельном и последовательном режимах.
3. **Проверка отказоустойчивости и диагностики (Step 4, Step 6):**
   - Принудительное `kill -9` контроллера/воркера во время браузерного теста (дважды): 0 оставшихся процессов Chromium; остаточные каталоги `/dev/shm/wishenka-pytest-*` и `/tmp/wk-chromium-*` удаляются при следующем запуске.
   - Откат на медленное хранилище (`WISHENKA_TEST_TMPDIR=/nonexistent`): 1 воркер и `WARNING: slow test storage: ...`.
   - Превышение стенного лимита (`TEST_WALL_LIMIT=3`): код `124` и подсказка `Makefile`.
   - Статический анализ (`make analyze`): `ruff check`, `ruff format --check` и `mypy` по 136 файлам без ошибок.
   - Правило таймаутов: `pytest --collect-only -q -m "not timeout" -p no:cacheprovider -n 0` → `814 deselected` (0 тестов без маркера `timeout`).

### 5.2. Результаты приёмки и соответствие DoD

На эталонной машине (6 ядер `nproc`, 5909 MiB ОЗУ `free -m`, `/dev/shm` 64 MiB `noexec`) зафиксированы следующие измерения:

| Прогон / проверка | Время (wall / pytest) | Результат | Память / `/dev/shm` |
| --- | --- | --- | --- |
| Базовый прогон до задачи (последовательно, диск) | — / 971.7 с | 798 passed | Снижение `MemAvailable` на 744 MiB |
| Параллельно, диск (`-n 6 --dist load`) — эксперимент I1 | — / 981 с | 28 failed, 9 errors, 763 passed | Отказ от параллелизма на медленном диске |
| Серия DoD Step 4: 3 + 3 прогона `make test` (`loadfile`) | 48.9–55.3 с / 47.5–48.9 с | 814 passed в каждом, наборы равны | Мин. `MemAvailable` 1908 MiB, `/dev/shm` 3.8–5.3 MiB |
| Повторные прогоны Step 6 и Step 7 (`make test`) | 50.1 с / 45.9 с (Step 6); — / 44.14 с (Step 7) | 814 passed | `/dev/shm` пуст, 0 процессов Chromium |
| Последовательный прогон (`make test-serial`) | 119 с / 114.08 с | 814 passed, множество равно `make test` | — |
| Единый шлюз качества (`make check`) | 51 с / 45.4 с | `analyze` чист (136 файлов), 814 passed | — |

Соответствие критериям приёмки (Definition of Done):

| Критерий DoD | Статус | Подтверждение |
| --- | --- | --- |
| 1. `make test` работает параллельно и укладывается в ≤ 120 с на эталонной машине | Выполнено | 48.9–55.3 с wall через `make test-bench` при бюджете 120 с |
| 2. Серия `K = 3` (и повторная серия из 3) без падений и расхождений | Выполнено | 6 финальных прогонов по 814 passed, 0 failed, множества тестов тождественны |
| 3. Последовательный режим даёт тот же набор вердиктов | Выполнено | `make test-serial` — 814 passed за 119 с, множество совпадает с параллельным |
| 4. Полнота набора и неизменность утверждений | Выполнено | 798 исходных + 16 контрактных = 814 тестов; diff тестовых модулей затронул только фикстуры и запуск Chromium |
| 5. Замеры `--durations` до и после | Выполнено | Зафиксированы в `21-baseline-data.md` и аудите Step 4 / Step 7 |
| 6. Безопасность модулей зоны риска C-4 | Выполнено | Все 4 многопроцессных модуля и `test_browser_prerequisites.py` стабильны параллельно |
| 7. Маркеры `timeout` сохранены, лимиты не повышены, нет ретраев | Выполнено | 814 из 814 с маркером `timeout`; худшее отношение `duration/limit` = 0.174 |
| 8. Пик памяти зафиксирован, OOM отсутствует | Выполнено | Пиковое потребление ~2.7–2.9 GiB, минимум `MemAvailable` 1908 MiB, `oom_kill = 0` |
| 9. Нет остаточных процессов, файлов и занятых портов | Выполнено | `/dev/shm` пуст, `wk-*` удалены, Chromium не запущен, `data/wishenka.db` не изменён |
| 10. `make analyze` зелёный и документация обновлена | Выполнено | `make analyze` без замечаний; обновлены `doc/dev/testing.md`, `doc/dev/infrastructure.md`, `doc/dev/verification-matrix.md` |

### 5.3. Известные ограничения и дальнейшие задачи

По итогам анализа технического долга (`ai-tasks/WISHENKA-166/60-tech-debt.md`) критических блокеров закрытия задачи нет. Зафиксированные ограничения и вынесенные задачи сопровождения:

- **Зависимость от `tmpfs` и критический путь (`D-7` → `WISHENKA-170`, `D-8` → `WISHENKA-171`):** ускорение достигнуто за счёт переноса файлов в `tmpfs`, тогда как каждый тест по-прежнему выполняет полную миграцию БД. На машинах без `tmpfs` с медленным `fsync` прогон занимает ~16 минут. Под `--dist loadfile` критический путь определяется модулями `test_shared_inventory_multiprocess.py` (~25.2 с) и `test_booking_ceiling_r5.py` (~19.6 с).
- **Неподтверждённость бюджета на CI и Python 3.12 (`D-9` → `WISHENKA-172`, `D-17` → `WISHENKA-175`):** время на `ubuntu-latest` (2–4 vCPU) оценочно составляет 55–110 с и требует фактического замера с логированием выбранного плана воркеров и хранилища; верификация выполнялась на Python 3.13.5 при целевой версии в CI 3.12.
- **Платформенная привязка к Linux и поведение `test-bench` (`D-10`, `D-18` → `WISHENKA-173`):** `xdist_support.py`, `browser_cdp.py` и `bench_suite.py` используют Linux-специфичные вызовы и команды (`os.sched_getaffinity`, `os.getuid`, `os.killpg`, `/proc/meminfo`, `nproc`, `free -m`); цель `test-bench` не зависит от `deps`.
- **Покрытие вспомогательных механизмов и мелкие дефекты (`D-1`, `D-2`, `D-5`, `D-13` → `WISHENKA-167`; `D-3`, `D-4` → `WISHENKA-168`; `D-6` → `WISHENKA-169`):**
  - Не покрыты прямыми модульными тестами ветки `read_debug_port`, завершение группы процессов Chromium (`setpriv`, `killpg`, `atexit`), `remove_stale*`, `plan_storage`/`plan_workers`, подсказка `Makefile` и `parse_junit`.
  - В `remove_stale_disk_dirs` возможен `FileNotFoundError` при гонке одновременного старта двух контроллеров, а при общем `/dev/shm` между разными pid-пространствами возможна очистка живого каталога; `WISHENKA_TEST_WORKERS` молча игнорирует некорректные и нулевые значения.
  - При пустой выборке тестов (код возврата `5`, например при `-k` без совпадений) `pytest_terminal_summary` выводит ложное сообщение `test files kept for diagnosis`, а пустой каталог остаётся до следующего прогона (`WISHENKA-169`).
- **Настраиваемость порогов и `faulthandler_timeout` (`D-11`, `D-12` → `WISHENKA-174`):** пороговые константы не вынесены в настройки; таймер `faulthandler` взводится только на этапе `pytest_sessionfinish`, поэтому зависание на этапе коллекции или блокировка контроллера ожидают срабатывания `TEST_WALL_LIMIT = 600` с.
- **Прочее (`D-14`, `D-15`, `D-16`):** документация (`D-14`) выполнена на Шаге 8; текстовое расхождение в `40-development.md` (`D-15`) исправлено; неучтённый файл `core` (`D-16`) относится к существующей задаче `WISHENKA-126`.
