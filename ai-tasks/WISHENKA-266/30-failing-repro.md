# WISHENKA-266: Failing repro (Step 3)

The acceptance check is the standing test
`tests/test_receipt_theme_browser.py::test_receipt_text_has_readable_contrast`
(`fallback`, `light`, `dark`). A new red test is N/A because the behavior is
already present on HEAD `e87a9c6`.

`wishenka/web/static/miniapp.css` already sets `background` and `color` of
`.receipt-sheet .btn-modal-close` from `--receipt-bg` and `--receipt-text`.
With that pair, dark contrast is already at least 4.5. This step does not add
a test, does not edit the standing test, and does not change product CSS.

## Command outcomes

Isolated collection hits a pre-existing import cycle and never reaches contrast:

```text
.venv/bin/pytest tests/test_receipt_theme_browser.py -q
```

`fallback`, `light`, and `dark` each ERROR in setup:
`ImportError` cannot import `WishlistStore` from the partially initialized
module `wishenka.wishlists.store`. That cycle is WISHENKA-357. It is out of
scope for this task and is not fixed here.

The same three nodes pass when collected after a module that finishes the
import:

```text
.venv/bin/pytest tests/test_receipt_modal_browser.py::test_stale_giver_card_is_neutral tests/test_receipt_theme_browser.py -q
```

Result: `4 passed`. The extra node is the loader
`test_stale_giver_card_is_neutral`. The three theme nodes, including dark,
pass, so dark contrast is already at least 4.5.
