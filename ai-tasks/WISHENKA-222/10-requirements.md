# WISHENKA-222: Verify Quantity Selection Threshold (20 vs 21) and Out-of-Range Numeric Input Validation

## Goals

Ensure reliable, regression-free quantity selection when a wishlist owner records received gifts:

1. **Predictable transition between dropdown and numeric stepper**: Wishes with up to 20 remaining units must present a compact dropdown list, while wishes with 21 or more remaining units must present a numeric input with increment/decrement steppers so users never face an unwieldy list of options. Verifying the exact 20-vs-21 boundary prevents off-by-one regressions from degrading mobile usability.
2. **Client-side protection against out-of-range numeric entries**: When a user enters an invalid quantity (less than 1 or greater than the remaining quantity) in the numeric input, the interface must clamp the committed value back into the allowed range and prevent invalid submissions in the browser. Verifying this behavior protects data integrity and avoids unnecessary error round-trips.

## User Stories

1. **As a wishlist owner**, when I open the receipt dialog for a wish with **20 remaining units**, I want to pick a quantity from a dropdown list (1–20) so that selecting a moderate quantity is fast and effortless.
2. **As a wishlist owner**, when I open the receipt dialog for a wish with **21 remaining units**, I want a numeric entry control with `-` / `+` steppers instead of a long dropdown so that the dialog remains easy to use on mobile screens.
3. **As a wishlist owner**, when I type an out-of-range quantity (such as `0` or a number above the remaining count) into the numeric quantity field and commit or attempt to submit it, I want the field to reject invalid submissions and clamp the value into the valid range `[1, remaining]` so that I cannot accidentally submit an invalid receipt.
4. **As a product maintainer**, I want automated verification covering both the 20-vs-21 selection boundary and out-of-range numeric input validation/clamping so that future UI or route changes cannot silently break these guarantees.

## Definition of Done

1. Automated verification confirms that a wish with **20 remaining units** renders the dropdown quantity selector (with options 1 through 20) and not the numeric stepper control.
2. Automated verification confirms that a wish with **21 remaining units** renders the numeric input with `-` / `+` stepper controls (bounded between 1 and 21) and not the dropdown selector.
3. Automated browser verification confirms that for a large-quantity wish (e.g., 500 remaining units):
   - Entering a value below the minimum (e.g., `0`) or above the maximum (e.g., `501`) fails browser form validation and blocks submission when un-clamped.
   - Committing the out-of-range input clamps the displayed quantity and summary text to the nearest valid bound (`1` for values below 1; `remaining` for values above `remaining`), after which the form is valid.
4. All existing and newly added automated checks pass without regressions.

## Task Description

### Problem & Background

During WISHENKA-161, the receipt dialog introduced a 20-unit threshold separating dropdown selection from numeric stepper entry, along with client-side clamping and browser validation constraints for numeric quantity inputs. However, automated test coverage only exercised values far from the boundary (`1`, `5`, and `500`) and only tested valid numeric input (`42`), leaving the exact `20` vs `21` boundary and out-of-range numeric validation (`0` and `remaining + 1`) unverified.

### Scope

- **In scope**:
  - Automated verification of the receipt dialog rendering at the exact boundary of `20` remaining units vs `21` remaining units.
  - Automated browser verification of out-of-range numeric quantity input (below `1` and above `remaining`) for validation blocking and value clamping upon input commit.
- **Out of scope**:
  - Changing the threshold value (`20`), altering receipt business rules, or modifying production UI behavior (unless a genuine defect is uncovered during verification).
  - Adding test coverage for edit/cancel modals or gifted-section focus restoration (tracked separately under WISHENKA-221).

### Programming Language

- **Python** (automated route and browser test suites).

### Key Business Entities

- **Wish Item**: A wishlist entry with a `remaining` quantity available to be marked as received.
- **Receipt Dialog**: The confirmation interface where the wishlist owner chooses how many units (`1` to `remaining`) to mark as received.
- **Quantity Selector**: Either a dropdown list (for `2 <= remaining <= 20`) or a numeric input with `-` / `+` steppers (for `remaining >= 21`).

### Constraints & Assumptions

- No production behavior changes are expected; this task closes test-coverage gaps identified in WISHENKA-161 technical debt.
- Verification must respect existing project test execution standards (bounded timeouts, no external network dependencies, clean browser console).

## Q&A

1. **Why is this task needed from a business perspective?**
   - Source: `ai-tasks/WISHENKA-161/60-tech-debt.md` (follow-up item for WISHENKA-222). Without boundary and out-of-range input tests, an off-by-one regression at 20/21 units or broken client-side numeric validation could slip into production unnoticed, harming mobile usability and causing invalid receipt submissions.
2. **Is the 20-unit threshold or validation rule expected to change?**
   - No. The existing product behavior (dropdown for `<= 20`, stepper/numeric input for `> 20`, clamping to `[1, remaining]`, and browser range validation) is the baseline to verify.
