# WISHENKA-121: Serialize User Write Operations on the Shared Data Store

## Goals

Ensure that user profile write operations (account registration/refresh, language preference updates, and birthdate updates) participate in the same single-writer concurrency contract as wishlist and inventory operations on the shared data store.

From a business perspective, this prevents user profile updates from failing unexpectedly when they overlap with concurrent wishlist or gift reservation activity, and ensures that if the data store remains busy beyond the configured wait window, the system returns a clear, retryable busy signal without corrupting or partially saving user data.

## User Stories

- **As a returning or new user** signing in via the web app or interacting with the Telegram bot while other users are actively reserving or editing gifts, I want my profile sync to wait cleanly for its turn to write—or fail with a retryable error if the system is temporarily overloaded—so my session is not disrupted by unexpected internal storage errors.
- **As a user updating my profile settings** (preferred language or birthdate) during high concurrent wishlist activity, I want my update to either succeed atomically or inform me that the service is temporarily busy so I can safely retry without losing or corrupting my settings.
- **As a platform operator**, I want all write paths sharing the same persistent store to follow one consistent write-coordination contract and surface lock timeouts as retryable errors, without altering existing gift quantity or reservation availability rules.

## Definition of Done

1. Every write operation on user records acquires exclusive write access before reading and modifying data, matching the write-coordination contract already enforced for wishlist and inventory writes on the shared data store.
2. A user write operation that overlaps with a concurrent wishlist or inventory commit does not attempt an unsafe mid-transaction read-to-write upgrade; instead, it waits up to the configured busy-wait limit and completes cleanly once the active writer finishes.
3. If the shared data store remains locked past the configured busy-wait limit, the user write operation aborts cleanly, leaves existing user data unchanged, and raises/returns a retryable busy error rather than an uncategorized failure.
4. Read-only user lookups remain unaffected and do not unnecessarily block writers.
5. Existing wishlist quantity, reservation, and inventory availability calculation rules are untouched.

## Task Description

### Problem Statement

Currently, wishlist and inventory operations follow an upfront write-locking contract on the shared persistent data store, whereas user profile write operations (creating or updating user records, setting locale, setting or clearing birthdate) use deferred write acquisition. When a user write overlaps with a concurrent inventory commit on the same data store, the deferred write can attempt to upgrade a read transaction into a write transaction across an already-committed inventory change, risking immediate lock-conflict failures rather than orderly waiting, or surfacing lock timeouts as generic storage errors instead of retryable busy conditions.

### Programming Language

- **Python**

### Functional Requirements

1. **Consistent Write Coordination**: All user write operations (user creation/upsert from web or bot channels, locale updates, birthdate updates and clearing) must acquire write coordination upfront in accordance with the shared store's write-locking contract.
2. **Orderly Waiting Under Contention**: When another writer (such as an inventory or wishlist update) holds the write lock, a concurrent user write must wait up to the configured timeout and succeed if the lock is released in time.
3. **Retryable Busy Error Mapping**: When a user write cannot acquire the write lock within the configured timeout, the operation must roll back cleanly with no partial state changes and surface a retryable busy error.
4. **Scope Preservation**: Gift quantity formulas, reservation capacity rules, and inventory availability logic must not be modified or reopened.

### Non-Functional Requirements

- **Atomicity & Data Integrity**: Failed or timed-out user write operations must leave previously persisted user attributes (locale, birthdate, profile fields) completely unchanged.
- **Consistency Across Entry Points**: Both web application and Telegram bot entry points that read or write user records must obey the same coordination contract on the shared data store.

### Constraints and Assumptions

- **Source**: Follow-up from WISHENKA-57 (`ai-tasks/WISHENKA-57/60-tech-debt.md`).
- **Explicit Out-of-Scope**: Reopening or changing wish quantity / reservation availability formulas is strictly out of scope.
- **Assumptions**: Wishlist and inventory operations already enforce the target upfront write-locking and busy-timeout contract on the shared store.

### Main Business Entities

- **User**: Represents a registered platform participant with identity attributes (Telegram identifier, name, username), preferred language/locale, and optional birthdate details.
- **Wishlist / Inventory Activity**: Concurrent domain writes (creating wishes, reserving gifts, updating quantities) that share the same underlying persistent store as User writes.

## Q&A

- **Q**: Why is this technical-debt item needed from a business perspective?
  **A**: User profile writes share the same underlying store as wishlist and inventory writes. Without the same upfront write-locking contract and retryable timeout mapping, concurrent wishlist activity can cause user logins or profile updates to fail unpredictably instead of waiting cleanly or signaling a safe retry.
- **Q**: Should wish quantity or reservation formulas be revisited as part of this task?
  **A**: No. Wish quantity formulas are explicitly out of scope and must remain unchanged.
