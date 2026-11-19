# WISHENKA-159: Fail-Closed Wishlist Context & Permission Enforcement

## Goals

Ensure that every wish item operation requiring parent wishlist context (permission verification, actor role resolution, or wishlist lifecycle state checks) fails closed rather than silently bypassing authorization or state validation when the parent wishlist is missing.

From a business and security perspective:
- **Zero silent authorization bypass**: Access-control and lifecycle-state rules (preventing edits on archived/deleted wishlists, preventing unauthorized receipt recording or editing, and enforcing self-reservation restrictions) must never be skipped due to missing parent wishlist context.
- **Invariant protection**: A wish item cannot legitimately exist or be acted upon outside a wishlist; if an unexpected state ever occurs where the parent wishlist context is absent, the system must reject the operation immediately and safely instead of proceeding with unverified permissions.
- **Regression confidence**: Automated verification must explicitly confirm that operations fail closed when parent wishlist context is absent.

## User Stories

- **As a Wishlist Owner / Co-owner**, I want all wish item edits, gift receipt recordings, and receipt modifications to strictly verify my wishlist membership and wishlist state, so that no unauthorized or out-of-state action can ever slip through even if internal context is incomplete.
- **As a Gifter**, I want wish reservation rules (including active-wishlist checks and recipient self-reservation restrictions) to always be enforced, so that reservations remain consistent and valid.
- **As a System Maintainer**, I want missing parent wishlist context during wish item operations to fail explicitly and deterministically, so that latent bugs or future refactorings cannot silently disable security or lifecycle guards.

## Functional Requirements

1. **Fail-Closed Item Editing**: When editing a wish item, if the parent wishlist context is unavailable, the system must reject the operation rather than skipping wishlist lifecycle-state checks (archived or deleted status).
2. **Fail-Closed Item Reservation**: When reserving a wish item, if the parent wishlist context is unavailable, the system must reject the operation rather than skipping wishlist lifecycle-state checks or actor reservation-eligibility checks (such as recipient self-reservation rules).
3. **Fail-Closed Gift Receipt Recording**: When recording gift fulfillment (a receipt) for a wish item, if the parent wishlist context is unavailable, the system must reject the operation rather than skipping membership authorization and wishlist lifecycle-state checks.
4. **Fail-Closed Gift Receipt Modification**: When modifying or removing an existing gift receipt for a wish item, if the parent wishlist context is unavailable, the system must reject the operation rather than skipping membership authorization and wishlist lifecycle-state checks.
5. **No Regression on Valid Contexts**: All existing wish item editing, reservation, and gift-receipt operations where the parent wishlist context is present must continue to behave identically.

## Non-Functional Requirements

- **Programming language**: Python.
- **Security (Fail-Closed Default)**: Missing or unresolvable authorization/state context must always result in denial/failure, never silent allowance.
- **Testability**: Each of the covered operations must have automated test coverage exercising the missing-wishlist-context branch and verifying that the operation fails closed without mutating state.
- **Determinism & Safety**: No partial state mutations may occur before the missing-context failure is raised.

## Main Business Entities

- **Wishlist**: The parent container owning wish items, membership/ownership roles, and lifecycle state (active, archived, deleted).
- **Wish Item**: An item belonging to a wishlist that can be edited, reserved, or fulfilled with gift receipts.
- **Actor (Owner / Co-owner / Gifter)**: The user attempting to perform an operation on a wish item, subject to role-based and relationship-based access rules.
- **Gift Receipt**: A record of wish item fulfillment managed by authorized wishlist members.

## Definition of Done

1. All wish item operations that check parent wishlist permissions, actor context, or wishlist lifecycle state (item editing, item reservation, gift fulfillment recording, and gift receipt modification) fail closed when the parent wishlist is absent.
2. None of the affected operations silently skip authorization, role-context resolution, or wishlist status validation when the parent wishlist is missing.
3. No state mutation occurs when an operation fails due to missing parent wishlist context.
4. Automated tests cover the missing-wishlist branch for each affected operation and verify fail-closed behavior.
5. All existing tests continue to pass without regression.

## Task Description

- **Problem**: Several wish item operations currently guard their wishlist-level checks (lifecycle status, membership authorization, and reservation eligibility) with a conditional check that silently skips validation when the wish item's parent wishlist reference is absent. While normal persistence guarantees the parent wishlist is attached, this fail-open pattern violates secure-by-default principles and creates a risk if an item is ever constructed or detached without its parent wishlist.
- **Scope**:
  - In scope: The four fail-open permission/context/lifecycle guards on wish item operations (editing, reserving, recording fulfillment, and modifying receipts) and automated tests for the missing-wishlist case.
  - Out of scope: Existence/error-branch checks for missing or deleted wishlists in non-guard flows (e.g., favorites or view history), changes to normal persistence behavior, and unrelated refactoring.
- **Constraints & Assumptions**:
  - In normal production persistence, every wish item always has an associated wishlist.
  - Implementation language is Python.

## Q&A

- **Q**: Why change behavior that is unreachable in normal production persistence?
  **A**: Fail-open security and state guards are a latent vulnerability: any future refactoring, edge case, or test setup that omits the parent wishlist reference would silently bypass authorization and lifecycle checks. Converting them to fail-closed enforces defense-in-depth.
