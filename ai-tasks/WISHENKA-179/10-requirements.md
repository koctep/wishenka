# WISHENKA-179: Supported Atomic Storage Operation for Saving Bot Drafts

## Goals

Eliminate the bot capture workflow's reliance on internal, unsupported wishlist-storage mechanisms when saving a wish draft and its confirmation receipt.

From a business and maintainability perspective:

- **Decoupled evolution**: Wishlist storage internals must be free to evolve without risking silent breakage or forced rewrites in the bot capture workflow.
- **Unbroken consistency**: Saving a captured wish into a wishlist and recording its save receipt must remain a single all-or-nothing outcome, so a user never ends up with a created wish without a receipt or a receipt without a persisted wish.
- **Preserved reliability**: Existing guarantees around failure rollback, concurrent capture/save actions, and duplicate save-confirmation retries (idempotency) must remain intact.

## User Stories

1. **Telegram Bot User (Wishlist Owner / Contributor)**:
   - As a bot user confirming a captured wish draft, I want my wish to be saved to the target wishlist and my save receipt recorded atomically, so that if anything fails midway nothing is half-saved, and if I tap confirm more than once or retry after a network blip, the wish is not duplicated.
2. **System Maintainer**:
   - As a maintainer of the wishlist storage and bot capture modules, I want the bot capture workflow to use a supported, public storage boundary for atomic draft-and-receipt persistence rather than internal storage details, so that storage internals can be refactored safely without breaking bot capture behavior.

## Definition of Done

1. **Supported boundary used**: The bot capture workflow saves a draft into a wishlist and persists its save receipt exclusively through a supported public storage operation, with zero direct use of private/internal storage snapshot methods.
2. **Atomicity and rollback preserved**: If either the wishlist domain update (adding the wish) or the draft/receipt update fails, neither change is persisted.
3. **Concurrency safety preserved**: Concurrent actions on the same draft or wishlist do not corrupt state, lose updates, or produce inconsistent draft/receipt pairs.
4. **Idempotency preserved**: Repeated confirmation of an already-saved draft at the same revision returns the existing saved outcome and receipt without creating duplicate wishes.
5. **Existing guarantees verified**: All existing automated tests covering rollback, concurrency, and idempotency in bot capture and storage continue to pass without weakening assertions.
6. **No user-facing behavior regression**: All existing bot capture flows (review, validation, authorization, saving, receipt display, and error handling) behave identically from the user's perspective.

## Task Description

### Problem Statement

Currently, when a user confirms saving a captured wish draft in the Telegram bot, the bot capture handler combines domain changes (adding the wish to the chosen wishlist) with updating the draft state and save receipt inside a single transaction by calling private internal snapshot methods of the wishlist store. While this preserves atomicity today, it couples the bot capture module to internal persistence details that are not part of the store's supported contract.

### Implementation Language

- **Python** (consistent with the existing repository).

### Functional Requirements

1. **Atomic Save Operation**: The wishlist storage boundary must provide a supported operation that allows the bot capture workflow to execute a domain mutation (such as adding a wish to an eligible wishlist) together with persisting the corresponding draft/receipt state within a single atomic unit of work.
2. **Bot Capture Adoption**: The bot capture save flow must use this supported operation instead of private internal storage methods.
3. **Eligibility & Authorization Preservation**: Access checks, wishlist eligibility checks, and draft state/revision checks must continue to apply before committing any change.
4. **Idempotent Replay**: Confirming an already-saved draft at the matching revision must continue to recognize the existing save receipt and report the saved outcome without duplicating the wish.

### Non-Functional Requirements

1. **Atomicity / Rollback**: Partial failures (domain validation error, storage error, or draft update failure) must roll back both domain and draft/receipt changes.
2. **Concurrency**: Concurrent mutations targeting the same draft or wishlist must remain serialized/isolated so no stale overwrite or split-brain state occurs.
3. **Behavioral Equivalence**: No changes to user-facing messages, keyboard flows, or draft/receipt lifecycles.

### Scope and Boundaries

- **In scope**:
  - Defining/exposing a supported atomic storage operation for combining wishlist domain changes with caller-scoped persistence (such as bot draft and receipt updates).
  - Migrating the bot capture save flow away from private storage snapshot methods to the supported operation.
  - Preserving and verifying rollback, concurrency, and idempotency test coverage.
- **Out of scope**:
  - Changing bot draft or receipt retention lifetimes, cleanup schedules, or ordering-watermark retention (covered separately).
  - Account deletion / personal-data anonymization for bot drafts and ordering records (covered separately).
  - Changing user-facing bot UI, copy, or capture workflow steps.

### Main Business Entities and Interactions

- **Wishlist**: A user's collection of wishes, governed by access/eligibility rules.
- **Wish**: A domain item added to a wishlist when a draft is confirmed.
- **Bot Draft**: A temporary, revision-tracked wish submission belonging to an owner in a specific chat, transitioning from active to saved (or cancelled/replaced).
- **Save Receipt**: The recorded reference linking a saved draft to the target wishlist and created wish, enabling idempotent confirmation and receipt display.
- **Wishlist Storage Boundary**: The component responsible for loading/saving wishlist domain state and providing transactional guarantees to callers.

### Constraints and Assumptions

- The task is a technical-debt refactoring originating from `WISHENKA-28` (`ai-tasks/WISHENKA-28/60-tech-debt.md`, Follow-up Task #3).
- No new external dependencies or user-facing protocol changes are expected.

## Q&A

- **Q: Why is this change needed if the current code already achieves atomicity?**
  - **A**: Using private internal snapshot methods couples the bot capture module to undocumented storage internals. Any future change to how the store reads, caches, or writes domain state could break bot capture or force coupled changes across modules. Exposing a supported storage operation preserves the exact same transactional boundary while establishing a clean, maintainable contract.
- **Q: Should any user-facing bot behavior change as part of this task?**
  - **A**: No. This is strictly an internal boundary refactoring; all user-visible flows, error messages, and guarantees (rollback, concurrency, idempotency) must remain unchanged.
