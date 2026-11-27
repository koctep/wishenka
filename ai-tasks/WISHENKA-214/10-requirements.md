# WISHENKA-214: Dialog errors stay visible without mixing in gift receipt

## Goals

A wishlist author who edits a wish or confirms archive must see why the
product refused the action. The message belongs in the dialog they already
have open, so the screen does not look as if the button did nothing.

Recording that a gift was received is a separate moment in the same
lifecycle. When the product refuses that receipt, the author must see the
receipt flow's own feedback and the list must update the way that flow
already does. Shared dialog handling must leave those refusals alone.

The product also keeps a standing check that shared page behavior contains
no gift-receipt reference. That check protects a boundary: gift-receipt
rules stay in the receipt flow, and they do not leak into behavior that
every page shares. The reported failure of
`test_inline_script_is_unchanged_and_free_of_receipt_code` is that shared
dialog handling mentions the gift-receipt refusal so it can step aside, and
the check treats that mention as a gift-receipt reference.

Both outcomes have to hold together. Authors keep clear dialog errors.
Refused receipts keep their own feedback. The standing check stays green.
This is debt on the gift lifecycle (parent epic WISHENKA-21), found while
that lifecycle was being built. It is not a new screen and not a change to
who may edit, archive, or record a receipt.

Implementation language: Python.

## User Stories

- As a **wishlist author** (owner, administrator, or member), when I save
  an edit and the product refuses it, I see the reason in the edit dialog
  so I know the wish was not saved and what to correct.
- As a **wishlist author**, when I confirm archive and the product refuses
  it, I see the reason and the list stays consistent with what was actually
  archived, so I am not left unsure whether the wish moved.
- As a **wishlist author** recording, adjusting, or cancelling receipt of a
  gift, when the product refuses that action, I see the receipt flow's own
  message and list update. Shared dialog handling does not replace or hide
  that feedback.
- As a **wishlist author** reordering wishes, and as a **giver** updating a
  reservation, I keep the feedback those flows already show. This task does
  not change those moments.
- As a **recipient**, I still never learn who reserved or bought a wish, or
  that a reservation exists, from an edit, archive, or receipt message.
- As a **maintainer**, I can trust the standing check that shared page
  behavior carries no gift-receipt reference, so receipt rules cannot
  silently become part of every page.

## Definition of Done

1. **Edit dialog.** Saving an edit the product refuses (for example a
   quantity below what was already received, a wish that is temporarily
   busy, an archived wishlist, or a wish that is no longer available) shows
   the existing reason in the edit dialog. Entered values stay available
   where the dialog stays open. The button does not fail in silence.
2. **Archive dialog.** Confirming archive when the product refuses shows
   the existing reason and leaves the list, the archive, and the gifted
   section consistent with the outcome. Nothing is shown as archived unless
   it was archived.
3. **Gift receipt left alone.** A refused receipt, including the case where
   nothing remains to receive, still shows the receipt flow's own notice
   and list update. Shared dialog handling does not take that response
   over, swallow it, or replace it with a generic dialog error.
4. **Neighboring flows.** Reordering wishes and reservation updates keep
   the messages and list updates they already have.
5. **Standing check.** The check that shared page behavior contains no
   gift-receipt reference passes. The reported failure is
   `test_inline_script_is_unchanged_and_free_of_receipt_code`: it finds a
   gift-receipt reference inside the shared behavior that steps aside for a
   receipt refusal. The same boundary stays green if that check now lives
   under a successor name.
6. **Surprise and roles.** Messages still hide giver identity, reservation,
   and purchase status from the recipient. Who may edit, archive, or record
   a receipt is unchanged.
7. **Languages.** The Russian and English messages already used for these
   refusals remain the messages the author sees.

## Task Description

### Programming language

Python.

### Problem

Edit and archive dialogs must surface a refusal inside the open dialog.
That shared behavior has to recognize a gift-receipt refusal and leave it
to the receipt flow. The standing integrity check requires the same shared
behavior to stay free of any gift-receipt reference. Naming the refusal in
order to step aside is what the reported check rejects. Until both sides
agree, either authors lose a visible dialog error, or a refused receipt can
be handled by the wrong flow, or the integrity check stays failed.

### Functional requirements

1. Shared dialog handling shows the existing refusal inside the edit dialog
   and the archive dialog when the refusal belongs to that dialog.
2. Shared dialog handling leaves a gift-receipt refusal to the receipt
   flow, which keeps its own notice and list update.
3. Wish reordering and reservation updates keep their current feedback.
4. The standing check that shared page behavior has no gift-receipt
   reference is green, including the reported check named above.
5. Surprise secrecy and the existing role rules for edit, archive, and
   receipt stay as they are.

### Non-functional requirements

- Dialog and receipt feedback stay immediate on the same action. This task
  does not add a new wait or a second confirmation.
- Refusal text stays the existing Russian and English copy. No giver name,
  reservation, or purchase fact is added to a message the recipient can see.
- The integrity check remains an automated guard that fails if gift-receipt
  rules appear in shared page behavior.

### Scope

In scope:

- Agreement between visible edit and archive errors, receipt-flow feedback
  for a refused receipt, and the standing receipt-free check on shared page
  behavior.
- Preservation of reorder feedback, reservation feedback, and surprise
  secrecy on these paths.

Out of scope:

- New receipt, archive, reorder, or reservation rules.
- A new app-wide notification style for unrelated failures.
- A visual redesign of the edit, archive, or receipt dialogs.
- Changing who may edit a wish, archive it, or record that it was received.

### Main entities

- **Wishlist.** A list of wishes. It may be active or archived. An archived
  list refuses further edits and new receipts.
- **Wish.** One wanted gift, with a requested quantity and a received
  quantity. Authors edit it, archive it, and record receipt against it.
- **Gift receipt.** The author's record that some or all of a wish was
  received. A refusal leaves that record unchanged and explains why.
- **Edit dialog and archive dialog.** The surfaces where an author changes
  a wish or confirms archive, and where a refusal of that action must be
  readable.
- **Receipt flow.** The separate surface and feedback for recording,
  adjusting, or cancelling a receipt. Its refusals are not dialog errors
  of the edit or archive dialog.
- **Shared page behavior.** Behavior every Mini App page uses to present
  dialog errors. It must show those errors and must not carry gift-receipt
  rules.
- **Recipient and giver.** The recipient must not learn reservation or
  giver facts from these messages. The giver's reservation feedback is
  unchanged by this task.

### Constraints and assumptions

- The product already has the dialog messages and the receipt messages.
  This task keeps both visible in the right moment. It does not invent new
  reasons.
- "Nothing remains to receive" is a receipt refusal. It stays on the
  receipt flow even when the author reached it while archiving.
- The standing check is part of the product contract, not an optional
  report. Making it green by dropping dialog errors, or by letting shared
  behavior absorb receipt rules, does not complete the task.
- How the two obligations are reconciled is decided in a later step. This
  document does not choose a mechanism.

## Q&A

- **Q: The report describes a failing check and a gift-receipt mention
  inside shared page behavior. What is the business reason?**
  **A:** Authors must see why an edit or an archive was refused, in the
  dialog they are using. A refused gift receipt must keep the receipt
  flow's own feedback. Shared page behavior must stay free of gift-receipt
  rules so that split can be checked. The check is red because stepping
  aside for a receipt refusal currently counts as a gift-receipt reference.
  Both the visible outcomes and the green check are required.

- **Q: Should gift-receipt refusals be shown by the shared dialog instead?**
  **A:** No. Receipt feedback stays on the receipt flow. Shared dialog
  handling only shows refusals that belong to edit and archive, and it
  leaves receipt refusals alone.

- **Q: Do the refusal rules change?**
  **A:** No. The same actions are refused for the same reasons, to the same
  roles, with the same Russian and English text. Surprise secrecy is
  unchanged.

- **Q: Is a new notification style part of this task?**
  **A:** No. Existing dialog and receipt feedback is enough. A general
  notification style for other failures is a different effort.
