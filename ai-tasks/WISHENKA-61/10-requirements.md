# WISHENKA-61: Client Idempotency Keys for Booking Mutations

## Goals

Users interact with the Telegram Mini App (TMA) primarily from mobile devices, where cellular connections frequently drop, stall, or time out while a request is in flight. When a giver reserves a wish, adjusts a reserved quantity, marks a reservation as purchased, cancels a reservation, or when an author records receipt of a gift, the server may successfully commit the change even though the client never receives the confirmation response.

Without server-side idempotency protection, retrying that timed-out or interrupted request causes the server to treat it as a brand-new user action. This leads to:

- Unintended duplicate reservations or extra unit deductions from a wish's remaining available quantity.
- Accidental double-recording of gift receipts, prematurely depleting a wish's remaining quantity.
- Confusing error states on retry (for example, a retry of a successful cancellation or purchase failing as "already cancelled" or "insufficient available quantity"), leaving the user unsure whether their action took effect.
- Duplicate downstream side effects, such as repeated notifications.

Client-side double-tap prevention alone cannot solve this problem because it does not survive network timeouts, connection drops, or client retries after an ambiguous outcome.

From a business perspective, this task is needed so that:

- Givers and wishlist authors on unstable mobile networks can safely retry interrupted booking and gift-receipt actions without risking duplicate deductions, duplicate reservations, or duplicate notifications.
- A single user intent produces at most one state mutation, preserving accurate item availability and reservation counts.
- The Surprise Invariant and role boundaries remain strictly enforced under all retry and replay scenarios.

## User Stories

- As a giver on an unstable mobile connection, I want my reservation request (from either a wishlist view or a public share link) to be safely retryable if the connection times out before I see the result, so that I do not accidentally reserve extra units or create duplicate reservations.
- As a giver managing my existing reservations, I want retrying an interrupted quantity update, purchase confirmation, undo-purchase, or cancellation request to return the outcome of the original operation rather than failing with a misleading conflict error.
- As a wishlist owner or collaborator recording that a gift was received, I want an interrupted or retried receipt confirmation with the same request key to be applied at most once, while a deliberate second tap for a new receipt still records a separate receipt.
- As a gift recipient, I must never gain access to reservation details or another user's operation results through idempotency key reuse or replay.
- As a service operator, I want idempotency records to expire after a reasonable retention period so that storage does not grow unboundedly while still protecting realistic client retry windows.

## Definition of Done

1. **At-most-once execution for keyed booking and receipt mutations**:
   - Repeating a request with the same client idempotency key, same actor, and identical operation parameters after the original request succeeded does not re-execute the mutation, does not deduct additional units from available or remaining quantity, does not create additional reservation or receipt records, and does not trigger duplicate notifications.
   - The repeated request returns the same outcome as the original completed request.
2. **Complete mutation coverage**:
   - Server-side idempotency key support covers all giver reservation mutations: creating a reservation (authenticated wishlist and public share-link flows), updating reservation quantity, cancelling a reservation, marking a reservation as purchased, and reverting a purchased reservation to active.
   - Server-side idempotency key support also covers gift-receipt confirmation mutations (API and UI receipt flows), fulfilling the deferred server-side duplicate-submission requirement.
   - Existing callers that do not supply an idempotency key continue to operate without breaking backward compatibility.
3. **Actor isolation and parameter mismatch protection**:
   - Idempotency keys are strictly isolated per actor and operation target; one user's key never affects or exposes another user's operations.
   - Reusing the same idempotency key with different operation parameters (such as a different quantity, different wish item, or different action) is rejected as a conflict without mutating state.
4. **Concurrency and failure handling**:
   - Concurrent duplicate requests carrying the same idempotency key execute the business mutation at most once, preventing race conditions from double-deducting item quantities.
   - If an original request fails before committing due to a transient unavailability (such as temporary resource contention), the key does not permanently block a subsequent retry from succeeding.
   - Malformed or invalid idempotency keys are rejected with a clear validation error before mutating state.
5. **TMA client retry support**:
   - The Telegram Mini App frontend generates a distinct idempotency key per user-initiated booking or receipt action and reuses that key when retrying a failed or timed-out attempt for the same action, rotating to a new key only when the user initiates a new action.
6. **Surprise Invariant and retention**:
   - Idempotent replay never leaks reservation or giver information to a wish recipient or unauthorized caller.
   - Idempotency records are retained for a bounded period sufficient for mobile retry recovery and cleaned up thereafter.
7. **Automated verification**:
   - Automated tests verify safe replay without double deduction across reservation creation (including public links), quantity updates, purchase/undo-purchase, cancellation, and gift-receipt recording, as well as parameter-mismatch rejection, cross-user isolation, concurrent duplicate handling, and expiration/cleanup behavior.

## Task Description

### Programming Language

- **Implementation language**: Python 3.12+ (consistent with the existing backend service).

### Business Domain Entities

- **Actor**: An authenticated user performing a mutation (a giver managing reservations or a wishlist owner/collaborator recording gift receipts).
- **Idempotency Key**: A client-generated opaque token identifying a single logical user intent across one or more network attempts.
- **Protected Mutation**: A state-changing booking or fulfillment action on a wish item or reservation (create reservation, update quantity, cancel, mark purchased, undo purchase, record gift receipt).
- **Idempotency Record**: The durable association between an actor, an idempotency key, the normalized intent parameters, the execution state (in-progress or completed), and the resulting outcome.

### Functional Requirements

1. **Idempotency Key Acceptance**:
   - All booking/reservation mutation entry points and gift-receipt mutation entry points accept an optional client-supplied `Idempotency-Key` header.
   - When the header is omitted, the operation executes using standard non-idempotent semantics for backward compatibility.
   - When the header is provided, it must be non-empty and within reasonable length/format bounds; invalid values are rejected immediately without performing any mutation.

2. **Deduplication and Replay Semantics**:
   - On the first valid request with a given `(actor, operation, idempotency key)`, the system executes the business operation normally and durably records the outcome atomically with the state change.
   - On any subsequent request with the same `(actor, operation, idempotency key)` and matching parameters:
     - If the original operation already completed and committed, the system returns the originally produced outcome without re-running the business logic or emitting duplicate notifications.
     - If the original operation is still in progress, the concurrent duplicate must not execute a second mutation; it is either serialized to receive the completed outcome or rejected cleanly as an in-flight conflict.
     - If the original operation failed before committing due to transient contention, the system must not return a stale success and must allow a safe retry.

3. **Parameter Consistency Check**:
   - Reusing an idempotency key that was already bound to different target identifiers or payload parameters (for example, a different quantity or a different item) must be rejected with a conflict error.

4. **Cross-User and Surprise Isolation**:
   - Keys are scoped to the authenticated user. Two different users sending the same key string never share an idempotency record.
   - If a user's access or role changes such that they become the recipient of a wish or lose access before a replay, the Surprise Invariant and access rules must still hold.

5. **Client Key Lifecycle in TMA**:
   - Each distinct user-triggered booking or receipt submission in the TMA generates a fresh key.
   - Retrying the same submission after a timeout or network error reuses the same key.
   - Starting a new deliberate action (for example, submitting a second receipt or changing quantity again after the first change completed) generates a new key.

### Non-Functional Requirements

- **Atomicity**: Recording the completed idempotency outcome must succeed or roll back together with the business mutation itself, so a committed mutation is never left without its idempotency record.
- **Retention**: Completed idempotency records remain valid for at least 24 hours to cover mobile reconnects and app resumes, after which expired records can be purged without affecting active reservations.
- **Performance**: Idempotency lookup and recording must add minimal latency to normal booking flows and must not block unrelated wish items or unrelated users.
- **Observability**: Idempotent replays, parameter-mismatch conflicts, and concurrent duplicate rejections should be observable for diagnostics without logging sensitive wish or surprise-violating details.

### Scope and Constraints

- **In Scope**:
  - Server-side `Idempotency-Key` handling for all reservation lifecycle mutations (authenticated and public-link creation, quantity update, cancel, purchase, undo-purchase) and gift-receipt confirmation mutations (API and UI).
  - TMA frontend key generation and reuse on retry for these mutations.
  - Bounded retention and cleanup of expired idempotency records.
- **Out of Scope**:
  - Read-only (`GET`) endpoints, which are inherently idempotent.
  - Non-booking wishlist/item CRUD mutations (such as editing wish titles or creating wishlists), unless explicitly added later.
  - Client-side offline queueing across full browser storage wipes.

## Q&A

- **Q**: Should gift-receipt mutations (`POST .../receipts` and `POST .../receipt`) be included alongside reservation mutations?
  **A**: Yes. Prior requirements and tech-debt tracking (`WISHENKA-22`, `WISHENKA-24`) explicitly deferred server-side idempotency for repeated receipt submissions to `WISHENKA-61`, and receipt confirmation directly deducts from remaining wish quantity just like reservations.
- **Q**: What happens if a client does not send `Idempotency-Key`?
  **A**: For backward compatibility with existing callers and tests, requests without `Idempotency-Key` continue to execute normally without deduplication; idempotency guarantees apply whenever the client supplies the header.
- **Q**: What if two deliberate actions happen sequentially (e.g., recording 1 received unit twice in a row)?
  **A**: Two deliberate actions are legal and must both succeed because the client generates a new `Idempotency-Key` for each distinct user action. Only retries of the same action reuse the same key.
