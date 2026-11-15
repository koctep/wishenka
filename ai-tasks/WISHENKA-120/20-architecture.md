# WISHENKA-120: Busy response test architecture

## Research

- `wishenka/web/routes/items.py` wraps item operations in `execute`; an
  `InventoryBusyError` becomes HTTP 503 with the exception's detail. The handler records
  `item_inventory_busy` without a giver identifier.
- `wishenka/web/routes/items_ui.py` catches the same exception in `submit_edit_item` and renders
  `partials/item_edit_modal.html` with status 503, the submitted form, and a retry sentence.
- Existing HTTP route tests use the application test client, authenticated request headers, and
  a monkeypatched store operation to induce a busy error without waiting for an actual lock.
  FastAPI documents test-client requests and dependency overrides for isolated tests:
  [FastAPI testing](https://fastapi.tiangolo.com/tutorial/testing/) and
  [dependency overrides](https://fastapi.tiangolo.com/advanced/testing-dependencies/).

## Implementation Plan

1. Add focused pytest route tests under `tests/`, reusing the project's app and authentication
   fixtures. Apply an explicit `pytest.mark.timeout` to each collected test.
2. After creating the required wish and authentication context, replace the store's async
   `execute_wish` with a stub raising `InventoryBusyError`. Ensure the app is using the store
   path rather than an injected `wishlist_service`; scope the patch to each test.
3. Exercise an item mutation endpoint that calls `items.execute` with `item_id`. Assert HTTP 503,
   the established busy detail, and absence of giver identity from the response. If logs are
   checked, assert structured warning fields without relying on live log output.
4. POST valid, distinctive edit form values to the real edit endpoint under the same simulated
   contention. Assert 503, rendered edit modal and retry sentence; parse the HTML and verify the
   submitted field values, including select/textarea values, rather than raw substring matching.
   Check that the original item remains unchanged where the fixture permits a stable read.
5. Run focused tests and the repository quality gate. Changes are test coverage only; do not alter
   production behavior to make a test pass.

**Failing repro (Step 3): N/A — no behavioral change.** Both handlers already implement the
contract. The new regression tests should be green on the current implementation; inventing a
failure would not reproduce a product defect. Step 3 should record this rationale in the roadmap.

## Architecture

```text
pytest + authenticated TestClient
    | PATCH item / POST edit form
    v
FastAPI routing and existing authentication
    |                                |
    v                                v
items.execute                submit_edit_item
    |                                |
    +---- store.execute_wish --------+
              |
              v
   test stub raises InventoryBusyError
              |
              v
  503 JSON detail          503 rendered edit modal and preserved form
```

The HTTP client exercises routing, authentication, error translation, and template rendering.
The single storage seam is replaced after setup so no external service or timing-dependent lock
race is required. The test must assert observable response behavior and avoid changing the
handler, template, or storage interface. Fixture cleanup restores the stub automatically.

## Q&A

- **Why use a stub?** It deterministically reaches the real HTTP error handlers without a flaky
  database contention race. Existing storage tests cover lock behavior separately.
- **Why no red test?** The task adds regression coverage for existing behavior; no runtime
  behavior is intended to change.
- **How is privacy verified?** Assert the expected JSON response and check it contains no giver
  identifier; any extra log assertions must likewise avoid identifying giver data.
