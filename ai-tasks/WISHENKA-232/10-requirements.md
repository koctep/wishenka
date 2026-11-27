# WISHENKA-232: Notice history survives a repeated data upgrade

## Goals

An existing wishlist remembers which gift-receipt notices were already associated with a giver,
including notices whose delivery is still uncertain and must stay unresolved. Operators apply the
product data upgrade more than once: a restart, a recovery, or a second pass over a store that
already completed the upgrade. That second pass must finish, and the wishlist's notice history
must match what it was after the first successful pass.

The standing check `test_upgrade_is_repeatable` stops with a storage error during the second
upgrade, before it can confirm that stored history is unchanged. Until that pass completes,
operators cannot treat a repeated upgrade as safe, and the memory that a giver was already
considered for a receipt notice is at risk. This task restores that safety. It was found during
WISHENKA-128.

Implementation language: Python.

## User Stories

- As a **giver**, I want the service to keep the memory that I was already considered for a
  receipt notice, including a notice whose delivery is still uncertain, so a repeated data
  upgrade leaves that memory intact.
- As a **wishlist owner**, I want gift receipts already recorded, and which wishes are archived,
  to stay as they were after the first successful upgrade.
- As a **recipient**, I continue to see none of the giver's identity, reservation, or purchase
  status. This upgrade preserves stored history and leaves notice wording as it is.
- As a **product operator**, I want a second application of the data upgrade on an already
  upgraded wishlist to complete, with notice history unchanged.
- As a **maintainer**, I want
  `tests/test_gift_receipt_migration.py::test_upgrade_is_repeatable` to pass. The check promises
  that running the upgrade again leaves recorded receipts and archive state unchanged.

## Definition of Done

1. On a wishlist that already completed the current data upgrade, applying that upgrade again
   completes successfully.
2. Notice history is the same after the second pass: the same givers stay associated with the
   same receipt notices, including notices left uncertain.
3. Uncertain receipt notices stay uncertain and stay recorded. They remain ineligible for an
   automatic retry.
4. Gift receipts recorded by the first upgrade, and which wishes are archived, stay the same
   after the second pass. That comparison is what `test_upgrade_is_repeatable` performs.
5. `tests/test_gift_receipt_migration.py::test_upgrade_is_repeatable` passes.
6. The first upgrade of a legacy wishlist still records the same approximate receipts and the
   same archive normalisation as today.
7. Who may receive a receipt notice, the wording of that notice, and the rule that an uncertain
   send waits for an operator stay as they are.
8. The recipient still learns nothing about giver identity, reservation, or purchase status from
   this change.

## Task Description

### Problem

`tests/test_gift_receipt_migration.py::test_upgrade_is_repeatable` builds a legacy wishlist,
applies the data upgrade, then applies it again. The check exists so the second run leaves
stored gift receipts and archive state unchanged. The second upgrade currently stops with a
storage error while notice history is being carried forward, so the comparison never runs.

The business consequence is that notice history on an existing wishlist is not yet guaranteed
to survive a repeated upgrade, because the upgrade does not finish.

### Functional Requirements

1. A repeated upgrade of an already upgraded wishlist completes.
2. Notice history present after the first upgrade is still present after the second, with the
   same association of receipt, notice kind, and giver.
3. Uncertain receipt notices stay uncertain and stay in the history.
4. Recorded gift receipts and archive state are unchanged by the second pass.
5. The named check passes.

### Non-functional Requirements

- **Data safety:** A second upgrade leaves notice history, gift receipts, and archive state as
  they were after the first successful upgrade.
- **Operability:** Operators can re-run the upgrade on a store that already holds notice
  history, and the run completes.
- **Surprise:** Recipient-facing secrecy is unchanged.
- **Scope:** No new screen and no new delivery policy. The meaning of sent, skipped, failed,
  and uncertain stays as it is.

### Constraints and Assumptions

- The implementation language is Python.
- The required outcome is that the second upgrade finishes and history is unchanged. The wording
  of the upgrade step is left to a later design step.
- Rollback classification of revisions, covered by WISHENKA-128, stays as it is. This task makes
  the repeated forward upgrade succeed.
- User-facing wishlist, bot, and notification features stay as they are aside from the data
  upgrade completing safely a second time.
- The legacy first-upgrade outcome (approximate receipts and archive normalisation) stays as it
  is.

### Main Entities and Interactions

- **Wishlist:** A person's list of wishes that is already in use and already holds history.
- **Gift receipt:** The record that some quantity of a wish was received.
- **Notice history:** The memory that a giver was already tied to a receipt notice of a given
  kind, including notices whose delivery is uncertain.
- **Giver:** The person who may be told that a gift was received. Their place in notice history
  must survive a repeated upgrade.
- **Recipient:** The person the gift is for. This work keeps giver identity and reservation
  status hidden from them.
- **Operator:** The person who applies the data upgrade, including a second time.
- **Data upgrade:** The product's versioned update of stored wishlist data. This task requires
  that applying it again is safe for notice history.

## Q&A

- **Why is this task needed?** An existing wishlist's notice history must survive applying the
  data upgrade more than once. A second pass that stops with a storage error means operators
  cannot rely on the upgrade, and the memory of who was already considered for a receipt notice
  is unsafe.
- **What does the standing check prove?**
  `tests/test_gift_receipt_migration.py::test_upgrade_is_repeatable` proves that running the
  upgrade again leaves recorded gift receipts and archive state unchanged. Completing that
  second run is what lets notice history survive.
- **Who asked for the business outcome?** The task is debt found during WISHENKA-128. The
  required outcome is data safety for notice history on a repeated upgrade, with Python as the
  implementation language.
- **What stays in place for people using the product?** Notice wording, who may be notified, and
  the rule that an uncertain send waits for an operator. The recipient's view stays free of
  giver and reservation detail.
