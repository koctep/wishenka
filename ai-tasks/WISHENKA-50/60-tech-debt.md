# WISHENKA-50: Technical Debt Analysis

## Shortcuts Taken

1. **Embedded In-Process Lifespan Worker**: The periodic cleanup loop runs directly inside the
   FastAPI `lifespan` context using `asyncio.create_task`. While optimal for single-process
   deployments, multi-worker setups (e.g. Uvicorn with multiple workers) would execute duplicate
   concurrent cleanup cycles without shared coordination.
2. **Single-Transaction Bulk Deletions**: Deletion of expired tokens and purge of soft-deleted
   wishlists operate in single atomic transactions. While clean and safe for current volume,
   unbounded bulk deletes could lock the SQLite database if hundreds of thousands of entities
   accumulate.

## Code Quality Issues

1. **Lack of User-Facing Restore Functionality**: Soft deletion marks lists with `status = deleted`
   and retains them for 30 days before permanent purging. However, the system currently lacks a
   user-facing endpoint or UI flow allowing users to self-serve restore a deleted wishlist within
   the retention period.
2. **Observability Export Limits**: Observability is implemented via structured JSON logs. While
   production-ready, formal Prometheus / OpenTelemetry counter and gauge metrics for token
   lifecycle and database purge duration are not yet exported.

## Missing Tests

1. **Multi-Process Concurrency Contention**: Existing tests thoroughly validate single-process
   concurrency and error recovery, but tests simulating multi-worker process locking on SQLite
   during cleanup are missing.
2. **Extreme Scale Purge Benchmarks**: Tests validate correct purging logic up to tens of entities,
   but do not benchmark transaction hold times under millions of cascade-deleted rows.

## Performance Concerns

1. **Unbounded Purge Query Execution Time**: In high-scale deployments, executing `DELETE FROM
   wl_lists WHERE status = 'deleted' AND updated_at <= :threshold` could cause long transactions
   and SQLite `busy_timeout` errors if batching with `LIMIT` is not implemented.
2. **Redundant Duplicate Runs Across Multiple Instances**: Without a distributed locking mechanism
   (e.g., Redis lock or SQLite advisory lock row), multiple workers will wake up simultaneously
   and attempt overlapping purge cycles.

## Follow-up Tasks

### DEBT-W50-1: Multi-Worker Background Task Coordination & Distributed Locking
- **Jira Issue**: [WISHENKA-83](https://pypost.atlassian.net/browse/WISHENKA-83)
- **Estimate**: 3 Story Points
- **Description**: Add distributed coordination (e.g. Redis lock or a dedicated `wl_locks` SQLite
  table with lease expiry) so that in multi-worker deployments only a single worker executes the
  cleanup cycle.
- **Impact / Severity**: Medium. Prevents lock contention and duplicate work across worker pods.
- **Priority**: Medium.
- **Blocker Status**: Non-blocker for WISHENKA-50.
- **Suggested Remediation**: Implement an advisory lease lock in `run_cleanup_cycle` before running
  the cleanup operations.

### DEBT-W50-2: Metrics Instrumentation for Token & Wishlist Lifecycle
- **Jira Issue**: [WISHENKA-84](https://pypost.atlassian.net/browse/WISHENKA-84)
- **Estimate**: 2 Story Points
- **Description**: Export formal Prometheus / OpenTelemetry metrics for background cleanup cycles
  (e.g. `wishenka_tokens_purged_total`, `wishenka_wishlists_purged_total`,
  `cleanup_duration_seconds`).
- **Impact / Severity**: Low. Facilitates operational dashboards and alerting.
- **Priority**: Low.
- **Blocker Status**: Non-blocker for WISHENKA-50.
- **Suggested Remediation**: Introduce standard Prometheus metrics in
  `wishenka/wishlists/cleanup.py`.

### DEBT-W50-3: Chunked Batching for Large-Scale Database Purges
- **Jira Issue**: [WISHENKA-85](https://pypost.atlassian.net/browse/WISHENKA-85)
- **Estimate**: 2 Story Points
- **Description**: Batch deletion of soft-deleted wishlists in configurable chunks (e.g., 500 rows
  per transaction) to bound transaction duration and avoid write starvation.
- **Impact / Severity**: Medium. Safeguards against long-held SQLite write transactions.
- **Priority**: Medium.
- **Blocker Status**: Non-blocker for WISHENKA-50.
- **Suggested Remediation**: Update `WishlistRepository.purge_archived_wishlists` to accept a batch
  limit and loop until zero rows remain.

### DEBT-W50-4: Self-Service Wishlist Restoration Within Retention Period
- **Jira Issue**: [WISHENKA-86](https://pypost.atlassian.net/browse/WISHENKA-86)
- **Estimate**: 3 Story Points
- **Description**: Expose an API endpoint and UI action allowing wishlist owners to view their
  soft-deleted wishlists and restore them back to active/archived status within 30 days.
- **Impact / Severity**: Low. Enhances user experience and data recovery self-service.
- **Priority**: Low.
- **Blocker Status**: Non-blocker for WISHENKA-50.
- **Suggested Remediation**: Add route `POST /api/wishlists/{id}/restore` and corresponding
  domain service method.

## Blocker Review

None of the identified technical debt items block closing WISHENKA-50.
All acceptance criteria and Definition of Done items from `10-requirements.md` are completely met.
All 180 automated tests in the test suite pass with explicit timeouts.
