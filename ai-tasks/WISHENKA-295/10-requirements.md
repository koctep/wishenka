# WISHENKA-295: Owner can delete their wishlist

## Goals

An owner must be able to get rid of a wishlist they no longer need, so that it stops getting in
the way of managing the lists that are still relevant. The story belongs to the epic
WISHENKA-5 (wishlist management and shared access) and to the sprint "Redesign Wishenka: a light
and recognizable interface". It gives the owner control over the life cycle of their own lists.

Deleting is a deliberate action, not the result of an accidental tap, and the user understands
the result afterwards: the list is gone from the active lists. The product principle of safe
removal stays intact (specs/00-high.md, 4.2: "safe deletion through archiving with a possibility
of restoration"). That principle is stated for wishes and for archiving; the time-limited
"Recently deleted" model for whole wishlists (restorable for a retention period) comes from the
existing product code and developer documentation, not from the high-level specification.

Implementation language: Python, JavaScript, HTML and CSS.

## Task Description

Today the product already knows the state "deleted" for a wishlist, the rule that only the owner
may delete and restore it, and the home-screen section "Recently deleted" (Недавно удалённые)
with a "Restore" action and the number of days left. What is missing for the user is the
beginning of the scenario: an owner cannot find a "delete wishlist" action in the wishlist
settings and therefore cannot start the deletion. This story adds that user-visible action with
a confirmation and a clear result, on top of the existing deletion and restoration rules.
It introduces no new lifecycle state and no new retention rule.

### Existing product rules this story relies on (facts found in the product)

These are facts about the product as it is, recorded so the requirements reflect it. They are
not changed by this story.

- Roles: only the owner deletes a wishlist (doc/dev/wishlists.md, permission matrix, line 502:
  "Delete wishlist (soft-delete)" is owner only; wishenka/wishlists/policy.py, `can_delete`).
  The specification (in-docs/spec.md, sections 3 and 4.4) says that the owner and administrators
  manage list settings and members, and that a participant adds, edits and archives wishes; it
  does not itself say who deletes a list. Settings and member management are owner and
  administrator only (policy.py `can_edit_settings`, `can_manage_members`).
- Archive is not deletion: the specification says that on reaching the event date the owner may
  send a list to the archive (in-docs/spec.md, 4.3); in the product an owner or administrator can
  archive and restore a list (policy.py `can_archive`). The wording of in-docs/spec.md 5.5
  ("deleting a wish means moving it to the archive; archived wishes can be restored") is about
  wishes, not wishlists. Deleting a wishlist is a separate, stronger action.
- Deleted lists (existing): a deleted list is hidden from every user, including its members,
  favorites and viewing history of other people, and its share and invitation links stop working.
  Active and purchased reservations of the list are cancelled.
- Restoration (existing): the owner sees their deleted lists in "Recently deleted" on the home
  screen, with the number of days left, and can restore one within the retention window (30 days
  by default). After the window the list is removed permanently and cannot be restored. A
  restored list becomes active again with new share and invitation links; the earlier links stay
  dead. Cancelled reservations are not revived.
- «Подаренные» (in-docs/spec.md, 7.2): the gifted history is removed permanently together with a
  deleted wishlist; no separate long-term history of receipts is kept after the list is deleted.
  In the product the data of a deleted list is kept during the retention period and removed by
  the scheduled cleanup after it (wishenka/wishlists/cleanup.py, service.py restore rule), so
  restoring within the period returns the list together with its history.
- Surprise secrecy (specs/00-high.md, 4.3; in-docs/spec.md): the recipient, and therefore the
  owner of a personal list, never learns that a wish is reserved, by whom, or whether it was
  bought. This applies to every screen, message and notification.
- Account deletion (in-docs/spec.md, section 11) is a different feature and is not changed.

### Business entities

- **Owner:** the user who owns the wishlist; the only role allowed to delete it.
- **Other roles:** administrator, participant, gifter, anonymous visitor; none may delete.
- **Wishlist:** has a title and a state (active, archived, deleted); deletion moves it to the
  state "deleted", from which the owner can restore it during the retention window.
- **Confirmation:** a deliberate step before deletion that shows the list title and the
  consequences.
- **Result message:** the clear statement after deletion that the list was deleted and can be
  restored for a limited period.
- **Recently deleted:** the existing owner-only place where deleted lists wait for restoration.

### Functional requirements

1. **Finding the action.** In the settings of a wishlist the owner sees a clearly named action
   "Delete wishlist". It is visually separated from the ordinary settings (title, description,
   event) and marked as a destructive action, so it is not mistaken for "Save".
2. **Owner only.** The action is offered only to the owner of the list. An administrator, a
   participant, a gifter and an anonymous visitor do not see it. A deletion request made by
   someone who is not the owner is refused, the list stays exactly as it was, and the refusal
   does not reveal anything beyond what that person may already see.
3. **Confirmation before deletion.** Selecting "Delete wishlist" never deletes immediately. The
   user sees a confirmation that:
   - shows the exact title of the list being deleted (so the user knows which list it is);
   - warns about the consequences in plain words: the list disappears from everyone; its share
     and invitation links stop working; any reservations on it are cancelled;
   - makes exactly two promises about time and history, and no other: (a) the owner can restore
     the list from "Recently deleted" within the retention period, with the real number of days
     left (30 by default), and a restored list returns with its wishes and its «Подаренные»
     history but with new links and with cancelled reservations still cancelled; (b) when the
     retention period ends, the list is deleted permanently together with its «Подаренные»
     history and cannot be restored. The confirmation never says that the history is removed
     "immediately" or "at once";
   - uses the same text for personal and collaborative (shared) lists;
   - offers two clearly distinct choices: confirm deletion and cancel; the destructive choice is
     not the default focus.
4. **Cancel leaves everything unchanged.** Cancelling, closing the confirmation or leaving the
   screen without confirming does not change the list, its wishes, members, links or settings.
5. **Result after confirmation.** After the user confirms:
   - the list disappears from the owner's active lists and from every place where it was shown
     as available (home lists, the list screen itself);
   - the user sees a clear result message that names the list and says that it was deleted and
     can be restored within the retention period, and is taken to the home screen, where the
     list is no longer among the active lists and appears under "Recently deleted";
   - the result message is shown once and is not misleading if the operation fails (see 9).
6. **Restoration under existing rules.** A list deleted by its owner appears in "Recently
   deleted" immediately, can be restored by the owner under the existing rules (owner only,
   within the retention window, new share and invitation links, reservations stay cancelled),
   and is removed permanently after the window. The story does not change these rules.
7. **Other data unaffected.** Deleting one list does not change other lists of the owner or of
   anyone else, the owner's profile, settings, favorites of other lists, or notification
   settings. Wishes, members and history of the deleted list are not shown elsewhere in the
   product after deletion.
8. **Surprise secrecy.** The confirmation, the result message and any other text are identical
   for every list, whatever its reservations: they never state whether anything is reserved, how
   many reservations exist, who reserved or whether something was bought. The warning about
   cancelled reservations is generic ("any reservations are cancelled"). No new notification is
   sent to a recipient, owner or member that reveals reservations.
9. **Failure and repeat.** If deletion fails (network, list already changed, rights lost), the
   list remains as it was and the user gets a clear failure message and can retry; no "deleted"
   message is shown. Confirming twice, a second tap, or deleting an already deleted list does not
   produce errors, duplicate effects or a second result; the user ends in the same state.
10. **Which lists.** Deletion is offered for the owner's lists that can be changed in the
    settings, that is, active lists, including shared (collaborative) lists owned by the user.
    Archived lists are first restored from the archive (see Q&A, Q3).
11. **Languages and themes.** All visible and announced texts (action, confirmation, warning,
    buttons, result, failure) exist in Russian and English with the same meaning and follow the
    selected language; they are readable in the light, dark and Telegram themes.
12. **Accessibility and touch.** The action and the confirmation are reachable and operable by
    keyboard and by screen-reader users, who learn which list is about to be deleted and what the
    choices are; after the confirmation closes the user is not lost (they land on a screen where
    the next step is obvious); the destructive choice is distinguishable by more than color;
    touch targets are not smaller than the 44 px convention of the product; narrow phones (320 px and up) show everything without horizontal
    overflow, including long titles that wrap.

### Non-functional requirements and constraints

- Works the same in the Telegram Mini App and in a normal mobile browser.
- Privacy: no new personal data is shown, stored or sent; the title shown in the confirmation is
  the owner's own list title.
- Existing behavior of archiving, restoring from the archive, restoring from "Recently deleted",
  permanent purge after the retention window, account deletion and surprise secrecy remains
  unchanged; existing tests stay green apart from known pre-existing failures.
- The action must not make accidental deletion easy (not a one-tap control; separated from "Save"
  and "Cancel" of the settings form).
- Out of scope: changing the retention period; immediate permanent deletion; bulk deletion of
  several lists; deleting someone else's list as administrator; deleting archived lists directly;
  new notifications to members of a deleted list; a trash for individual wishes; changes to
  account deletion; emptying the whole "Recently deleted" section.

## User Stories

- As an owner, I find "Delete wishlist" in my list settings, so I can remove a list I no longer
  need.
- As an owner, I am asked to confirm with the list title and consequences, so I do not delete the
  wrong list by accident.
- As an owner, I can cancel and nothing changes, so I can safely look at the action.
- As an owner, after deleting I see a clear result and the list is no longer among my active
  lists, so I know it worked.
- As an owner, I can restore the deleted list for a limited time, so a mistake is not final.
- As an administrator, a participant or a gifter, I cannot delete someone else's list.
- As a recipient or owner of a personal list, I never learn from the deletion texts whether any
  gift was reserved.
- As a Russian or English speaking user, I see all texts in my language.

## Definition of Done

1. The owner finds a visually separated "Delete wishlist" action in the settings of their list;
   nobody else is offered it.
2. A confirmation shows the exact list title, the consequences (disappears for everyone, links
   stop working, reservations cancelled), the restoration period in days, and the rule that after
   the retention period the list and its «Подаренные» history are deleted permanently; restoring
   within the period returns the list with its history. It has distinct confirm and cancel
   choices and the same text for personal and collaborative lists.
3. Cancelling or closing the confirmation leaves the list unchanged.
4. After confirming, the list is not among the owner's active lists, the owner sees a clear
   result message and the list appears in "Recently deleted" with the days left.
5. A non-owner cannot delete the list by any means; a refused attempt leaves everything
   unchanged.
6. The owner can restore the deleted list under the existing rules (within the retention window,
   new links, cancelled reservations stay cancelled); after the window it is gone permanently.
7. Other lists and other user data are unchanged by a deletion.
8. No text of the feature reveals anything about reservations (state, number or people).
9. Failure and repeated confirmation behave as described: no false success, no duplicate
   effects.
10. Russian and English texts are equivalent; the feature is readable in all themes, accessible
    by keyboard and assistive technology, fully visible without horizontal overflow on a 320 px phone with 44 px touch targets.
11. An automated check reproduces the missing behavior first (fails before the change) and passes
    after it; existing tests for archive, restore and deletion remain green.

## Q&A

- **Why this change?** An owner has no way to remove a list they no longer need; stale lists
  clutter the home screen and the owner's control over the life cycle of their own lists is
  incomplete (Jira WISHENKA-295, epic WISHENKA-5). Deletion must be deliberate and understandable
  and, in line with the product principle of safe removal, reversible for a limited time.
- **What already exists?** Found in the product: the "deleted" state, owner-only rights to delete
  and restore, cancellation of reservations on deletion, hiding of deleted lists from everyone,
  the "Recently deleted" section with "Restore" and days left, 30-day retention and permanent
  purge afterwards, new links on restore. Missing: the visible action in the list settings with
  confirmation and result for the user (there is no screen element that starts the deletion).
  Today there is no user-visible way to start deletion.
- **Q1. Where is the action?** In the settings section of the list (the same place as title,
  description and event). Decision: the settings section is visible to the owner and to
  administrators of an active list, so the action is shown only to the owner there. Reason: the
  ticket says "in the settings of their wishlist" and the product allows only the owner to
  delete.
- **Q2. Does deletion mean immediate permanent removal or restorable deletion?** Decision:
  restorable deletion with the existing retention window. Reason: the ticket asks for
  restoration "within existing rules" where it exists, and it exists; specs/00-high.md states
  safe removal through archiving.
- **Q3. Can an archived list be deleted?** Decision (confirm with the product owner). Fact: the settings are shown only for active
  lists and the existing rules reject changes to an archived list, including deletion. Decision:
  keep the existing rule; an owner who wants to delete an archived list first restores it from
  the archive. Reason: the ticket does not ask for a change of archive rules; to be confirmed by
  the product owner if direct deletion from the archive is wanted (separate story).
- **Q4. What happens to the gifted history ("Подаренные")?** Fact: in-docs/spec.md 7.2 says it is
  removed permanently together with the deleted list. Fact in the product: the data of a deleted
  list is kept during the retention period and purged after it, so a restore within the period
  brings the history back. Decision: business rule "the history goes together with the list when
  the retention period ends; restoring within the period returns the list with its history". The
  confirmation makes exactly the two promises of requirement 3 (restorable within N days with
  history; permanent deletion of list and history after the period) and nothing about immediate
  removal, so Step 3 can test both. Reason: this is true to both the specification and the
  product.
- **Q5. Are members and gifters of a shared or published list notified?** Not defined by the
  ticket or the specification. Decision: no new notification in this story. Reason: any such
  notification risks revealing reservations and is a separate decision. Members simply no
  longer see the list.
- **Q6. What about reservations of gifters on the deleted list?** Fact: they are cancelled by
  the existing deletion rule and are not revived on restore. Decision: the warning mentions this
  generically and never by number or person. Reason: surprise secrecy; the owner of a personal
  list is the recipient.
- **Q7. Is the "Recently deleted" section changed?** No. It is the restoration place required by
  the ticket and already works; this story only guarantees that a list deleted by the new action
  appears there.
- **Q8. Where does the user land after deletion?** Decision: on the home screen of lists, with
  the result message. Reason: the deleted list screen is no longer available to anyone.
- **Q9. Does deleting a list affect favorites and viewing history of other users?** Fact: a
  deleted list is hidden from them like an unavailable list. Decision: no new behavior is
  required; their entries simply do not open the list.
- **Q10. Should the confirmation require typing the title?** Decision: no; showing the exact
  title with an explicit confirm button is enough and is consistent with the confirmations of the
  product. To be reconsidered only if the product owner wants a stronger guard.
- **Q11. Sources, and which backs which claim.**
  - Owner-only deletion and restoration: doc/dev/wishlists.md (permission matrix, line 502) and
    wishenka/wishlists/policy.py (`can_delete`, `can_restore_deleted`); not in the specification.
  - Settings and members managed by owner and administrator: in-docs/spec.md 4.4 and policy.py;
    participants manage wishes: in-docs/spec.md section 3.
  - Archive of lists: in-docs/spec.md 4.3 (owner) and policy.py `can_archive` (owner and
    administrator); archive of wishes: in-docs/spec.md 5.5.
  - Safe removal principle: specs/00-high.md 4.2 (wishes and archiving).
  - "Подаренные" removed with a deleted list: in-docs/spec.md 7.2; retention and purge:
    wishenka/wishlists/service.py, cleanup.py and doc/dev/wishlists.md.
  - Surprise secrecy: specs/00-high.md 4.3 and in-docs/spec.md; account deletion: in-docs/spec.md
    section 11; deleted-list restoration tests; Jira issue WISHENKA-295.
