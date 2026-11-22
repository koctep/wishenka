# Спецификация: WISHENKA-3 — Каркас репозитория, Makefile, линтеры, CI/CD и тестовая среда

**Статус:** реализовано  
**Связанная задача:** WISHENKA-3  
**Стек и инструменты:** Python 3.12+, FastAPI, Uvicorn, aiogram v3, Jinja2, HTMX, SQLite (WAL), GNU Make, Ruff, Mypy, Pytest, Docker, GitHub Actions  

---

## 1. Назначение и бизнес-цель

### 1.1. Постановка проблемы

На момент завершения концептуального (`WISHENKA-1`) и высокоуровневого архитектурного (`WISHENKA-2`) проектирования сервиса **Telegram Wishlist Service («Вишенка»)** в репозитории отсутствовали физический каркас Python-приложения, унифицированные команды разработки, средства автоматического контроля качества, тестовый контур и конфигурация среды выполнения.

Без этого фундамента разработка прикладных модулей — модели вишлистов (`WISHENKA-4`), механизма бронирования подарков (`WISHENKA-5`), подсистемы уведомлений (`WISHENKA-6`) и интерфейса Telegram Mini App (`WISHENKA-7`) — сталкивалась со следующими рисками:

- отсутствие единого стандарта оформления и статической проверки типов кода;
- невозможность регулярного регрессионного тестирования с защитой от зависаний;
- расхождение локальных окружений разработчиков и среды развертывания;
- отсутствие автоматического барьера качества (Quality Gate) перед слиянием изменений.

### 1.2. Бизнес-цель и ценность

Задача **WISHENKA-3** формирует стандартизированную инженерную основу проекта и обеспечивает следующую системную и продуктовую ценность:

1. **Ускорение итераций разработки (Time-to-Market):** единый фасад команд (`Makefile`) и готовый каркас пакета устраняют инфраструктурные барьеры при старте разработки новых продуктовых функций.
2. **Раннее предотвращение дефектов:** автоматический Quality Gate (`make check`) в CI/CD блокирует попадание синтаксических ошибок, нарушений типизации и регрессий в основные ветки репозитория.
3. **Защита критических бизнес-инвариантов на этапе анализа кода:** строгая статическая типизация (`mypy` в режиме `strict = true`) снижает риск случайной утечки закрытых полей бронирования в модели и ответы, доступные получателю подарка («принцип сюрприза»).
4. **Воспроизводимость сред:** декларативное управление зависимостями (PEP 621) и контейнеризация через Docker / Docker Compose гарантируют одинаковую среду выполнения на локальных машинах, в CI-раннерах и при деплое.
5. **Надежная обратная связь при тестировании:** конфигурация `pytest-asyncio` и обязательные таймауты `pytest-timeout` исключают зависание тестовых прогонов.

### 1.3. Границы задачи (Scope и Non-Goals)

В объем **WISHENKA-3** входят:

- формирование структуры каталогов репозитория (`wishenka/`, `tests/`, `doc/dev/`);
- спецификация метаданных пакета, зависимостей и инструментов качества в `pyproject.toml`;
- реализация корневого `Makefile` с полным набором команд жизненного цикла;
- настройка линтера/форматтера `Ruff`, строгого статического анализатора `Mypy` и тестовой среды `Pytest`;
- создание базового каркаса FastAPI-приложения с загрузкой конфигурации (`Settings`), структурированным логированием и эндпоинтом `/healthz`;
- настройка локальной контейнеризации (`Dockerfile`, `docker-compose.yml`), CI-пайплайна (`.github/workflows/ci.yml`), правил `.gitignore`, `README.md` и руководства [infrastructure.md](../../doc/dev/infrastructure.md).

В объем **WISHENKA-3** **не входят** (реализуются в последующих задачах):

- доменные сущности, ORM-модели и миграции вишлистов, желаний и участников (`WISHENKA-4`);
- бизнес-логика бронирования подарков и изоляции тайны сюрприза (`WISHENKA-5`);
- фоновый воркер доставки уведомлений и интеграция с Telegram Bot API (`WISHENKA-6`);
- шаблоны и пользовательские экраны Telegram Mini App (`WISHENKA-7`);
- продуктовая инфраструктура развертывания (Kubernetes, TLS-терминация, внешние коллекторы метрик).

---

## 2. Функциональные требования и пользовательские сценарии

### 2.1. Фасад команд жизненного цикла (`Makefile`)

Корневой `Makefile` предоставляет унифицированный интерфейс для разработчиков, AI-агентов и CI-раннеров. Все команды работают через локальное виртуальное окружение `.venv`.

| Команда | Входные зависимости | Поведение и выходной результат |
| --- | --- | --- |
| `make help` | — | Действие по умолчанию (`.DEFAULT_GOAL`); выводит отсортированный перечень целей и описаний из комментариев `##` |
| `make venv` | Системный `python3` | Создает каталог `.venv` (если отсутствует) и обновляет `pip` |
| `make deps` | `venv` | Устанавливает пакет в editable-режиме с инструментами разработки: `pip install -e ".[dev]"` |
| `make build` | `deps` | Проверяет синтаксис и компилируемость байткода: `python -m compileall wishenka tests` |
| `make analyze` | `deps` | Запускает `ruff check`, `ruff format --check` и `mypy` по каталогам `wishenka` и `tests`; падает при любой ошибке |
| `make format` | `deps` | Автоматически форматирует код (`ruff format`) и применяет безопасные автоисправления (`ruff check --fix`) |
| `make test` | `deps` | Запускает `pytest` по каталогу `tests/` с подробным отчетом и строгой проверкой маркеров |
| `make check` | `analyze`, `test` | Единый Quality Gate: сначала выполняет `analyze`, затем `test`; возвращает ненулевой код при любом сбое |
| `make run` | `deps` | Запускает локальный сервер разработки `uvicorn wishenka.main:app --host 0.0.0.0 --port 8000 --reload` |
| `make clean` | — | Удаляет кэши `.pytest_cache`, `.ruff_cache`, `.mypy_cache`, `__pycache__`, `*.egg-info`, `build`, `dist`, `.coverage` |

### 2.2. Пользовательские и системные сценарии

**UC-01. Быстрый старт и локальный запуск (US-1):** разработчик клонирует репозиторий и выполняет `make deps`, затем `make run`. Система создает `.venv`, устанавливает зависимости и запускает ASGI-сервер на `0.0.0.0:8000` с активной пробой `GET /healthz`.

**UC-02. Контроль качества и форматирования кода (US-2):** после правки исходников разработчик вызывает `make format` для приведения стиля к стандарту, а перед отправкой изменений — `make analyze` или `make check`. Любое нарушение правил `Ruff` или строгой типизации `Mypy` останавливает выполнение с кодом ошибки.

**UC-03. Автоматизированный запуск тестов с защитой от зависаний (US-3):** разработчик запускает `make test`. Тестовый раннер автоматически выполняет синхронные и асинхронные тесты (`asyncio_mode = "auto"`) и принудительно завершает тест при превышении заданного лимита времени (`pytest-timeout`).

**UC-04. Автоматический контроль качества в CI (US-4):** при событии `push` или `pull_request` в ветки `main` и `master` GitHub Actions поднимает раннер `ubuntu-latest` с Python `3.12`, устанавливает зависимости (`make deps`) и выполняет `make check`. Провал любого шага блокирует слияние изменений.

**UC-05. Изолированный запуск в контейнере (US-5):** разработчик или DevOps-инженер выполняет `docker compose up --build`. Собирается multi-stage образ, сервис запускается под непривилегированным пользователем с сохранением файлов SQLite в томе `sqlite_data` и регулярной проверкой `HEALTHCHECK`.

### 2.3. Базовые поведенческие требования к приложению и среде

- **Загрузка конфигурации:** параметры приложения читаются с приоритетом: переменные окружения с префиксом `WISHENKA_` → файл `.env` в корне проекта → значения по умолчанию в `Settings`. Неизвестные переменные окружения игнорируются (`extra="ignore"`).
- **Проверка работоспособности (Healthcheck):** эндпоинт `GET /healthz` доступен без авторизации и возвращает HTTP `200 OK` с JSON-телом `{"status": "ok"}`.
- **Точка входа сервера:** импорт `wishenka.main` подготавливает настройки, инициализирует логирование и создает экземпляр `app = create_app(settings)`; вызов `main()` запускает `uvicorn` с автоматическим `reload` при `settings.debug` или `settings.environment == "development"`.

### 2.4. Ключевые инфраструктурные инварианты

1. **Fail-fast Quality Gate:** цель `make check` выполняет статический анализ (`analyze`) строго до тестов (`test`); при ошибке линтинга или типизации тестовый прогон не запускается.
2. **Обязательность явных таймаутов в тестах:** каждый тестовый модуль или тест обязан явно ограничивать время исполнения через `pytest-timeout` (`pytestmark = pytest.mark.timeout(10)` или маркер на функции).
3. **Строгая типизация рабочего кода:** все функции и методы внутри пакета `wishenka/` обязаны иметь полные аннотации аргументов и возвращаемых значений.
4. **Гигиена системы контроля версий:** `.gitignore` гарантирует исключение виртуальных окружений, байткода, кэшей анализаторов, локальных файлов `.env*` и файлов базы данных SQLite (`*.db`, `*.db-wal`, `*.db-shm`, `*.sqlite`, `*.sqlite3`).
5. **Совместимость логирования с тестовым захватом:** `configure_logging()` удаляет только прямые экземпляры `logging.StreamHandler` (`type(existing_handler) is logging.StreamHandler`), не затрагивая обработчики `pytest` (`caplog`).

---

## 3. Архитектура, компоненты и интерфейсы

### 3.1. Структура репозитория

В рамках **WISHENKA-3** сформирована следующая базовая структура файлов:

```text
.
├── .github/
│   └── workflows/
│       └── ci.yml                 # GitHub Actions CI Quality Gate
├── .gitignore                     # Исключения Git (venv, кэши, SQLite, .env, IDE)
├── Dockerfile                     # Многоэтапная сборка образа на python:3.12-slim
├── Makefile                       # Единый фасад команд жизненного цикла
├── README.md                      # Краткое руководство по быстрому старту
├── docker-compose.yml             # Локальное окружение с томом sqlite_data
├── pyproject.toml                 # Метаданные PEP 621, зависимости, конфиги инструментов
├── doc/
│   └── dev/
│       └── infrastructure.md      # Руководство по инфраструктуре и инструментарию
├── tests/
│   ├── __init__.py
│   ├── test_infra.py              # Тесты пакета, Settings и /healthz
│   └── test_observability.py      # Тесты JsonFormatter, configure_logging и middleware
└── wishenka/
    ├── __init__.py                # Экспорт __version__ = "0.1.0"
    ├── config.py                  # Конфигурация Settings (pydantic-settings)
    ├── logging.py                 # JsonFormatter и configure_logging()
    ├── main.py                    # Точка входа ASGI и функция main()
    └── web/
        ├── __init__.py
        └── app.py                 # create_app(), lifespan, RequestLoggingMiddleware, /healthz
```

### 3.2. Модули, классы и интерфейсы

#### `wishenka/__init__.py`

- Экспортирует строковую константу версии пакета `__version__ = "0.1.0"`.

#### `wishenka/config.py` — класс `Settings(BaseSettings)`

Конфигурация среды исполнения (`env_prefix="WISHENKA_"`, `env_file=".env"`, `extra="ignore"`):

| Поле `Settings` | Переменная окружения | Тип | Значение по умолчанию | Назначение |
| --- | --- | --- | --- | --- |
| `app_name` | `WISHENKA_APP_NAME` | `str` | `"wishenka"` | Имя приложения в FastAPI и метаданных логов |
| `environment` | `WISHENKA_ENVIRONMENT` | `str` | `"development"` | Среда выполнения (`development`, `production`, `test`) |
| `debug` | `WISHENKA_DEBUG` | `bool` | `False` | Флаг отладочного режима FastAPI и reload сервера |
| `log_level` | `WISHENKA_LOG_LEVEL` | `str` | `"INFO"` | Пороговый уровень логирования корневого логгера |
| `log_json` | `WISHENKA_LOG_JSON` | `bool` | `False` | Включение вывода логов в формате JSON Lines |
| `sqlite_db_path` | `WISHENKA_SQLITE_DB_PATH` | `str` | `"data/wishenka.db"` | Путь к файлу базы данных SQLite |
| `database_url` | `WISHENKA_DATABASE_URL` | `str` | `"sqlite+aiosqlite:///data/wishenka.db"` | DSN подключения SQLAlchemy / `aiosqlite` |
| `bot_token` | `WISHENKA_BOT_TOKEN` | `str` | `""` | Токен Telegram Bot API |

#### `wishenka/logging.py` — `JsonFormatter` и `configure_logging`

- **`JsonFormatter(logging.Formatter)`:** метод `format(record: logging.LogRecord) -> str` сериализует запись в JSON-строку с ключами `timestamp`, `level`, `logger`, `message`. При наличии `record.exc_info` добавляется ключ `exception`. Все дополнительные поля `record.__dict__` (кроме стандартных атрибутов `LogRecord` и имен, начинающихся с `_`) группируются в объект `extra`.
- **`configure_logging(log_level: str = "INFO", json_logs: bool = False) -> None`:** нормализует уровень логирования (с фоллбэком на `logging.INFO`), подключает `StreamHandler(sys.stdout)` с `JsonFormatter` (при `json_logs=True`) либо текстовым форматером `%(asctime)s [%(levelname)s] %(name)s: %(message)s` (`datefmt="%Y-%m-%d %H:%M:%S"`), заменяет существующие базовые `StreamHandler` и задает уровень корневого логгера.

#### `wishenka/web/app.py` — фабрика приложения и middleware

- **`RequestLoggingMiddleware(BaseHTTPMiddleware)`:** замеряет время выполнения запроса через `time.perf_counter()`, фиксирует старт (`DEBUG`), завершение со статусом и длительностью в миллисекундах (`INFO`) или необработанное исключение со стектрейсом (`ERROR` / `logger.exception`) с повторным пробросом исключения.
- **`create_app(settings: Settings | None = None) -> FastAPI`:**
  - создает `Settings()` при отсутствии явного аргумента;
  - вызывает `configure_logging(log_level=settings.log_level, json_logs=settings.log_json)`;
  - инициализирует `FastAPI(title=settings.app_name, debug=settings.debug, lifespan=lifespan)`;
  - регистрирует `RequestLoggingMiddleware` и маршрут `GET /healthz`, возвращающий `{"status": "ok"}`.

#### `wishenka/main.py` — точка входа

- На уровне модуля создает `settings = Settings()`, настраивает логирование и строит `app = create_app(settings)`.
- Функция `main() -> None` записывает уведомление о запуске и стартует `uvicorn.run("wishenka.main:app", host="0.0.0.0", port=8000, reload=..., log_level=settings.log_level.lower())`.

### 3.3. Контракты сборки, качества кода, контейнеризации и CI

- **Упаковка (`pyproject.toml`):** сборочный бэкенд `hatchling` (PEP 517/621), `requires-python = ">=3.12"`, версия `"0.1.0"`.
  - Базовые зависимости (`dependencies`): `fastapi>=0.115.0`, `uvicorn[standard]>=0.32.0`, `aiogram>=3.15.0`, `jinja2>=3.1.4`, `python-multipart>=0.0.12`, `sqlalchemy[asyncio]>=2.0.36`, `aiosqlite>=0.20.0`, `alembic>=1.14.0`, `pydantic>=2.10.0`, `pydantic-settings>=2.6.0`, `httpx>=0.28.0`, `beautifulsoup4>=4.12.3`.
  - Зависимости разработки (`optional-dependencies.dev`): `pytest>=8.3.0`, `pytest-asyncio>=0.24.0`, `pytest-timeout>=2.3.1`, `ruff>=0.8.0`, `mypy>=1.13.0`.
- **Ruff (`[tool.ruff]`):** `target-version = "py312"`, `line-length = 100`; активные правила `E`, `W`, `F`, `I`, `B`, `C4`, `UP`, `SIM`; `known-first-party = ["wishenka"]`.
- **Mypy (`[tool.mypy]`):** `python_version = "3.12"`, `strict = true`, `disallow_untyped_defs = true`, `disallow_incomplete_defs = true`, `check_untyped_defs = true`, `no_implicit_optional = true`, `warn_redundant_casts = true`, `warn_unused_ignores = true`, `warn_return_any = true`, плагин `pydantic.mypy`. Для `tests.*` отключено требование обязательных аннотаций сигнатур (`disallow_untyped_defs = false`) при включенной проверке тел (`check_untyped_defs = true`).
- **Pytest (`[tool.pytest.ini_options]`):** `minversion = "8.0"`, `testpaths = ["tests"]`, `asyncio_mode = "auto"`, `asyncio_default_fixture_loop_scope = "function"`, `addopts = "-v --strict-markers"`.
- **Контейнер (`Dockerfile` и `docker-compose.yml`):**
  - Этап `builder` (`python:3.12-slim`) ставит `build-essential`, создает `/opt/venv` и устанавливает пакет через `pip install --no-cache-dir .`.
  - Этап `runtime` (`python:3.12-slim`) создает пользователя `appuser` (UID `10001`, GID `10001`), копирует `/opt/venv` и `wishenka/`, подготавливает каталог `/app/data`, выставляет `PYTHONUNBUFFERED=1` и `PYTHONDONTWRITEBYTECODE=1`, открывает порт `8000`, настраивает `HEALTHCHECK` на `http://localhost:8000/healthz` и запускает `uvicorn wishenka.main:app --host 0.0.0.0 --port 8000`.
  - `docker-compose.yml` определяет сервис `wishenka` (`container_name: wishenka-app`) с пробросом `8000:8000`, томом `sqlite_data:/app/data`, read-only монтированием `./wishenka:/app/wishenka:ro`, переменными `WISHENKA_DATABASE_URL=sqlite+aiosqlite:////app/data/wishenka.db`, `WISHENKA_ENVIRONMENT=development`, `WISHENKA_DEBUG=1`, `WISHENKA_BOT_TOKEN=${BOT_TOKEN:-dummy_bot_token}` и `restart: unless-stopped`.
- **CI (`.github/workflows/ci.yml`):** workflow `CI Quality Gate` запускается на `push` и `pull_request` в `main` и `master` на `ubuntu-latest`, использует `actions/checkout@v4` и `actions/setup-python@v5` (`python-version: "3.12"`, `cache: "pip"`), выполняет `make deps` и `make check`.

### 3.4. Переходы состояний

1. **Жизненный цикл веб-приложения (`lifespan`):**
   `Инициализация конфигурации и логирования (create_app)` → `Запуск (lifespan enter, запись INFO с метаданными среды)` → `Обработка HTTP-запросов (RequestLoggingMiddleware → маршрут)` → `Остановка (lifespan exit, запись INFO о завершении работы)`.
2. **Конвейер Quality Gate (`make check` и CI):**
   `Подготовка окружения (make deps)` → `ruff check` → `ruff format --check` → `mypy` → (при отсутствии ошибок) `pytest` → `Успешное завершение (exit 0)` либо немедленное прерывание с ненулевым кодом на первом неуспешном шаге.

---

## 4. Нефункциональные требования, безопасность и наблюдаемость

### 4.1. Производительность и ограничения

- **Защита от зависания тестов:** базовый лимит `10` секунд на уровне модуля (`pytestmark = pytest.mark.timeout(10)`) предотвращает блокировку локальных проверок и CI-раннеров; для отдельных длительных интеграционных тестов допускается точечное переопределение маркера.
- **Оптимизация статического анализа:** использование `Ruff` на базе Rust минимизирует время прогона линтинга и проверки форматирования; максимальная длина строки кода зафиксирована на уровне `100` символов.
- **Минимизация контейнерного образа и пробы:** multi-stage сборка не переносит компиляторные пакеты (`build-essential`) в `runtime`-образ; встроенный `HEALTHCHECK` выполняется каждые `30s` с таймаутом `5s`, периодом старта `5s` и `3` повторами.
- **Фундамент хранения SQLite:** контейнерная конфигурация выделяет постоянный том `sqlite_data` под `/app/data`, обеспечивая сохранность данных при перезапусках и готовность к работе SQLite в режиме WAL.

### 4.2. Безопасность и приватность

- **Принцип наименьших привилегий в контейнере:** процесс `uvicorn` в `Dockerfile` запускается от непривилегированного пользователя `appuser` (`UID 10001`, `GID 10001`), а исходный код в `docker-compose.yml` монтируется только на чтение (`:ro`).
- **Защита секретов и файлов БД:** `.gitignore` исключает `.env`, `.env.local`, `.env.*.local` и файлы SQLite (`*.db`, `*.db-wal`, `*.db-shm`, `*.sqlite`, `*.sqlite3`); чувствительные параметры (в том числе `WISHENKA_BOT_TOKEN`) передаются через окружение.
- **Типовая защита бизнес-инвариантов:** включенный `strict = true` в `Mypy` и плагин `pydantic.mypy` обеспечивают проверку границ моделей на этапе анализа до запуска кода.
- **Безопасное логирование:** `RequestLoggingMiddleware` и `/healthz` не записывают в журнал тела HTTP-запросов, заголовки и крупные структуры данных — логируются только метод, путь, код ответа и длительность обработки.

### 4.3. Наблюдаемость: логирование и метрики

- **Управление форматом и уровнем:** логирование настраивается переменными `WISHENKA_LOG_LEVEL` (по умолчанию `INFO`) и `WISHENKA_LOG_JSON` (по умолчанию `false`). Поддерживаются человекочитаемый вывод в консоль для разработки и структурированный JSON Lines (`JsonFormatter`) для агрегаторов логов (ELK, Vector, Loki) через stdout/stderr контейнера.
- **Реализованные события журнала:**
  - **ERR (`logger.exception`):** `wishenka/web/app.py:RequestLoggingMiddleware` — необработанные исключения при обработке HTTP-запроса с полным стектрейсом и контекстом (`method`, `path`, `duration_ms`).
  - **WARNING:** стандартные предупреждения Python, перехватываемые настроенным корневым логгером.
  - **INFO:**
    - `wishenka/main.py:main` — уведомление о запуске сервера (`Starting Wishenka server on http://0.0.0.0:8000`);
    - `wishenka/web/app.py:lifespan` — события старта приложения с метаданными (`app_name`, `environment`, `debug`, `log_level`) и его остановки (`Wishenka web application shutting down`);
    - `wishenka/web/app.py:RequestLoggingMiddleware` — завершение каждого HTTP-запроса (`method`, `path`, `status_code`, `duration_ms`).
  - **DEBUG:**
    - `wishenka/web/app.py:RequestLoggingMiddleware` — начало обработки HTTP-запроса (`method`, `path`);
    - `wishenka/web/app.py:healthcheck` — обращение к пробе `/healthz` (`Healthcheck endpoint probed`).
- **Метрики и пробы:**
  - **Время отклика и пропускная способность:** длительность `duration_ms` вычисляется через `time.perf_counter()` и фиксируется в access-логах middleware; поток ошибок отслеживается по ответам 5xx и записям уровня `ERROR`.
  - **Системное здоровье:** эндпоинт `GET /healthz` (`{"status": "ok"}`) для liveness/readiness-проб Docker и оркестраторов.
  - **Отложенная наблюдаемость:** продуктовые бизнес-метрики, экспорт в Prometheus, дашборды Grafana и правила алертинга в рамки `WISHENKA-3` не входят.

---

## 5. Верификация и критерии приёмки

### 5.1. Автоматизированные тестовые сценарии

Базовый тестовый контур задачи размещен в двух модулях с установленным таймаутом `pytestmark = pytest.mark.timeout(10)`:

1. **`tests/test_infra.py`:**
   - `test_package_version`: подтверждает импортируемость пакета `wishenka` и значение `wishenka.__version__ == "0.1.0"`.
   - `test_application_settings`: проверяет загрузку `Settings()` из `wishenka.config` и значение по умолчанию `app_name == "wishenka"`.
   - `test_healthcheck_endpoint`: через `TestClient(create_app())` выполняет `GET /healthz`, проверяя статус `200` и тело `{"status": "ok"}`.
2. **`tests/test_observability.py`:**
   - `test_json_formatter`: проверяет формирование валидного JSON функцией `JsonFormatter.format()` с полями `timestamp`, `level`, `logger`, `message` и `extra`.
   - `test_configure_logging`: проверяет установку уровня `logging.DEBUG` и подключение обработчика на корневом логгере.
   - `test_request_logging_and_lifespan`: через `TestClient(app)` с фикстурой `caplog` проверяет полный жизненный цикл записей при запросе к `/healthz`: запуск приложения, срабатывание пробы, завершение HTTP-запроса и остановку приложения.

По зафиксированным в артефактах `WISHENKA-3` (`40-code-cleanup.md`, `50-observability.md`) результатам проверок на момент закрытия задачи:

- `ruff check` и `ruff format --check` пройдены без ошибок и предупреждений по всем 7 Python-файлам на этапе очистки кода (`40-code-cleanup.md`);
- `mypy` в строгом режиме (`strict = true`) пройден без замечаний по всем 7 файлам этого прогона;
- `pytest` и единый Quality Gate `make check` пройдены успешно (3 теста в `tests/test_infra.py` за `0.44s` на этапе очистки кода и полный прогон, включая `tests/test_observability.py`, после внедрения наблюдаемости).

### 5.2. Критерии приёмки

Задача **WISHENKA-3** считается принятой при выполнении следующих критериев:

1. **AC-1 (Структура репозитория):** выделены пакет приложения `wishenka/`, каталог тестов `tests/`, документация разработчика `doc/dev/infrastructure.md`, корневые конфигурации и `README.md`.
2. **AC-2 (Управление зависимостями и окружением):** зависимости в `pyproject.toml` разделены на runtime и `dev`; `make venv` и `make deps` воспроизводимо разворачивают `.venv`.
3. **AC-3 (Стандартные команды `Makefile`):** реализованы и задокументированы цели `help`, `venv`, `deps`, `build`, `analyze`, `format`, `test`, `check`, `run`, `clean`.
4. **AC-4 (Статический анализ):** `make analyze` запускает `ruff check`, `ruff format --check` и `mypy` (`strict = true`) и завершается ненулевым кодом при любых нарушениях.
5. **AC-5 (Тестовый контур с таймаутами):** настроены `pytest`, `pytest-asyncio` (`auto`) и `pytest-timeout`; базовые тесты имеют явный таймаут `10` с и проходят в изолированной среде без внешней БД и Telegram API.
6. **AC-6 (Контейнеризация):** подготовлены multi-stage `Dockerfile` (пользователь `appuser`, `HEALTHCHECK`) и `docker-compose.yml` с постоянным томом `sqlite_data`.
7. **AC-7 (CI Quality Gate):** настроен workflow `.github/workflows/ci.yml`, выполняющий `make check` на Python `3.12` при `push` и `pull_request` в ветки `main`/`master`.
8. **AC-8 (Исключение служебных файлов):** `.gitignore` исключает `.venv/`, кэши инструментов, `.env*` и файлы SQLite (`*.db`, `*.db-wal`, `*.db-shm`, `*.sqlite`, `*.sqlite3`).

### 5.3. Известные ограничения и задачи технического долга

По результатам анализа технического долга (`60-tech-debt.md`) зафиксированы следующие допущения и ограничения базовой реализации:

- **Расхождение версий Python (`3.12` и `3.13`):** `Dockerfile` и CI используют Python `3.12`, тогда как локальное окружение разработки может работать на `3.13`; матрица версий в CI на этапе `WISHENKA-3` не настроена.
- **Поверхностная проба `/healthz`:** эндпоинт возвращает `{"status": "ok"}` без проверки соединения с SQLite, поскольку слой БД отложен до `WISHENKA-4`.
- **Fallback-токен бота в `docker-compose.yml`:** по умолчанию подставляется `WISHENKA_BOT_TOKEN=${BOT_TOKEN:-dummy_bot_token}` без строгой валидации до этапа инициализации бота.
- **Устаревание `TestClient` в Starlette:** прогон `pytest` с `starlette.testclient.TestClient` и `httpx` генерирует `StarletteDeprecationWarning`.
- **Совмещение `lifespan` в `wishenka/web/app.py` и отсутствие lock-файла в Docker:** вынесение управления жизненным циклом в отдельный модуль и фиксация хешей зависимостей отложены на последующее развитие.
- **Шум в логах от частых healthcheck-запросов:** `RequestLoggingMiddleware` логирует все запросы (включая `/healthz`) на уровне `INFO`.

Зарегистрированные в Jira follow-up задачи по техническому долгу:

| Ключ | Описание | Оценка и приоритет |
| --- | --- | --- |
| [WISHENKA-40](https://pypost.atlassian.net/browse/WISHENKA-40) | Добавить сборку Docker-образа и smoke-проверку `/healthz` контейнера в GitHub Actions CI | 2 SP, Low |
| [WISHENKA-41](https://pypost.atlassian.net/browse/WISHENKA-41) | Заменить `starlette.testclient.TestClient` в тестах на `httpx.AsyncClient` для устранения deprecation-предупреждений | 1 SP, Low |
| [WISHENKA-42](https://pypost.atlassian.net/browse/WISHENKA-42) | Добавить middleware обработки 500-ошибок с логированием traceback и error-path тест по контракту `caplog` | 2 SP, Low |
| [WISHENKA-43](https://pypost.atlassian.net/browse/WISHENKA-43) | Исключить или понизить до `DEBUG` логирование запросов к `/healthz` в `RequestLoggingMiddleware` | 1 SP, Low |
