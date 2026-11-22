# Спецификация: WISHENKA-111 — Управляемая эволюция схемы БД вишлистов (миграции Alembic)

**Задача:** WISHENKA-111  
**Компонент:** хранилище домена вишлистов (`wishenka/wishlists/`)  
**Стек:** Python, SQLAlchemy 2.0, Alembic, SQLite (`aiosqlite` / `sqlite3`)  
**Статус:** реализовано (с зафиксированными ограничениями и задачами техдолга)

## 1. Назначение и бизнес-цель

### 1.1. Постановка проблемы

До внедрения изменений инициализация хранилища вишлистов (`WishlistStore._initialize()`) совмещала создание базовых таблиц (`CREATE TABLE IF NOT EXISTS`) и ситуативную совместимую мутацию схемы в рантайме: инспекцию столбцов через `PRAGMA table_info` для добавления `wl_lists.warn_on_delete_reserved` и `wl_items.display_order`, а также деструктивное пересоздание таблиц `wl_*` при обнаружении устаревшего JSON-столбца `payload`. Такой подход не формировал единую контролируемую и аудируемую историю изменений структуры данных, создавал риск расхождения схемы между новыми и давно живущими установками и не обеспечивал сериализацию одновременного запуска нескольких процессов.

### 1.2. Цели и ценность для пользователей и системы

**Основные цели:**

- Заменить мутации схемы в коде приложения на версионные, упорядоченные и идемпотентные миграции Alembic для всех таблиц домена вишлистов (`wl_*`).
- Гарантировать сохранность существующих вишлистов, желаний, бронирований и пользовательских настроек при обновлении приложения.
- Обеспечить приведение как новой (включая `:memory:`), так и обновляемой существующей базы данных к единому целевому состоянию (`head`).
- Ввести безопасное усыновление (adoption) признанных legacy-баз без таблицы `alembic_version` только после полной проверки структурного контракта, исключив тихую модификацию или уничтожение несовместимых баз.
- Сериализовать старт нескольких экземпляров приложения на одном файле SQLite и устранить гонки за выбор режима журналирования `WAL`.

**Ценность по ролям:**

- **Владелец вишлиста:** существующие списки, желания и настройки (включая предупреждение при архивации забронированных желаний `warn_on_delete_reserved` и пользовательский порядок карточек `display_order`) сохраняются при обновлении без повторного ввода.
- **Соавтор и даритель:** совместные списки и бронирования продолжают работать консистентно без потери, дублирования или искажения данных после выката новой версии.
- **Оператор продукта:** получает прозрачную историю применённых ревизий в `alembic_version`, воспроизводимый порядок миграций, явную диагностику несовместимых схем и структурированное журналирование процесса старта.

### 1.3. Границы применимости (Scope)

Изменения охватывают жизненный цикл схемы БД вишлистов (`wl_*`), запуск миграций в `WishlistStore.initialize()`, корректное завершение `:memory:`-хранилища в `WishlistStore.dispose()` и `lifespan` веб-приложения, а также автоматическую проверку путей обновления.

Задача **не** изменяет пользовательские функции вишлистов, права доступа, правила бронирования, пользовательский интерфейс и не переводит таблицу `users` (`UserStore.initialize()`) в цепочку Alembic.

## 2. Функциональные требования и пользовательские сценарии

### 2.1. Пользовательские истории

- **Владелец вишлиста:** после обновления приложения существующие списки и настройки должны оставаться доступными без пересоздания.
- **Соавтор или даритель:** совместный вишлист должен сохранять предсказуемое поведение после обновления, чтобы решения о бронировании и покупке оставались надёжными.
- **Оператор продукта:** каждое изменение структуры данных должно иметь явную, повторяемую историю для уверенного развёртывания обновлений и диагностики сбоев старта.

### 2.2. Сценарии поведения системы

#### Сценарий 1. Старт на новой (пустой) или `:memory:` базе данных

1. Приложение или тест создаёт `WishlistStore(database_url)` и вызывает `await store.initialize()`.
2. Раннер миграций обнаруживает отсутствие таблиц `wl_*` и `alembic_version` и пропускает шаг усыновления legacy-схемы.
3. Выполняется `alembic upgrade head`, создаётся таблица `alembic_version` и последовательно применяются все ревизии от `base_normalized` до `head`.
4. Для файловой БД (включая временный файл за `:memory:`) выставляется `PRAGMA journal_mode=WAL`.
5. Новая файловая БД и `:memory:`-хранилище приходят к одному и тому же идентификатору ревизии `head`.

#### Сценарий 2. Повторный старт на уже мигрированной БД

1. При повторном запуске `WishlistStore.initialize()` раннер обнаруживает таблицу `alembic_version`.
2. Шаг усыновления legacy-схемы не выполняется.
3. `alembic upgrade head` применяет только ещё не применённые ревизии (либо завершается без изменений, если БД уже на `head`).
4. Существующие записи и настройки пользователей не дублируются, не удаляются и не перезаписываются.

#### Сценарий 3. Безопасное усыновление признанной legacy-БД

Если в файле БД присутствуют таблицы `wl_*`, но отсутствует таблица `alembic_version`, система рассматривает файл как потенциальную legacy-БД, созданную прежним инициализатором:

1. Проверяется точное соответствие множества пользовательских таблиц девяти базовым таблицам (игнорируется только системная `sqlite_sequence`).
2. Проверяется комбинация трёх исторических маркеров в `wl_lists` и `wl_items` (см. таблицу соответствия в разделе 2.3).
3. Каждая из девяти таблиц сверяется с эталонной структурной сигнатурой (столбцы, типы, `NOT NULL`, значения по умолчанию, первичные и внешние ключи с действиями `ON DELETE`, уникальные и обычные индексы с учётом направления сортировки), а присутствующие маркеры проверяются на точное совпадение с историческим определением.
4. При полном совпадении вызывается `command.stamp(..., revision)` для записи выбранной ревизии в `alembic_version` без изменения данных, после чего `command.upgrade(..., "head")` накатывает только недостающие ревизии.

#### Сценарий 4. Отказ на неизвестной, повреждённой или устаревшей несовместимой схеме

Если в БД без `alembic_version` обнаружено хотя бы одно отклонение от контракта:

- отсутствуют или присутствуют лишние таблицы;
- присутствует устаревший JSON-столбец `payload` (для которого прежний код сбрасывал и пересоздавал таблицы);
- изменены внешний ключ или каскадное действие;
- изменён порядок индекса (например, `idx_wl_view_history_user_time` создан с `viewed_at ASC` вместо `DESC`);
- маркер `warn_on_delete_reserved`, `display_order` или `idx_wl_items_order` присутствует в несовместимой комбинации или с неверным типом/определением (например, `display_order TEXT`),

то усыновление и миграция немедленно прерываются с исключением `RuntimeError` (`Unsupported wishlist database schema: ...`), таблица `alembic_version` не создаётся, а база данных не модифицируется.

#### Сценарий 5. Жизненный цикл `:memory:`-хранилища

Поскольку Alembic работает через собственное синхронное соединение, а SQLite `:memory:` изолирована в рамках одного соединения, `WishlistStore("sqlite+aiosqlite:///:memory:")` создаёт изолированный временный файл (`wishenka-*.sqlite`). При завершении работы `await store.dispose()` (вызываемый в том числе в блоке `finally` `lifespan` веб-приложения) закрывает пул соединений `engine.dispose()` и удаляет временный файл вместе с его lock-файлом `.migrate.lock`.

#### Сценарий 6. Конкурентный запуск нескольких экземпляров приложения

При одновременном старте нескольких процессов на одном файле БД раннер захватывает эксклюзивную файловую блокировку `<db>.migrate.lock`. Первый процесс выполняет усыновление, `upgrade head` и выбор `WAL`. Остальные процессы ожидают освобождения блокировки, после чего повторно читают состояние БД, видят `alembic_version` и выполняют `upgrade head` как no-op без ошибок и гонок.

### 2.3. Входные/выходные контракты и правила усыновления

#### Входные параметры

- `database_url` (из `Settings.database_url` / `WISHENKA_DATABASE_URL`, по умолчанию `sqlite+aiosqlite:///data/wishenka.db`):
  - `WishlistStore.__init__` принимает только URL с префиксом `sqlite+aiosqlite:///`; любой иной URL немедленно вызывает `ValueError("Wishlist storage requires SQLite")`.
  - При прямом вызове `upgrade_to_head` или `upgrade_to_head_sync` с URL без `sqlite+aiosqlite:///` возникает `ValueError("Wishlist migrations support only SQLite URLs")`.

#### Таблица соответствия legacy-маркеров (`_REVISIONS`)

| `wl_lists.warn_on_delete_reserved` | `wl_items.display_order` | `idx_wl_items_order` | Выбранная ревизия для `stamp` |
| --- | --- | --- | --- |
| Нет | Нет | Нет | `base_normalized` |
| Да | Нет | Нет | `add_warn_on_delete_reserved` |
| Да | Да | Нет | `add_display_order` |
| Да | Да | Да | `add_item_order_index` |

Любая иная комбинация флагов (например, `display_order` без `warn_on_delete_reserved` или `idx_wl_items_order` без `display_order`) отклоняется с `RuntimeError("Unsupported wishlist database schema: incompatible migration markers")`.

### 2.4. Продуктовые и технические инварианты

1. **Единственный источник изменений схемы:** создание и изменение таблиц `wl_*` происходит исключительно через упорядоченные скрипты ревизий Alembic; в `WishlistStore` запрещены `CREATE TABLE IF NOT EXISTS`, `ALTER TABLE` и ветвление по `PRAGMA table_info`.
2. **Строгое чтение мигрированных столбцов:** после `upgrade_to_head()` столбцы `warn_on_delete_reserved` и `display_order` считаются гарантированно присутствующими; код хранилища обращается к ним напрямую без `hasattr`/`getattr` и без подстановки значений по умолчанию для отсутствующей колонки.
3. **Сохранность данных:** при успешном усыновлении и апгрейде существующие строки `wl_lists`, `wl_items` и смежных таблиц остаются нетронутыми.
4. **Безопасный отказ:** нераспознанная схема никогда не штампуется в `alembic_version` и не подвергается деструктивному пересозданию.
5. **Блокировка готовности:** `WishlistStore.initialize()` не возвращает управление до достижения `head` (или выбрасывает исключение), не позволяя приложению обслуживать трафик на немигрированной БД.

## 3. Архитектура, компоненты и интерфейсы

### 3.1. Общая схема процесса инициализации и миграций

```mermaid
flowchart LR
    App["Запуск приложения / lifespan"] --> Init["WishlistStore.initialize()"]
    Init --> Thread["upgrade_to_head() (asyncio.to_thread)"]
    Thread --> Sync["upgrade_to_head_sync()"]
    Sync --> Lock["Захват _migration_lock (.migrate.lock)"]
    Lock --> Check{"Есть alembic_version или нет wl_*?"}
    Check -->|Да| Upgrade["alembic upgrade head"]
    Check -->|Нет (legacy)| Validate["Проверка 9 таблиц и маркеров (_adopt_known_schema)"]
    Validate -->|Валидна| Stamp["command.stamp(revision)"]
    Stamp --> Upgrade
    Validate -->|Несовместима| Fail["Лог ERROR + RuntimeError (без изменений БД)"]
    Upgrade --> WAL["PRAGMA journal_mode=WAL (файловые БД)"]
    WAL --> Ready["Готовый WishlistStore"]
```

### 3.2. Модули, классы и интерфейсы

| Компонент | Расположение | Назначение и ключевые символы |
| --- | --- | --- |
| Раннер миграций | `wishenka/wishlists/migrations.py` | `upgrade_to_head`, `upgrade_to_head_sync`, `head_revision`, `migration_lock_path`, `_adopt_known_schema`, `_migration_lock`, `_schema_signature`, `_baseline_signatures`, `_marker_signatures` |
| Окружение Alembic | `wishenka/wishlists/alembic/env.py` | `run_migrations_online()` (`NullPool`, короткоживущее соединение), `run_migrations_offline()` (`literal_binds=True`) |
| Конфигурация Alembic | `alembic.ini` | Базовый ini-файл в корне репозитория (`script_location`, placeholder `sqlalchemy.url = sqlite://`) |
| Ревизии схемы | `wishenka/wishlists/alembic/versions/` | Линейная цепочка версионных скриптов Alembic |
| Репозиторий / Хранилище | `wishenka/wishlists/store.py` | `WishlistStore.__init__`, `WishlistStore.initialize()`, `WishlistStore.dispose()`, `_configure_immediate_transactions` |
| Жизненный цикл веб-приложения | `wishenka/web/app.py` | Вызов `app.state.wishlist_store.initialize()` на старте и `app.state.wishlist_store.dispose()` в `finally` `lifespan` |

#### Основные программные интерфейсы

- `async def upgrade_to_head(database_url: str) -> None` — запускает `upgrade_to_head_sync` в пуле потоков `asyncio.to_thread`, не блокируя цикл событий.
- `def upgrade_to_head_sync(database_url: str) -> None` — сериализует выполнение через `_migration_lock`, при необходимости усыновляет legacy-БД через `_adopt_known_schema`, выполняет `command.upgrade(_configured(database_url), "head")` и для файловых БД (`path is not None`) выставляет `PRAGMA journal_mode=WAL` на отдельном `sqlite3`-соединении.
- `def head_revision(database_url: str = "sqlite+aiosqlite:///:memory:") -> str` — считывает единственный `head` из `ScriptDirectory` без открытия БД (поднимает `RuntimeError`, если `head is None`).
- `def migration_lock_path(path: Path) -> Path` — формирует путь к sidecar-файлу блокировки `<db>.migrate.lock`.
- `WishlistStore.initialize(self) -> None` — вызывает `await upgrade_to_head(self.database_url)`; перехватывает `(OSError, RuntimeError, ValueError, SQLAlchemyError)` и выбрасывает `RuntimeError("Unable to initialize wishlist storage") from exc`.
- `WishlistStore.dispose(self) -> None` — вызывает `await self.engine.dispose()`, затем (если использовался `:memory:` с временным файлом) удаляет временный `.sqlite`-файл и его `.migrate.lock` sidecar.

### 3.3. Контракт схемы данных (ревизии WISHENKA-111)

В рамках `WISHENKA-111` определена линейная цепочка из четырёх ревизий (расширяемая последующими ревизиями проекта):

| Порядок | Revision ID | `down_revision` | Изменения схемы | Поведение `downgrade()` в WISHENKA-111 |
| --- | --- | --- | --- | --- |
| 1 | `base_normalized` | `None` | Создаёт 9 базовых таблиц (`wl_lists`, `wl_members`, `wl_items`, `wl_reservations`, `wl_favorites`, `wl_view_history`, `wl_tokens`, `wl_invite_tokens`, `wl_counters`) и базовые индексы | Удаление 9 базовых таблиц в обратном порядке (уточнение защитной политики вынесено в `WISHENKA-128`) |
| 2 | `add_warn_on_delete_reserved` | `base_normalized` | `ALTER TABLE wl_lists ADD COLUMN warn_on_delete_reserved INTEGER NOT NULL DEFAULT 1` | Выбрасывает `NotImplementedError` (SQLite не удаляет столбец без пересборки таблицы) |
| 3 | `add_display_order` | `add_warn_on_delete_reserved` | `ALTER TABLE wl_items ADD COLUMN display_order INTEGER NOT NULL DEFAULT 0` | Выбрасывает `NotImplementedError` |
| 4 | `add_item_order_index` | `add_display_order` | `CREATE INDEX idx_wl_items_order ON wl_items(wishlist_id, display_order)` | `DROP INDEX idx_wl_items_order` |

#### Контракт структурной валидации при усыновлении

Функция `_schema_signature(connection, table)` извлекает для каждой из девяти таблиц `_TABLES` кортеж из трёх компонентов:

1. **Столбцы (`PRAGMA table_info`):** имя, тип (SQLite affinity), признак `NOT NULL`, значение по умолчанию (`dflt_value`), участие в `PRIMARY KEY`.
2. **Внешние ключи (`PRAGMA foreign_key_list`):** целевая таблица, столбцы и правила каскадирования (включая `ON DELETE CASCADE` для `wl_members`, `wl_items`, `wl_reservations`, `wl_favorites`, `wl_view_history`).
3. **Индексы (`PRAGMA index_list` без `sqlite_autoindex*` + `PRAGMA index_xinfo`):** имя, уникальность, источник (`origin`), ключевые столбцы и направление сортировки `desc` (включая нисходящий индекс `idx_wl_view_history_user_time ON wl_view_history(user_id, viewed_at DESC)`).

Сравнение выполняется с эталоном, динамически собираемым в памяти из `base_normalized.DDL` (`_baseline_signatures()`), а маркерные столбцы/индекс сверяются с точными сигнатурами из `_marker_signatures()`:

- `wl_lists.warn_on_delete_reserved`: `INTEGER NOT NULL DEFAULT 1`;
- `wl_items.display_order`: `INTEGER NOT NULL DEFAULT 0`;
- `idx_wl_items_order`: `CREATE INDEX idx_wl_items_order ON wl_items(wishlist_id, display_order)`.

### 3.4. Разделение PRAGMA-настроек SQLite

- **Уровень старта миграций (`upgrade_to_head_sync`):** `PRAGMA journal_mode=WAL` выставляется однократно на файловой БД (под миграционной блокировкой), так как режим журналирования является персистентным состоянием файла БД и его одновременная установка на пуле соединений приводит к конкуренции за эксклюзивную блокировку SQLite.
- **Уровень соединений пула (`_configure_immediate_transactions` в `store.py`):** при подключении задаются `isolation_level = None`, `PRAGMA foreign_keys=ON` и `PRAGMA busy_timeout=5000`; при открытии транзакции (`begin`) выставляется `PRAGMA busy_timeout=5000` и выполняется `BEGIN` (для `read_only`) или `BEGIN IMMEDIATE`.

## 4. Нефункциональные требования, безопасность и наблюдаемость

### 4.1. Производительность, надёжность и ограничения

- **Неблокирующий старт:** выполнение синхронного Alembic API вынесено в `asyncio.to_thread` (`upgrade_to_head`), чтобы не блокировать event loop приложения.
- **Сериализация и таймаут блокировки:** `_migration_lock` использует неблокирующий опрос `fcntl.flock(..., LOCK_EX | LOCK_NB)` с интервалом `_LOCK_POLL_SECONDS = 0.05` с и общим ограничением ожидания `_LOCK_TIMEOUT_SECONDS = 60.0` с. По истечении 60 с генерируется `TimeoutError("Timed out waiting for another process to finish wishlist migration")`.
- **Издержки при повторных запусках:** на актуальной БД `upgrade head` выполняется за счёт чтения таблицы `alembic_version` и сканирования каталога ревизий плюс одно `sqlite3.connect` для `PRAGMA journal_mode=WAL`.
- **Операции пересборки таблиц (batch):** в будущих ревизиях изменения, не поддерживаемые SQLite `ALTER TABLE` на месте, должны использовать `op.batch_alter_table` с оценкой длительности блокировки и влияния на внешние ключи.
- **Ограничение ОС:** раннер импортирует `fcntl` на уровне модуля и поддерживает только POSIX-системы (Windows не поддерживается).
- **Ограничение упаковки:** `_configured` ищет `alembic.ini` по пути `Path(__file__).parents[2] / "alembic.ini"` (относительно корня репозитория), что рассчитано на запуск из checkout исходного кода (вынесено в `WISHENKA-130`).

### 4.2. Безопасность и приватность

- **Права lock-файла:** sidecar-файл `<db>.migrate.lock` открывается с правами `0o600` (`os.open(..., os.O_RDWR | os.O_CREAT, 0o600)`) и игнорируется системой контроля версий (`*.migrate.lock`).
- **Защита путей и пользовательских данных в логах:** логгер `wishenka.wishlists.migrations` намеренно не включает в текст сообщений и поля `extra` пути к файлам БД, имена файлов, URL подключения, а также содержимое таблиц или пользовательские данные.
- **Предотвращение случайного уничтожения данных:** отказ от прежнего автоматического `DROP TABLE` при обнаружении столбца `payload` защищает исторические базы от потери данных; несовместимая БД требует явного вмешательства оператора или восстановления из резервной копии.
- **SQL-безопасность инспекции:** интерполяция в `PRAGMA table_info({table})` / `foreign_key_list` / `index_list` / `index_xinfo` использует исключительно внутренний константный набор `_TABLES` и имена индексов из системного каталога SQLite.

### 4.3. Наблюдаемость: структурированное журналирование и метрики

Все события жизненного цикла миграций записываются на логгер `wishenka.wishlists.migrations` со структурированными полями `extra`:

| Событие (`extra["event"]`) | Уровень | Дополнительные поля `extra` | Условие и семантика |
| --- | --- | --- | --- |
| `wishlist_migration_started` | `INFO` | — | Фиксируется в начале `upgrade_to_head_sync` |
| `wishlist_migration_legacy_schema_adopted` | `INFO` | `revision` | Фиксируется после успешного `command.stamp` валидированной legacy-БД (имя ревизии дублируется и в тексте сообщения) |
| `wishlist_migration_completed` | `INFO` | `duration_ms` | Фиксируется после успешного завершения усыновления, `upgrade head` и установки `WAL`; `duration_ms` — неотрицательное `int` (миллисекунды, включая ожидание блокировки) |
| `wishlist_migration_failed` | `ERROR` | — | Фиксируется через `logger.exception` (с `exc_info`) при любом сбое в `upgrade_to_head_sync`, после чего исключение пробрасывается дальше; `adopted` и `completed` при этом не логируются |

**Метрики и мониторинг:**

- **Метрика производительности:** `duration_ms` в событии `wishlist_migration_completed`.
- **Метрика здоровья системы:** поток событий `started` / `completed` / `failed` для настроенного в приложении агрегатора логов.
- **Бизнес-метрики:** не применимы (миграция схемы является инфраструктурной операцией старта).
- **Интеграция с Prometheus / Grafana / алертингом:** в рамках `WISHENKA-111` не добавлялась (метрики только в логах; задача добавления порога/алерта по длительности старта вынесена в `WISHENKA-125`).

## 5. Верификация и критерии приёмки

### 5.1. Автоматизированные тестовые сценарии и результаты проверки

| Тестовый модуль / кейс | Таймаут | Проверяемое поведение | Статус в WISHENKA-111 |
| --- | --- | --- | --- |
| `tests/test_wishlist_alembic_migrations.py::test_legacy_database_is_adopted_at_alembic_head_without_losing_rows` | 10 с (модульный) | Legacy-БД с 9 таблицами (без `warn_on_delete_reserved` и `display_order`) усыновляется, доводится до `head`, получает оба поля и `idx_wl_items_order`, сохраняя предзаполненные строки | Пройден |
| `tests/test_wishlist_alembic_migrations.py::test_fresh_and_memory_stores_reach_the_same_alembic_head` | 10 с (модульный) | Новая файловая БД и `:memory:`-хранилище приходят к одинаковой ревизии в `alembic_version` | Пройден |
| `tests/test_wishlist_alembic_migrations.py::test_memory_store_dispose_removes_its_temporary_database` | 10 с (модульный) | `WishlistStore.dispose()` удаляет принадлежащий `:memory:` временный файл | Пройден |
| `tests/test_wishlist_alembic_migrations.py::test_app_lifespan_disposes_its_memory_wishlist_store` | 10 с (модульный) | `lifespan` приложения `create_app` удаляет временный файл `:memory:`-хранилища при остановке | Пройден |
| `tests/test_wishlist_alembic_migrations.py::test_legacy_schema_with_ascending_history_index_is_not_adopted` | 10 с (модульный) | Legacy-схема с `idx_wl_view_history_user_time` (`ASC` вместо `DESC`) отклоняется ошибкой `RuntimeError("Unable to initialize wishlist storage")` без создания `alembic_version` | Пройден |
| `tests/test_wishlist_alembic_migrations.py::test_legacy_schema_with_malformed_display_order_marker_is_not_adopted` | 10 с (модульный) | Legacy-схема с неверным типом маркера `display_order TEXT` отклоняется ошибкой `RuntimeError` без создания `alembic_version` | Пройден |
| `tests/test_wishlist_api.py::test_concurrent_instances_allocate_distinct_ids` | 30 с (модульный) | Параллельная работа экземпляров хранилища не конфликтует за `PRAGMA journal_mode=WAL` | Пройден |
| `tests/test_wishlist_migrations_concurrency.py::test_concurrent_startup_on_shared_database` (`fresh`, `legacy_base_normalized`) | 120 с (модульный) | 4 параллельных процесса (`spawn`, 3 прогона) на одном файле БД сериализуются, фиксируют одну строку `head_revision()` в `alembic_version`, режим `wal` и сохранённые legacy-данные | Покрыто регрессионным тестом |
| `tests/test_wishlist_migrations_observability.py::test_fresh_database_logs_started_and_completed` | 30 с (модульный) | Новая БД логирует `INFO` `wishlist_migration_started` -> `wishlist_migration_completed` с `duration_ms >= 0` (`int`) без утечки пути/имени БД/данных | Пройден |
| `tests/test_wishlist_migrations_observability.py::test_legacy_database_logs_adoption_with_revision` | 30 с (модульный) | Legacy-БД логирует `started`, ровно одно `wishlist_migration_legacy_schema_adopted` с валидным `revision` в `extra` и сообщении, затем `completed` | Пройден |
| `tests/test_wishlist_migrations_observability.py::test_unsupported_schema_logs_failure_and_reraises` | 30 с (модульный) | Неподдерживаемая схема логирует `started`, затем `ERROR` `wishlist_migration_failed` с `exc_info` (`RuntimeError`) и пробрасывает исключение без `adopted`/`completed` и без путей в логах | Пройден |

**Сводка верификации по результатам Шага 5 и Шага 6 (`40-code-cleanup.md`, `50-observability.md`):**

- `make analyze` (Ruff lint, Ruff format check, Mypy по 91 исходному файлу): пройдено без замечаний.
- Финальный сфокусированный прогон (`tests/test_wishlist_api.py::test_concurrent_instances_allocate_distinct_ids` + `tests/test_wishlist_alembic_migrations.py`): 7 тестов пройдены.
- Полный `make test` на этапе очистки: 458 passed, 3 failures — 1 сбой параллельного хранилища вызван задачей и исправлен переносом выбора `WAL` в `upgrade_to_head_sync`; 2 оставшихся сбоя являются предсуществующими проблемами Chromium UI (отслеживаются как `NON-BLOCKER` в `WISHENKA-124`).
- Проверка наблюдаемости (`tests/test_wishlist_migrations_observability.py`): все 3 теста пройдены через `caplog`.

### 5.2. Критерии приёмки

1. Все изменения схемы БД вишлистов (`wl_*`) применяются в детерминированном порядке через версионные ревизии Alembic; в `WishlistStore` отсутствуют runtime DDL-операции (`CREATE TABLE IF NOT EXISTS`, `ALTER TABLE`, `PRAGMA table_info`).
2. Новая файловая БД, `:memory:`-хранилище и усыновлённая поддерживаемая legacy-БД приходят к одной и той же ревизии `head` в `alembic_version`.
3. При усыновлении и обновлении legacy-БД сохранённые списки, желания и настройки пользователей остаются читаемыми и неизменными.
4. Повторный запуск инициализации на уже мигрированной БД идемпотентен и не дублирует, не удаляет и не повреждает данные.
5. Несовместимая или повреждённая БД без `alembic_version` отклоняется понятным исключением на старте, не штампуется и не модифицируется.
6. Одновременный запуск нескольких процессов на одном файле БД сериализуется без ошибок конкуренции за миграцию или смену `journal_mode=WAL`.
7. Завершение `:memory:`-хранилища через `WishlistStore.dispose()` (включая `lifespan` приложения) удаляет созданный временный файл и его `.migrate.lock` sidecar.
8. В логах `wishenka.wishlists.migrations` фиксируются события `started`, `legacy_schema_adopted` (при усыновлении), `completed` (с `duration_ms`) или `failed` (с traceback) без раскрытия путей к БД, URL и пользовательских данных.

### 5.3. Известные ограничения, отклонения и follow-up задачи (из `60-tech-debt.md`)

**Зафиксированные отклонения от исходной архитектуры (`20-architecture.md`) на момент закрытия WISHENKA-111:**

- Выбор `PRAGMA journal_mode=WAL` перенесён из connection-хука хранилища в `upgrade_to_head_sync`.
- Хранилища `:memory:` используют временный файл и требуют явного `WishlistStore.dispose()` (подключено в `wishenka/web/app.py`).
- Политика `downgrade()` в ревизиях `WISHENKA-111` осталась неоднородной: `add_display_order` и `add_warn_on_delete_reserved` выбрасывают `NotImplementedError`, а `base_normalized` удаляла таблицы без защитного ограничения (передано в `WISHENKA-128`).
- Ошибки инициализации в `WishlistStore.initialize` оборачиваются в общий `RuntimeError("Unable to initialize wishlist storage")` с сохранением исходной причины в `__cause__`.
- Конфигурация Alembic получает `sqlalchemy.url` программно через `Config.set_main_option`.
- На этапе Шага 6 добавлено структурированное журналирование и метрика `duration_ms`.

**Задачи последующей доработки (все `NON-BLOCKER`):**

| № | Jira | Описание и область |
| --- | --- | --- |
| 1 | `WISHENKA-124` | Предсуществующие падения 2 браузерных Chromium UI тестов (`test_browser_copy_share_and_role_controls`, `test_mini_app_home_sections_and_badges_browser`) |
| 2 | `WISHENKA-126` | Бесхозный core dump `core` (~197 МБ) в корне репозитория; удаление после проверки, добавление `core` / `core.*` в `.gitignore` и расследование причины падения pytest |
| 3 | `WISHENKA-127` | Недостающие тесты усыновления для ревизий `add_warn_on_delete_reserved`, `add_display_order`, `add_item_order_index`, путей отказа (таблицы, FK/каскады, `payload`, маркер `warn_on_delete_reserved`, дрейф индексов) и проверка побайтовой неизменности файла при ошибке |
| 4 | `WISHENKA-128` | Формализация и документирование политики `downgrade` (one-way vs reversible, защита от деструктивного отката `base_normalized`, явные сообщения) и тесты на откат, идемпотентный второй старт, non-SQLite URL и offline-режим Alembic |
| 5 | `WISHENKA-129` | Рефакторинг `_adopt_known_schema` на функции detect/validate/stamp с именованной структурой маркеров, устранение ручного дублирования DDL в `_marker_signatures()` и отказ от хардкода `head` в `_REVISIONS` |
| 6 | `WISHENKA-130` | Отвязка `Config` от корневого `alembic.ini` (или включение в пакет), проверка попадания ревизий в wheel-сборку и парсинг URL через `sqlalchemy.engine.make_url` |
| 7 | `WISHENKA-131` | Увеличение модульного таймаута `tests/test_wishlist_alembic_migrations.py` с 10 с до 30 с для снижения риска флаков на медленном CI |
| 8 | Покрыто Шагом 8 `WISHENKA-111` | Актуализация устаревших разделов о миграциях и `PRAGMA` в `doc/dev/miniapp.md`, `doc/dev/items.md`, `doc/dev/architecture.md` и описание workflow Alembic (`doc/dev/migrations.md`) |
| 9 | `WISHENKA-125` | Добавление порога/алерта на длительность стартовой миграции при появлении нетривиальных batch-ревизий |
| 10 | `WISHENKA-132` | Освобождение временного файла `:memory:`-хранилища через `dispose()` при сбое внутри `WishlistStore.initialize()` |
| 11 | `WISHENKA-133` | Удаление избыточного условия `if path != ":memory:":` в `WishlistStore.__init__` |
| 12 | `WISHENKA-134` | Перевод 7 существующих тестовых модулей (31 вызов `store.engine.dispose()`) на `await store.dispose()` для предотвращения утечки временных файлов при переходе на `:memory:` |
