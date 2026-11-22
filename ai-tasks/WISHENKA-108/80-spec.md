# Спецификация: WISHENKA-108 — Независимость поведения страницы вишлиста от inline-скрипта и адреса страницы

**Задача Jira:** WISHENKA-108 (тип: Debt, приоритет: Low, оценка: 2 SP)  
**Источник требований:** технический долг из `ai-tasks/WISHENKA-15/60-tech-debt.md`  
**Область действия:** веб-интерфейс Wishenka (Jinja-шаблоны, статический скрипт `/static/wishlist.js`, UI-тесты и документация)  
**Статус:** реализована и задокументирована в рамках Top-Down workflow

## 1. Назначение и бизнес-цель

### 1.1. Постановка проблемы

До выполнения задачи WISHENKA-108 клиентская логика страницы вишлиста зависела от двух хрупких решений:

1. **Встраивание кода в общую HTML-разметку:** функция раскрытия/сворачивания карточек желаний (`toggleWishCard`) и IIFE-обработчик перетаскивания для смены порядка (drag-and-drop reorder) располагались во встроенном (inline) теге `<script>` базового шаблона `wishenka/web/templates/base.html`, а вызов `toggleWishCard` дублировался в атрибутах `onclick` и `onkeydown` каждой карточки (`wishenka/web/templates/partials/item_card.html`). В результате скрипт включался в HTML каждой страницы приложения (включая страницы без списка желаний), не мог кэшироваться отдельно и препятствовал внедрению строгой политики безопасности контента (CSP без `'unsafe-inline'`).
2. **Определение вишлиста по URL браузера:** обработчик `drop` извлекал идентификатор вишлиста с помощью разбора `window.location.pathname`. При изменении структуры маршрутов, добавлении префиксов или открытии списка по альтернативному адресу разбор завершался неудачей: карточка переставлялась на экране, но запрос на сохранение не отправлялся, и пользователь не получал никакого предупреждения о потере порядка.

### 1.2. Цели задачи

- Вынести поведение раскрытия/сворачивания карточек желаний и drag-and-drop сортировки из inline-скрипта `base.html` и inline-атрибутов `partials/item_card.html` в отдельный статический JavaScript-файл `/static/wishlist.js`.
- Заменить определение идентификатора вишлиста из адреса страницы (`window.location.pathname`) на явную декларацию в разметке контейнера списка (`#items-list[data-wishlist-id]`).
- Гарантировать отсутствие «тихого рассинхрона»: если на момент сброса карточки отсутствует валидный идентификатор вишлиста или объект `window.htmx`, визуальная перестановка в DOM не выполняется, а причина фиксируется в консоли браузера.
- Полностью сохранить прежнее пользовательское поведение, доступность (клавиатура и ARIA-атрибуты) и серверные правила доступа.

### 1.3. Ценность для пользователей и системы

- **Надёжность для владельцев и соавторов:** переименование или реструктуризация маршрутов не ломают сохранение порядка желаний; порядок карточек на экране владельца гарантированно совпадает с порядком на сервере, который видят дарители и гости.
- **Уменьшение объёма HTML и готовность к CSP:** разметка страниц освобождается от повторяющегося кода управления карточками и inline-обработчиков `on*`, снимая один из блоков для ужесточения браузерных политик безопасности.
- **Поддерживаемость:** логика страницы вишлиста изолирована в самостоятельном файле с явным DOM-контрактом и может проверяться и развиваться отдельно от шаблонов.

### 1.4. Границы задачи (Non-Goals)

В рамки WISHENKA-108 **не входят**:

- Поддержка touch-перетаскивания для мобильных устройств и Telegram Mini App (отдельная задача `WISHENKA-109`).
- Полноценные браузерные end-to-end тесты (Playwright/CDP) для раскрытия карточек и drag-and-drop (отдельная задача `WISHENKA-110`).
- Вынос остального inline-кода, на момент выполнения WISHENKA-108 остававшегося в `base.html` (CSRF, управление бронированиями, `swapWishCard`), и inline-`onclick` из модальных фрагментов (`item_edit_modal.html`, `item_archive_modal.html`, `item_preview_card.html`) — вынесено в follow-up `WISHENKA-140`.
- Изменение политики кэширования статики (`Cache-Control: no-store` в `BrowserSecurityMiddleware`) и внедрение cache-busting (версионирования/хэширования URL ассетов) — вынесено в follow-up `WISHENKA-139`.
- Включение строгого заголовка CSP, изменение серверной логики сортировки, прав доступа, модели бронирований или визуального оформления.

## 2. Функциональные требования и пользовательские сценарии

### 2.1. Роли и применимость на страницах

| Роль / страница | Маршрут | Раскрытие карточки (toggle) | Drag-and-drop сортировка |
| --- | --- | --- | --- |
| Владелец / соавтор активного вишлиста | `/web/wishlists/{wishlist_id}` | Доступно (клик, `Enter`, `Space`) | Доступна (карточки имеют `draggable="true"`) |
| Посетитель / даритель (публичная ссылка) | `/share/{public_token}` | Доступно (клик, `Enter`, `Space`) | Недоступна (`draggable="true"` отсутствует) |

### 2.2. Функциональные требования

#### FR-1. Раскрытие и сворачивание карточки желания

- Поведение одинаково на странице вишлиста (`/web/wishlists/{wishlist_id}`) и на публичной странице (`/share/{public_token}`).
- Переключение срабатывает при клике (`click`) по области `.item-card-summary` либо при нажатии клавиши `Enter` или пробела (`' '`, событие `keydown`), если событие дошло до `.item-card-summary`.
- **Исключения (подавление toggle):** если `event.target.closest('a, button, input, select, textarea, [data-no-toggle]')` находит элемент в цепочке предков от цели события, переключение не выполняется; нажатие передаётся интерактивному контролу штатно.
- **Клавиатурная защита прокрутки:** для события `keydown` с `Enter` или `' '` вызывается `event.preventDefault()` (чтобы пробел не прокручивал страницу), но только если цель не попадает под селектор исключений.
- **Изменение состояния карточки:** считывается текущее значение `aria-expanded === 'true'` на `.item-card-summary`, выставляется противоположное (`'true'` или `'false'`), а у элемента `.item-card-details` внутри родителя `summary.parentElement` свойство `hidden` устанавливается равным прежнему значению `expanded`.
- Динамически вставленные или перерисованные карточки (после htmx-запросов и `swapWishCard`) работают автоматически за счёт делегирования событий на `document`.

#### FR-2. Drag-and-drop переупорядочивание желаний (HTML5 DnD)

- Доступно только при наличии права редактирования: атрибут `draggable="true"` рендерится на `.item-card` только при `can_edit_wishlist`.
- При `dragstart` на элементе `.item-card[draggable="true"]` сохраняется ссылка на перетаскиваемую карточку и устанавливается `event.dataTransfer.effectAllowed = 'move'`.
- При `dragover` над контейнером `#items-list` (если активно перетаскивание) вызывается `event.preventDefault()` для разрешения сброса.
- При `drop` вычисляется целевая карточка `.item-card`:
  - Если отсутствует `#items-list`, не найдена целевая `.item-card` или целевая карточка совпадает с перетаскиваемой (`target === dragged`), состояние сбрасывается и ничего не изменяется.
  - Положение вставки определяется относительно вертикальной середины целевой карточки: если `event.clientY > rect.top + rect.height / 2`, карточка вставляется после цели (`target.nextSibling`), иначе — перед целью.
- При `dragend` состояние активного перетаскивания сбрасывается.

#### FR-3. Явная идентификация вишлиста и защита от расхождения состояния

- Идентификатор вишлиста считывается в момент `drop` из атрибута `data-wishlist-id` живого элемента `document.getElementById('items-list')`; обращение к `window.location` не используется.
- Значение идентификатора должно соответствовать шаблону `/^\d+$/`.
- Проверка валидности `data-wishlist-id` и наличия `window.htmx` выполняется **до** вызова `list.insertBefore(...)`.
- Если `data-wishlist-id` отсутствует/нечисловой или `window.htmx` не загружен, DOM не изменяется, сетевой запрос не отправляется и в консоль выводится `console.warn` с указанием конкретной причины.
- При выполнении предусловий карточка перемещается в DOM, собирается упорядоченный массив `data-item-id` всех `.item-card` внутри `#items-list` и вызывается `window.htmx.ajax('POST', '/web/wishlists/' + wishlistId + '/items/reorder', { target: '#items-list', swap: 'innerHTML', values: { item_ids: ids } })`.

#### FR-4. Сохранение `data-wishlist-id` при обновлениях списка

- Оба шаблона (`wishlist_detail.html` и `share_wishlist.html`) задают атрибут `data-wishlist-id="{{ wishlist.id }}"` на корневом контейнере `<section class="wishlist-items" id="items-list">`.
- Все серверные и клиентские операции обновления списка (drag-and-drop reorder, кнопки move up/down, быстрое добавление, редактирование, архивация через OOB-swap, восстановление из архива) меняют только внутреннее содержимое `#items-list` (`innerHTML`, `beforeend`, `afterbegin` либо `none` с OOB-вставками) и никогда не заменяют сам контейнер через `outerHTML` или `delete`.
- Фрагменты ответа (`partials/items_list.html`) не содержат `id="items-list"`.

#### FR-5. Удаление inline-скрипта toggle/DnD и inline-обработчиков карточек

- В `base.html` не содержатся функция `toggleWishCard` и код drag-and-drop; вместо этого в `<head>` после тегов `htmx` / `json-enc` подключается `<script src="/static/wishlist.js" defer></script>`.
- В `partials/item_card.html` отсутствуют inline-атрибуты `onclick`, `onkeydown` и иные `on*`-атрибуты, при сохранении `role="button"`, `tabindex="0"`, `aria-expanded="false"` и `aria-controls="item-details-{{ item.id }}"` на `.item-card-summary`.

### 2.3. Пользовательские сценарии

- **UC-108-01 (Раскрытие/сворачивание карточки):** владелец на странице вишлиста или гость на странице `/share/{token}` кликает по области карточки или нажимает `Enter`/`Space` на сфокусированном `.item-card-summary` -> панель `.item-card-details` открывается или скрывается, `aria-expanded` обновляется; клики по ссылкам, кнопкам, полям ввода и элементам `[data-no-toggle]` не меняют раскрытие карточки.
- **UC-108-02 (Сортировка перетаскиванием):** владелец на странице вишлиста (в том числе с query-параметрами в URL или изменённой схемой адреса страницы) перетаскивает карточку до или после другой карточки -> порядок в DOM обновляется, отправляется `POST /web/wishlists/{wishlist_id}/items/reorder` с новым перечнем `item_ids`, содержимое `#items-list` перерисовывается ответом сервера, а `data-wishlist-id` на контейнере сохраняется.
- **UC-108-03 (Сброс на себя или вне списка):** владелец отпускает карточку поверх неё самой или за пределами карточек списка -> DOM не меняется, запрос на сервер не отправляется.
- **UC-108-04 (Отказ при неисправной странице):** если на контейнере `#items-list` отсутствует корректный `data-wishlist-id` или не загружен `window.htmx`, при попытке `drop` порядок на экране не меняется и в консоли браузера фиксируется причина пропуска.
- **UC-108-05 (Работа после динамического обновления списка):** после добавления, редактирования, перемещения кнопками, архивации или восстановления желания повторные клики и drag-and-drop продолжают работать без перезагрузки страницы.

### 2.4. Ключевые инварианты

1. **Неизменность пользовательского поведения:** наблюдаемое поведение раскрытия карточек, доступность с клавиатуры и механика drag-and-drop полностью сохраняются.
2. **Атомарность «DOM + отправка»:** визуальная перестановка карточки в DOM не происходит, если невозможно сформировать корректный запрос на сохранение.
3. **Защита контейнера `#items-list`:** ни один HTMX-сценарий не заменяет элемент `#items-list` целиком (`outerHTML`/`delete`), поэтому объявленный `data-wishlist-id` сохраняется на всём протяжении жизни страницы.
4. **Изоляция ролей и прав:** посетитель публичной страницы не получает возможности сортировки; авторитетная проверка прав доступа и целостности перестановки остаётся на сервере.

## 3. Архитектура, компоненты и интерфейсы

### 3.1. Компонентная схема и потоки взаимодействия

```text
base.html (<head>)
  |-- /static/miniapp.css
  |-- telegram-web-app.js, htmx.org@1.9.12, json-enc.js (CDN)
  `-- /static/wishlist.js (defer)        <-- Вынесенная логика toggle + HTML5 DnD

wishlist_detail.html / share_wishlist.html
  `-- <section class="wishlist-items" id="items-list" data-wishlist-id="{{ wishlist.id }}">
        `-- partials/items_list.html -> partials/item_card.html
              |-- .item-card [data-item-id] [draggable="true" для редактора]
              `-- .item-card-summary (без onclick/onkeydown)

wishenka/web/static/wishlist.js (IIFE, 'use strict', без глобалей)
  |-- click / keydown (document) --> findSummary() --> toggleWishCard()
  `-- dragstart / dragover / drop / dragend (document)
        `-- drop --> #items-list[data-wishlist-id] (/^\d+$/) + window.htmx
              `-- htmx.ajax POST /web/wishlists/{id}/items/reorder
                    --> target: '#items-list', swap: 'innerHTML'
```

*(Примечание: на момент завершения WISHENKA-108 в `base.html` оставался не затронутый задачей inline-блок CSRF/броней/`swapWishCard`, независимый от `wishlist.js`; позднее он также был вынесен в статические скрипты в рамках follow-up задач.)*

### 3.2. Модули и ответственность

| Компонент / файл | Назначение и ответственность в рамках WISHENKA-108 |
| --- | --- |
| `wishenka/web/static/wishlist.js` | Единственный клиентский модуль поведения карточек списка желаний: делегированное переключение деталей (`toggleWishCard`, `findSummary`) и HTML5 drag-and-drop сортировка. Зависит только от DOM-контракта и `window.htmx` (в момент `drop`). |
| `wishenka/web/templates/base.html` | Подключает `/static/wishlist.js` с атрибутом `defer` после скриптов `htmx` и `json-enc`; не содержит кода `toggleWishCard` и DnD. |
| `wishenka/web/templates/wishlist_detail.html` | Страница владельца/участника; декларирует `data-wishlist-id="{{ wishlist.id }}"` на `<section id="items-list">`. |
| `wishenka/web/templates/share_wishlist.html` | Публичная страница по ссылке; декларирует `data-wishlist-id="{{ wishlist.id }}"` на `<section id="items-list">`. |
| `wishenka/web/templates/partials/item_card.html` | Шаблон карточки желания; сохраняет ARIA-атрибуты и классы, не содержит `onclick`/`onkeydown`. |
| `wishenka/web/app.py` | Монтирует каталог статики через `app.mount("/static", StaticFiles(...), name="static")`, обеспечивая раздачу `/static/wishlist.js`. |
| `wishenka/web/routes/items_ui.py` | Серверная ручка `reorder_items_ui` (`POST /web/wishlists/{wishlist_id}/items/reorder`) и `move_item_ui` через общий хелпер `_reordered_response`; не модифицировалась. |

### 3.3. Ключевые элементы `wishenka/web/static/wishlist.js`

В рамках WISHENKA-108 скрипт построен как классический файл внутри IIFE (`(() => { 'use strict'; ... })();`) с полным JSDoc и без экспорта глобальных имён:

- **Константы:**
  - `SUMMARY_SELECTOR = '.item-card-summary'`
  - `TOGGLE_EXCLUSION = 'a, button, input, select, textarea, [data-no-toggle]'`
  - `WISHLIST_ID_PATTERN = /^\d+$/`
- **Состояние:** `let dragged = null` — ссылка на перетаскиваемую карточку в ходе текущего DnD-жеста.
- **Функции:**
  - `findSummary(event)` — безопасно возвращает ближайший `.item-card-summary`, проверяя наличие `event.target.closest`.
  - `toggleWishCard(event, summary)` — проверяет `event.target.closest(TOGGLE_EXCLUSION)`, вызывает `event.preventDefault()` при `event.type === 'keydown'`, переключает `aria-expanded` и `details.hidden`.
- **Обработчики событий на `document`:** `click`, `keydown` (фильтр `Enter` и `' '`), `dragstart`, `dragover`, `drop`, `dragend`.

### 3.4. Контракты данных и интерфейсы

#### Контракт «HTML-шаблон -> `wishlist.js`»

- `#items-list[data-wishlist-id]` — строковое представление положительного целого идентификатора `wishlist.id` (проверяется паттерном `/^\d+$/`).
- `.item-card[data-item-id]` — идентификатор желания; при `can_edit_wishlist` также присутствует `draggable="true"`.
- `.item-card-summary` — элемент с `role="button"`, `tabindex="0"`, `aria-expanded="false"|"true"`, `aria-controls="item-details-<id>"`.
- `.item-card-details` — вложенная панель деталей внутри `.item-card`, скрываемая атрибутом `hidden`.
- `[data-no-toggle]` — явная разметка элементов внутри summary (например, `.item-giver`, формы бронирования, `.item-actions`), не переключающих карточку.

#### Контракт «`wishlist.js` -> серверный API»

- **Запрос переупорядочивания:**

```http
POST /web/wishlists/{wishlist_id}/items/reorder HTTP/1.1
Content-Type: application/x-www-form-urlencoded

item_ids=<id_1>&item_ids=<id_2>&...
```

- **Успешный ответ (`200 OK`):** HTML-фрагмент `partials/items_list.html` без тега `<section id="items-list">`, подставляемый в `#items-list` через `swap: 'innerHTML'`.
- **Ошибка перестановки (`400 Bad Request`):** возвращается при расхождении перечня `item_ids` с текущим активным составом списка (`ValueError` из `WishlistService.reorder_wish_items`).
- **Загрузка статического ресурса:** `GET /static/wishlist.js` -> `200 OK`, заголовок `Content-Type` содержит `javascript`.

### 3.5. Переходы состояний

1. **Состояние раскрытия карточки (`Collapsed` <-> `Expanded`):**
   - Исходное состояние при рендере: `aria-expanded="false"`, `.item-card-details[hidden]`.
   - Событие `click` или `keydown` (`Enter` / `' '`) на `.item-card-summary` вне `TOGGLE_EXCLUSION` переводит карточку в противоположное состояние (`aria-expanded` и `details.hidden` инвертируются).
2. **Состояние drag-and-drop перестановки:**
   - `Idle` (`dragged = null`) --(`dragstart` на `.item-card[draggable="true"]`)--> `Dragging` (`dragged = card`).
   - `Dragging` --(`dragover` внутри `#items-list`)--> `Dragging` (`event.preventDefault()`).
   - `Dragging` --(`drop` на другую `.item-card` при валидных `data-wishlist-id` и `window.htmx`)--> перестановка в DOM + `POST .../items/reorder` -> `Idle` (`dragged = null`).
   - `Dragging` --(`drop` на себя / вне `.item-card` / невалидный `data-wishlist-id` / отсутствует `window.htmx` / `dragend`)--> `Idle` (`dragged = null`, DOM не изменён).

## 4. Нефункциональные требования, безопасность и наблюдаемость

### 4.1. Производительность и доставка статики

- **Сложность обработки событий:** делегированные слушатели на `document` работают за `O(1)` по числу обработчиков (не зависят от количества карточек в вишлисте). Обработчик `keydown` немедленно завершается для всех клавиш, кроме `'Enter'` и `' '`.
- **Размер ресурса:** выделенный `wishlist.js` в объёме WISHENKA-108 занимал 3 868 байт; этот код больше не дублируется в каждом HTML-ответе.
- **Кэширование:** `BrowserSecurityMiddleware` (`wishenka/web/security.py:79`) устанавливает `Cache-Control: no-store` на все HTTP-ответы, включая `/static/*`. Это гарантирует мгновенную доставку обновлений скрипта без версионирования URL, но вызывает повторное скачивание ресурса при загрузке страницы. Настройка раздельной политики кэширования для статики оформлена как follow-up `WISHENKA-139`.

### 4.2. Безопасность, приватность и ограничения

- **Движение к строгой CSP:** удаление toggle/DnD из inline `<script>` в `base.html` и устранение `onclick`/`onkeydown` в `partials/item_card.html` убирает один из барьеров на пути к отказу от `'unsafe-inline'`. Полный переход к строгой CSP требует переноса оставшихся inline-фрагментов (`WISHENKA-140`).
- **Авторитетность сервера и тайна сюрприза:** проверка `WISHLIST_ID_PATTERN = /^\d+$/` на клиенте носит защитно-диагностический характер (формально допускает `0` и ведущие нули). Права доступа (`_ensure_member_and_active`), статус вишлиста и консистентность списка элементов проверяются на сервере; публичная страница по ссылке не содержит `draggable="true"`; видимость бронирований не затрагивается.
- **Конфиденциальность диагностик:** клиентское предупреждение в консоли содержит только фиксированный текст причины и строковое значение `data-wishlist-id` из шаблона (или пустую строку), без персональных данных пользователей.
- **Платформенное ограничение:** HTML5 drag-and-drop в объёме WISHENKA-108 не срабатывает на большинстве сенсорных устройств (мобильные браузеры / Telegram); альтернативой служат кнопки перемещения вверх/вниз, а touch-поддержка вынесена в `WISHENKA-109`.

### 4.3. Наблюдаемость: логирование и метрики

- **Клиентское логирование (`wishenka/web/static/wishlist.js`):**
  - Штатные операции раскрытия и успешной сортировки не логируются.
  - При невозможности отправить запрос сортировки в обработчике `drop` выводится единое предупреждение `console.warn` с префиксом `wishlist.js: reorder skipped: ` и перечислением применимых причин через `; `:
    - `#items-list[data-wishlist-id] is not numeric (got "<value>")`
    - `window.htmx is not loaded (CDN blocked or script order)`
  - Поскольку невалидный `wishlist_id` на сервер не отправляется, данное предупреждение является единственным диагностическим сигналом сбоя шаблона или порядка загрузки скриптов.
- **Серверное логирование (`wishenka/web/routes/items_ui.py`):**
  - Не менялось в рамках задачи; проверены существующие структурированные события:
    - `INFO` — `extra={"event": "ui_items_reordered", "wishlist_id": ..., "actor_id": ..., "user_id": ..., "item_count": ...}` при успешном `POST /web/wishlists/{wishlist_id}/items/reorder`.
    - `WARNING` — `extra={"event": "ui_items_reorder_rejected", "wishlist_id": ..., "actor_id": ..., "user_id": ..., "reason": "invalid_permutation"}` при отклонении перестановки с кодом `400`.
    - Смежный `POST /items/{item_id}/move` использует ту же ветку отклонения `ui_items_reorder_rejected`, а при успехе логирует `INFO` с `event="ui_item_moved"` (`wishlist_id`, `item_id`, `actor_id`, `user_id`, `direction`).
- **Метрики и телеметрия:**
  - Прикладной стек метрик (Prometheus/Grafana) и система сбора клиентских ошибок (`Sentry`, error-beacon) в проекте отсутствуют и в задаче не вводились. Запросы к `/static/wishlist.js` (статус `200`/`404`/`5xx` и задержка) фиксируются в access-логах `uvicorn` и `RequestLoggingMiddleware`.

## 5. Верификация и критерии приёмки

### 5.1. Критерии приёмки (Definition of Done)

1. Раскрытие и сворачивание карточки кликом и клавишами `Enter`/`Space` работает без изменений на странице владельца и на публичной странице; клики по ссылкам, кнопкам, полям форм и элементам `[data-no-toggle]` не переключают карточку.
2. Drag-and-drop сортировка для владельца работает как прежде; сброс карточки на саму себя или вне карточек списка ничего не изменяет.
3. Идентификатор вишлиста считывается из объявленного страницей атрибута `data-wishlist-id` на `#items-list` и не зависит от URL страницы (включая наличие query-параметров).
4. После любых перерисовок списка (reorder, move up/down, добавление, редактирование, архивация, восстановление) `data-wishlist-id` сохраняется на `#items-list`, и последующий drag-and-drop отправляет запрос для правильного вишлиста.
5. Страницы владельца и публичной ссылки не содержат inline-кода toggle/DnD в `base.html` и inline-`on*` атрибутов на карточках; поведение доставляется через `/static/wishlist.js`, подключаемый с `defer` в `base.html`.
6. Прочая логика `base.html` (идентификация/CSRF, бронирования, контролы дарителя, `swapWishCard`) остаётся нетронутой в рамках задачи.
7. Полный набор автоматических тестов зелёный; тесты, искавшие `toggleWishCard` в HTML, адаптированы только к новому месту доставки без ослабления поведенческих проверок.
8. Документация разработчика (`doc/dev/miniapp.md`, `doc/dev/wishlists.md`, `doc/dev/reservations.md`) отражает новое расположение скрипта и контракт `data-wishlist-id`.

### 5.2. Автоматизированные и ручные тестовые сценарии

Для проверки требований без браузерного JS-раннера создан модуль `tests/test_wishlist_static_script.py` (`pytestmark = pytest.mark.timeout(30)`, `TestClient` + изолированная SQLite в `tmp_path`, без сети, параметризация по страницам `owner` и `share`):

| Группа | Тест / проверка | Проверяемый контракт |
| --- | --- | --- |
| A | `test_inline_script_no_longer_holds_toggle_or_dnd` | В объединённом тексте inline `<script>` отсутствуют `toggleWishCard`, `dragstart`, `dragover`, `window.location`, `/items/reorder`. |
| A | `test_page_loads_wishlist_script_deferred_after_htmx` | В `<head>` присутствует `<script src="/static/wishlist.js" defer>` после скрипта `htmx.org`. |
| B | `test_static_wishlist_script_content` | `GET /static/wishlist.js` возвращает `200` и `content-type` с `javascript` (при сдаче WISHENKA-108 проверялись и строковые маркеры поведения, впоследствии перенесённые в браузерные тесты `WISHENKA-110`). |
| C | `test_cards_have_no_inline_event_handlers` | На owner- и share-страницах ни у одного элемента нет `on*`-атрибутов; `.item-card-summary` сохраняет `role="button"`, `tabindex="0"`, `aria-expanded="false"`, `aria-controls`. |
| D | `test_items_list_declares_wishlist_id` | Контейнер `#items-list` имеет `data-wishlist-id == str(wishlist_id)` на обеих страницах. |
| D | `test_items_list_wishlist_id_independent_of_query` | Запрос owner-страницы с `?x=1` сохраняет то же значение `data-wishlist-id`. |
| D (guard) | `test_guard_no_swap_replaces_items_list_container` | Ни один элемент с `hx-target="#items-list"` не использует `hx-swap` равный `outerHTML` или `delete`; ответы `POST .../items/reorder` и `POST .../items/{id}/move` возвращают `200` и не содержат `id="items-list"`. |

Точечно обновлены существующие тесты (без изменения сути проверок):

- `tests/test_wish_items_list_reorder_ui.py` — проверка ссылки `src="/static/wishlist.js"` на странице и статуса `200` на `GET /static/wishlist.js` вместо поиска `toggleWishCard` в HTML.
- `tests/test_wish_card_giver_controls.py` (`assert_expanded_refresh_clears_hidden`) — смена sanity-маркера с `toggleWishCard` на `swapWishCard` при сохранении проверки восстановления `aria-expanded` и сброса `hidden`.
- `tests/test_reservations_cabinet_ui.py` — без изменений.

По артефактам закрытия WISHENKA-108 (`00-roadmap.md`, `40-code-cleanup.md`):

- Модульный тест задачи (`tests/test_wishlist_static_script.py`): `11 passed` (после шага Step 3, где 10 тестов были красными и 1 guard — зелёным).
- Профильные UI-тесты (reorder, giver controls, кабинет броней, CRUD/TMA): `73 passed`.
- Полный прогон `PYTHONDONTWRITEBYTECODE=1 make test`: `523 passed, 0 failed` (2 сторонних deprecation-предупреждения, 455 с).
- Статический анализ: `make analyze` (`ruff`, `ruff format`, `mypy` по 97 файлам) — без замечаний; `node --check wishenka/web/static/wishlist.js` — синтаксис валиден.
- Одноразовая ручная sanity-проверка в Chromium CDP (htmx замокан, CDN заблокирован, скрипт не коммитился): клик переключает `aria-expanded`, `Enter` возвращает состояние, `drop` отправляет `POST /web/wishlists/1/items/reorder` с `item_ids: ["2", "1"]`.

### 5.3. Известные ограничения и дальнейшие задачи (`60-tech-debt.md`)

Блокирующих дефектов (BLOCKER) не выявлено; зафиксированы следующие неблокирующие follow-up задачи и принятые отклонения:

1. **Оставшийся inline-код в `base.html` и модальных partials (`WISHENKA-140`):** на момент закрытия WISHENKA-108 в `base.html` сохранялся inline-блок (CSRF, брони, `swapWishCard`), а в `partials/item_edit_modal.html` (`:11`, `:82`, `:96`, `:189`), `partials/item_archive_modal.html` (`:32`) и `partials/item_preview_card.html` (`:56`) оставались inline `onclick`; тест C не проверял разметку модальных фрагментов.
2. **Отсутствие реального кэширования `/static/*` (`WISHENKA-139`):** действие `Cache-Control: no-store` из `wishenka/web/security.py` распространяется и на `/static/wishlist.js`, не позволяя браузеру кэшировать скрипт до внедрения политики исключения `/static/*` и версионирования URL для всех ассетов (`miniapp.css`, `miniapp.js`, `wishlist.js`).
3. **Захардкоженный маршрут reorder и селекторы в JS (`WISHENKA-141`):** путь `/web/wishlists/${wishlistId}/items/reorder` дублирует серверную маршрутизацию `items_ui.py`; предлагается передавать `data-reorder-url` на `#items-list` и убрать регулярное выражение `/^\d+$/` (целесообразно совместить с `WISHENKA-109`).
4. **Хрупкие строковые проверки JS и отсутствие автотестов реального исполнения (`WISHENKA-110`):** в WISHENKA-108 не было JS-раннера и автоматической проверки реального исполнения `toggleWishCard`, DnD, ветки `console.warn` и выживания `data-wishlist-id` после OOB-архивации; строковые проверки в `test_wishlist_static_script.py` и подстрочная проверка `"onclick" not in html` в `test_wish_items_list_reorder_ui.py` отмечены для замены поведенческими браузерными тестами в `WISHENKA-110`.
5. **Смежные существующие задачи (без дублирования):** `WISHENKA-109` (touch-сортировка для мобильных/Telegram), `WISHENKA-110` (Playwright/CDP тесты), `WISHENKA-126` (неотслеживаемый файл `core` в корне репозитория, требующий точечного `git add`).
6. **Принятые мелкие особенности реализации:** чтение `list.getAttribute('data-wishlist-id')` вместо `list.dataset.wishlistId`; отсутствие повторной проверки наличия `.closest` у `event.target` внутри `toggleWishCard` (гарантируется предшествующим `findSummary`); модульная переменная `dragged` (может не сброситься при удалении карточки из DOM параллельным htmx-свопом во время перетаскивания); внешние CDN-скрипты без SRI.
