# WISHENKA-122: Consistent rejection of invalid reservation quantities

## Goals

Give clients a consistent, useful explanation when a reservation quantity is invalid, regardless
of whether the requested wish can be found. Prevent invalid requests from creating reservations.

## User Stories

- As a gift giver, I want an invalid quantity to be rejected clearly so I can correct my request.
- As an operator, I want validation failures recorded without identifying a gift giver.

## Definition of Done

- A create-reservation request with a quantity below one returns HTTP 400 and the existing detail
  `Reservation quantity must be at least 1`, whether the wish can be loaded or not.
- The invalid request does not create or modify a reservation.
- Invalid quantities are rejected before wish lookup, and the validation event does not contain
  a giver identifier.
- A valid quantity for a missing wish continues to return the existing HTTP 404 response.
- The existing quantity check remains effective for callers outside the HTTP create path.
- Existing reservation actions, permissions, quantity calculations, and responses for valid
  requests remain unchanged.

## Task Description

Today the same invalid quantity receives different responses depending on whether the requested
wish can be loaded. The work applies to reservation creation and preserves the existing promise
API and quantity rules. It does not change reservation resize or other actions.

The business entities are the giver, the wish, its containing wishlist, and a reservation with a
requested quantity. Request validation and diagnostic records must preserve giver privacy.

Implementation language: Python.

## Q&A

- **Why change the response?** Clients should receive the same actionable validation error for
  the same invalid input without depending on the existence of the referenced wish.
- **What happens for valid input referencing a missing wish?** The existing not-found response
  remains in effect.
- **Source:** [WISHENKA-18 technical debt](../WISHENKA-18/60-tech-debt.md).
