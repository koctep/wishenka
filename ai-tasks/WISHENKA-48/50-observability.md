# WISHENKA-48: Observability Implementation

## Logging Implementation

### Added Logs

Structured production logs added to the storage and repository layers:

- **ERR**:
  - `wishenka.wishlists.store`: `Wishlist storage integrity error` on unexpected constraint
    failures (`event="wishlist_store_integrity_error"`).
  - `wishenka.wishlists.store`: `Wishlist storage operation failed due to database error` on
    underlying SQLAlchemy exceptions (`event="wishlist_store_error"`).
- **WARNING**:
  - `wishenka.wishlists.store`: `Capability token collision encountered, retrying operation` on
    `TokenCollision` or unique token index collision (`event="wishlist_token_collision_retry"`).
  - `wishenka.wishlists.store`: `Public token uniqueness violation, retrying operation` on
    duplicate public token conflicts (`event="wishlist_token_collision_retry"`).
- **INFO**:
  - `wishenka.wishlists.store`: `Wishlist store snapshot loaded: %d wishlists, %d items` on
    transactional snapshot read (`event="wishlist_store_read"`).
  - `wishenka.wishlists.store`: `Wishlist store committed changes: %d wishlists, %d items` on
    transactional snapshot commit (`event="wishlist_store_write"`).
  - `wishenka.wishlists.repository`: `Wishlist repository mutation: %s %s` on row mutations
    covering wishlists, items, reservations, favorites, and view history
    (`event="wishlist_repo_mutation"`).

### Log Structure

Log format used:
- Structured logs: Yes (`extra={"event": ...}`)
- Includes context: Yes (entity ID, user ID, aggregate counts, operation type)
- Log levels: INFO, WARNING, ERROR

### Event Specifications

1. **`wishlist_store_read`** (Logger: `wishenka.wishlists.store`, Level: `INFO`):
   - Emitted when loading database records into the in-memory transactional snapshot.
   - Context: `wishlists_count`, `items_count`, `reservations_count`, `members_count`,
     `favorites_count`, `history_count`.
   - Security guarantee: No raw token strings or entity payload data logged.

2. **`wishlist_store_write`** (Logger: `wishenka.wishlists.store`, Level: `INFO`):
   - Emitted when persisting modified entities and synchronizing monotonic counters.
   - Context: `wishlists_count`, `members_count`, `items_count`, `reservations_count`,
     `deleted_wishlists_count`, `deleted_members_count`, `deleted_items_count`,
     `deleted_reservations_count`.
   - Security guarantee: Aggregated counts only; no token or credential leakage.

3. **`wishlist_repo_mutation`** (Logger: `wishenka.wishlists.repository`, Level: `INFO`):
   - Emitted on direct repository mutations (`upsert` or `delete` actions).
   - Context: `entity` (wishlist, item, reservation, favorite, view_history), `operation`
     (upsert, delete, record, clear), and non-sensitive identifiers (`entity_id`, `user_id`,
     `wishlist_id`, `item_id`, `status`, `priority`).
   - Security guarantee: Capability tokens (`public_token`, `invite_token`) are strictly
     omitted from both message templates and extra context dictionaries.

4. **`wishlist_token_collision_retry`** (Logger: `wishenka.wishlists.store`, Level: `WARNING`):
   - Emitted when a generated capability token collides with an existing token during insert.
   - Context: `attempt` (integer attempt counter 1..5).
   - Security guarantee: Colliding token value is masked and never printed.

## Redaction Guarantees

- **Capability Token Redaction**: Public share tokens and member invitation tokens grant
  direct authorization access. They are treated as secrets and excluded from all logs.
- **Engine Query Parameter Masking**: `create_async_engine` is initialized with
  `hide_parameters=True`, ensuring SQLAlchemy masks bound parameters in tracebacks.
- **Driver Trace Suppression**: `aiosqlite` logger level is clamped to `WARNING` to prevent
  accidental query bound-value dumping in production debug traces.
- **Surprise Invariant**: Repository mutations record only non-confidential metadata (item IDs,
  reservation quantities, reservation statuses). Gifter details are never broadcast to recipients.

## Automated Validation & Caplog Contracts

The observability test suite in `tests/test_wishlists_sqlite_repo_observability.py` validates
all logging contracts under bounded execution (`pytestmark = pytest.mark.timeout(10)`):

1. **`test_wishlist_store_read_write_structured_logging`**:
   - Asserts structured `wishlist_store_read` and `wishlist_store_write` events upon store
     transaction execution.
   - Validates count attributes (`wishlists_count`, `members_count`, `items_count`).

2. **`test_wishlist_repo_mutation_structured_logging`**:
   - Asserts sequential `wishlist_repo_mutation` log events for all repository actions:
     wishlist upsert/delete, item upsert/delete, reservation upsert/delete, favorite
     upsert/delete, view history record/clear.

3. **`test_token_redaction_in_all_logs`**:
   - Executes store and repository operations with distinct secret tokens.
   - Dumps and inspects every record message and extra context across all loggers.
   - Asserts zero occurrences of secret capability tokens anywhere in log records.

4. **`test_token_collision_retry_logging`**:
   - Triggers token collision retry path via pre-populated invite token database collisions.
   - Asserts emission of `wishlist_token_collision_retry` warning logs.
   - Verifies the colliding token string is completely absent from all log messages and extras.

## Validation Results

- [x] Logs are structured with `extra={"event": ...}`
- [x] Includes operational context without sensitive data
- [x] Sensitive tokens (public/invite capabilities) are redacted
- [x] Error and warning handling for token collision retries
- [x] Caplog test suite passing (`make check` Quality Gate green)
- [x] All lines conform to line length requirements (<= 100 chars)
