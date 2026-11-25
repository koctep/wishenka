# WISHENKA-312: One confirmation creates one wishlist

## Goals

An owner who decides to create a wishlist must get exactly the list they confirmed, once. After
the creation flow changed, opening "Create wishlist" no longer creates a list; the list appears
only when the owner confirms a valid form. That change must not let one deliberate confirmation
create a second list or send a second creation request. Duplicate lists clutter "My wishlists"
and break the owner's trust that each confirmation matches one list they chose to make.

Implementation language: Python for the product and its tests. The confirmation the owner
performs stays in the existing Mini App (the same client used in a plain mobile browser).

## User Stories

- As an owner, I confirm a new wishlist once and get one list, so my home screen matches the
  decision I made.
- As an owner, I repeat the confirmation while it is still being carried out (several taps, or a
  tap together with confirming from the keyboard) and still get one list and one creation
  request.
- As an owner, I open "Create wishlist" and leave without confirming, and no list appears.
- As an owner in Russian or English, in the Telegram Mini App or in a plain mobile browser, I get
  the same single-list result from one confirmation.

## Definition of Done

1. One deliberate confirmation of a valid creation form creates exactly one wishlist and sends
   exactly one creation request.
2. Repeating that confirmation before the outcome is known — several taps on the confirmation,
   several keyboard confirmations, or a mix of the two — still creates at most one list and sends
   at most one creation request.
3. If one deliberate confirmation can already produce only one list and one creation request
   after the flow change, the owner's experience stays as it is.
4. If one deliberate confirmation can still produce more than one list or more than one creation
   request, that path is closed so criteria 1 and 2 hold.
5. One confirmation of the form creates one list and sends one creation request. The product
   is adjusted only when one deliberate create action can still produce more than one list or
   more than one creation request.
6. Opening the flow, cancelling, leaving, or confirming with invalid data still creates nothing
   and sends no creation request.
7. A later, separate confirmation after a visible failed creation follows the existing rule: the
   failed attempt leaves no list, and one successful retry leaves one list.
8. The home "Create wishlist" action still only opens the flow. Repeating it creates nothing.
9. Other owner actions (editing, archive, delete, restore, share, favorites, history) are
   unchanged, in both languages and in both the Mini App and a plain mobile browser.

## Task Description

This is follow-up debt from WISHENKA-294 (item 5), to be settled after WISHENKA-296. It does not
add a new way to create lists. It keeps a promise the product already made: one deliberate create
does not duplicate.

### What changed before this task

WISHENKA-296 moved creation off the first tap. The home "Create wishlist" action opens a creation
flow and creates nothing. A wishlist exists only after the owner explicitly confirms the form
with a valid title (description, event name, and event date stay optional). Repeated taps on the
old instant-create action were not allowed to send more than one creation request. That action is
no longer the one that creates the list. The confirmation is.

### Business entities

- **Owner:** the person who creates a personal wishlist.
- **Creation flow:** the path from choosing "Create wishlist" until the owner confirms or leaves.
  It shows the fields of a new list.
- **Deliberate create action:** one explicit confirmation of that form with valid data. Extra
  taps or keyboard confirmations while that confirmation is still in progress are the same
  action, not new decisions.
- **Wishlist:** the personal list that appears only as the result of that action. It is active,
  owned by the owner, and shown in "My wishlists".

### Functional requirements

1. **One confirmation, one list.** A deliberate create action creates exactly one wishlist with
   the details the owner confirmed, shows it in "My wishlists", and opens it, as WISHENKA-296
   already requires for a successful confirmation.
2. **One confirmation, one creation request.** That same action sends exactly one creation
   request. A second request must not leave the product while the first confirmation is still in
   progress.
3. **Repeating the confirmation is still one action.** Several quick taps on the confirmation,
   repeated keyboard confirmation, and any mix of those, before the owner sees the outcome,
   produce at most one list and at most one creation request.
4. **One confirmation creates one list and one request.** After the flow change, one deliberate
   confirmation creates one list and sends one creation request. The product is adjusted only
   when one deliberate create action can still produce more than one list or more than one
   creation request. When that already holds, the owner's experience stays as it is.
5. **The form confirmation is the create.** Confirming the form once creates one list and sends
   one creation request. Opening the flow does not create a list. The product is adjusted only
   when one deliberate create action can still produce more than one list or more than one
   creation request.
6. **Unchanged creation rules.** Pressing "Create wishlist" on the home screen only opens the
   flow, however many times it is pressed. Cancel, back, closing the app or the tab, reload, and
   switching away before confirmation create nothing. Invalid or missing data creates nothing,
   keeps what the owner typed, and explains the problem. A remembered draft stays out of scope.
7. **A failed attempt is not a second list.** When the owner sees that creation failed, no list
   from that attempt is shown. One later confirmation can be tried again and, if it succeeds,
   creates one list. This task does not remove the known limit that a retry can create a second
   list when the first request actually succeeded and only the response was lost (WISHENKA-296;
   tracked apart from this task).
8. **Same result everywhere.** The single-list outcome is the same in the Telegram Mini App and
   in a plain mobile browser, in Russian and in English.
9. **Nothing else moves.** Settings, archive, delete, restore, sharing, favorites, history, and
   surprise secrecy stay as they are. Lists that already exist are not cleaned up or duplicated
   by this task.

### Non-functional requirements

- One confirmation stays one request even when the owner repeats it quickly, before any outcome
  is shown.
- While that confirmation is in progress, the owner can tell that it is in progress, and a repeat
  does not start another creation.
- The rule holds on a narrow phone and in both host environments already supported for creation.
- No reservation information is shown in the creation flow.

### Constraints and assumptions

- The business rule is the invariant above. The product changes only when one deliberate create
  action can still produce more than one list or more than one creation request.
- WISHENKA-296 remains the source of the creation rules (confirm to create, leave to create
  nothing, title required). This task does not reopen those rules.
- Out of scope: saved drafts; creating a list from the bot; making the lost-response retry safe;
  cleanup of lists that already exist; protection of actions other than wishlist creation;
  new fields, new screens, or a different confirmation step.
- Assumption: "one deliberate create action" means one decision to confirm a valid form,
  including repeats of that confirmation before the outcome is known. A new confirmation after
  the owner has seen a failure is a new action and follows requirement 7.

## Q&A

- **Why is this needed?** Owners must be able to trust that confirming a new list once adds one
  list. WISHENKA-296 changed which gesture creates the list (home tap opens a form; confirmation
  creates the list). The duplicate-protection promise was attached to the old gesture and had to
  be checked again for the confirmation. Source: Jira WISHENKA-312, WISHENKA-294 debt item 5,
  WISHENKA-296 requirement that a burst of confirmations still yields one list and one request.
- **What is in the gap?** The home action no longer sends the creation request. The request is
  sent when the owner confirms the form. The question this task answers is whether that
  confirmation, repeated as one action, can still send more than one creation request or create
  more than one list. The answer decides whether anything in the product must change
  (requirement 4).
- **Which confirmation is in scope?** The form confirmation the owner performs now. One
  confirmation creates one list and sends one creation request. The product is adjusted only
  when one deliberate create action can still produce more than one list or more than one
  creation request.
- **What was decided without a product owner?** The task text and WISHENKA-296 already state the
  rule, so no new product rule was invented: one deliberate confirmation must not duplicate, and
  behavior is adjusted only if the changed flow can still duplicate. The lost-response retry
  stays out of scope, as WISHENKA-296 left it.
