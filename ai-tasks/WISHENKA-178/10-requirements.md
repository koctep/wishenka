# WISHENKA-178: Bounded Retention for Bot Capture Message Ordering

## Goals

Limit how long the system retains per-conversation message-ordering state used by the Telegram bot
wish-capture flow, so user conversation metadata is not stored indefinitely after a user stops
using the flow, while preserving reliable protection against delayed, out-of-order, and replayed
messages for active and recently active conversations.

The implementation language is **Python 3.12+**.

## User Stories

- As a **bot user**, I want my conversation ordering metadata to be retained only as long as
  needed for reliable wish capture, so personal conversation identifiers are not kept forever when
  I am inactive.
- As a **bot user in an active capture flow**, I want delayed or repeated messages from earlier in
  my conversation to remain ignored, so my current draft is not overwritten or duplicated.
- As a **user deleting my account**, I want all of my bot capture state—including any remaining
  message-ordering records—to be removed immediately upon account deletion without waiting for
  retention expiry.
- As a **service operator**, I want stale ordering records to be cleaned up automatically in bounded
  increments, so stored state does not grow without bound over time.

## Definition of Done

1. A bounded retention period is defined and enforced for bot capture message-ordering records,
   strictly longer than the draft lifetime so that expiring a draft does not immediately discard
   ordering protection.
2. During the retention window, a delayed or replayed message older than the latest recorded
   message in that conversation is still rejected/ignored and cannot become current again or
   overwrite a newer draft or active edit.
3. Ordering records for active conversations (conversations with an active draft or recent capture
   activity) are preserved and refreshed on new activity; cleanup never removes ordering state for
   an active conversation.
4. Once a conversation has been inactive beyond the retention period (with no active draft), its
   ordering record becomes eligible for automatic cleanup and is removed in bounded batches.
5. After an expired ordering record is cleaned up, sending a new message in that private
   conversation works normally and establishes a fresh ordering baseline.
6. Account deletion (`WISHENKA-35`) continues to immediately remove all bot capture ordering state
   for the deleted user regardless of whether the retention period has elapsed, and retention
   cleanup remains compatible with account deletion.

## Task Description

### Functional scope

In the Telegram bot wish-capture flow (`WISHENKA-28`), the system tracks the latest processed
message per private conversation to guard against out-of-order, delayed, and redelivered updates.
Currently, this ordering state has no expiration policy and persists indefinitely unless the user
deletes their account.

This task establishes a finite retention policy for that ordering state:
- **Retention & refresh:** Ordering state has a defined lifetime that is renewed when new capture
  activity occurs in the conversation.
- **Late-delivery protection:** Deleting a draft upon draft expiry must not immediately erase the
  ordering watermark; the watermark must outlive the draft for a reasonable safety window to block
  delayed or replayed messages from resurfacing as current drafts.
- **Active conversation safety:** Active drafts and ongoing field-editing interactions must never
  lose their ordering watermark during cleanup.
- **Automatic cleanup:** Expired ordering records are purged periodically without requiring user
  intervention or account deletion.
- **Account deletion coordination:** Account deletion (`WISHENKA-35`) must still purge the user's
  ordering state immediately on deletion, independent of retention expiry.

### Non-functional requirements

- **Data minimization & privacy:** Conversation ordering metadata (user/chat/message identifiers)
  is not retained indefinitely for inactive users.
- **Correctness under concurrency & redelivery:** Enforcing retention and cleanup must not weaken
  ordering guarantees for concurrent updates, retries, or delayed Telegram deliveries.
- **Bounded operational impact:** Cleanup runs in bounded work units so purging accumulated
  expired records does not degrade responsiveness for active users.
- **No user-facing regression:** Existing Russian and English bot capture prompts, draft editing,
  saving, cancellation, and error handling remain unchanged for normal user interactions.

### Constraints and assumptions

- **Language:** Python 3.12+.
- **Upstream context:** Follow-up from `ai-tasks/WISHENKA-28/60-tech-debt.md`; coordinated with
  account deletion scope in `WISHENKA-35`.
- **Out of scope:** Changing the wish-draft lifetime itself, altering Telegram webhook/polling
  delivery semantics, or changing user-facing copy for normal capture flows.
- **Design boundary:** Exact retention duration, storage representation, and cleanup scheduling
  mechanism are deferred to Step 2 (Architecture).

### Business entities

- **Bot User:** A Telegram user interacting with the bot in a private conversation.
- **Private Conversation:** A one-to-one chat between a Bot User and the bot where wish capture
  occurs.
- **Capture Draft:** An unsaved proposed wish with its own finite lifetime, editable and savable by
  the user.
- **Message Ordering Watermark:** The per-conversation record of the latest processed capture
  message used to reject older, delayed, or replayed messages.
- **Retention Window:** The bounded period after the last capture activity during which the
  Message Ordering Watermark is preserved before becoming eligible for cleanup.

### Scenarios

1. **Late delivery after draft expiry:** A user creates a draft and lets it expire without saving.
   Within the ordering retention window, a delayed or replayed older message arrives; it is ignored
   rather than reviving an obsolete draft.
2. **Active conversation during cleanup:** A user has an active draft or is actively editing a
   field when periodic cleanup runs; the conversation's ordering watermark is preserved and
   subsequent messages continue to be ordered correctly.
3. **Inactive conversation cleanup:** A user stops using the bot capture flow and remains inactive
   past the retention window; periodic cleanup removes the stale ordering watermark. When the user
   later sends a new message, a fresh watermark is recorded and capture works normally.
4. **Account deletion before retention expiry:** A user with an existing ordering watermark deletes
   their account (`WISHENKA-35`) before the retention window expires; their ordering watermark is
   removed immediately as part of account deletion.

## Q&A

- **Why is this needed?** To prevent indefinite retention of user conversation metadata and
  unbounded growth of ordering records while keeping protection against delayed or replayed
  Telegram messages.
- **Why not delete the ordering watermark as soon as a draft expires?** Because a delayed or
  replayed message from before draft expiry could arrive shortly afterward; without the watermark,
  that old message could be treated as a new, current message.
- **How does this relate to `WISHENKA-35`?** `WISHENKA-35` removes user data immediately upon
  account deletion. This task covers bounded retention for users who do *not* delete their account,
  and must remain fully compatible with immediate removal during account deletion.
