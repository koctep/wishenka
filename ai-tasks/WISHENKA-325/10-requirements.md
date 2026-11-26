# WISHENKA-325: Opening viewing history gathers wishlists together

## Goals

A person opens a personal history of wishlists they recently viewed. That
history sits apart from the main list of their own, shared, and favorite
wishlists. Opening it today looks up each wishlist on the recent list one
at a time. A longer recent list means more separate lookups, even though
the person still sees the same short list.

This task makes that opening gather the wishlists for the recent list
together, so the lookup does not repeat once per row. The history the
person sees stays the same. Older stored visits stay stored. The recent
list may still be capped, as it already is.

The work is a medium technical-debt follow-up from WISHENKA-80 (2 story
points, label tech-debt). It does not add a new screen or a new history
rule.

Implementation language: Python.

## User Stories

- As a person, I open my recent viewing history and see the same wishlists
  I see today, in the same order, so a cheaper opening does not change what
  I recognize.
- As a person, each row still shows the wishlist name, description, event
  title, event date, when I viewed it, whether it is a favorite, and my
  role on that wishlist.
- As a person, a wishlist I can no longer view, a missing wishlist, and a
  deleted wishlist stay off the recent list, as they do today.
- As a person with more stored visits than the recent list shows, opening
  history still shows only the capped recent list, and the older visits
  remain stored.
- As a person, recording a new visit does not drop older stored visits, and
  clearing my history still clears it.
- As a person, another person's viewing history never appears in mine.
- As a Russian or English speaking person, in the Telegram Mini App, the
  history I open keeps the same meaning.

## Definition of Done

- Opening one person's viewing history gathers the wishlists for that
  recent list together. It does not look up each wishlist one at a time.
- The history the person sees is unchanged: the same wishlists, the same
  order, and the same details on each row.
- Wishlists the person can no longer view, missing wishlists, and deleted
  wishlists stay out of the list.
- The recent list may still be capped at the limit the product already
  uses. This task does not raise or remove that cap.
- Older stored visits stay stored. Recording a visit does not delete older
  visits. That outcome, already shipped by WISHENKA-323, remains.
- Recording a visit, clearing history, who may see a wishlist in history,
  and every other wishlist action stay as they are.
- No new person-facing signal is added.

## Task Description

WISHENKA-80 left opening a person's viewing history as one lookup per
wishlist on the recent list. That performance note is filed as this Debt
issue. The business reason is a responsive personal history that still
shows the wishlists the person already recognizes.

`specs/00-high.md` treats recent viewing history as a personal section,
beside favorites. `in-docs/spec.md` section 8.2 says the service keeps a
history of recently opened wishlists, available apart from the main list.
This task does not change those product rules. It changes only how the
wishlists for one opening are gathered.

WISHENKA-323 already unified the wishlist action rules, including viewing
history. Its shipped history outcomes stand: the list order and the cap
stay, and recording a visit does not delete older stored rows. This task
does not reopen that unification. It only stops the recent list from being
built by a separate lookup for each wishlist.

### Business entities

- **Person:** an authenticated user. Viewing history belongs to one person
  and is not shared.
- **Wishlist:** a personal or shared collection the person has opened. On
  the history row the person sees its name, description, event title, event
  date, favorite mark, and the person's role.
- **Viewing visit:** the record that this person opened that wishlist at a
  given time. Stored visits can outnumber the recent list.
- **Recent history list:** the capped list the person opens. It is ordered
  as it is today, most recently viewed first. When two visits share a time,
  their relative order stays as it is today. The list omits deleted
  wishlists, missing wishlists, and wishlists the person can no longer view.

### Functional requirements

1. **One opening, one gathering.** When a person opens their recent viewing
   history, the wishlists for that list are gathered together. The opening
   does not look up each wishlist one at a time.
2. **The history they see stays the same.** The same wishlists appear, in
   the same order, with the same name, description, event title, event
   date, viewed time, favorite mark, and role.
3. **The same omissions.** A deleted wishlist, a missing wishlist, and a
   wishlist the person can no longer view stay off the recent list. Who
   may see a wishlist in history stays as it is: the owner, a member, or a
   person who still has share access.
4. **The cap stays.** The recent list may still be limited to the number of
   visits the product already shows. Older stored visits are not required
   to appear on that opening.
5. **Stored visits stay.** Recording a new visit does not delete older
   stored visits. Clearing history still removes that person's history.
   This task does not change recording or clearing.
6. **Privacy stays.** One person does not see another person's history.
   Surprise isolation in `specs/00-high.md` is unchanged. History does not
   reveal reservations or givers.

### Non-functional requirements

- **Responsiveness:** the work of opening history does not grow by one
  separate wishlist lookup for each row on the recent list.
- **Sameness:** a person who opens history before and after this task, with
  the same stored visits and the same access, sees the same list.
- **Compatibility:** Russian and English, and the Mini App history the
  person already uses, keep their current meaning.
- **Operability:** this task does not add a new person-facing signal. Log
  events people already rely on for listing history keep their current
  meaning.

## Constraints and assumptions

- The implementation language is Python, matching the existing service.
- `specs/00-high.md` and `in-docs/` remain the product authority. This task
  does not change who may view history, what a row shows, the order, or the
  cap.
- WISHENKA-323 outcomes for history stay in force: older stored rows stay,
  and listing may still be capped. This task does not reopen rule-set
  unification.
- Out of scope:
  - WISHENKA-323, rule-set unification (already shipped).
  - WISHENKA-324, how the receipt screen reaches wishlist data.
  - WISHENKA-326, a retry when a save is briefly busy.
  - Changing how a visit is recorded, how history is cleared, or how access
    is revoked when membership or a share ends.
  - Raising or removing the recent-list cap.
  - Splitting large wishlist modules, and any new product feature.

## Q&A

- **Q: Why change opening history if the list already looks right?**
  **A:** The list is right, and it must stay right. Opening it still looks
  up each wishlist on its own. Gathering those wishlists together keeps the
  same list without a lookup per row.
- **Q: Will the person see more of their older visits?**
  **A:** No. The recent list may still be capped as it is today. Older
  stored visits stay stored. Recording a visit does not delete them, which
  is the outcome WISHENKA-323 already shipped.
- **Q: Does this change recording, clearing, or who may see a wishlist in
  history?**
  **A:** No. Only how the wishlists for one opening of the recent list are
  gathered.
- **Q: Are the rule-set unification, the receipt screen, and the busy-save
  retry part of this task?**
  **A:** No. Those are WISHENKA-323, WISHENKA-324, and WISHENKA-326.
  WISHENKA-323 is already shipped. This task keeps the history outcomes it
  shipped and does not take on the other two.
