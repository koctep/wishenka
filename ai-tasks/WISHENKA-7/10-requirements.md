# WISHENKA-7: Wishlist management and sharing

## Goals

Enable people to maintain wishlists and share them with gift givers without registration
barriers, while preventing unauthorized changes and protecting the recipient's surprise.
The implementation language is Python, as established by the project architecture.

## User Stories

- As an authenticated user, I can create an empty personal wishlist and later update its
  details so that I can prepare a list without completing a lengthy form.
- As an owner or administrator, I can manage the list's details and archive or restore it
  so that the list remains current and can be recovered when needed.
- As a gift giver, I can open a shared list without registering, so that I can see the
  wishes without an onboarding barrier.
- As an owner, I can share a link without granting its holder permission to edit the list.
- As an owner or administrator, I can replace a compromised public link so that its old
  holder no longer has access through that link.
- As a recipient, I do not see information about reservations or purchases of my wishes,
  even if I also manage the list.

## Definition of Done

- An authenticated user can create more than one initially empty personal wishlist. The
  creator is its owner; name, description, event and date are optional at creation.
- An authenticated user can retrieve their own and shared-member wishlists and read a
  wishlist to which they belong. Lists remain available after creation and modification.
- The owner and administrators can change an active wishlist's name, description, event
  and date. Other members and link holders cannot change these settings.
- The owner and administrators can archive and restore a wishlist. Archiving preserves its
  data and hides it from the active list. Archived lists are read-only; public visitors see
  that the list is archived and cannot make new reservations. Restoration makes it active.
- An event date passing does not automatically archive or close the wishlist.
- Each wishlist has a distinct share link that opens that wishlist for anonymous reading
  without registration. A share link alone never grants membership or editing permission.
- An owner or administrator can reset the public share link. The replacement opens the
  same wishlist and the previous link immediately stops granting access. Other members and
  public visitors cannot reset it.
- Public share links resist practical guessing so that access is limited to people who
  have been given a link, subject to the recipient sharing it further.
- Missing, invalid or unavailable lists and unauthorized changes are rejected without
  exposing another user's private data or changing stored data.
- Views respect the surprise invariant: a recipient cannot see reservation existence,
  quantities, giver identities or purchase status for their own wishes. A public view must
  not disclose private account or membership information unnecessarily.

## Task Description

The business objects are a wishlist (owner, optional details, event and date, lifecycle
state), its membership (person and role), and its public share link. The owner's authority
and each member's role apply per wishlist. A participant may view the list but cannot edit
its settings; a public visitor receives read access only. A recipient is a contextual role
for a particular wish, independent of a person's administrative role.

This task covers wishlist creation, retrieval, changing details, reversible archival,
sharing and authorization for these operations. Managing invitations, roles, individual
wishes, reservations, notification delivery and the user interface are separate work.
The existing WISHENKA-6 decomposition describes the wider lifecycle and permission model;
permanent deletion and ownership transfer are outside this task's stated scope.

## Constraints and Assumptions

- Public access is by possession of the specific link, not a searchable public directory.
- The user identity and membership are supplied by existing authentication and membership
  capabilities; a public visitor need not be authenticated.
- The functional specification leaves identification of an unregistered recipient open.
  Public output must therefore avoid exposing reservation information when recipient status
  cannot be established safely; broader recipient identification is separate work.
- No quantitative performance target is specified. Access checks and link uniqueness must
  hold across users and lists, including concurrent operations.

## Q&A

- **Why support sharing?** The product enables gift givers to consult a recipient's wishes
  directly, while retaining control over who can change the list.
- **Why archive rather than remove?** The lifecycle in WISHENKA-6 preserves list data and
  permits restoration after an event or a change of plans.
- **Sources:** `specs/00-high.md`, `in-docs/spec.md`, and
  `ai-tasks/WISHENKA-6/10-requirements.md`; the task description defines the scope.
