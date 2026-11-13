# WISHENKA-49: Reliable Concurrent Gift Reservations

## Goals

Gift coordination is valuable only if a gifter can rely on the outcome of a reservation. When
several gifters act at nearly the same time, the service must preserve the requested quantity so
they do not unknowingly buy duplicate gifts. This protects the product's reservation-limit
invariant while retaining the surprise for the recipient.

The task makes contention a supported product scenario rather than an opportunity for a
misleading success response or an inconsistent reservation result.

## Programming Language

The implementation language is Python.

## User Stories

- As a gifter, I can try to reserve available units even while other gifters are doing the same,
  so I receive an outcome that matches the inventory actually available to me.
- As a gifter, I receive a clear refusal when another gifter has already taken the requested
  units, so I can choose a different gift instead of assuming that my reservation succeeded.
- As a wishlist owner or recipient, I can trust that the requested number of units is never
  exceeded, so gift coordination remains credible.
- As a recipient, I continue to see no reservation quantities, statuses, or gifter identities,
  regardless of concurrent activity.

## Functional Requirements

1. The total units held by active gift reservations and units already received must never exceed
   the quantity requested for a wish.
2. The same limit must hold when multiple independent gifters submit reservation actions for the
   same wish at the same time.
3. A successful reservation must represent units that remain within the available quantity at the
   time its outcome is finalized.
4. A reservation request that cannot be fulfilled because the available quantity was taken must
   leave the caller without an additional reservation and must not reduce another caller's
   reservation.
5. Concurrent activity on one wish must not change the quantities or reservation outcomes of a
   different wish.
6. Existing reservation lifecycle actions remain meaningful under contention: an eligible gifter
   may create, change, cancel, mark purchased, or undo purchase only when the resulting inventory
   remains valid.
7. Recipient-facing views and notifications must continue to omit reservation availability,
   reservation status, and gifter identity.
8. The product must verify the invariant with repeatable concurrent and stress scenarios covering
   one-unit and multi-unit wishes.

## Non-Functional Requirements

- Outcomes under normal contention must be deterministic with respect to the quantity invariant:
  no request may create an overbooked state.
- A request that cannot complete safely must not leave a partial or ambiguous reservation result.
- Contention verification must have bounded execution time and must not depend on external gift
  merchants or manual timing.
- The change must retain the current product roles, authorization rules, and surprise guarantees.

## Definition of Done

- Concurrent attempts to reserve the final available units do not overbook a wish.
- The aggregate reservation and received quantities remain at or below the requested quantity in
  each verified concurrent scenario.
- Losing reservation attempts have no unintended inventory or reservation side effect.
- Reservation actions on unrelated wishes remain isolated from the contested wish.
- Recipient-facing data remains free of reservation details during and after concurrent activity.
- Repeatable automated stress coverage demonstrates these outcomes for single-unit and multi-unit
  wishes.
- Existing supported reservation lifecycle behavior and authorization guarantees remain intact.

## Scope and Boundaries

### In Scope

- Correct quantity outcomes for simultaneous reservation lifecycle actions on the same wish.
- Clear all-or-nothing outcomes for requests affected by availability contention.
- Automated verification of the reservation-limit invariant under bounded concurrent load.
- Preservation of the existing surprise and role-based access rules while contention occurs.

### Out of Scope

- Changing how wishlist members, public links, or recipient identities are managed.
- New payment, purchase, merchant, or fulfilment integrations.
- Changing the user-visible product rules for requested quantity, received quantity, or the
  reservation lifecycle beyond making their concurrent outcomes reliable.
- Exposing reservation details to recipients for troubleshooting or support.

## Business Entities and Interactions

- **Wish**: a requested gift with a requested quantity and any quantity already received.
- **Reservation**: a gifter's commitment for a quantity of one wish; active and purchased
  commitments consume available units, while cancelled commitments do not.
- **Gifter**: an eligible person who can request a reservation action and sees their own outcome.
- **Recipient**: the person intended to receive the gift; they must not receive reservation
  information.
- **Available quantity**: the portion of the requested quantity not already received or held by
  active or purchased reservations.

Gifters compete only for the available quantity of the same wish. Their actions update the wish's
reservation state, while the recipient receives a privacy-preserving view of that state.

## Constraints and Assumptions

- The requested quantity is the product ceiling; there is no waitlist, oversell, or partial
  success outcome unless the existing product action explicitly supports a requested partial
  quantity.
- A gifter may receive a refusal when another valid request has consumed the available quantity;
  refusal is an expected business outcome, not a successful reservation.
- The product continues to support both one-unit and multi-unit wishes.
- The current role and authorization policy remains the source of eligibility for a reservation
  action.
- Existing recipient privacy guarantees apply to every result, including a failed or contested
  reservation request.

## Q&A

### Why does a technical locking request need this work?

The underlying business need is to prevent duplicate gift purchases and preserve trust in the
wishlist. The product must give competing gifters outcomes that respect the finite inventory
without revealing reservation information to the recipient.

### What is the invariant this task protects?

For every wish, active and purchased reservation units plus received units must not exceed the
requested quantity.
