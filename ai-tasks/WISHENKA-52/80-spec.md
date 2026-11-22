# Спецификация: WISHENKA-52 — Неблокирующий разбор HTML тяжёлых страниц

- **Задача:** WISHENKA-52 (техдолг, 2 Story Points; эпик WISHENKA-10)
- **Язык и стек:** Python 3.12+, `asyncio`, FastAPI, `httpx`, `BeautifulSoup4` (`html.parser`)
- **Статус:** реализовано, верифицировано и задокументировано

## 1. Назначение и бизнес-цель

### 1.1. Постановка проблемы

Сервис «Вишенка» обслуживает множество пользователей в рамках одного асинхронного процесса. При добавлении желания по ссылке сервис загружает веб-страницу магазина и извлекает из неё метаданные товара (название, описание, изображение, цену, валюту, название и иконку магазина) при помощи синхронного вызова `HtmlMetadataExtractor.extract`, использующего `BeautifulSoup` с парсером `html.parser`.

HTML-документы современных маркетплейсов нередко превышают 1 МБ. До выполнения задачи разбор такого документа осуществлялся синхронно непосредственно в потоке цикла событий (`event loop`). На всё время парсинга цикл событий блокировался и не мог переключаться на обработку других корутин, из-за чего веб-интерфейс (Telegram Mini App) и Telegram-бот временно переставали отвечать всем остальным пользователям.

### 1.2. Бизнес-цель и ценность решения

**Бизнес-цель:** исключить деградацию отзывчивости сервиса для всех пользователей при обработке тяжёлой ссылки одним пользователем, сохранив при этом прежний результат извлечения метаданных, форматы контрактов и существующие защитные ограничения.

Ценность для участников и эксплуатации:

- **Владелец и соавторы вишлиста:** получают прежний предпросмотр товара (или предсказуемый fallback при ошибке) даже при вставке ссылок на страницы размером более 1 МБ.
- **Прочие пользователи и гости публичных вишлистов:** продолжают открывать вишлисты и выполнять запросы без заметного замедления во время разбора чужих тяжёлых страниц.
- **Эксплуатация и разработка:** сервис сохраняет отзывчивость без смены парсера (исключаются регрессии в интерпретации некорректного HTML) и без добавления внешних зависимостей.

### 1.3. Границы задачи

**В области задачи:**

- Перевод обоих мест вызова `HtmlMetadataExtractor.extract` (предпросмотр ссылки в `ItemPreviewService` и получение метаданных по URL в `UrlMetadataService`) в неблокирующий режим выполнения.
- Сохранение локальной обработки ошибок и существующих fallback-результатов на каждом пути.
- Добавление автоматических тестов неблокирующего поведения и проверка неизменности извлекаемых данных.
- Обновление документации разработчика в `doc/dev/items.md`.

**Вне области задачи:**

- Изменение алгоритма извлечения метаданных (каскады JSON-LD `@graph`/`AggregateOffer`, OpenGraph, Microdata, HTML fallback) и правил маркетплейсов.
- Замена парсера `html.parser` на сторонние C-парсеры.
- Изменение сетевых таймаутов, правил SSRF-защиты, лимита размера ответа (`MAX_RESPONSE_BYTES`), политики anti-bot fallback и форматов DTO/UI.
- Внедрение пула процессов, ограничения числа параллельных парсингов или новых метрик конкурентной нагрузки (вынесено в отдельную задачу [WISHENKA-113](https://pypost.atlassian.net/browse/WISHENKA-113)).

## 2. Функциональные требования и пользовательские сценарии

### 2.1. Функциональные требования

- **FR-1. Выгрузка разбора HTML из цикла событий на обоих путях:**
  - В `ItemPreviewService.fetch_preview` (и алиасе `ItemPreviewService.preview`) в `wishenka/items/service.py` вызов `HtmlMetadataExtractor.extract(html_text, base_url=response_url)` должен выполняться через `await asyncio.to_thread(...)` внутри существующего блока `try`.
  - В `UrlMetadataService.fetch_and_extract` в `wishenka/items/fetcher.py` вызов `HtmlMetadataExtractor.extract(html_text, base_url=final_url)` должен выполняться через `await asyncio.to_thread(...)` внутри существующего блока `try`.
- **FR-2. Идентичность результата извлечения:**
  - Для любого корректного или частично размеченного HTML-документа выгрузка в поток не изменяет логику разбора и возвращает точно такой же объект `ExtractedMetadata` (и, соответственно, `ItemPreviewDTO`), как при прежнем прямом вызове.
- **FR-3. Сохранение классификации входа и работы кеша:**
  - Вход типа `InputType.PLAIN_TEXT` обрабатывается синхронно без сетевых запросов и без запуска парсера, возвращая `ItemPreviewDTO(input_type=InputType.PLAIN_TEXT, title=classification.residual_text, is_fallback=False)`.
  - Для `EXPLICIT_URL`, `IMPLICIT_URL` и `COMPOSITE_SHARE` выполняется очистка URL (`clean_url`), проверка `PreviewCache` (при попадании после перепроверки `validate_url` переиспользуется `cached.metadata` без разбора HTML), защищённая загрузка и проверка anti-bot сигнатур, и только при отсутствии кеша и блокировок запускается выгруженный разбор.
- **FR-4. Сохранение локальных fallback-сценариев и fail-closed поведения кассет:**
  - Исключения защищённой загрузки (`SSRFBlockedError`, `InvalidUrlSchemeError`, `ResponseBodyTooLargeError`, `httpx.TimeoutException`, `httpx.HTTPStatusError`, сетевые `httpx.HTTPError`) и anti-bot экраны (`CHALLENGE_SIGNATURES` и статусы `403`/`429`/`503`) продолжают обрабатываться до этапа разбора.
  - `CassetteError` (включая `CassetteMissError`) явно пробрасывается (`raise`) без перехвата в обоих сервисах.
  - Исключение, возникшее внутри `HtmlMetadataExtractor.extract` в рабочем потоке, распространяется через `await asyncio.to_thread(...)` в локальный обработчик `except Exception`:
    - `ItemPreviewService.fetch_preview` возвращает `ItemPreviewDTO` с `is_fallback=True`, `fallback_reason="http_error"`, очищенным `url`, определённым `store_name` и `title=classification.residual_text`.
    - `UrlMetadataService.fetch_and_extract` возвращает `ExtractedMetadata(store_name=derive_store_name(url))`.

### 2.2. Входы и выходы сервисных точек входа

| Точка входа | Входные параметры | Успешный результат | Результат при ошибке разбора |
| ----------- | ----------------- | ------------------ | ----------------------------- |
| `ItemPreviewService.fetch_preview` | `raw_input: str`, опционально `client`, `routes` | `ItemPreviewDTO` (`is_fallback=False`, извлечённые метаданные или `residual_text`) | `ItemPreviewDTO` (`is_fallback=True`, `fallback_reason="http_error"`, `store_name`, `residual_text`) |
| `UrlMetadataService.fetch_and_extract` | `url: str`, опционально `client`, `routes` | `ExtractedMetadata` (название, описание, фото, цена, валюта, магазин, иконка) | `ExtractedMetadata(store_name=derive_store_name(url))` (остальные поля по умолчанию) |
| `HtmlMetadataExtractor.extract` | `html: str`, `base_url: str` | `ExtractedMetadata` | Исключение передаётся в вызывающий `await asyncio.to_thread(...)` |

### 2.3. Пользовательские сценарии

- **UC-01. Предпросмотр тяжёлой страницы товара:** пользователь вставляет ссылку на карточку товара размером свыше 1 МБ в универсальное поле ввода или отправляет её боту. Сервис загружает документ с проверкой SSRF и лимита 2 МБ, выгружает разбор HTML в рабочий поток и возвращает заполненную карточку предпросмотра.
- **UC-02. Отзывчивость сервиса при параллельном разборе:** во время разбора тяжёлого HTML-документа (> 1 МБ) по запросу одного пользователя другой пользователь или гость открывает страницу или отправляет лёгкий запрос (например, `GET /healthz`). Цикл событий свободно планирует лёгкую корутину и возвращает ответ без ожидания завершения парсинга.
- **UC-03. Деградация при ошибке парсинга или защитном блоке:** при возникновении ошибки внутри `HtmlMetadataExtractor.extract`, срабатывании SSRF-проверки, превышении лимита 2 МБ или обнаружении anti-bot страницы пользователь получает корректный fallback-ответ с очищенной ссылкой, названием магазина и доступной формой ручного ввода без сбоя 500.

### 2.4. Продуктовые и архитектурные инварианты

1. **Неблокирующий цикл событий:** асинхронный код не должен вызывать `HtmlMetadataExtractor.extract` напрямую в потоке цикла событий; все обращения из обработчиков выполняются через `ItemPreviewService` или `UrlMetadataService`.
2. **Неизменность контрактов:** публичные сигнатуры методов, поля `ItemPreviewDTO` и `ExtractedMetadata`, а также форматы ответов API и UI не изменяются.
3. **Неослабление защиты:** все проверки схемы, DNS/IP-фильтрации (SSRF), потокового ограничения размера ответа и anti-bot классификации выполняются в полном объёме до выгрузки разбора.

## 3. Архитектура, компоненты и интерфейсы

### 3.1. Архитектурная схема потока обработки

```text
Запрос предпросмотра (TMA / бот)          Прямой запрос метаданных по URL
               |                                          |
               v                                          v
ItemPreviewService.fetch_preview          UrlMetadataService.fetch_and_extract
               |                                          |
               +--- проверка кеша / _fetch_html (async, SSRF, <= 2 МБ) ---+
                                          |
                                          v
                     await asyncio.to_thread(HtmlMetadataExtractor.extract, ...)
                                  (standard default executor)
                                          |
                                          v
                     HtmlMetadataExtractor.extract (синхронный, без изменений)
                                          |
                                          v
                     локальный маппинг DTO / локальный except-fallback
```

### 3.2. Модули, классы и функции

| Модуль | Компонент / символ | Роль в рамках WISHENKA-52 |
| ------ | ------------------ | ------------------------- |
| `wishenka/items/service.py` | `ItemPreviewService.fetch_preview`, `preview` | Ожидает `await asyncio.to_thread(HtmlMetadataExtractor.extract, html_text, base_url=response_url)` после `_fetch_html` и проверки `_is_challenge`; сохраняет запись в `PreviewCache` и локальные fallback-ветки. |
| `wishenka/items/fetcher.py` | `UrlMetadataService.fetch_and_extract` | Ожидает `await asyncio.to_thread(HtmlMetadataExtractor.extract, html_text, base_url=final_url)` внутри `try ... except CassetteError ... except Exception`; сохраняет защищённую загрузку `_fetch_html` и `_stream_and_read`. |
| `wishenka/items/parser.py` | `HtmlMetadataExtractor.extract(cls, html: str, base_url: str) -> ExtractedMetadata` | Остаётся синхронным чистым интерфейсом на `BeautifulSoup(html, "html.parser")` (JSON-LD `@graph`/`AggregateOffer`, OpenGraph, Microdata, HTML fallback). |
| `wishenka/items/models.py` | `ExtractedMetadata`, `InputClassificationResult`, `InputType` | Доменные структуры данных входа и результата извлечения (без изменений). |
| `wishenka/items/schemas.py` | `ItemPreviewDTO` | Неизменяемая Pydantic-схема ответа предпросмотра (без изменений). |
| `wishenka/items/ssrf.py` | `MAX_RESPONSE_BYTES`, `ALLOWED_SCHEMES`, `SSRFSafeTransport`, `resolve_and_validate_host` | Границы безопасности загрузки и лимит тела ответа 2 МБ (без изменений). |

### 3.3. Обоснование архитектурного решения

- **Выбор `asyncio.to_thread` вместо смены парсера:** переход на другой HTML-парсер способен изменить правила восстановления невалидной разметки и исказить извлекаемые метаданные, что противоречит требованию полной эквивалентности результата.
- **Выбор `asyncio.to_thread` вместо `ProcessPoolExecutor`:** пул процессов обходит GIL, но требует сериализации документов/DTO, отдельного управления жизненным циклом воркеров и межпроцессного сбора логов. `asyncio.to_thread` использует стандартную библиотеку Python 3.12+, переносит разбор с потока цикла событий, пробрасывает контекстные переменные (`ContextVar`) и сохраняет внутрипроцессное логирование `wishenka.items` без новых зависимостей.
- **Сохранение явного вызова на каждом пути:** оба сервиса сохраняют собственные блоки `try/except` и различные контракты деградации (`ItemPreviewDTO` с кодами `fallback_reason` против `ExtractedMetadata(store_name=...)`).

### 3.4. Контракты данных

**`ExtractedMetadata` (`wishenka/items/models.py`):**

- `title: str | None = None` — очищенное название товара.
- `description: str | None = None` — описание товара.
- `image_url: str | None = None` — URL изображения товара.
- `price: int | float | None = None` — извлечённая цена (целое или десятичное число > 0).
- `currency: str = DEFAULT_CURRENCY` — нормализованный код валюты ISO 4217 (по умолчанию `RUB`).
- `store_name: str | None = None` — название магазина.
- `store_icon_url: str | None = None` — URL иконки магазина.
- `raw_html_title: str | None = None` — исходный текст тега `<title>`.

**`ItemPreviewDTO` (`wishenka/items/schemas.py`, `frozen=True`):**

- Поля метаданных: `input_type`, `url`, `title`, `description`, `image_url`, `price`, `currency`, `store_name`, `store_icon_url`.
- Поля состояния деградации: `is_fallback: bool = False`, `fallback_reason: str | None = None` (значения причин: `"ssrf_blocked"`, `"response_too_large"`, `"timeout"`, `"anti_bot_challenge"`, `"http_error"`).

### 3.5. Состояния и переходы выполнения

1. **Классификация входа (`UniversalInputClassifier.classify`):**
   - `PLAIN_TEXT` -> немедленный возврат `ItemPreviewDTO(is_fallback=False)` без сети и парсера.
   - `EXPLICIT_URL` / `IMPLICIT_URL` / `COMPOSITE_SHARE` -> очистка URL (`clean_url`) -> переход к проверке кеша (в `ItemPreviewService`) или к загрузке.
2. **Проверка кеша предпросмотра (`PreviewCache`, только в `ItemPreviewService` при отсутствии переданных `client` и `routes`):**
   - Попадание (`hit`) -> перепроверка всех URL цепочки через `validate_url` -> переиспользование `cached.metadata` без запуска парсера.
   - Промах (`miss`) -> переход к защищённой загрузке `_fetch_html`.
3. **Защищённая загрузка (`_fetch_html`):**
   - Валидация схемы (`http`/`https`), запрет учётных данных, SSRF-проверка DNS/IP и потоковое чтение до `MAX_RESPONSE_BYTES` (2 МБ) с декодированием `decode_html`.
   - При ошибке загрузки или `CassetteError` парсер не запускается: выполняется локальный fallback (или `raise CassetteError`).
4. **Проверка anti-bot сигнатур (только в `ItemPreviewService`):**
   - При совпадении тела с `CHALLENGE_SIGNATURES` разбор не запускается, возвращается fallback с `fallback_reason="anti_bot_challenge"`.
5. **Выгруженный разбор HTML (`await asyncio.to_thread`):**
   - Задача помещается в default executor цикла событий; рабочий поток выполняет `HtmlMetadataExtractor.extract`, в это время цикл событий обрабатывает прочие корутины.
   - Успешное завершение -> возврат `ExtractedMetadata` (и сохранение в `PreviewCache` при допустимости кеширования в `ItemPreviewService`).
   - Исключение в парсере -> проброс через `await` в локальный `except Exception` -> логирование ошибки и возврат сервисного fallback.
6. **Отмена ожидания (cancellation):**
   - Отмена корутины на `await asyncio.to_thread(...)` прерывает ожидание у вызывающего запроса, однако уже начатый в рабочем потоке вызов `HtmlMetadataExtractor.extract` не прерывается принудительно и выполняется до завершения.

## 4. Нефункциональные требования, безопасность и наблюдаемость

### 4.1. Производительность, конкурентность и ограничения

- **Целевой размер тяжёлой страницы и верхний предел:** задача ориентирована на документы размером свыше 1 МБ (в тестах проверяется > 1 МиБ); максимальный объём загружаемого ответа жёстко ограничен `MAX_RESPONSE_BYTES = 2 * 1024 * 1024` (2 МБ).
- **Таймауты:** `DEFAULT_TIMEOUT = httpx.Timeout(4.0, connect=2.0)` ограничивает HTTP-запрос, но не является таймаутом на выполнение парсера в потоке executor.
- **Свойства `default executor` и CPython GIL:**
  - Число потоков стандартного executor ограничено; при множестве одновременных тяжёлых запросов задачи могут ставиться в очередь, удерживая строки HTML в памяти.
  - Из-за CPython GIL выгрузка в поток освобождает цикл событий для планирования других задач, но не обеспечивает истинного параллелизма CPU и жёсткой гарантии задержки при насыщении CPU.
  - В контролируемом тестовом прогоне при реальном разборе документа > 1 МиБ параллельный запрос `GET /healthz` завершается до окончания парсинга со статусом `200` и задержкой `< 1.0` с.

### 4.2. Инварианты безопасности и приватности

- **SSRF и сетевая изоляция:** проверка схем `ALLOWED_SCHEMES`, запрет `username`/`password` в URL и заголовка `Authorization`, проверка всех IP через `resolve_and_validate_host` и `SSRFSafeTransport` / `SSRFSafeNetworkBackend`, а также `RejectCookies` и `trust_env=False` сохраняются без изменений.
- **Защита от DoS по объёму ответа:** ранняя проверка `Content-Length` и потоковый подсчёт чанков в `_stream_and_read` прерывают чтение при превышении 2 МБ.
- **Приватность логов:** изменения данной задачи не добавляют в лог-записи тело HTML-документа, крупные структуры извлечённых метаданных и значения удаляемых трекинговых query-параметров. Существующие события загрузчика продолжают логировать URL и текст исключений без дополнительной редакции.

### 4.3. Наблюдаемость, логирование и метрики

Дублирующие логи и внешние экспортёры метрик (Prometheus, Grafana, алертинг) в рамках задачи не добавлялись. Используются существующие структурированные события логгера `wishenka.items` (поля передаются через `extra`):

| Событие (`extra["event"]`) | Уровень | Модуль | Фиксируемые поля и назначение |
| -------------------------- | ------- | ------ | ----------------------------- |
| `item_preview_success` | `INFO` | `wishenka/items/service.py` | `url_domain`, `input_type`, `duration_ms` (включает загрузку, очередь executor и разбор), `price`, `currency`, `is_fallback`. |
| `item_metadata_parsing_error` | `ERROR` | `wishenka/items/service.py` | `url_domain`, `input_type`, `duration_ms`, `fallback_reason="http_error"` при исключении выгруженного парсера. |
| `fetch_and_extract_fallback` | `WARNING` | `wishenka/items/fetcher.py` | `url`, `error` при ошибке загрузки или выгруженного разбора в `UrlMetadataService.fetch_and_extract`. |
| `url_fetch_success` | `INFO` | `wishenka/items/fetcher.py` | `url`, `effective_url`, `bytes` (объём загруженного HTML до передачи в парсер). |
| `metadata_extraction_started`, `metadata_stage_resolved`, `jsonld_graph_traversal`, `jsonld_aggregate_offer_extracted` | `DEBUG` | `wishenka/items/parser.py` | Диагностика этапов каскадного парсинга, продолжающая поступать в ту же инфраструктуру логирования из рабочего потока. |

**Ограничения наблюдаемости:**

- Показатель `duration_ms` в `item_preview_success` является сквозным временем предпросмотра (сеть + ожидание в очереди executor + разбор), а не изолированным временем парсинга или задержкой цикла событий.
- Отдельные счётчики глубины очереди executor, чистого времени разбора, потребления CPU, пропускной способности и частоты ошибок не добавлены; при агрегации логов успешность и ошибки могут вычисляться по указанным событиям.
- При отмене ожидания (`await asyncio.to_thread`) вызывающим запросом терминальный лог предпросмотра может отсутствовать, несмотря на продолжение работы потока до завершения парсинга.

## 5. Верификация и критерии приёмки

### 5.1. Автоматические тестовые сценарии

Все новые и существующие сценарии модуля сосредоточены в `tests/test_metadata_extractor_service.py` (модульный таймаут `pytestmark = pytest.mark.timeout(30)`):

1. **Управляемая проверка неблокирующего планирования (`test_heavy_extraction_does_not_block_event_loop`):**
   - Параметризован по обоим входам (`"preview"` и `"metadata"`).
   - Имитирует загрузку HTML размером `1024 * 1024 + 1` байт и подменяет `HtmlMetadataExtractor.extract` синхронной функцией с событиями `threading.Event` (`entered`, `release`) и страховочным watchdog-потоком с ограниченными таймаутами.
   - На исходном синхронном коде цикл событий блокировался и тест падал; после выгрузки в `asyncio.to_thread` цикл событий выполняет лёгкие корутины до освобождения `release`, а сервис возвращает ожидаемые метаданные.
2. **Проверка реального парсинга > 1 МиБ при параллельном HTTP-запросе (`test_real_heavy_extraction_keeps_loop_responsive`):**
   - Параметризован по `"preview"` и `"metadata"`.
   - Генерирует HTML > 1 МиБ (60 000 элементов `<span>`) и перехватывает начало реального разбора в `BeautifulSoupHTMLParser.handle_starttag`, планируя через `loop.call_soon_threadsafe` запрос `GET /healthz` к `create_app()` через `httpx.ASGITransport`.
   - Подтверждает, что `GET /healthz` завершается со статусом `200` ещё во время разбора документа (`request_finished_during_parse.is_set()`), задержка ответа составляет `< 1.0` с, а `result.title == "Real product"`.
3. **Проверка сохранения fallback-поведения и событий ошибок (`test_extraction_error_preserves_existing_fallback`):**
   - Параметризован по `"preview"` и `"metadata"`.
   - Подменяет `HtmlMetadataExtractor.extract` функцией, выбрасывающей `ValueError("parser failed")`.
   - Проверяет возврат `ItemPreviewDTO(is_fallback=True, fallback_reason="http_error", store_name="Ozon")` с событием `item_metadata_parsing_error` для `"preview"` и `ExtractedMetadata(title=None, store_name="Ozon")` с событием `fetch_and_extract_fallback` для `"metadata"`.
4. **Регрессия извлечения и наблюдаемости:**
   - Существующий корпус тестов в `tests/test_metadata_extractor_service.py` (JSON-LD `@graph`, `AggregateOffer`, правила маркетплейсов и очистка трекинг-параметров, нормализация цен/валют, anti-bot fallback и отсутствие сырого HTML в логах) и полный набор тестов репозитория.

### 5.2. Результаты проверок

Согласно отчётам верификации задачи (`ai-tasks/WISHENKA-52/40-code-cleanup.md`, `50-observability.md`, `60-tech-debt.md`):

- **`make analyze`:** проверки линтинга и форматирования Ruff пройдены; `mypy` не выявил ошибок в 72 исходных файлах.
- **`make test`:** пройдены все 312 тестов (зафиксировано одно предупреждение о депрекации зависимости); каждый тестовый модуль имеет явный таймаут.
- **`git diff --check`:** пройден без замечаний, маркеры конфликтов слияния отсутствуют.

### 5.3. Критерии приёмки

1. Разбор HTML-документа размером > 1 МБ на обоих путях (`ItemPreviewService.fetch_preview` и `UrlMetadataService.fetch_and_extract`) не блокирует цикл событий для параллельных лёгких запросов.
2. Извлекаемые метаданные (`title`, `image_url`, `price`, `currency`, `store_name`, `store_icon_url`, `description`) и поведение fallback идентичны прежним.
3. Ошибки парсинга в рабочем потоке корректно передаются в локальные обработчики обоих сервисов без падения приложения и фиксируются в логах (`item_metadata_parsing_error` / `fetch_and_extract_fallback`).
4. Ограничение размера ответа (2 МБ), SSRF-защита и anti-bot деградация не ослаблены.
5. Проверки `make analyze`, `make test` и документация разработчика (`doc/dev/items.md`) актуализированы и пройдены.

### 5.4. Известные ограничения, технический долг и последующие шаги

Согласно анализу технического долга (`ai-tasks/WISHENKA-52/60-tech-debt.md`):

- **Ограничения GIL и очереди executor:** при множестве одновременных тяжёлых разборов задачи могут конкурировать за CPython GIL и накапливаться в очереди `default executor`, удерживая HTML-документы в памяти и увеличивая задержки других задач на том же executor.
- **Неотменяемость активного потока:** отмена ожидания со стороны вызывающей корутины не прерывает уже запущенный в потоке вызов `BeautifulSoup`.
- **Границы тестового покрытия:** тест `/healthz` проверяет одиночный тяжёлый парсинг с порогом `< 1.0` с в контролируемой среде и не моделирует насыщение очереди или массовую отмену запросов; наблюдение за началом парсинга использует внутренний метод `BeautifulSoupHTMLParser.handle_starttag`, что может потребовать корректировки при обновлении `beautifulsoup4`.
- **Локальное дублирование:** явные вызовы `asyncio.to_thread` размещены независимо в обоих сервисах для ясности их различных обработчиков ошибок; дополнительный рефакторинг не требуется.
- **Запланированный follow-up (NON-BLOCKER — Medium):** замерить задержки запросов, глубину очереди executor и потребление памяти под репрезентативной конкурентной нагрузкой и при отменённых запросах; по результатам ввести ограничение допуска (admission limit) или изолированную стратегию воркеров с наблюдаемыми таймингами очереди и разбора при полном сохранении SSRF-защиты, лимитов ответа и паритета вывода. Задача в Jira: [WISHENKA-113](https://pypost.atlassian.net/browse/WISHENKA-113).
