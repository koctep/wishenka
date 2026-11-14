# WISHENKA-112: Мелкий рефакторинг items_ui.py и store.py после WISHENKA-15

## Research

Дата: 2026-11-14. Внешних источников не нужно: задача внутри репозитория, все факты проверены
по коду (`lsr-python`, `lsr-markdown`, `do-testing`). Поведение не меняется, схема БД не меняется.

### Группа ошибок в `wishenka/web/routes/items_ui.py`

- `_NOT_FOUND_ERRORS` (строка 809) — кортеж из пяти ошибок: `WishlistNotFoundError`,
  `WishlistDeletedError`, `ItemNotFoundError`, `PermissionDeniedError`, `WishlistArchivedError`.
  Используется ровно в четырёх `except`: `_reordered_response` (839), `archive_confirm_ui`
  (947), `archive_item_ui` (1005), `restore_item_ui` (1055). Везде за ним сразу идёт
  `_raise_http(exc)`.
- `_raise_http(exc: Exception) -> NoReturn` принимает любое исключение: `WishlistArchivedError`
  даёт 409 «Wishlist is archived», всё остальное — 404 «Resource not found». Вне `items_ui.py`
  функция не используется.
- В модуле есть и другие доменные ошибки с отдельной обработкой (`CannotReduceQuantityBelowReservedError`,
  `InventoryBusyError`), поэтому имя `_DOMAIN_ERRORS` без пояснения было бы слишком широким.
- Соглашения по именам: в модуле одна константа-кортеж, имена приватных констант в соседних
  роутах — `_UPPER_SNAKE` (`_BOOKED`, `_NOTICES`).
- Ни `doc/dev/`, ни `specs/`, ни `in-docs/`, ни `tests/` не упоминают `_NOT_FOUND_ERRORS`,
  `_reordered_response`, `_raise_http`.

### Колбэк `_reordered_response`

`reorder: Callable[[WishlistService, list[int]], list[int]]`; helper вызывает
`reorder(svc, [it.id for it in current])`. Вызывающие: `reorder_items_ui`
(`lambda _svc, _cur: item_ids`) и `move_item_ui` (`compute(_svc, current)`). `svc` не
используется нигде. `ItemNotFoundError`, который `compute` бросает для неизвестного item, летит
внутри `action`, то есть ловится группой ошибок и даёт 404 — это сохраняется.

### Столбцы и `hasattr`/`getattr`

Проверено правило «каждый SELECT вызывающего содержит столбец»:

| Место | Вызывающие SELECT | Столбец в SELECT | Схема |
| ----- | ----------------- | ---------------- | ----- |
| `store.py` ~382 `hasattr(r, "warn_on_delete_reserved")` | `_read` `l_stmt` (`FROM wl_lists`) | да | `NOT NULL DEFAULT 1` (`db_models.py:24`, миграция `add_warn_on_delete_reserved`) |
| `store.py` ~437 `hasattr(ir, "display_order")` | `_read` `i_stmt` | да | `NOT NULL DEFAULT 0` (`db_models.py:80`, миграция `add_display_order`) |
| `store.py` ~893 `getattr(wishlist_row, "warn_on_delete_reserved", None)` | один SELECT `FROM wl_lists WHERE id` в загрузке одного item | да | то же |
| `repository.py` ~45 `hasattr(row, "warn_on_delete_reserved")` в `_row_to_wishlist` | единственный вызов — `get_wishlist` (SELECT с колонкой, строка ~133) | да | то же |
| `repository.py` ~102 `getattr(row, "display_order", 0)` в `_row_to_item` | два вызова: `get_wishlist` (items SELECT) и `get_item`; оба содержат `display_order` | да | то же |

Прочие вызовы `_row_to_wishlist`/`_row_to_item` вне `repository.py` отсутствуют. Фейковых строк
в тестах нет: `grep` по `tests/` на `SimpleNamespace`/`namedtuple`/`Mock` рядом со store/repo
находит только `AsyncMock` для store в тестах фонового cleanup (они не строят строки), а
`tests/test_wishlists_sqlite_repo*.py` и `test_wish_*` работают с реальной SQLite. Значит, ни один
код-путь не получает строку без столбца. Остальные `getattr` в `store.py` (75, 95, 766) касаются
других объектов (исключения SQLAlchemy, имена сервиса) — вне scope.

## Implementation Plan

### (a) Новое имя группы ошибок

Выбрано **`_DOMAIN_ERRORS`** (как предложено в долге) плюс одно предложение комментария над
кортежем: «Domain errors that `_raise_http` translates: archived -> 409, all others -> 404».
Почему не длиннее: `_WISHLIST_ACCESS_ERRORS` неверно описывает `ItemNotFoundError`;
`_HTTP_MAPPED_ERRORS` описывает механику, а не смысл. Двусмысленность «все ли доменные ошибки»
снимается комментарием и тем, что рядом стоит `_raise_http`.

`_raise_http` остаётся без изменений (тип параметра `Exception` намеренно широкий, общий
кортеж в сигнатуре не нужен, `isinstance`-логика не трогается). Заменяются все четыре места
использования (839, 947, 1005, 1055) и определение. Старое имя нигде не остаётся.

### (b) Сигнатура колбэка

`reorder: Callable[[list[int]], list[int]]` (текущие id -> новые id). Изменения:

- `_reordered_response`: `new_ids = reorder(current_ids)`, где `current_ids = [it.id for it in current]`
  вычисляется один раз и используется и в сравнении `new_ids != current_ids` (раньше список
  строился дважды; поведение то же).
- `reorder_items_ui`: `lambda _current: item_ids`.
- `move_item_ui`: `def compute(current: list[int]) -> list[int]` (тело без изменений).
- Импорт `WishlistService` остаётся: он нужен в сигнатурах `action` внутри модуля.
  `mypy` строгий (`pyproject.toml`), типы сходятся без `cast`.

### (c) Что чистим

- `store.py` ~382 и ~437: убрать `hasattr`, оставить `is not None` (инвариант «None guards stay»):
  `bool(r.warn_on_delete_reserved) if r.warn_on_delete_reserved is not None else True` и
  `int(ir.display_order) if ir.display_order is not None else 0`.
- `store.py` ~893: **чистим** — тот же случай (одна колонка, тот же SELECT-контракт), заменяем на
  `warn_raw = wishlist_row.warn_on_delete_reserved`; выражение `True if warn_raw is None else bool(warn_raw)`
  не меняется. Требования разрешали трогать, если случай тривиально тот же: так и есть.
- `repository.py` ~45: **чистим**, убрать `hasattr`, `None`-защита остаётся.
- `repository.py` ~102: **чистим** как «сиблинг, пропущенный списком требований»:
  `int(row.display_order or 0)`. `or 0` сохраняется (None-защита). Побочный эффект: при отсутствии
  колонки теперь `AttributeError` вместо тихого 0 — осознанно, по контракту схемы.
- Не трогаем: `getattr` в `store.py` 75, 95, 766, `hasattr` в `sharing.py` и `items/fetcher.py`
  (другие объекты, см. требования).

Критерий приёмки 3 выполняется, кроме `repository.py` дополнительно закрыты ещё 2 места;
«оставленных защит» нет, записывать причину не нужно.

### (d) Инварианты и чем защищены

| Инвариант | Защита |
| --------- | ------ |
| 409 + «Wishlist is archived», 404 + «Resource not found» на reorder/move/archive-confirm | уже есть статусы в `test_rbac_and_surprise_invariant_on_reorder_and_archive`; **detail-строки** и archive/restore — новый characterization-модуль (ниже) |
| 400 «Invalid item order» | существующий тест допускает `(400, 422)` и detail не проверяет — нужен точный тест |
| Нет записи при неизменном порядке; первый вверх / последний вниз; неизвестный item = 404 | существующих проверок нет — characterization-модуль (счётчик вызовов `reorder_wish_items`) |
| События `ui_items_reordered`, `ui_item_moved`, `ui_items_reorder_rejected` | в `tests/` не проверяются (только в doc) — characterization с `caplog` |
| Значения по умолчанию (warn=True, order=0) и загрузка | существующие тесты store/repo/UI на реальной SQLite; новых не нужно (None-ветки не достижимы через схему `NOT NULL`, ветки остаются как есть) |
| Без миграций и изменения SELECT | диф затрагивает только выражения над строкой; проверяется ревью диффа |

### (e) Failing Repro (Step 3)

Рефакторинг без изменения поведения: настоящего «красного поведения» нет. По духу td-25 делаем
две группы.

**Красные сейчас, зелёные после** — `tests/test_wishenka_112_structure.py`
(`pytestmark = pytest.mark.timeout(30)`), три маленьких теста:

1. `items_ui` не содержит `_NOT_FOUND_ERRORS` и содержит `_DOMAIN_ERRORS`, равный кортежу из
   пяти ожидаемых классов (по `set`, порядок не важен).
2. `typing.get_type_hints(_reordered_response)["reorder"]` — это `Callable[[list[int]], list[int]]`
   (`get_args` -> `([list[int]], list[int])`); так проверяется один позиционный параметр без
   привязки к тексту аннотации.
3. AST-скан `wishenka/wishlists/store.py` и `repository.py`: нет вызовов `hasattr`/`getattr`,
   у которых второй аргумент — строковая константа `"warn_on_delete_reserved"` или
   `"display_order"`.

Это красные сейчас по правильной причине (AssertionError, а не ImportError: импорт модулей
работает, красным падает именно проверка). Слабость честно: такие тесты закрепляют **имена и
форму кода**, а не поведение; их ценность — не дать откатить очистку, они не доказывают
корректность. Поэтому они минимальны (3 теста) и не покрывают ничего сверх критериев 1–3.

**Зелёные до и после (characterization)** — `tests/test_items_ui_error_mapping.py`
(timeout 30; фикстура `test_app`/`auth_header`/`make_user` копируется из
`tests/test_wish_items_list_reorder_ui.py`, общего conftest нет). Пишется только то, чего нет в
существующих тестах (покрыто: статусы 404/409 для reorder, move, archive-confirm; успешные
move/reorder/archive/restore; 400/422 без detail):

- параметризованно по маршрутам reorder, move, archive-confirm, archive, restore: архивный
  список -> 409 и `detail == "Wishlist is archived"`; чужой пользователь, несуществующий item и
  несуществующий wishlist -> 404 и `detail == "Resource not found"` (форму тела ответа
  реализатор сверяет по `HTTPException` в приложении);
- неверная перестановка -> ровно 400, `detail == "Invalid item order"`, порядок не изменён;
  `caplog` (logger `wishenka.web.items_ui`, WARNING) содержит событие
  `ui_items_reorder_rejected`, `reason == "invalid_permutation"`;
- «нет записи»: `monkeypatch`-обёртка над `WishlistService.reorder_wish_items` считает вызовы
  (spy с `wraps`): reorder тем же порядком, move первого вверх, move последнего вниз -> 0
  вызовов; реальное перемещение -> 1 вызов;
- события `ui_items_reordered` (с `item_count`) и `ui_item_moved` (с `direction`, `item_id`)
  на INFO присутствуют при успехе и отсутствуют при ошибке.

Эти тесты запускаются **до** правок и должны быть зелёными, затем остаются зелёными после
Step 4 — это и есть проверка сохранения поведения. Порядок: Step 3 пишет обе группы, подтверждает
красный структурный модуль и зелёный characterization-модуль, production-код не трогает;
Step 4 делает правки до зелёного. `skip`/`xfail` не используются.

### (f) Документация (Step 8)

`grep` по `doc/`, `specs/`, `in-docs/` не находит ни одного затронутого идентификатора.
`doc/dev/items.md` (624) и `doc/dev/miniapp.md` (506, 569, 744) описывают события и статусы
reorder — они не меняются. Ожидаемый итог Step 8: правок нет, фиксируется в roadmap.

## Architecture

Новых модулей и интерфейсов нет; меняются внутренности двух слоёв.

```text
items_ui.py (web routes)
  reorder_items_ui / move_item_ui
        | reorder: Callable[[list[int]], list[int]]      <- меняется
        v
  _reordered_response --except _DOMAIN_ERRORS--> _raise_http (409 / 404)
                      --except ValueError------> 400 + ui_items_reorder_rejected
        v
  WishlistService (get_wishlist_by_id, list_wish_items, reorder_wish_items)

store.py / repository.py: строка SQLAlchemy Row -> доменная модель (без проверок наличия колонок)
```

Паттерны: без новых. Сохраняется схема «маршрут -> общий helper -> сервис; единый переводчик
доменных ошибок в HTTP». Ограничение схемы: `NOT NULL DEFAULT` в миграциях (WISHENKA-111)
гарантирует колонки, значит `hasattr` защищал только от невозможного случая.

## Q&A

- **Почему `_DOMAIN_ERRORS`, а не более длинное имя?** Имя из долга, точное по смыслу (это
  доменные ошибки, которые переводит `_raise_http`); возможная двусмысленность закрыта комментарием.
- **Почему чистим `repository.py` и строку ~893?** Каждый вызывающий SELECT содержит колонку,
  фейковых строк в тестах нет; None-защиты остаются.
- **Не слишком ли слабы структурные тесты?** Да, они закрепляют имена; поэтому их три, а
  поведение защищают characterization-тесты, зелёные до и после.
- **Нужны ли правки документации?** Нет, идентификаторы в `doc/` не упомянуты.
- **Кто принимает шаг?** Пользовательского подтверждения нет; шаг принимает оркестратор после
  PASS независимого ревью.
