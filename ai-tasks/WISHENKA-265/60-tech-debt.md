# WISHENKA-265: Technical Debt Analysis

No new technical debt. The giver-card refresh in
`wishenka/web/static/app.js` publishes `window.swapWishCard` and calls
that property when the card fetch returns text. The existing wrapper in
`wishlist.js` writes the neutral sentence. There is no new follow-up.

Reviewed: the `app.js` diff, `10-requirements.md`, `20-architecture.md`,
`40-code-cleanup.md`, and `50-observability.md`.

## Shortcuts Taken

None. The two functional lines are the Step 2 plan. After the local
`swapWishCard` function, the script assigns
`window.swapWishCard = swapWishCard`. The `htmx:afterRequest` card fetch
calls `window.swapWishCard(card, markup)` when `response.text()`
resolves, so the wrap installed by `wishlist.js` is the function that
runs. The file header names that publish. The sentence, the class, the
card route, and the fetch stay where they were. `app.js` still has no
`receipt` substring.

## Code Quality Issues

None. The publish is one assignment inside the IIFE, the same pattern as
`window.prepareCsrf`. The live path reads the property when the response
arrives. It does not copy the sentence, branch on status, or interpret
why the body is not the same card. No new hardcoded sentence, status, or
timeout was added.

## Missing Tests

No `do-testing` blocker. No new test was added.
`tests/test_receipt_modal_browser.py` declares
`pytestmark = [pytest.mark.timeout(45), pytest.mark.browser]`, which
covers `test_stale_giver_card_is_neutral`. That node already waits for
the Russian neutral sentence, rejects a JSON error body, and checks that
a still-available card refreshes and stays open. The wait stays the
5 second default. `tests/test_receipt_static_script.py` declares
`pytestmark = pytest.mark.timeout(30)` and still rejects a `receipt`
substring in `app.js`.

## Performance Concerns

None. Each card refresh does one extra property read on `window` before
the same DOM swap. No new request, poll, or server work.

## Follow-up Tasks

None. There is no new follow-up. Pre-existing issues from other tasks
are not listed here.

User documentation under `doc/` was left unchanged. The sentence a giver
sees did not change. Developer docs still say the swap is defined by an
inline script in `base.html` (`doc/dev/gift-receipt.md`, stale card).
That correction belongs to Step 8.
