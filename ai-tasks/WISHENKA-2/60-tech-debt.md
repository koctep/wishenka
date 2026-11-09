# WISHENKA-2: Technical Debt Analysis

## Shortcuts Taken

- Никаких временных технических решений или "костылей" не допущено. Задача выполнена исключительно как архитектурно-спецификационная, с полной фиксацией всех требований и договоренностей.

## Code Quality Issues

- N/A: Исполняемый код в рамках задачи не реализовывался. Архитектурный документ `20-architecture.md` полностью прошел независимое ревью с вердиктом `PASS`.

## Missing Tests

- N/A: Для чисто архитектурной задачи тесты не требуются (статус Шага 3 `N/A — no behavioral change` подтвержден независимым ревью).

## Performance Concerns

- **SQLite при пиковых нагрузках**: Выбран SQLite с режимом WAL (`PRAGMA journal_mode = WAL;`) и `busy_timeout = 5000`. Для сервиса средней нагрузки это обеспечивает быструю работу без выделенного сервера БД. В случае масштабирования до сотен одновременных пишущих транзакций потребуется переход на PostgreSQL, что предусмотрено архитектурой благодаря использованию SQLAlchemy 2.0 Async ORM.

## Follow-up Tasks

Все дальнейшие этапы проектирования и реализации декомпозированы и зафиксированы в Jira:
- [WISHENKA-3](https://pypost.atlassian.net/browse/WISHENKA-3) — `[Инфраструктура] Каркас репозитория, Makefile, линтеры, CI/CD и тестовая среда`
- [WISHENKA-4](https://pypost.atlassian.net/browse/WISHENKA-4) — `[Аутентификация] Валидация Telegram WebApp initData и сессионный контекст`
- [WISHENKA-6](https://pypost.atlassian.net/browse/WISHENKA-6) — `[Декомпозиция] Ролевая модель, жизненный цикл вишлистов и права доступа соавторов`
- [WISHENKA-7](https://pypost.atlassian.net/browse/WISHENKA-7) — `[Backend] CRUD API вишлистов, публичный шеринг по ссылке и права доступа`
