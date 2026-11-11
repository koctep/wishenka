# WISHENKA-8: Wishlist Management Interface

## Goals

Let people create and maintain wishlists in the Telegram Mini App, invite trusted
collaborators, and share a gift-selection link without losing control of permissions or
exposing the surprise. The interface must make the difference between a collaborator
invitation and a public gift-selection link clear before either is shared.

## Scope and Business Entities

- A wishlist has a title, optional description, optional event name and date, an owner,
  members, a lifecycle status, and distinct public and collaborator access links.
- An owner creates and controls a list and can promote or demote administrators.
- An administrator can update settings and invite or remove ordinary members, but cannot
  manage administrators or remove the owner. A member can work on wishes but cannot manage
  global list settings or membership. A gifter can view the shared list without acquiring
  collaborator privileges. Recipient is a contextual role for a particular wish.
- This task covers the management interface and user-facing sharing flow. Wishlist content
  management, favorites, reminders, and gift reservation workflows are separate scope.

Implementation languages: Python and JavaScript, in the existing Mini App environment.

## User Stories

- As a Telegram user, I can create an empty personal wishlist and start adding wishes
  immediately, without first supplying a title, description, or event details.
- As an owner or administrator, I can view and change the list title, description, event
  name, and date, or leave the list ongoing, so that its purpose stays current.
- As an owner or administrator, I can invite collaborators and manage ordinary members,
  so that trusted people can help maintain the list.
- As an owner, I can appoint and remove administrators and see their roles, so that I can
  delegate settings and membership management deliberately.
- As an owner or administrator, I can copy a public gift-selection link or share it through
  Telegram, so that gift givers can open the intended list directly in the Mini App.
- As a collaborator or gifter, I can understand what access a link grants and am not offered
  controls that imply privileges I do not have.

## Functional Requirements and Definition of Done

1. An authenticated user can create an active, empty personal wishlist without completing a
   settings form, and is taken directly to its wish list with an entry point to add a wish.
   Creation does not require a title, description, event name, or date from the user.
2. An owner or administrator can open settings for an active list, see the current values,
   change and save its title, description, event name and date, and leave optional event
   fields empty. Returning to settings shows the saved values. An ongoing list remains
   possible without an event or date. Passing an event date does not close or archive a list.
3. The interface provides feedback for invalid input, denied access, and unsuccessful saves;
   it does not claim an unsuccessful change succeeded, and preserves entered values for
   correction or retry. Cancelling an edit leaves persisted settings unchanged.
4. The owner and administrator can see the members and roles of an active list, obtain a
   collaborator invitation, and remove an ordinary member. The invitation must be distinct
   from the public gift-selection link, identify the access it grants, and require the invitee
   to confirm joining. The owner or administrator can revoke and replace an invitation;
   a revoked invitation cannot grant access. Successful membership changes are reflected in
   the interface.
5. Only the owner can grant or revoke administrator status. Neither an administrator nor an
   ordinary member can remove the owner or alter administrator status. Non-managers cannot
   change settings or membership; the interface reflects these permissions and rejected or
   stale operations do not change data.
6. The public list header offers copy and Telegram share actions. Each uses the current
   public gift-selection link for that specific list and never substitutes a collaborator
   invitation. A successful copy is acknowledged; failure or unavailable sharing is reported
   without claiming success. Opening the public link reaches the correct list in the Mini App
   without registration, subscription, onboarding, or a request for personal data.
7. Owners and administrators can replace the public link; the interface communicates that
   the old link ceases to work and uses the replacement for subsequent sharing. Ordinary
   members and gifters cannot reset it. Sharing a public link does not grant editing rights.
8. An archived list is presented read-only: settings, invitations, membership changes, and
   link resets cannot be performed until an authorized user restores the list. Unauthorized
   requests and stale views remain subject to the same access and lifecycle rules.
9. Management and sharing views do not disclose a recipient's reservation status, quantity,
   giver identity, comments, or purchase state for that recipient's own wishes, including
   when the recipient is also an owner or administrator.
10. The interface is usable on a small touch screen and communicates loading, success, and
    recoverable failure without relying solely on color. Interactive controls have meaningful
    labels, and user-entered content is displayed safely. Access links are revealed only in
    their intended sharing context.

## Constraints and Assumptions

- Product scope is Telegram Bot and Mini App; a separate public website is out of scope.
- Roles and invitation semantics follow [WISHENKA-6](../WISHENKA-6/10-requirements.md),
  particularly its permissions matrix and distinct invitation/public link rules.
- Empty immediate creation follows [functional specification](../../in-docs/spec.md),
  section 4.2. A system-supplied display name is acceptable if no title is entered, provided
  creation never requires one from the user.
- The existing [WISHENKA-7 requirements](../WISHENKA-7/10-requirements.md) govern the
  current wishlist behavior. The interface must reconcile any missing service capabilities
  needed for the acceptance criteria; an unavailable operation is not silently treated as
  successful.
- Exact wording and presentation may follow existing product conventions; this document
  specifies user outcomes and permissions rather than the screen's implementation.

## Q&A

- **Why is this needed?** Users need a direct way to organize lists, delegate maintenance,
  and share with gift givers while keeping editorial access separate and surprises secret.
- **Can sharing invite a collaborator?** Only the distinct collaborator invitation grants
  that possibility, after confirmation; a public gift-selection link does not.
- **Must a new list have a user-entered title?** No. The functional specification requires
  immediate empty-list creation, with settings supplied later.
