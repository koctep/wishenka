# WISHENKA-142: Technical Debt Analysis

## Shortcuts Taken

- **Увеличенный viewport в браузерных тестах раскрытой карточки (`Low`)**: в [tests/test_wishlist_touch_reorder_browser.py](file:///home/src/tests/test_wishlist_touch_reorder_browser.py#L79-L135) для тестов с раскрытой карточкой (`test_touch_drag_handle_reorders[expanded-card]`, `test_expanded_card_stays_expanded_after_cancelled_touch_drag`, `test_expanded_card_drag_preserves_details_and_list_positions`) передаётся `viewport=(412, 1000)` вместо стандартного `(412, 800)`. Это сделано для того, чтобы третья карточка списка с учётом видимого блока подробностей не уходила к нижней границе экрана и не вызывала автоскролл во время базовых тестов перетаскивания. Компромисс осознанный и не влияет на production-код.

## Code Quality Issues

- **Устаревшие упоминания в `doc/dev/` (закрывается на Шаге 8 — `td-70-dev-docs`, не является отложенным долгом)**:
  - В [doc/dev/miniapp.md](file:///home/src/doc/dev/miniapp.md#L618-L623) всё ещё описано скрытие `.item-card-details` через `display: none` и сдвиг списка вверх при старте жеста (`WISHENKA-142`).
  - В [doc/dev/testing.md](file:///home/src/doc/dev/testing.md#L215) среди помощников [tests/browser_helpers.py](file:///home/src/tests/browser_helpers.py) всё ещё упоминается удалённая функция `retarget_touch_drag`.
- **Отклонения от архитектуры и маркеры таймаутов**:
  - Изменение в [wishenka/web/static/miniapp.css](file:///home/src/wishenka/web/static/miniapp.css#L109-L116) полностью соответствует [20-architecture.md](file:///home/src/ai-tasks/WISHENKA-142/20-architecture.md) (удалено только правило `.item-card.is-touch-dragging .item-card-details { display: none; }`).
  - Модуль [tests/test_wishlist_touch_reorder_browser.py](file:///home/src/tests/test_wishlist_touch_reorder_browser.py#L41) имеет явный модульный маркер таймаута `pytestmark = [pytest.mark.timeout(45), pytest.mark.browser]` — **Blocker**-проблемы отсутствуют.

## Missing Tests

- **Перетаскивание раскрытой карточки на коротких мобильных экранах с автоскроллом (`Low`)**: сценарий перетаскивания раскрытой карточки, когда целевая карточка оказывается у нижнего края viewport (например, `412x800` или `375x667`) и требует автоскролла, не покрыт отдельным браузерным тестом. Покрытие автоскролла и проверка на реальных устройствах осознанно вынесены за рамки `WISHENKA-142` (см. [10-requirements.md](file:///home/src/ai-tasks/WISHENKA-142/10-requirements.md#L47)) и отслеживаются в рамках задачи `WISHENKA-143`.

## Performance Concerns

- **Композитинг более высокой карточки во время жеста (`Low` / несущественно)**: поскольку `.item-card-details` остаётся видимым при `.is-touch-dragging`, браузер композитит чуть более высокий элемент с `opacity: .85`, `box-shadow` и `will-change: transform` при сдвиге `transform: translateY(dy)`. Так как `transform` выполняется на уровне композитора и не вызывает пересчёт layout на каждом `pointermove`, влияние на производительность пренебрежимо мало.

## Follow-up Tasks

Новых `Blocker`, `High` или `Medium` задач технического долга не выявлено.

- Актуализировать [doc/dev/miniapp.md](file:///home/src/doc/dev/miniapp.md#L618-L623) и [doc/dev/testing.md](file:///home/src/doc/dev/testing.md#L215) — выполняется в рамках **STEP 8 (`td-70-dev-docs`)** текущей задачи `WISHENKA-142` (отдельный Jira-тикет не требуется).
- Проверка перетаскивания раскрытой карточки на реальных мобильных устройствах и в сценариях с автоскроллом — уже отслеживается в существующей задаче **`WISHENKA-143`** (отдельный Jira-тикет не требуется).
