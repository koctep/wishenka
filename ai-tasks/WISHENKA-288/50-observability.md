# WISHENKA-288: Observability Implementation

## Logging Implementation

### Added Logs

N/A — no server-side or client-side logging was added in `WISHENKA-288`.

Audit of `WISHENKA-288` scope (`git diff`):

- `wishenka/web/static/miniapp.css`: pure CSS tokens (`--canvas`, `--surface`, `--ink`, `--muted`,
  `--accent`, `--accent-dark`, `--danger`, `--focus`), typography, card/form/button/badge rules,
  `:focus-visible` outlines, and scoped `.receipt-sheet` / `.modal-sheet` contrast rules. Served
  under `/static` via `StaticFiles` in `wishenka/web/app.py` behind `RequestLoggingMiddleware` and
  `BrowserSecurityMiddleware`.
- `wishenka/web/static/miniapp.js`: adds optional `className = ''` to
  `button(text, handler, className = '')` and passes `'btn-primary'` or `'btn-danger'` on seven
  existing controls (`sharePanel`, `showHistory`, `showHome`, `settingsForm`, `memberControls`,
  `publicView`, `invitationView`). Introduces no new routes, API calls, state transitions, or
  failure branches. Existing `#status` live-region notices (`status(t(...))`) and bounded i18n
  fallback warnings (`console?.warn?.(...)` with `WARNED_MISSING_KEYS`) remain intact; zero debug
  `console.log` statements or client telemetry beacons were added.
- `wishenka/web/templates/partials/member_list.html`: adds `btn-danger` to `.btn-delete`
  (`hx-delete="/wishlists/{{ wishlist_id }}/members/{{ member.user_id }}/partial"`). No new
  template context, endpoint, or action semantics.
- `wishenka/web/templates/settings.html`: adds `class="btn-primary"` to `#birthdate-form` submit and
  `class="btn-danger"` to `#delete-account-start-btn` and `#delete-account-confirm-btn`. Existing
  `settings.js`, HTMX `/api/profile/locale`, and `#*-feedback` live regions remain unchanged.
- `tests/test_visual_identity_browser.py`: offline Chromium visual-identity tests only; no
  production code.

### Existing Production Observability

All execution paths behind the styled controls retain existing structured repository logging:

- **HTTP, lifecycle, and security** (`wishenka/web/app.py`, `wishenka/web/security.py`,
  `wishenka/logging.py`):
  - `wishenka.web`: `RequestLoggingMiddleware.dispatch` logs `HTTP request started` (`DEBUG`:
    `method`, `path`), `HTTP request completed` (`INFO`: `method`, `path`, `status_code`,
    `duration_ms`), and unhandled exceptions (`ERROR` via `logger.exception`) across HTML shells,
    `/static/*`, and API routes while redacting `/api/public/wishlists/{token}`, `/share/{token}`,
    and `/invite/{token}` paths (matched by `ShareTokenAccessFilter` on `uvicorn.access`).
  - `wishenka.web.security`: `BrowserSecurityMiddleware.dispatch` logs `origin_mismatch`,
    `csrf_origin_mismatch`, and `csrf_token_invalid` at `WARNING`.
  - `JsonFormatter` (`wishenka/logging.py`) emits structured JSON records when `settings.log_json`
    is enabled.
- **Mini App shell** (`wishenka/web/routes/miniapp.py`):
  - `wishenka.web.miniapp`: `miniapp` (`GET /`) emits `miniapp_shell_requested` (`INFO`) and
    `miniapp_catalog_embedded` (`DEBUG`: `locale`, `key_count`) without dumping full catalogs.
- **Auth and CSRF** (`wishenka/web/routes/auth.py`):
  - `wishenka.auth`: emits `auth_success` (`INFO`), `logout` (`INFO`), `csrf_token_issued` (`INFO`),
    and `csrf_cookie_missing` (`WARNING`) without logging session or CSRF tokens.
- **Wishlist, history, invite, member, and public actions** (`wishenka/web/routes/wishlists.py`,
  `wishenka/web/routes/sharing.py`):
  - `wishenka.web.wishlists`: emits `wishlist_created`, `wishlist_updated`,
    `wishlist_mutation_committed`, `view_history_listed`, `view_history_recorded`,
    `view_history_cleared`, `member_removed`, `invitation_previewed`, `invitation_accepted`, and
    `public_entry_viewed` (`INFO`); emits `member_removal_denied`, `wishlist_access_denied`,
    `wishlist_archived_mutation_blocked`, `invitation_token_invalid_or_expired`,
    `invitation_join_failed`, and `public_entry_unavailable` (`WARNING`).
  - `wishenka.web.sharing`: `remove_member_partial` (called by `.btn-delete.btn-danger` in
    `wishenka/web/templates/partials/member_list.html`) emits `member_removed` (`INFO`:
    `wishlist_id`, `removed_user_id`, `removed_by`); `preview_invite` and `join_invite` emit
    `invite_preview_accessed` (`INFO`), `invite_joined` (`INFO`), and `invite_join_failed`
    (`WARNING`).
- **Settings and account deletion** (`wishenka/web/routes/profile.py`,
  `wishenka/wishlists/deletion.py`):
  - `wishenka.web.profile`: emits `profile_malformed_json`, `locale_invalid_request`,
    `birthdate_invalid_request`, `birthdate_user_not_found`, `notification_global_invalid_request`,
    `notification_wishlist_invalid_request`, `notification_wishlist_not_found`, and
    `account_deletion_rejected` (`WARNING`) without raw inputs or PII.
  - `wishenka.bot.i18n`: emits `bot_commands_locale_sync_failed` (`WARNING`) if best-effort
    Telegram command sync fails after a locale update.
  - `wishenka.wishlists.deletion`: emits `account_deletion_preview_computed` (`DEBUG`),
    `account_deleted` and `account_deletion_already_deleted` (`INFO`), and
    `account_deletion_failed` (`ERROR` with `exc_info=True`, `subject_hash_prefix`, `error_class`,
    `duration_ms`).

### Log Structure

- Structured logs: `yes` (unchanged `extra={"event": ...}` fields via `JsonFormatter` in
  `wishenka/logging.py`; zero new log calls added in `WISHENKA-288`).
- Includes context: `yes` (scalar IDs, HTTP `method`/`path`/`status_code`/`duration_ms`, `locale`,
  `key_count`, `reason`; no tokens, secrets, or form values).
- Log levels: none added (`DEBUG`, `INFO`, `WARNING`, `ERROR` already used on existing paths).

## Metrics Implementation (if applicable)

### Performance Metrics

N/A — no Prometheus, Grafana, OpenTelemetry, or StatsD exporter is wired in this repository. HTTP
`duration_ms` and `status_code` continue to be recorded by `RequestLoggingMiddleware` in
`wishenka/web/app.py`.

### Business Metrics

N/A — action outcomes remain observable through existing structured `event` fields
(`miniapp_shell_requested`, `wishlist_created`, `view_history_cleared`, `member_removed`,
`account_deleted`).

### System Health Metrics

N/A — no new background workers, queues, or storage resources were introduced; `/healthz` in
`wishenka/web/app.py` is unchanged.

## Monitoring Integration

- [ ] Prometheus metrics (N/A — no Prometheus exporter in repository)
- [ ] Grafana dashboards (N/A)
- [ ] Alerting rules (N/A)
- [x] Log aggregation (existing structured `extra` fields formatted by `JsonFormatter`)

## Validation Results

Checks executed after the final edit:

- [x] Zero backend Python production files modified in `WISHENKA-288`
- [x] `node --check wishenka/web/static/miniapp.js` exited `0` (no debug `console.log` added)
- [x] `git diff --check` exited `0` and all `ai-tasks/WISHENKA-288/*.md` lines are `<= 100` chars
- [x] `make analyze` passed (`ruff check`: `All checks passed!`, `ruff format --check`: `250 files
  already formatted`, `mypy`: `Success: no issues found in 250 source files`)
- [x] Targeted visual-identity, observability, deletion, static-script, and i18n checks passed
  (`72 passed` across `tests/test_visual_identity_browser.py` [5], `tests/test_observability.py`
  [3], `tests/test_wishlist_management_observability.py` [9], `tests/test_account_deletion.py` [5],
  `tests/test_receipt_static_script.py` [10], `tests/test_i18n_unit.py` [37], and
  `tests/test_i18n_sync.py` [3])

## Notes

- Pre-existing baseline observation outside `WISHENKA-288` scope: in
  `tests/test_wishlists_htmx_observability.py` (untouched by this task), 6 of 7 tests pass
  (including `test_member_removed_observability`), while `test_wishlist_shared_view_observability`
  fails because `wishenka/web/routes/sharing.py` logs `is_recipient=True` on an anonymous
  `/share/{token}` `GET` (`WISHENKA-288` made zero edits to `sharing.py`).
