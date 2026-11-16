# WISHENKA-122: Validate reservation quantity before wish loading

## Research

- `wishenka/web/routes/reservations.py` authenticates the caller through `User`, then calls
  `execute`. The persistent store's `execute_wish` loads the wish before invoking the action.
  Consequently a missing wish raises `ItemNotFoundError` and becomes HTTP 404 before the service
  can validate the quantity.
- `WishlistService.create_reservation` already rejects quantities below one with a `ValueError`
  and the required detail. The existing `execute` handler maps that error to HTTP 400 and emits
  `reservation_validation_error` without a giver identifier. Its injected-service path bypasses
  the persistent store, so validation must be consistent across both paths.
- The shared `ReservationQuantityDTO` is also used by the update endpoint; a model constraint
  would change that endpoint and FastAPI's normal validation response. Keep its contract intact.
- [FastAPI error handling](https://fastapi.tiangolo.com/tutorial/handling-errors/) documents
  raising `HTTPException` to terminate a path operation with a specified status and detail.

## Implementation Plan

1. Add a create-only quantity check in the authenticated route after dependency resolution and
   before `execute`. Return HTTP 400 with the existing detail for a quantity below one. Emit the
   existing `reservation_validation_error` event with operation and item scope, never giver data.
2. Keep the service's validation as a domain guard for direct callers. Prefer sharing the fixed
   validation detail or a small validator to avoid divergence; do not change update semantics.
3. Keep positive quantities on the existing transaction, permission and error mapping path.
   Authentication, CSRF and request parsing continue to run through existing dependencies and
   middleware before the route; do not move validation into an unauthenticated middleware.
4. Run the reviewed regression tests and relevant reservation, permission and privacy tests.

### Failing Repro (Step 3)

Before modifying production code, add bounded HTTP tests under `tests/` using the production
SQLite-backed `wishlist_store` path, with no injected `wishlist_service`. Authenticate a giver and
provide valid CSRF credentials. For quantities `0` and `-1`, POST to a nonexistent wish and
assert HTTP 400 with the existing detail; the current code produces 404, demonstrating the defect.
Include controls for an existing wish with invalid quantity (400), a positive quantity on a missing
wish (404), and persisted reservation state unchanged. Use an explicit pytest timeout. Additional
implementation-phase tests should confirm the request does not call `execute_wish`, the event
contains no giver ID, the injected-service path agrees, and unauthenticated requests retain their
existing response. Do not change production code until the failing test is independently reviewed.

## Architecture

```text
HTTP client
  -> authentication / CSRF / request parsing
  -> create_reservation route: validate quantity
       -> invalid: privacy-safe validation event -> HTTP 400
       -> valid: execute -> store.execute_wish or injected service
                       -> WishlistService.create_reservation domain guard
                       -> existing reservation projection and HTTP response
```

- **Route boundary** owns create-request validation precedence and HTTP error mapping. Its inputs
  remain path IDs, `ReservationQuantityDTO`, authenticated user and request; its success response
  remains `PromiseActionDTO` and HTTP 201.
- **Wishlist service** remains the authority for direct calls and retains its validation guard,
  permissions, quantity rules and reservation lifecycle.
- **Store** retains its transaction and loading behavior for valid input. The invalid branch never
  reaches storage or emits a not-found or completion event.
- **Diagnostics** use the existing route logger and structured validation event. Avoid including
  the user, giver identifier, or user-provided request body in the event.
- **Other promise routes** and the shared DTO remain unchanged.

## Q&A

- **Why not constrain the DTO?** It is shared with resize, and a model error would normally be
  HTTP 422 rather than the required existing HTTP 400 contract.
- **Does a missing wish become discoverable?** No: invalid quantities have the same 400 for any
  wish; valid missing-wish requests retain the existing uniform 404.
- **Does this affect unauthenticated callers?** No route logic should run before the existing
  authentication and CSRF checks; validate this using the real HTTP stack.
