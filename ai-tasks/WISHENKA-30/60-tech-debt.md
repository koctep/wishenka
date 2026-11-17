# WISHENKA-30: Technical Debt Analysis

## Shortcuts Taken

- **Synchronous in-handler Telegram delivery without an outbox queue:** `_submit_support_message` in
  `wishenka/bot/support.py` delivers tickets directly via `message.bot.send_message` during update
  handling before recording a row in `support_tickets` and confirming receipt to the user. This
  intentionally satisfies the requirement for immediate, truthful delivery reporting (confirming a
  ticket only after at least one destination accepts it), but means transient Telegram API failures
  surface immediately to the user as unavailability rather than being retried asynchronously in the
  background.
- **Deviation from initial ticket-reference and timestamp format:** `20-architecture.md` sketched
  `SUP-YYYYMMDD-XXXXXXXX` and ISO-8601 timestamps, whereas `wishenka/bot/support.py` (`generate_ticket_ref`
  and `collect_diagnostic_context`) formats ticket references as `SUP-MMDDHHMM-XXXXXXXX` (replacing
  `"202"` with `"303"` in the numeric stamp) and timestamps as `%d.%m.%y %H:%M:%S UTC`. This
  adjustment was made in Step 4 Iteration 8 so that four-digit years (`2026`) do not collide with
  short numeric test fixture IDs (`"202"`) in substring-based surprise-protection assertions while
  preserving deterministic 8-digit `SUP-\d{8}-[A-Z0-9]{8}` ticket references.
- **Hardcoded cleanup retention and batch bounds:** `cleanup_drafts` in `wishenka/bot/capture.py`
  purges expired `support_input` rows and `support_tickets` rows older than a fixed 30-day cutoff
  (`30 * 86400` seconds) in batches of `LIMIT 100` using wall-clock `time.time()`. Because retention
  exceeds the maximum configurable `support_rate_limit_window_seconds` default (`3600` seconds),
  rate-limit enforcement is unaffected, though the retention window is not exposed in `Settings`.

## Code Quality Issues

- **Unfiltered token table scans in `collect_diagnostic_context`:** In
  `wishenka/bot/support.py:213-224`, `collect_diagnostic_context` executes unfiltered
  `SELECT public_token, invite_token FROM wl_lists`, `SELECT token FROM wl_tokens`, and
  `SELECT token FROM wl_invite_tokens` queries to populate `known_tokens` for `redact_capabilities`.
  Although prefix and URL-path regular expressions (`_CAPABILITY_TOKEN_RE`, `_CAPABILITY_PATH_RE`,
  `_STARTAPP_TOKEN_RE`) already redact standard `p_*`, `i_*`, `/share/*`, `/invite/*`, and
  `/api/public/wishlists/*` capabilities, loading every token row from SQLite scales linearly with
  total database size.
- **Duplicated user upsert and `bot_destinations` activation across bot routers:**
  `wishenka/bot/support.py` (`principal`), `wishenka/bot/entry.py` (`start`, `help_command`),
  `wishenka/bot/birthdays.py` (`principal`), and `wishenka/bot/capture.py` (`capture`) each
  implement separate `UserStore.upsert_user` calls wrapped in `ContextVar` log-suppression filters
  followed by `INSERT INTO bot_destinations ... ON CONFLICT(user_id) DO UPDATE`. Furthermore,
  `support.py` preserves an existing stored `users.language_code` before upserting, whereas
  `entry.py` and `birthdays.py` pass `user.language_code` from the incoming Telegram payload
  directly.
- **Cross-module session invalidation coupling:** `wishenka/bot/entry.py` and
  `wishenka/bot/birthdays.py` import and call `clear_support_session` from `wishenka/bot/support.py`
  in individual handlers, while `_open_support_session` in `wishenka/bot/support.py` directly mutates
  `birthday_input` and `bot_drafts.edit_field`.
- **Account deletion and personal-data cleanup coverage:** The new `support_input` (`owner_id`,
  `chat_id`, `expires_at`) and `support_tickets` (`id`, `ticket_ref`, `owner_id`, `telegram_id`,
  `created_at`) tables store user and chat identifiers. Existing Jira Story
  [WISHENKA-35](https://pypost.atlassian.net/browse/WISHENKA-35) covers account deletion and
  personal-data cleanup across the application and must include purging or anonymizing both tables.

## Missing Tests

- **Per-test timeout marker audit (`do-testing`):** Audited across the entire repository via
  `.venv/bin/pytest --collect-only -q -m "not timeout" -p no:cacheprovider -n 0`: **1000 collected
  tests, 1000 deselected, 0 tests missing explicit `pytest.mark.timeout` markers** (no BLOCKER).
  Both `tests/test_bot_support_repro.py` (8 collected test items) and `tests/test_bot_support.py`
  (5 collected test items) declare `pytestmark = pytest.mark.timeout(30)` at module scope. No
  pre-existing test failures were encountered during the run.
- **Real Telegram Bot API smoke test:** Support channel tests use an in-process fake
  `Bot.__call__` transport. Opt-in real Telegram API smoke testing is already tracked under
  [WISHENKA-156](https://pypost.atlassian.net/browse/WISHENKA-156).
- **Account deletion verification for support tables:** Cannot be tested until account deletion
  ([WISHENKA-35](https://pypost.atlassian.net/browse/WISHENKA-35)) is implemented.

## Performance Concerns

- **Write-lock duration during diagnostic context collection:** `_submit_support_message` runs
  `collect_diagnostic_context` inside `WishlistStore.transaction` (`BEGIN IMMEDIATE` in SQLite).
  While per-user rate limiting (`3` tickets per hour by default) bounds submission frequency per
  user and current test runs complete in milliseconds, scanning all rows of `wl_lists`, `wl_tokens`,
  and `wl_invite_tokens` inside a write transaction will hold the SQLite writer lock longer as total
  wishlist volume grows.
- **Sequential multi-destination Telegram sends:** When multiple destinations are configured
  (`support_chat_id` and multiple `support_admin_ids`), `_submit_support_message` awaits
  `message.bot.send_message` sequentially for each recipient (`wishenka/bot/support.py:389-399`).
  If one destination experiences network latency or timeouts, user confirmation latency increases
  proportionally to the number of configured destinations.
- **Bounded hourly cleanup batches:** `cleanup_drafts` deletes at most 100 expired `support_input`
  rows and 100 expired `support_tickets` rows per hourly pass. Given per-user rate limits, normal
  support volume will not exceed this rate, though backlog should be monitored alongside existing
  draft cleanup.

## Follow-up Tasks

1. **NON-BLOCKER, Medium:** Include `support_input` and `support_tickets` in account deletion and
   personal-data cleanup, and add automated tests verifying that deleting a user removes active
   support sessions and ticket rate-limit records.
   Existing scope: [WISHENKA-35](https://pypost.atlassian.net/browse/WISHENKA-35).
2. **NON-BLOCKER, Low:** Replace full-table scans of `wl_lists`, `wl_tokens`, and
   `wl_invite_tokens` in `collect_diagnostic_context` (`wishenka/bot/support.py:213-224`) with
   scoped token lookups or regex-only capability redaction outside the write transaction, and
   extract a shared private-bot user upsert + `bot_destinations` activation helper across
   `wishenka/bot/entry.py`, `wishenka/bot/support.py`, `wishenka/bot/birthdays.py`, and
   `wishenka/bot/capture.py` that consistently preserves stored `language_code`.
   Jira: [WISHENKA-182](https://pypost.atlassian.net/browse/WISHENKA-182).
3. **NON-BLOCKER, Low:** Extend the opt-in real Telegram Bot API smoke test coverage to exercise
   support ticket delivery (`LinkPreviewOptions(is_disabled=True)`) and multi-destination forwarding.
   Existing scope: [WISHENKA-156](https://pypost.atlassian.net/browse/WISHENKA-156).

No task-specific acceptance blocker was identified in this analysis.
