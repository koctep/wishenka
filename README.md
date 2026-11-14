# Wishenka («Вишенка»)

Telegram Wishlist Service with FastAPI, HTMX, aiogram v3, and SQLite (WAL).

## Requirements

- Python 3.12+
- GNU Make

## Quick Start

```bash
# Create virtual environment and install dependencies
make deps

# Prepare Chromium for browser UI tests (required by make check)
make deps-browser

# Run Quality Gate (static analysis + test suite)
make check

# Run local development server
make run
```

## Documentation

- [Architecture Overview](doc/dev/architecture.md) — high-level service architecture, invariants, and database schema.
- [Developer & Infrastructure Guide](doc/dev/infrastructure.md) — repository structure, Makefile targets, linters, testing guidelines, Docker, and CI/CD.
- [Browser UI Tests](doc/dev/testing.md) — Chromium discovery, `make deps-browser`, fail-vs-skip policy, and troubleshooting.

