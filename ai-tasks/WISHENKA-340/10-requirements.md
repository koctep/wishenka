# WISHENKA-340: Personal screens read the current person's records

## Goals

Viewing history, favorites, recently deleted lists, and saving a wish from
the bot are personal. A person opening one of them should cause the product
to read that person's records for that screen, together with the list
details the screen already shows.

These openings used to read every wishlist in the product. That wider read
is already gone. Each opening already starts from the signed-in person.
The history list and clearing history already stay on that person's visits
and the list summaries those rows show. Favorites, recently deleted lists,
the bot's list choice, and recording a visit still continue into each
chosen list and read its wishes and reservations, which those screens leave
off the page.

This task closes that remaining gap. The lists, order, permissions, and
words the person already sees stay the same. This is a technical-debt
follow-up from WISHENKA-213. It adds no screen and no permission.

Implementation language: Python.

## User Stories

- As a person opening viewing history, I see only my recent visits, in the
  same order, with the same row: wishlist name, description, occasion, when
  I viewed it, whether it is a favorite, and my role. That opening already
  reads my visits and those list summaries. This task keeps that opening
  on those records.
- As a person recording a visit, the product stores my visit on a list I
  may see. A deleted list and a list I may not see stay refused. Today,
  before the visit is stored, the product opens that list in full,
  including every wish and every reservation. After this task, preparing
  the visit reads my permission to record it and stores my visit.
- As a person clearing history, only my visits are removed. That is already
  true, and another person's visits stay in their own history.
- As a person opening favorites, I see only my bookmarks of other people's
  lists that I may still open, with the same card: name, description,
  occasion, status, my role, and the favorite mark. Today the product
  chooses those bookmarks and then opens each list in full. After this
  task, the opening reads my bookmarks and those card details.
- As an owner opening recently deleted lists, I see only my deleted lists
  that I can still restore, newest first, with the same recovery card:
  name, description, occasion, when it was deleted, when recovery ends, and
  how many days remain. Today each of those lists is opened in full. After
  this task, the opening reads my recoverable deleted lists and those
  recovery details.
- As a person saving a wish in the bot, the offered lists are still only
  the lists I may add a wish to, with the same titles and the same order.
  Today that offer opens each of those lists in full. After this task, the
  offer reads the lists I may use and their titles. Saving the wish onto
  the list I pick still follows the same rules as today.
- As another person, my visits, bookmarks, deleted lists, and bot drafts
  stay on my own screens.

## Definition of Done

- Opening viewing history reads the current person's recent visits and the
  list summaries those rows show. The cap, the order, and the row details
  stay as they are. Wishes and reservations on those lists stay out of
  that opening, as they already do.
- Clearing history removes the current person's visits.
- Recording a visit stores the current person's visit on a list they may
  see. Preparing that visit reads the permission and the visit. The wishes
  and reservations on the list stay out of that preparation. A deleted
  list and a list the person may not see stay refused. A person who is not
  stored stays on the existing refusal from WISHENKA-351.
- Opening favorites reads the current person's bookmarks they may still
  open, and the card details that screen shows. The wishes and
  reservations on those lists stay out of that opening. Own lists and
  deleted lists stay off the favorites screen, as they do today.
- Opening recently deleted lists reads the lists the current person owns
  that are still inside the recovery window, and the recovery details that
  screen shows. The wishes and reservations on those lists stay out of
  that opening. Lists past recovery stay off the screen.
- The bot's list offer reads the lists the current person may add a wish
  to, and their titles. The wishes and reservations on those lists stay
  out of that offer. Saving the chosen wish still adds it under the same
  rules as today. The draft stays that person's draft in that chat.
- What each person sees is unchanged: the same lists, the same order, the
  same details, and the same refusals.
- WISHENKA-325, WISHENKA-338, and WISHENKA-351 stay as they are.
  WISHENKA-325 is how the history list gathers its summaries. WISHENKA-338
  is the save lock on opening one wishlist. WISHENKA-351 is the refusal
  when a visit is recorded for a person who is not stored.

## Task Description

WISHENKA-213 left viewing history, favorites, recently deleted lists, and
the bot capture flow reading every wishlist in the product whenever one
person opened them. The business reason is that a personal screen should
read the current person's records. A wider read makes one person's opening
grow with everyone else's lists, and it pulls wishes and reservations onto
a path that does not show them.

That full-product read is already gone. The four surfaces now start from
the signed-in person. What remains is a second, smaller widening: after
the person's own lists are chosen, favorites, recently deleted lists, the
bot's list offer, and recording a visit open each chosen list in full.

`in-docs/spec.md` section 8.1 keeps favorites as a person's bookmarks of
other people's lists. Section 8.2 keeps viewing history as that person's
recently opened lists, apart from the main list. The bot offer is the
choice of a list the person may add a captured wish to
(`in-docs/bot-scenarios.md`). Recently deleted lists are the owner's
soft-deleted lists still inside the recovery window. Archived wishes are
a separate action and stay there.

### Current behavior

- **Viewing history.** The screen reads the current person's recent visits,
  up to the cap the product already uses, and the list summaries for those
  rows: name, description, occasion, when the person viewed it, whether it
  is a favorite, and the person's role. It reads that person's membership
  on those lists. Another person's visits stay in that other person's
  history. Wishes and reservations on the listed wishlists stay unread by
  this opening.
- **Clearing history.** Clearing removes the current person's visits.
- **Recording a visit.** The product stores one visit for the current
  person on one list they may see. A deleted list and a list they may not
  see stay refused. Before the visit is stored, the product opens that
  list in full: every member, every wish, and every reservation.
- **Favorites.** The screen chooses the current person's bookmarks of lists
  they may still open. Their own lists and deleted lists stay out. Each
  chosen list is then opened in full. The screen shows the list card
  described above.
- **Recently deleted lists.** The screen chooses soft-deleted lists the
  current person owns, then shows the ones still inside the recovery
  window, newest first. Each owned deleted list is opened in full on the
  way there. The screen shows the recovery card described above.
- **Bot capture.** The draft belongs to the current person and chat. The
  list offer loads every active list that person owns or belongs to, each
  in full, and keeps the lists they may add a wish to. The offer shows
  those titles. Saving the wish adds it to the chosen list under the
  existing wish rules.

### Scope

In scope: the history list, recording a visit, clearing history, the
favorites list, the recently deleted lists screen, and the bot's offer of
lists when capturing a wish.

Left as they are:

- How the history list gathers its summaries (WISHENKA-325).
- The save lock on opening one wishlist (WISHENKA-338).
- The refusal when a visit is recorded for a person who is not stored
  (WISHENKA-351).
- Adding or removing a favorite, restoring a deleted list, and the main
  list of the person's own and shared lists.
- Who may see a list, the history cap, and the words on these screens.
- The wish that is saved once the person has picked a list in the bot.

### Business entities

- **Person:** the signed-in user. Visits, bookmarks, recoverable deleted
  lists, and bot drafts belong to one person.
- **Visit:** one person's opening of one wishlist, kept in that person's
  recent history.
- **Bookmark:** one person's favorite of someone else's list that they may
  still open.
- **Recently deleted list:** a list the owner deleted that is still inside
  the recovery window.
- **Captured wish:** a bot draft for one person and one chat, offered a
  choice of lists that person may add a wish to.
- **List summary:** the name, description, occasion, status, and the
  person's own role. The wishes and reservations on the list are a
  separate reading, used when the person opens the list itself.

## Q&A

**Which openings already stay on the current person?**
The history list and clearing history. They read and change that person's
visits and the list summaries the history rows show. They already leave
the wishes and reservations on those lists unread.

**Which openings still read more than the screen shows?**
Favorites, recently deleted lists, the bot's list offer, and recording a
visit. Each starts from the current person, then opens the chosen lists
in full, including wishes and reservations the screen leaves off the page.

**Does "deleted" here mean archived wishes?**
It means the owner's recently deleted lists that can still be restored.
Archived wishes stay a separate action.

**Does the bot save itself stay on the chosen list?**
Yes. Once the person picks a list, saving the wish follows the same rules
as today. This task narrows the offer of lists, which today opens each
offered list in full.

**Which earlier tasks stay closed?**
WISHENKA-325 (history summaries), WISHENKA-338 (the save lock on a one-list
read), and WISHENKA-351 (a visit for a person who is not stored).
