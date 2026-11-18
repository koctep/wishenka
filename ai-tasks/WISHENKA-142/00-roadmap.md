# Roadmap: WISHENKA-142

## Task Metadata

- **Implementation language**: JavaScript, Python

## Step Status

- [x] **STEP 1: Requirements Gathering and Documentation**
  - [ ] `ai-tasks/WISHENKA-142/10-requirements.md` — бизнес-требования, пользовательские сценарии и критерии приёмки
- [x] **STEP 2: High-Level Architecture Design**
  - [ ] `ai-tasks/WISHENKA-142/20-architecture.md` — исследование кодовой базы, план реализации (включая красный браузерный тест для Шага 3), Mermaid-диаграмма, ответственность модулей и CSS/JS-интерфейсы
- [x] **STEP 3: Failing Repro Test**
  - [x] `tests/test_wishlist_touch_reorder_browser.py::test_expanded_card_drag_preserves_details_and_list_positions` — красный браузерный тест, падающий на текущем `wishenka/web/static/miniapp.css` из-за `display: none` и обнуления высоты `.item-card-details` (`detailsDisplay == 'none'`, `detailsHeight == 0`) при активации `.is-touch-dragging`
- [x] **STEP 4: Development**
  - [x] Удалено CSS-правило `.item-card.is-touch-dragging .item-card-details { display: none; }` в `wishenka/web/static/miniapp.css` (сохранено визуальное приглушение `.is-touch-dragging` без скрытия подробностей и скачка списка)
  - [x] Обновлены браузерные тесты в `tests/test_wishlist_touch_reorder_browser.py` и удалён неиспользуемый helper `retarget_touch_drag` в `tests/browser_helpers.py`; все тесты `test_wishlist_touch_reorder_browser.py` (включая `test_expanded_card_drag_preserves_details_and_list_positions`), смежные UI/reorder-тесты и `ruff`/`mypy` проходят
- [x] **STEP 5: Code Cleanup**
  - [x] `make analyze` (`ruff check`, `ruff format --check`, `mypy`) — 0 ошибок и 0 предупреждений в 204 файлах
  - [x] Проверены изменённые файлы (`wishenka/web/static/miniapp.css`, `tests/browser_helpers.py`, `tests/test_wishlist_touch_reorder_browser.py`) на неиспользуемые импорты/переменные, отладочный вывод, маркеры таймаутов (`pytest.mark.timeout(45)`) и конфликты слияния
  - [x] `.venv/bin/pytest tests/test_wishlist_touch_reorder_browser.py -q` — 20 passed
  - [x] `ai-tasks/WISHENKA-142/40-code-cleanup.md` — отчёт о проверке и очистке кода
- [x] **STEP 6: Observability**
  - [x] Проведена оценка требований наблюдаемости: production-изменение ограничено удалением CSS-правила в `wishenka/web/static/miniapp.css`, backend и `wishenka/web/static/wishlist.js` не затрагивались, runtime-логирование и метрики не требуются (N/A)
  - [x] `ai-tasks/WISHENKA-142/50-observability.md` — документация оценки и обоснования отсутствия runtime-телеметрии
- [x] **STEP 7: Technical Debt Analysis**
  - [x] Проведён анализ технического долга по `git diff`, `10-requirements.md` и `20-architecture.md`: `Blocker`/`High`/`Medium` проблем не выявлено, модульный `pytest.mark.timeout(45)` присутствует, отклонений от архитектуры нет
  - [x] Зафиксированы `Low`-наблюдения (`viewport=(412, 1000)` в expanded-card тестах, автоскролл/реальные устройства покрываются `WISHENKA-143`, актуализация `doc/dev/miniapp.md` и `doc/dev/testing.md` переходит в STEP 8)
  - [x] `ai-tasks/WISHENKA-142/60-tech-debt.md` — отчёт анализа технического долга
- [x] **STEP 8: Dev Docs**
  - [x] Обновлён `doc/dev/miniapp.md` (раздел touch reorder / Feedback classes): описано, что `.item-card-details` остаётся видимым во время touch drag и высота карточки сохраняется без скачка списка (`WISHENKA-142`)
  - [x] Обновлён `doc/dev/testing.md` (таблица `tests/browser_helpers.py`): удалено устаревшее упоминание `retarget_touch_drag`
- [x] **COMMIT: Commit Changes**

## Status Legend

- `[ ]` — step not started
- `[/]` — step in progress
- `[x]` — step completed and accepted (acceptance gate passed)

See the `td-roadmap` skill for who writes which mark and when.

## Artifacts

### STEP 1: Requirements

- `ai-tasks/WISHENKA-142/10-requirements.md`

### STEP 2: Architecture

- `ai-tasks/WISHENKA-142/20-architecture.md`

### STEP 3: Failing Repro

- Automated red test(s) under `tests/` (or N/A note in roadmap)

### STEP 4: Development

- Source code
- Tests
- Documentation updates

### STEP 5: Code Cleanup

- `ai-tasks/WISHENKA-142/40-code-cleanup.md`

### STEP 6: Observability

- `ai-tasks/WISHENKA-142/50-observability.md`

### STEP 7: Technical Debt

- `ai-tasks/WISHENKA-142/60-tech-debt.md`

### STEP 8: Dev Docs

- `doc/dev/`

### COMMIT

- No artifact recorded here beyond the `[x]` mark above. Branch name and commit hash are reported
  in chat only, never written to this file.
