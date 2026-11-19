# WISHENKA-63: Safe Public Projections and Service Construction Boundary

## Goals

Protect the gift-surprise invariant and user data durability across all wishlist entry points.
Specifically, ensure that every public view of a shared wishlist consistently hides reservation
and private membership details from anonymous visitors and recipients, and ensure that
production entry points cannot accidentally operate against ephemeral, non-persistent storage.

The implementation language is Python, as established by the project architecture.

## User Stories

- As a **recipient** (whether list owner, administrator, or participant), I want all views of my
  wishlist—including opening my own public share link—to never reveal whether wishes are reserved,
  how many units are reserved, who reserved them, or whether they were purchased, so that the
  surprise is always preserved.
- As an **anonymous visitor** opening a shared wishlist link without logging in, I want to see the
  wishlist details and wishes without encountering private member lists or reservation details, so
  that the list is safely viewable with zero onboarding barrier and without leaking recipient
  surprises.
- As a **service operator**, I want all production entry points to require explicit persistent
  storage rather than silently falling back to temporary in-memory state, so that user wishlists,
  changes, and share links are never lost or isolated by mistake.

## Definition of Done

- All public-link lookup paths produce a single, consistent safe projection for anonymous visitors,
  never exposing reservation existence, reserved quantities, giver identities, purchase statuses,
  or private account/membership details.
- Authenticated recipients (including owners and administrators) viewing a wishlist through either
  authenticated or public-link views never see reservation existence, quantities, giver identities,
  or purchase statuses for their own wishes.
- Constructing the wishlist management capability for production use requires an explicit
  persistent storage backing; accidental creation of an unbacked in-memory instance in production
  contexts is prevented.
- Automated tests explicitly verify both anonymous public-link views and recipient views (including
  owner/administrator views) against a wishlist containing wishes and reservations, confirming no
  reservation or private membership data is disclosed.
- Automated tests verify that production-style initialization without persistent storage is
  rejected or prevented, while intentional isolated test usage remains supported.

## Task Description

### Business Problem

Follow-up analysis from `WISHENKA-7` identified two risks that affect product invariants as new
entry points (additional routes, bot handlers, and background workers) are integrated:

1. **Inconsistent public projections:** Two different public-link lookup paths exist with
   different visibility rules—one exposes gift-giver reservation information to anonymous
   callers, while the other restricts it. Reusing the permissive path in another entry point
   would violate the Surprise Invariant.
2. **Accidental non-persistent operation:** The wishlist management capability can currently be
   initialized without persistent storage, silently creating an isolated in-memory instance.
   Production callers that omit persistent storage would lose user data on restart and diverge
   from shared state.

### Scope

- **In scope:**
  - Consolidating public-link wishlist views into a single safe projection behavior across all
    entry points.
  - Enforcing the boundary between persistent production initialization and explicit
    non-persistent (test-only) initialization.
  - Adding verification coverage for anonymous visitor views, recipient views (owner and
    administrator), and the persistent-storage construction boundary.
- **Out of scope:**
  - Implementing new reservation, wish-management, or notification features.
  - Changing the authenticated gift-giver coordination workflow or introducing unregistered
    recipient identification.
  - Database schema migrations, query-level performance optimization, or token-history compaction
    (tracked separately).

### Main Business Entities and Interactions

- **Wishlist:** A collection of wishes with owner, optional metadata (name, description, event,
  date), lifecycle state (active or archived), membership, and a public share link.
- **Wish:** An item in a wishlist with descriptive details and requested quantity.
- **Reservation:** A gift giver's commitment toward a wish (quantity and purchase status), which
  must remain completely invisible to recipients and to unauthenticated visitors.
- **Viewer Contexts:**
  - *Anonymous Visitor:* Unauthenticated user accessing via a public share link; receives only
    public wishlist and wish information.
  - *Recipient (Owner / Administrator / Participant):* Authenticated user associated with the
    wishlist; receives wishlist and wish details without any reservation data.
  - *Gift Giver:* Non-recipient context where coordination data is permitted; must never be
    selected for anonymous visitors or recipients.

## Constraints and Assumptions

- Unauthenticated visitors cannot be reliably distinguished from recipients; therefore, anonymous
  public views must treat the caller conservatively and omit all reservation details.
- Existing authenticated membership and ownership checks remain the source of truth for
  determining recipient/member roles.
- Intentional in-memory usage for isolated unit tests must remain possible without weakening the
  guardrail for production callers.

## Q&A

- **Why consolidate public projections now?**
  Because having a permissive public-link lookup alongside a restricted one creates a latent
  privacy and surprise-invariant leak whenever new entry points (such as bot handlers or new web
  views) are added.
- **Why restrict in-memory initialization instead of keeping it as a default?**
  A silent fallback to in-memory storage risks data loss and split-brain state in production if a
  caller forgets to supply persistent storage. Making persistence mandatory by default prevents
  silent data-loss bugs.
- **Why test both anonymous and recipient views explicitly?**
  Both roles are bound by the Surprise Invariant, yet they reach wishlists through different
  access paths (public share link vs. authenticated membership). Verifying both ensures neither
  path leaks reservation or private membership information.
- **Sources:** `ai-tasks/WISHENKA-7/60-tech-debt.md`, `ai-tasks/WISHENKA-7/10-requirements.md`,
  `specs/00-high.md`.
