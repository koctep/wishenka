# WISHENKA-108: Вынести inline JS из base.html в статический файл и читать wishlist id из data-атрибута

## Research

Дата исследования: 2026-11-14. Внешних источников не требуется: задача целиком внутри репозитория,
все факты проверены по файлам. Язык: Python (шаблоны, тесты) + JavaScript (один статический файл),
см. `lsr-python`, `lsr-javascript`, `lsr-markdown`, `do-testing`.

### Что сейчас в `wishenka/web/templates/base.html`

Один inline-`<script>` в `<head>` (после htmx), содержит пять независимых частей:

| Часть | Что делает | Судьба в этой задаче |
| ----- | ---------- | -------------------- |
| `toggleWishCard(event, summary)` | глобальная функция, вызывается из `onclick`/`onkeydown` в `item_card.html` | переезжает в `wishlist.js` |
| IIFE drag-and-drop (`dragstart`/`dragover`/`drop`/`dragend` на `document`) | перестановка карточек, `htmx.ajax('POST', '/web/wishlists/<id>/items/reorder', ...)`, id берётся из `window.location.pathname` | переезжает, id читается из `#items-list[data-wishlist-id]` |
| `DOMContentLoaded` + `htmx:configRequest` (CSRF) | viewer/CSRF | остаётся inline (вне scope, требования, п. Out of scope) |
| `reservationRequestPath`, `htmx:afterRequest` | брони, кабинет, giver-контролы | остаётся inline |
| `swapWishCard` | `outerHTML` карточки с сохранением `aria-expanded` | остаётся inline |

Toggle и DnD не зависят от остального inline-кода (никаких общих переменных), поэтому вынос
безопасен и не меняет порядок выполнения остального.

### Как `item_card.html` подключает toggle

`partials/item_card.html:8-17`: `.item-card-summary` (`role="button"`, `tabindex="0"`,
`aria-expanded`, `aria-controls`) несёт inline `onclick="toggleWishCard(event, this)"` и
`onkeydown="if (event.key === 'Enter' || event.key === ' ') { toggleWishCard(event, this); }"`.
Исключения из toggle: `event.target.closest('a, button, input, select, textarea, [data-no-toggle]')`
(`closest` идёт вверх по всему дереву, не только внутри summary); для `keydown` перед переключением
вызывается `preventDefault()` (чтобы Space не прокручивал страницу), но **только если** цель не
интерактивная. Эти нюансы нужно сохранить дословно. Внутренний `data-no-toggle` стоит на
`.item-giver`, форме брони, `.item-actions` и др. (16 мест) — разметка не меняется.

Карточка уже несёт `data-item-id`, `data-wishlist-id`, `data-is-first/last` (используются inline
`htmx:afterRequest`/`swapWishCard`) — эти атрибуты не трогаем.

### Контейнер списка и перерисовки

`#items-list` — `<section class="wishlist-items" id="items-list">` в двух шаблонах:
`wishlist_detail.html:27` и `share_wishlist.html:27`; оба рендерят `partials/items_list.html` с
`wishlist.items`, то есть `wishlist.id` в контексте есть на обеих страницах. Все htmx-обновления
идут **во внутрь** контейнера: каждый элемент с `hx-target="#items-list"`
(`item_quick_add.html:5` — `beforeend`; `item_edit_modal.html:30` — `beforeend`;
`archived_items_section.html:17` (кнопка «Восстановить») — `beforeend`; кнопки move up/down
`item_card.html:182,192` — `innerHTML`; `item_archive_modal.html:18` — `hx-swap="none"`, ответ
приходит через OOB-swap, `items_ui.py:1024-1025`) и сам reorder
(`htmx.ajax(..., swap: 'innerHTML')`).
Эндпоинты возвращают `partials/items_list.html` (`_items_list_html`, `items_ui.py:779`), в нём нет
`id="items-list"`. Ни один swap не заменяет `#items-list` через `outerHTML`, поэтому атрибут на
`<section>` переживает все перерисовки; повторно его выдавать из фрагментов не нужно.
Единственные `outerHTML` в проекте — `swapWishCard` (карточка), кабинет броней и модалки/превью —
к `#items-list` не относятся. Инвариант «никто не делает `outerHTML` по `#items-list`» защищаем
тестом (см. Failing Repro, группа D).

### Статика

- `wishenka/web/app.py:201`: `app.mount("/static", StaticFiles(directory=.../static), name="static")`;
  в каталоге `miniapp.css`, `miniapp.js`.
- `base.html` грузит только `/static/miniapp.css` (без версии/хэша в URL).
  `miniapp.js` подключается **только** страницей Mini App (`routes/miniapp.py:24`, `defer`) — это
  самостоятельный SPA-скрипт с top-level `const root = document.getElementById('app')`,
  `api()`, `status()` и т. п. Подключать его на обычных страницах нельзя (глобальные побочные
  эффекты, чужой код, 399 строк ради 40).
- Cache-busting в репозитории не применяется ни для css, ни для js.
- `BrowserSecurityMiddleware` (`security.py:78-80`) выставляет `Cache-Control: no-store` на **все**
  ответы, включая `/static/*`. Значит, цель «кэшируемый ресурс» из требований технически достигается
  только при смене этой политики (вне scope: сейчас файл не кэшируется, но и не дублируется в каждой
  странице как inline и не мешает будущей строгой CSP). Фиксируем как факт для Step 7 (tech debt),
  не меняем.

### Существующие тесты, зависящие от расположения кода

| Тест | Где зависимость | Что делаем |
| ---- | --------------- | ---------- |
| `tests/test_wish_items_list_reorder_ui.py:136` | `assert "toggleWishCard" in html` (комментарий «inline toggle attributes») | заменяем на проверку нового расположения (см. ниже) |
| `tests/test_wish_card_giver_controls.py:447-502` | `inline_script(html)`; `assert_expanded_refresh_clears_hidden` берёт inline-скрипт и в качестве проверки «скрипт прочитан» ищет в нём `toggleWishCard` | `swapWishCard` остаётся inline, поэтому поиск `outerHTML`/`aria-expanded` не меняется; sanity-маркер меняется на `swapWishCard` |
| `tests/test_reservations_cabinet_ui.py:509-574` | `base_script()` читает inline-скрипты (для `refresh_script_problems`, ветка `.reservation-row`), `static_script()` читает `/static/miniapp.js` | не меняются: рефреш броней остаётся inline; `static_script` переиспользуем для `wishlist.js` |
| `tests/test_wishlist_management_browser.py`, `test_wishlist_sections_ui.py` (Chromium) | не затрагивают toggle/DnD (grep по `dragstart`, `toggleWishCard`, `reorder`, `onclick` в `tests/` — только три файла выше) | не меняются |

Других хелперов, ищущих JS в разметке, в `tests/` нет (grep по `base.html`, `toggleWishCard`,
`inline_script`, `base_script`, `window.location`, `dragstart`, `onkeydown`, `onclick`).

### Тестовая инфраструктура

JS-раннера нет, `package.json` нет. `pytest-timeout>=2.3.1` в dev-extras, каждый модуль обязан
иметь `pytestmark = pytest.mark.timeout(...)` (do-testing). Фикстура `test_app` и
`auth_header`/`make_user` дублируются в тестовых модулях (общего `conftest` для приложения нет;
`tests/conftest.py` содержит только `chromium_executable`). Браузерные тесты (`browser_support`)
для toggle/DnD принадлежат WISHENKA-110 и в этой задаче не пишутся.

## Implementation Plan

1. **Новый файл `wishenka/web/static/wishlist.js`** (классический скрипт, IIFE, `'use strict'`,
   ES6+, JSDoc на функциях). Содержит: `toggleWishCard`, делегированные `click`/`keydown`,
   DnD-обработчики. Никаких глобальных имён.
2. **`base.html`**: удалить из inline-`<script>` функцию `toggleWishCard` и DnD-IIFE; добавить
   `<script src="/static/wishlist.js" defer></script>` после тегов htmx/json-enc (перед inline
   блоком, который остаётся). Остальной inline-код (CSRF, брони, `swapWishCard`) не трогается.
3. **`partials/item_card.html`**: убрать `onclick` и `onkeydown` у `.item-card-summary`; `role`,
   `tabindex`, `aria-expanded`, `aria-controls` остаются без изменений.
4. **`wishlist_detail.html` и `share_wishlist.html`**: добавить
   `data-wishlist-id="{{ wishlist.id }}"` на `<section ... id="items-list">`.
5. **Тесты**: новый модуль + минимальные правки трёх существующих (см. ниже).
6. **Документация (Step 8)**: `doc/dev/miniapp.md` (~443, ~452), `doc/dev/wishlists.md` (~316, плюс
   дерево шаблонов/статики около 282), `doc/dev/reservations.md` (~335, ~343, ~382, ~534, ~1051:
   пересмотреть каждую ссылку на `base.html`; править только те, что говорят о toggle/DnD,
   остальные — про CSRF/брони — остаются верными).

### Порядок загрузки и `defer`

`<script src defer>` в `<head>` после htmx. Обработчики навешиваются на `document` (делегирование) и
не требуют готового DOM, поэтому порядок относительно htmx/DOMContentLoaded не критичен;
`window.htmx` проверяется в момент `drop`, а не при загрузке (как и сейчас). `defer` сохраняет
порядок выполнения и не блокирует разбор страницы. Не `type="module"`: репозиторий использует
классический `defer` для `miniapp.js`, модуль не даёт выигрыша для одного IIFE.

### Дизайн делегирования событий

- **Toggle (click)**: один `document.addEventListener('click', ...)`:
  `summary = e.target.closest('.item-card-summary')`; если нет — выйти; иначе вызвать
  `toggleWishCard(e, summary)`.
- **Toggle (keyboard)**: `document.addEventListener('keydown', ...)`: тот же поиск summary и условие
  `e.key === 'Enter' || e.key === ' '`, затем `toggleWishCard`. Поведение ровно как у inline:
  `keydown` всплывает от дочерних элементов, интерактивные цели отсекаются внутри
  `toggleWishCard`, `preventDefault()` только для не-интерактивных.
- **Тело `toggleWishCard`** переносится без изменений логики (селектор исключений
  `a, button, input, select, textarea, [data-no-toggle]`, переключение `aria-expanded`, поиск
  `.item-card-details` через `summary.parentElement`, `details.hidden`). Хук — существующий класс
  `.item-card-summary`; нового data-атрибута на карточках не вводим (класс уже стабилен, на нём
  держатся CSS и `swapWishCard`). Делегирование на `document` автоматически покрывает карточки,
  появившиеся после htmx-swap и `swapWishCard`, повторной привязки не нужно (это лучше, чем inline).
- **DnD**: переносится как есть (уже делегирован на `document`), с двумя изменениями:
  1. wishlist id читается в момент `drop` из `list.dataset.wishlistId` живого
     `document.getElementById('items-list')`, валидируется `/^\d+$/`;
  2. проверка id и `window.htmx` выполняется **до** `insertBefore`; если id нет/невалиден или htmx
     недоступен, карточка не переставляется и в консоль пишется `console.warn` — исключаем
     сегодняшнее «на экране переставилось, но не сохранено». URL строится как
     `'/web/wishlists/' + id + '/items/reorder'` (путь `/web/wishlists/` остаётся в JS как префикс
     API, но от `location` больше не зависит).
  `drop на себя / вне списка` по-прежнему ничего не меняет, `dragend` сбрасывает состояние.

### Cache-busting

Не добавляем: в репозитории нет механизма (ни для `miniapp.css`, ни для `miniapp.js`), а
`no-store` на всех ответах делает его бессмысленным. URL — `/static/wishlist.js` (как в note из
`ai-tasks/WISHENKA-15/60-tech-debt.md`).

### Стратегия тестов

JS-раннера нет и вводить его вне scope, а требования ограничивают проверки тем, что возможно без
браузера. Поэтому: (а) Python-тесты, которые парсят HTML (`BeautifulSoup`, уже используется в
тестах) и читают отдаваемый `/static/wishlist.js` как текст; (б) браузерная проверка паритета
(Chromium/CDP) — в WISHENKA-110, не здесь. Риск, что статические проверки строк не докажут
поведенческий паритет, снижаем так: проверяем смысловые признаки (селектор исключений дословно,
обе клавиши, `preventDefault` только в keydown-ветке, чтение `dataset.wishlistId`, отсутствие
`location`), а на Step 4 разработчик один раз вручную прогоняет страницу в Chromium (скилл `run`)
и фиксирует результат в roadmap; в репозиторий этот ручной прогон не коммитится.

### Failing Repro (Step 3)

Новый модуль `tests/test_wishlist_static_script.py`, `pytestmark = pytest.mark.timeout(30)`
(интеграционные тесты через `TestClient` + SQLite в `tmp_path`, без сети и браузера;
детерминированы: нет ожиданий, часов и случайности). Фикстуры `test_app`, `auth_header`, `make_user`,
сидирование — по образцу `tests/test_wish_items_list_reorder_ui.py` (владелец с двумя желаниями,
второй пользователь-друг, публичная ссылка). Сети нет: тесты не исполняют JS и не обращаются к
CDN, только `client.get`.

Тесты (все **красные на текущем коде** по правильным причинам):

- **A. Inline-код выведен из `base.html`** (owner-страница и share-страница, параметризация):
  в объединённом тексте inline-скриптов нет `toggleWishCard`, `dragstart`, `dragover`,
  `window.location`, `/items/reorder`; в `<head>` есть
  `<script src="/static/wishlist.js" defer>`, и он стоит после `htmx.org` (порядок по индексам
  `<script>`). Падает сейчас: inline содержит всё перечисленное, `src` отсутствует.
- **B. Статический файл**: `GET /static/wishlist.js` -> 200, `content-type` содержит `javascript`;
  тело содержит `toggleWishCard`, селектор исключений
  `a, button, input, select, textarea, [data-no-toggle]`, `'Enter'`, `' '` (пробел),
  `.item-card-summary`, `dragstart`, `dragover`, `drop`, `dragend`, `/items/reorder`,
  `wishlistId` или `data-wishlist-id`; не содержит `location.pathname`/`window.location`.
  Падает сейчас: 404 (assert на статус стоит первым, чтобы причина была очевидной).
- **C. `item_card` без inline-обработчиков**: на owner- и share-странице у **ни одного** элемента нет
  атрибутов, начинающихся с `on` (`onclick`, `onkeydown` и т. п.), а у `.item-card-summary`
  сохранены `role="button"`, `tabindex="0"`, `aria-expanded="false"`, `aria-controls`.
  Падает сейчас: `onclick`/`onkeydown` есть.
- **D. Явное объявление wishlist id**:
  - owner-страница и share-страница: `#items-list` имеет `data-wishlist-id == str(wl.id)`;
    owner-страница, запрошенная с query (`?x=1`), даёт то же значение. Падает сейчас: атрибута нет.
  - **Переживает перерисовки**: на owner-странице каждый элемент с `hx-target="#items-list"` имеет
    `hx-swap` не равный `outerHTML` и `delete` (допустимы `innerHTML`, `beforeend`, `afterbegin`,
    `none`; белый список не используется, чтобы не краснеть на `none` у архивного модального окна), а ответы
    `POST .../items/reorder` и `POST .../items/{id}/move` (фрагменты, заменяющие содержимое) не
    содержат `id="items-list"`. Эти проверки зелёные уже сейчас и остаются инвариантом после
    изменения (фиксируют п. 4 DoD); помечаются в docstring как guard, не red.
- Красные тесты A–C и D (атрибут) падают по ожидаемой причине (отсутствие поведения), а не из-за
  ошибок фикстур: перед ними сидирование проверяется smoke-assert'ом `200` на страницах.

Последовательность: Step 3 пишет модуль и подтверждает, что A, B, C и D-атрибут красные, а D-guard
зелёный; Step 4 вносит production-изменения и правит три существующих теста; затем весь
`make test` зелёный.

### Правки существующих тестов (только расположение, assertions по смыслу прежние; DoD п. 7)

- `tests/test_wish_items_list_reorder_ui.py:136`: вместо `assert "toggleWishCard" in html`
  (проверка «страница несёт toggle-механизм») -> проверка, что страница ссылается на
  `/static/wishlist.js` и что `GET /static/wishlist.js` содержит `toggleWishCard`; комментарий строки
  «inline toggle attributes» обновить. Остальные assert'ы (aria-expanded, structure) неизменны.
- `tests/test_wish_card_giver_controls.py:502`: sanity-маркер `"toggleWishCard" in script` ->
  `"swapWishCard" in script` (код рефреша остаётся inline; assertions про `outerHTML`,
  `aria-expanded`, очистку `hidden` не меняются). Имя и docstring `inline_script` остаются верными.
- `tests/test_reservations_cabinet_ui.py`: без изменений (ветка `.reservation-row` остаётся inline).

## Architecture

```text
base.html (<head>)
  |-- /static/miniapp.css
  |-- telegram-web-app.js, htmx, json-enc (CDN)
  |-- /static/wishlist.js  (defer)   <-- NEW: toggle + DnD, делегирование на document
  `-- inline <script>                      (остаётся: CSRF, брони, swapWishCard)

wishlist_detail.html / share_wishlist.html
  `-- <section id="items-list" data-wishlist-id="{{ wishlist.id }}">   <-- NEW атрибут
        `-- partials/items_list.html -> partials/item_card.html
              `-- .item-card-summary  (БЕЗ onclick/onkeydown)

wishlist.js
  click/keydown(document) --> closest('.item-card-summary') --> toggleWishCard()
  dragstart/dragover/drop/dragend(document)
  drop --> #items-list.dataset.wishlistId --> htmx.ajax POST /web/wishlists/{id}/items/reorder
                                               target '#items-list', swap innerHTML
```

Модули и ответственность:

- **`wishlist.js`** — единственное место поведения карточки списка желаний (раскрытие, DnD).
  Зависит от DOM-контракта: классы `.item-card`, `.item-card-summary`, `.item-card-details`,
  `#items-list`, атрибуты `data-item-id`, `data-no-toggle`, `draggable`, `data-wishlist-id`
  на `#items-list`; и от `window.htmx` (только для reorder). Серверу не нужен.
- **Шаблоны** — декларируют контракт: `data-wishlist-id` на контейнере, никакой логики и
  обработчиков в разметке.
- **inline-блок `base.html`** — только viewer/CSRF/брони; не зависит от `wishlist.js` и наоборот
  (общих глобалей нет: `toggleWishCard` больше не глобальна).

Паттерны и обоснование:

- **Делегирование событий на `document`** — переживает htmx-swap и `outerHTML` карточки без
  повторной привязки, не требует inline-атрибутов (путь к строгой CSP, цель задачи).
- **Data-атрибут как контракт «страница -> скрипт»** — убирает разбор URL; живой поиск
  `#items-list` в момент `drop` защищает от устаревших замыканий.
- **Новый файл вместо `miniapp.js`**: `miniapp.js` — отдельное SPA Telegram Mini App с top-level
  состоянием (`root`, `csrf`), грузится только его страницей; смешивание дало бы побочные эффекты
  на всех страницах и связало два несвязанных приложения. Имя `wishlist.js` совпадает с
  follow-up в `ai-tasks/WISHENKA-15/60-tech-debt.md`.
- **`data-wishlist-id` на контейнере, а не чтение с карточки** (карточка тоже несёт id): требования
  и tech-debt прямо называют контейнер; он единственный источник, который «страница объявляет
  как свой», и не зависит от наличия карточек (пустой список).

Интерфейсы:

- Страница -> скрипт: `#items-list[data-wishlist-id]` (положительное целое, строка из
  `wishlist.id`).
- Скрипт -> сервер: без изменений, `POST /web/wishlists/{id}/items/reorder` с полем `item_ids`
  (значения — `data-item-id` карточек по порядку DOM), ответ — `partials/items_list.html`
  в `#items-list` (innerHTML). Бэкенд не меняется.
- Статика: `GET /static/wishlist.js` (существующий mount, `no-store` остаётся).

Что **не** меняется: Python-код, роуты, DTO, права, правила порядка, CSS, inline-код CSRF/броней.

## Q&A

- **Q: Почему не `miniapp.js`?**
  A: Это отдельное приложение с top-level `const root = document.getElementById('app')` и своим
  состоянием; на обычных страницах оно дало бы лишний код и побочные эффекты. Новый
  `wishlist.js` небольшой и изолирован.
- **Q: Что с кэшируемостью, о которой говорят требования?**
  A: `BrowserSecurityMiddleware` ставит `Cache-Control: no-store` на все ответы, включая
  `/static/*`. Задача выносит код в отдельный ресурс (готовность к кэшу и CSP), но не меняет
  политику кэширования; это фиксируется в Step 7 как возможный долг (исключить `/static` из
  `no-store`, добавить версию в URL).
- **Q: Почему оставляем inline-код CSRF, броней и `swapWishCard`?**
  A: Out of scope по требованиям; на них опираются существующие тесты (`base_script`,
  `inline_script`). Их вынос — отдельная задача, и полная строгая CSP до неё недостижима.
- **Q: Нужен ли `data-wishlist-id` при перерисовках?**
  A: Атрибут стоит на самом `<section id="items-list">`, а ни один swap не заменяет сам
  контейнер (содержимое меняется через `innerHTML`/`beforeend`, архивирование использует `none` и OOB);
  это закреплено тестом на `hx-swap`/отсутствие `id="items-list"` во фрагментах.
- **Q: Не потеряется ли поведение клавиатуры?**
  A: Нет: `keydown` на `document` получает те же всплывающие события; Enter/Space и
  исключение интерактивных элементов переносятся без изменений. Семантика сохранена и
  проверяется строковыми признаками плюс ручным прогоном в Chromium на Step 4;
  автоматизированные браузерные тесты — WISHENKA-110.
- **Q: Что при отсутствии/битом `data-wishlist-id`?**
  A: Карточка не переставляется и пишется `console.warn` (сегодня — тихое расхождение экрана и
  сервера). Это единственное осознанное отличие от нынешнего поведения и касается только
  неисправного состояния страницы.
- **Q: Почему нет браузерного (Chromium) теста в этой задаче?**
  A: Требования ограничивают проверки тем, что возможно без браузера; браузерные тесты
  toggle/DnD принадлежат WISHENKA-110, touch-DnD — WISHENKA-109.
