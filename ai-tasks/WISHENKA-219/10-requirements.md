# WISHENKA-219: Complete a purchased promise after full receipt

## Goals

Let a giver explicitly finish a purchased promise after the wish has been fully received. This
keeps the giver's active reservations meaningful, releases the units held by a finished promise,
and stops receipt-related notifications that no longer require the giver's attention. Receipt
alone must not imply that the giver personally delivered the gift.

## User Stories

- As a giver with a purchased promise on a fully received wish, I can mark my own promise as
  completed so it no longer appears as active work.
- As a giver with an intended, unpurchased promise, I can still cancel or reduce it, or mark it
  purchased before completing it, without falsely claiming completion directly.
- As a recipient or author, I can manage receipt without learning who promised a gift or whether
  anyone purchased or completed a promise.

## Definition of Done

1. In My Reservations, the giver can choose an explicit Complete / Gift Delivered action for
   their own open purchased promise when its wish is fully received. Cancellation remains
   available according to the existing rules. Receipt alone never completes a promise.
2. A successful action closes that promise as Completed and releases its occupied units. The
   completed promise no longer counts as open when calculating availability or the number of
   distinct wishes with active promises. Fully received wishes remain unavailable for new
   promises unless the receipt state later changes under existing rules.
3. A completed promise is not treated as an active promise in My Reservations; its completed
   status is distinguishable from cancellation wherever the promise is presented.
4. An intended promise cannot be completed directly, including when the wish is fully received.
   Its giver may reduce or cancel it or mark it purchased under existing rules. A purchased
   promise on a partially received or unreceived wish cannot be completed through this action.
5. Only the promise's giver may complete it. Anonymous visitors, recipients, authors and other
   givers cannot complete someone else's promise, including by invoking an action directly.
6. Attempts against a missing, already closed, no-longer-purchased or no-longer-fully-received
   promise do not complete it or change any other promise. A repeated completion does not release
   units twice or create extra side effects. The giver receives a clear outcome.
7. Receipt and undo-receipt notifications apply only to open promises. After completion, the
   application does not send a receipt or undo-receipt notice for that promise, including one
   still awaiting submission to the delivery provider. Other eligible open promises retain their
   existing notifications. A notice already accepted by the provider before completion may be
   displayed later; its display time is outside the application's control.
8. Completing one promise does not alter receipt records, the requested quantity, or any other
   giver's promise. Subsequent receipt corrections do not silently reopen a completed promise.
9. A concurrent change to receipt or promise status is checked against the current state when
   completing; an action whose eligibility no longer holds does not succeed. Concurrent or
   repeated actions cannot release the same units more than once.
10. Completion and its outcome do not reveal promise existence, quantity, purchase status or
    giver identity to recipients or authors who lack permission to see that information.
11. The completion action and its user-facing result are available in both supported languages,
    English and Russian, consistent with the giver's selected language.

## Task Description

The product currently records receipt independently of a giver's promise. Full receipt therefore
does not automatically close an open purchased promise, and the giver needs a deliberate way to
finish it. This task covers the completion action, its eligibility, closed-state effects, active
counts and receipt-notification behavior. It does not change the receipt workflow, automatically
complete promises, change cancellation rules, or introduce shared purchases.

The implementation language is Python. Existing Mini App access and privacy rules, notification
preferences, and supported languages remain in force. Completion should remain reliable when a
giver acts on an outdated view or multiple actions occur at once; the operation must not produce
partial business outcomes.

### Business entities

- **Giver:** the person who created and manages their own promise.
- **Wish:** a requested gift with a requested quantity and receipt progress; it is fully received
  when its received quantity reaches the requested quantity.
- **Promise:** a giver's quantity commitment, which can be intended, purchased, cancelled or
  completed. Intended and purchased promises are open; cancelled and completed promises are closed.
- **My Reservations:** the giver's view and its count of distinct wishes with open promises.
- **Receipt notice:** a personal notice about a receipt or an undo of receipt for an open promise.

## Q&A

- **Why does a purchased promise need an explicit completion action?** Receipt may be recorded
  independently of any particular giver. The giver, rather than the recipient, decides when their
  own commitment is finished, preventing stale active counts and irrelevant later notices.
- **Does full receipt alone complete a promise?** No. The giver must choose the action.
- **Can an unpurchased promise be completed?** No. The giver may first mark it purchased, or
  instead reduce or cancel it under the existing rules.
- **Does releasing units make a fully received wish bookable?** No. Availability still accounts
  for received units and remains zero while the wish is fully received.
- **What happens to a notice already sent before completion?** A notice accepted by the delivery
  provider before completion may appear later. Notices still awaiting submission are suppressed.
- **Sources:** [Product specification, sections 6.4 and 7.3](../../in-docs/spec.md), and
  [WISHENKA-154 technical debt](../WISHENKA-154/60-tech-debt.md).
