# WISHENKA-316: One rule for restoring a deleted wishlist

## Goals

An owner who deletes a wishlist, looks at "Recently deleted", or restores a list must get one
answer: the list is still restorable, or the retention period has ended. The number of days the
owner is told must be that same period.

Today the product can decide this more than once. Deletion, restoration, the "Recently deleted"
list, the days shown before the owner confirms, and the later permanent removal can each carry
their own copy of the period. A missing setting can be filled, on its own, with a fixed 30
days. If those copies diverge, the owner can be promised a restore in one place and refused in
another, or shown a different number of days from the one that is applied.

This task keeps a single restorability rule and a single deletion action, so the Mini App and
every other way the owner deletes or restores a list stay in agreement. It comes from
WISHENKA-295 (debt items on deletion classification, retention arithmetic, and the days shown
to the owner). It is maintainability work. The owner-visible behavior that already matches
these rules stays as it is.

Implementation language: Python.

## User Stories

- As an owner, the days I am told about deletion and the days that decide whether I can still
  restore the list are the same configured period.
- As an owner, deleting, deleting again, restoring, and opening "Recently deleted" all agree on
  whether the list is still restorable.
- As an owner, deleting a list a second time while it is still restorable does not give me a
  new retention period.
- As an owner, once the period has ended I can no longer restore the list, and it no longer
  appears in "Recently deleted".
- As a person who is not the owner, I still cannot delete the list, and the refusal tells me
  nothing about whether the list exists.
- As an owner, the deletion result I already rely on stays the same, in Russian and in English,
  in the Mini App and in a plain mobile browser.

## Definition of Done

1. Deletion, a repeated deletion, restoration, "Recently deleted", the days the owner is told,
   and permanent removal after the period all use one restorability rule and one configured
   retention period.
2. With the product left at its usual setting, that period is 30 days. A configured period of
   another length is the period the owner is told and the period the rule applies.
3. A change to the period, or to when a deleted list is still restorable, takes effect for all
   of those together. The owner is left with one answer.
4. Confirming deletion still applies the existing deletion outcome once. A second confirmation
   while the list is still restorable does not delete it again and does not restart the period.
5. An unknown list and a caller who is not the owner still receive the same refusal, and the
   list stays unchanged.
6. After the period, the owner cannot restore the list, a further deletion does not restore it,
   and "Recently deleted" omits it until permanent removal.
7. Log messages and the names and fields of the events already recorded for deletion, refusal,
   listing deleted lists, and restore stay as they are.
8. The checks that already describe owner deletion keep passing, and the owner-visible deletion
   behavior they lock stays the same.

## Task Description

WISHENKA-295 gave the owner a deliberate way to delete their own wishlist and relied on the
retention rules the product already had. Those rules are still right. What is weak is that the
decision "can this deleted list still be restored?" and the act of deletion can be repeated
apart from each other, and the length of the period can be filled in separately, including with
a fixed 30 days, wherever a setting is missing.

The business need is one decision about restorability and one deletion action. The Mini App and
every other owner path then follow that decision. This task does not add a new lifecycle state,
does not change who may delete or restore, and does not change the promises already made to the
owner.

### Business entities

- **Owner:** the only person who may delete a wishlist and restore it from "Recently deleted".
- **Other people:** an administrator, a participant, a gifter, or an anonymous visitor. None of
  them may delete the list. A refusal does not reveal that the list exists.
- **Wishlist:** has a title and a state (active, archived, deleted). Deletion moves an owner's
  list to "deleted" and starts the retention period from that moment.
- **Retention period:** the single configured length of time a deleted wishlist can still be
  restored. The usual length is 30 days. Days left are counted from the deletion moment with
  this length.
- **Restorability:** a deleted wishlist is restorable while the deletion moment is still inside
  the retention period. Outside that period it is no longer restorable.
- **Deletion action:** the single act that marks the owner's list deleted, cancels its active
  and purchased reservations, hides it, and stops its share and invitation links.
- **Recently deleted:** the owner's list of their own deleted wishlists that are still
  restorable, with the days left.

### Functional requirements

1. **One restorability rule.** A deleted wishlist can be restored only while it is inside the
   retention period. Deletion of an already deleted list, restoration, "Recently deleted", the
   days the owner is told, and permanent removal all follow this rule.
2. **One retention period.** That period is the product's configured wishlist retention period.
   The usual configured length is 30 days. Every owner-facing use takes this configured length.
   A missing setting is filled from that same configured length, including the usual 30 days.
   No path keeps a private length that can disagree with the others.
3. **The days the owner sees.** The warning before deletion, the result after deletion, and the
   days left in "Recently deleted" are derived from this period and from the deletion moment.
   The next time the owner opens the product, all of those show the period then in effect.
4. **One deletion action.** When the owner confirms deletion of a list that is not yet deleted,
   one deletion action applies the whole existing outcome: the list becomes deleted, active and
   purchased reservations are cancelled, the list leaves the active lists, share and invitation
   links stop working, and the retention period starts from that deletion. The Mini App and any
   other path the owner can use to delete a list both end in that outcome.
5. **Repeating deletion.** Confirming again while the list is still restorable is a success for
   the owner and does not run the deletion action again. Reservations stay cancelled, links stay
   stopped, and the retention period keeps the original deletion moment.
6. **The period has ended.** When the list is deleted and the period has ended, the owner is
   told that it can no longer be restored. A further deletion does not restore the list and does
   not run the deletion action again. Restoration is refused on the same rule. The list stays
   until permanent removal.
7. **Who may delete.** Only the owner can delete. An unknown list and a person who is not the
   owner receive the same refusal. The list, its wishes, members, links, and reservations stay
   as they were. The refusal reveals nothing about whether the list exists.
8. **"Recently deleted" and restore.** The section lists only the owner's own deleted wishlists
   that are still restorable, with days left from the same period and the same deletion moment.
   Restore inside the period makes the list active again, issues new share and invitation links,
   and leaves cancelled reservations cancelled. The earlier links stay dead. Restore outside the
   period is refused under requirement 6.
9. **Permanent removal.** After the period, the existing cleanup removes the deleted wishlist
   for good, together with its wishes and its «Подаренные» history. Cleanup uses the same
   configured period as the restorability rule.
10. **Records stay.** The log messages already written for these outcomes, and the names and
    fields of the events already recorded, stay as they are. This includes deletion by the
    owner, a repeated deletion, a refusal for an unknown list, a refusal for a non-owner, listing
    of deleted lists, and restore.
11. **The rest of deletion stays.** Confirmation, cancel, the result message, surprise secrecy,
    Russian and English with the same meaning, themes, and the rule that no new notification is
    sent stay as WISHENKA-295 defined them. Archived lists are still restored from the archive
    before they can be deleted. Other lists and the owner's profile stay untouched. Account
    deletion stays a separate feature.

### Non-functional requirements

- During one visit the owner gets one period and one restorability answer from deletion,
  restoration, and "Recently deleted".
- The usual deletion, listing, and restore remain as quick as they are today for a single list.
- No new personal data is shown, stored, or sent. Surprise secrecy is unchanged: no text states
  whether anything was reserved, how many reservations exist, who reserved, or whether something
  was bought.
- A non-owner learns nothing new from a refused deletion.

### Constraints and assumptions

- WISHENKA-295 remains the source of the owner-visible deletion rules. This task binds those
  rules to one decision and one deletion action.
- The checks that already lock owner deletion keep passing. Where the product already matches
  this document, the owner's experience stays as it is.
- The retention period is a product setting. Its usual value is 30 days. It changes with the
  product configuration. An owner who already has the product open is covered on the next open,
  when every use of the period follows the new value together.
- Log wording that still says "restore" for a deletion that expired, a separate accessible name
  for the delete confirmation, focus after the period has ended, and a delete control on a plain
  web list screen are separate follow-ups (WISHENKA-318, WISHENKA-317, and an open product
  decision). Notices to gifters whose reservations were cancelled, and favorite or history rows
  that can reappear if the owner restores the list, stay with their existing follow-ups.
- Out of scope: changing the usual 30-day length; immediate permanent deletion; deleting several
  lists at once; deleting another person's list; deleting an archived list directly; emptying
  "Recently deleted"; account deletion; a trash for individual wishes.
- Assumption: "one deletion action" means the outcome of moving a list into the deleted state
  happens once. A later confirmation while the list is still restorable reports success and
  leaves that outcome and its original deletion moment in place.

## Q&A

- **Why is this needed?** The owner must be able to trust the retention promise. WISHENKA-295
  already defined it: the owner can restore a deleted list during the retention period, and
  after that the list is gone for good. That promise is currently decided in more than one
  place, and a missing setting can be replaced by a separate fixed 30 days. One rule and one
  deletion action keep the Mini App and every other owner path on the same answer. Source: Jira
  WISHENKA-316, from WISHENKA-295 debt on deletion classification, duplicated retention
  decisions, and the days shown to the owner. The debt is not a blocker.
- **What should stay the same?** Who may delete, what deletion does, the idempotent second
  delete that does not extend the period, the uniform refusal for a non-owner and an unknown
  list, "Recently deleted", restore with new links and cancelled reservations, permanent removal
  after the period, surprise secrecy, and the existing log messages and event fields.
- **What is the retention period?** The configured wishlist retention period. The usual
  configured length is 30 days, which is the length WISHENKA-295 already tells the owner.
  Another configured length replaces 30 days everywhere this task covers.
- **Does a second delete extend the period?** It does not. The period keeps the original
  deletion moment. The owner still gets a successful result while the list is restorable.
- **Do the records change?** They stay. Making the shared expiry log say "operation" rather
  than "restore" belongs to WISHENKA-318.
- **Does the plain web list screen gain a delete control?** That remains a separate product
  decision and is outside this task. The deletion action this task unifies is the one the owner
  already uses.
- **What was decided without a further product question?** The ticket already states the
  business need and says the current behavior and the existing deletion checks must remain. No
  new owner-visible rule was added. The usual period of 30 days is the period the product
  already uses when it is left unconfigured.
