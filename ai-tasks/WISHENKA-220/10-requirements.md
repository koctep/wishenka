# WISHENKA-220: Missing-wish archive shows a notice, not a crash or reload

## Goals

A wishlist author who tries to archive a wish that is not on the list must
see that the wish or wishlist is no longer available. The wishes that are
still on the list stay where they are. The page stays put. The moment must
not look like a reload and must not look like a generic crash.

The product already presents this failure as a list notice. That notice is
how the author learns the archive did not happen. A standing check still
treats the same moment as a silent unmarked error that a receipt-style
listener is supposed to observe, and it treats a list notice as the wrong
outcome. The check times out because that unmarked error never arrives.

The check has to agree with what the author sees. A list notice for a wish
that is not on the list is the outcome. It is not evidence that a
receipt-style listener saw an unmarked error. The separate case where the
list order itself is stale still announces that the list changed and then
reloads; this task does not change that case.

This is debt on the gift lifecycle (parent epic WISHENKA-21): receiving a
gift and archiving what was given. It does not add a screen and does not
change who may archive, what archiving means, or how received gifts are
kept apart from the archive.

Implementation language: Python.

## User Stories

- As a **wishlist author** (owner, administrator, or member), when I try to
  archive a wish that is not on the list, I see that the wish or wishlist
  is no longer available, the remaining wishes stay on the list, and the
  page does not reload or look broken.
- As a **wishlist author** reordering wishes after the list changed
  elsewhere, I still see that the list changed and the page still refreshes
  itself. This task does not change that moment.
- As a **wishlist author** recording that a gift was received, I keep the
  receipt flow's own feedback. An archive of a missing wish is not reported
  as an unmarked receipt error.
- As a **recipient**, I still never learn who reserved or bought a wish, or
  that a reservation exists, from this notice.
- As a **maintainer**, I can trust
  `test_unmarked_error_neither_shows_notice_nor_reloads` to describe the
  visible outcome: a list notice, no reload, and no claim that a
  receipt-style listener saw an unmarked error.

## Definition of Done

1. **Missing wish.** Trying to archive a wish that is not on the list shows
   the existing notice "Wish or wishlist is no longer available." (Russian:
   "Желание или вишлист больше недоступны."). Any open item dialog for that
   attempt closes. Wishes that are still on the list stay on the list,
   in the same order. The page does not reload. The screen does not look
   like a generic crash.
2. **Standing check.** `test_unmarked_error_neither_shows_notice_nor_reloads`
   passes. Today it times out after 5 seconds waiting for an unmarked error
   to reach a receipt-style listener, and it also requires the list notice
   to stay empty. After this task the check confirms the outcome in item 1
   and does not require that listener to have seen an unmarked error,
   because the product shows the failure as a list notice instead.
3. **Stale list order.** When the list order is no longer valid, the author
   still sees that the list changed and the page still reloads. That moment
   stays distinct from archiving a wish that is not on the list.
4. **Neighboring archive outcomes.** A successful archive still moves the
   wish into the archive and leaves received gifts in "Gifted". A fully
   received wish still refuses archive with the existing receipt-flow
   notice. Those outcomes are unchanged.
5. **Surprise and roles.** The notice still hides giver identity,
   reservation, and purchase status from the recipient. Who may archive is
   unchanged.
6. **Languages.** The Russian and English sentences already used for a wish
   or wishlist that is no longer available remain the sentences the author
   sees.

## Task Description

### Problem

Archiving means moving a wish off the active list while keeping the history
of what was received. If the wish is already gone from the list, the
archive cannot happen. The author needs a plain explanation on the current
page, not a refresh and not a crash.

The product does that: the author sees the "no longer available" list
notice, and the rest of the list stays. The standing check
`test_unmarked_error_neither_shows_notice_nor_reloads` was written when
this failure was silent. It still waits for a receipt-style listener to
observe an unmarked error, and it fails the run if a list notice appears.
The wait never completes. The failure has been present since commit
`e8279e6` (found during WISHENKA-161) and was still present at `1acdffc`
during WISHENKA-214.

The check's original purpose still matters for a different failure. Only
the case where the list order is stale should announce a change and reload
the page. An archive of a wish that is not on the list must not borrow that
reload, and it must not be described as an unmarked error once the author
is already shown a list notice.

### Scope

- The visible result of trying to archive a wish that is not on the list.
- The meaning of
  `test_unmarked_error_neither_shows_notice_nor_reloads`: it guards "no
  reload and no crash" and accepts the list notice as the way the failure
  is shown.
- The distinction from a stale list order, which still announces the change
  and reloads.

### Constraints

- Do not change who may archive a wish.
- Do not change what a successful archive does, or how received gifts stay
  in "Gifted" rather than in the archive.
- Do not change the stale-order announcement or its reload.
- Do not change receipt feedback for recording, adjusting, or cancelling a
  received gift.
- Keep the existing Russian and English wording for this notice.
- Keep surprise secrecy: the notice names no giver, reservation, or
  purchase.

### Non-goals

- A new kind of error for every failed request in the Mini App.
- A change to edit-dialog errors, reservation updates, or receipt quantity.
- A change to the rule that a fully received wish is not archived as a
  whole.

### Main entities

- **Wishlist** — the list the author is looking at. It has an active list,
  an archive of wishes taken off that list, and a separate "Gifted"
  history for what was received.
- **Wish** — one entry. It is either on the active list, in the archive, in
  "Gifted", or no longer available to this author.
- **Wishlist author** — the owner, an administrator, or a member. These
  roles may archive wishes on the list. A recipient who is also an author
  of that wish keeps that right and still must not see giver details.
- **List notice** — the short status on the list that tells the author why
  an action did not change the list. For this task the notice is the
  existing "no longer available" sentence.
- **Archive attempt** — the author's confirmation that a wish should leave
  the active list. When the wish is not on the list, the attempt fails and
  the list is unchanged.
- **Stale list order** — a different failure, where the order of wishes no
  longer matches the list. That failure tells the author the list changed
  and refreshes the page. It is not this task's failure.

## Q&A

- **Q:** Why does the check fail if the author already sees a notice?
  **A:** The check still expects a silent unmarked error: an empty notice,
  and a receipt-style listener that observed the failure. The product shows
  a list notice instead, so the listener never reports an unmarked error
  and the check times out. The author-facing result is already the notice.
  The check has to stop requiring the silent-error observation.

- **Q:** Should the page reload when the wish is not on the list?
  **A:** No. A reload means the list order changed and the page is
  refreshing itself. A wish that is simply not on the list stays on the
  current page, with the remaining wishes untouched.

- **Q:** Should this look like a crash or an empty failure?
  **A:** No. The author sees the existing "no longer available" notice.
  The list does not go blank, and wishes that are still on the list do
  not disappear.

- **Q:** Does a list notice mean a receipt-style listener saw an unmarked
  error?
  **A:** No. The notice is the product's way of showing this archive
  failure. The check must not treat that notice as proof of an unmarked
  receipt error, and it must not wait for such an error.

- **Q:** Does this task change archive, receipt, or surprise rules?
  **A:** No. Who may archive, what a successful archive does, how received
  gifts stay in "Gifted", and what a recipient is allowed to learn all stay
  as they are. The stale-order reload stays as it is.
