# WISHENKA-60: Reliable Giver Notifications for Gift and Reservation Lifecycle Events

## Goals

When a giver reserves a wish or marks a reservation as purchased, they commit to buying a real-world
gift based on the current state of the wishlist. Later, the wishlist owner or a collaborator may
change the lifecycle state of that wish or wishlist—for example, by recording that the gift has
already been partially or fully received, archiving a wish that still has open reservations,
restoring or editing a reserved wish, or archiving, restoring, or updating the wishlist itself.

From a business perspective, this task is needed so that:

- Givers holding open reservations are reliably and proactively notified in Telegram whenever a
  gift or wishlist lifecycle change affects their reservation, preventing wasted purchases and
  orphaned reservations.
- Recording a gift receipt, archiving a wish, or updating a wishlist never slows down, fails, or
  rolls back because Telegram is temporarily unreachable, rate-limited, or blocked by a recipient
  of the notification.
- Conversely, if a gift or wishlist change itself is rejected or fails, no false notification is
  ever sent to givers or collaborators.
- The gift recipient's surprise is strictly protected under all role combinations and subsequent
  lifecycle changes, so a recipient never learns about reservations, purchases, or gift-receipt
  notifications for their own wish.

## User Stories

- As a giver with an open (planned or purchased) reservation, I want to receive a Telegram
  notification when a wishlist author marks the wish as partially or fully received—even if the
  author immediately archives the remaining unreceived units—so that I can review, adjust, or
  cancel my reservation without buying a duplicate gift.
- As a giver with an open reservation on a wish, I want to receive a Telegram notification when the
  wish is archived, restored, or updated, or when its parent wishlist is archived, restored, or
  updated, so that I know whether my reserved gift is still wanted and can manage my commitment.
- As a wishlist owner or collaborator, I want my actions (marking a gift received, archiving or
  restoring a wish, editing a wish or wishlist, or changing collaborator roles) to complete
  immediately and reliably regardless of whether Telegram message delivery to givers succeeds, is
  delayed, or fails.
- As a giver who holds multiple reservations on the same wish or within the same wishlist, I want
  to receive at most one notification per lifecycle event rather than duplicate messages for each
  reservation entry.
- As a giver, I want my global and per-wishlist notification preferences to be respected both when
  an event occurs and right before a message is sent, so that turning off a notification category
  stops pending and future messages of that category.
- As a wish recipient (whether the owner of a personal wishlist or the designated recipient of a
  wish on a collaborative wishlist), I must never receive any notification triggered by a
  reservation, purchase, or gift receipt on my own wish, even if my role or the wish's designated
  recipient changes before delivery.
- As a service operator, I want completed and skipped notification records to be cleaned up after
  their retention period without losing protection against duplicate notifications, and I want
  ambiguous delivery outcomes held safely without automatic duplicate resends.

## Definition of Done

1. **Atomic coupling of lifecycle changes and notification intents**:
   - Recording a partial or full gift receipt, archiving or restoring a wish, updating a wish,
     archiving or restoring or updating a wishlist, changing collaborator membership or roles, or
     performing an opted-in own-reservation change records the corresponding notification intents
     as part of the same atomic business operation across all supported user and application entry
     points.
   - If the business operation is rejected or aborted, no notification intent is recorded or sent.
   - Once the business operation succeeds, the recorded notification intents survive service
     restarts until processed.
2. **Complete giver notification coverage across gift and wishlist lifecycle events**:
   - **Gift receipt**: Each distinct giver holding an open (planned or purchased) reservation on
     the wish at the moment of receipt (excluding the wish recipient) is queued for one gift-receipt
     notification per receipt act. If a wish is partially received and its remaining unreceived
     units are subsequently archived before the notification is sent, the pending gift-receipt
     notification remains eligible and is delivered to the giver.
   - **Wish lifecycle changes**: When a wish is archived, restored, or updated, each distinct
     eligible collaborator and each distinct eligible giver holding an open reservation on that
     wish (excluding the actor) is queued for one notification describing the change.
   - **Wishlist lifecycle and membership changes**: When a wishlist is archived, restored, or
     updated, or when its collaborator membership or member roles change (through any supported
     service or web/API flow), each distinct eligible collaborator and—for wishlist archive,
     restore, and update events—each distinct eligible giver holding an open reservation on any
     wish in that wishlist (excluding the actor) is queued for one notification.
3. **Surprise Invariant and recipient exclusion under role changes**:
   - The recipient of a wish (the owner on a personal wishlist, or the designated recipient on a
     collaborative wishlist) is never queued for or sent a gift-receipt notification, an
     own-reservation confirmation, or any notification whose eligibility derives from holding a
     reservation on that wish.
   - If a user is not a collaborator on the wishlist (or their collaborator membership was removed)
     and they are or become the recipient of the wish before delivery, any pending notification
     whose eligibility relied on a reservation on that wish is suppressed before sending.
   - Notification messages for gift receipt and wish or wishlist lifecycle events never contain
     reserved or received quantities, other givers' identities, purchase statuses, or secret access
     links.
4. **Live eligibility, preference precedence, and verified bot reachability**:
   - Before sending any queued notification, the system re-verifies current eligibility: the user
     must have an active verified private bot chat, must still have required access or an eligible
     open reservation (where applicable), must not be excluded as the wish recipient, and must have
     the relevant notification category enabled.
   - A per-wishlist notification preference overrides the user's global preference for that
     wishlist; when neither is set, the category default applies (gift-receipt, wishlist-change,
     and reminder notifications enabled by default; own reservation-change confirmations disabled
     by default unless explicitly enabled by the actor).
5. **Asynchronous, non-blocking delivery and failure isolation**:
   - Notification delivery runs asynchronously outside the user's gift or reservation action.
   - Provider rate limits, temporary failures, permanent rejections (such as a blocked bot chat),
     or ambiguous send outcomes never fail, delay, or roll back the completed gift receipt,
     archival, or reservation action, and never block delivery to other users.
   - Transient failures are retried with bounded attempts and backoff; ambiguous outcomes (such as
     network timeouts after a send request is issued) are quarantined without automatic duplicate
     resending.
6. **Retention and deduplication integrity**:
   - Background maintenance purges terminal (delivered, skipped, and permanently failed)
     notification records across both gift-receipt and lifecycle/reminder notification queues once
     they pass the configured retention age, while preserving deduplication guarantees and keeping
     pending, in-progress, and uncertain records intact.
7. **Automated verification**:
   - Automated tests verify transactional rollback and commit persistence, gift-receipt delivery
     when a partially received wish is subsequently archived, wish and wishlist lifecycle
     notifications (including archive, restore, settings update, and role change flows) for givers
     with open reservations, recipient exclusion when roles change before send, non-blocking
     behavior under delivery failures, and retention cleanup across notification queues.

## Task Description

### Problem and business context

In a wishlist service, reservations and owner actions happen independently over time. A giver may
reserve a gift weeks before an occasion. If the owner later receives the gift from someone else,
archives the wish because they no longer want it, edits the wish details, or archives/restores the
entire wishlist, the giver needs timely notice in Telegram so they do not buy an unwanted or
duplicate item.

Earlier work established gift-receipt notifications and shared wishlist notifications, but several
lifecycle and consistency requirements remain to make reservation-related notifications complete and
uniform:

- Archiving the remaining unreceived part of a partially received wish must not cancel or suppress
  a pending gift-receipt notification for the units that were already received.
- Givers holding open reservations on wishes in a wishlist must be notified consistently not only
  when the wishlist is archived, but also when the wishlist is restored or updated, and all
  wishlist update and collaborator role-change flows must record their corresponding lifecycle
  events.
- A user whose only relationship to a wish is a reservation must never receive a notification if
  they are or become the wish's recipient before the message is delivered.
- Terminal notification records across all notification queues must follow a consistent retention
  cleanup policy so operational history does not grow without bound.

### Programming language

- **Python 3.12+**

### Scope and system boundaries

- **In scope**:
  - Atomic creation of notification intents for gift lifecycle and reservation-affecting events
    (gift receipt, wish archive/restore/update, wishlist archive/restore/update, collaborator
    membership/role changes, and opted-in own-reservation confirmations).
  - Audience selection and live pre-send eligibility rules for givers with open reservations,
    collaborators, and wishlist owners, including strict recipient exclusion under role changes.
  - Preservation of pending gift-receipt notifications when a partially received wish is later
    archived.
  - Asynchronous background dispatch, rate limiting, retry with backoff, permanent-failure handling,
    and uncertain-delivery quarantine.
  - Retention cleanup of terminal notification records across all notification queues.
- **Out of scope**:
  - User interface screens in the Mini App for editing notification settings (owned by
    `WISHENKA-34`).
  - External metrics exporters such as Prometheus or OpenTelemetry (owned by `WISHENKA-84`).
  - Reversing or undoing a recorded gift receipt (owned by `WISHENKA-153`).
  - Full account and personal-data erasure flows (owned by `WISHENKA-35`).

### Functional requirements

- **FR-1 (Atomic intent recording)**: Every supported gift lifecycle or wishlist mutation that
  completes successfully must record its notification intents in the same atomic operation. Any
  mutation that fails validation, authorization, or persistence must leave zero notification
  intents behind.
- **FR-2 (Gift receipt notification durability across partial archival)**: Recording a partial or
  full gift receipt queues at most one gift-receipt notification per distinct eligible giver with
  an open (planned or purchased) reservation on that wish. If the wish is partially received and
  subsequently archived while its receipt notification is still pending, the receipt notification
  must still be delivered (provided the wishlist is not deleted, the giver is not the wish
  recipient, and the giver's notification preference permits it).
- **FR-3 (Wish and wishlist lifecycle notifications for givers with open reservations)**:
  - Archiving, restoring, or updating a wish notifies eligible collaborators and givers holding
    open reservations on that wish, excluding the actor.
  - Archiving, restoring, or updating a wishlist notifies eligible collaborators and givers holding
    open reservations on any wish in that wishlist, excluding the actor.
  - Adding, removing, or changing the role of a collaborator on a wishlist through any supported
    flow notifies eligible participants, excluding the actor.
- **FR-4 (Strict surprise protection and recipient exclusion)**:
  - A wish recipient must never be notified about reservations, purchases, cancellations, or gift
    receipts for their own wish.
  - A reservation on a wish must never grant notification eligibility to a user who is the
    recipient of that wish at the time the event is recorded or at the time the notification is
    sent.
  - Notification messages must omit reserved quantities, received quantities, other givers' names
    or identifiers, purchase statuses, and secret capability tokens.
- **FR-5 (Preference hierarchy and live verification)**:
  - Each notification is governed by its category preference (gift-receipt, wishlist-change,
    reminder, or own reservation-change notifications), with per-wishlist preferences overriding
    global user preferences.
  - Eligibility, preferences, and verified private-chat reachability are checked before sending;
    ineligible pending notifications are marked skipped and are not sent.
- **FR-6 (Decoupled delivery, retry, and uncertain quarantine)**:
  - Delivery failures, throttling, or timeouts in the messaging provider never cause the
    originating gift receipt, wish archival, or reservation action to fail.
  - Definite retryable errors are retried with bounded attempts and backoff; permanent rejections
    mark the notification failed and deactivate unreachable bot destinations; ambiguous outcomes
    transition the notification to an uncertain state awaiting explicit operator resolution.
- **FR-7 (Retention cleanup of terminal notifications)**:
  - Periodic background cleanup removes terminal (delivered, skipped, and permanently failed)
    notification records older than the configured retention period across both gift-receipt and
    service/lifecycle notification queues, without removing pending, in-progress, or uncertain
    records and without allowing duplicate receipt notices.

### Non-functional requirements

- **Reliability and durability**: Notification intents recorded by a committed user action persist
  across process restarts until settled.
- **Non-blocking responsiveness**: User-facing gift receipt, wish archival, wishlist management,
  and reservation actions perform no live network calls to Telegram during the user transaction.
- **Privacy and log hygiene**: Operational logs and diagnostic outputs never expose bot tokens,
  capability tokens, chat message texts, or personal user identifiers.
- **Localization**: Notification messages are rendered in English for users with an English
  language preference and in Russian otherwise, with titles safely truncated to bounded lengths.
- **Bounded resource usage**: Background queue claiming, rate limiting, and retention cleanup
  operate in bounded batches without blocking concurrent user actions during network delivery.

### Constraints and assumptions

- External message delivery over network APIs cannot guarantee mathematical exactly-once delivery
  when a network connection drops after a request is sent; therefore, ambiguous delivery attempts
  must be quarantined rather than automatically resent.
- Users can receive Telegram notifications only after they have interacted with the bot in a
  private chat so that a verified destination exists.
- Gift receipt remains independent of reservation status: notifying a giver about a gift receipt or
  wish archival never automatically cancels, modifies, or completes the giver's reservation.

### Main business entities

- **Wishlist and Wish**: The gift list and individual gift item whose lifecycle changes (creation,
  update, partial/full receipt, archival, restoration, deletion) may affect collaborators and
  givers.
- **Reservation**: A giver's open (planned or purchased) or cancelled commitment to provide one or
  more units of a wish.
- **Gift Receipt**: A wishlist author's dated record that one or more units of a wish were received
  in real life.
- **Notification Intent**: A durable record representing a pending message to a specific user about
  a specific gift or wishlist lifecycle event, progressing through pending, in-progress, delivered,
  skipped, permanently failed, or uncertain outcomes.
- **Notification Preference**: A user's global or wishlist-specific setting controlling whether a
  given notification category is enabled.
- **Verified Bot Destination**: Proof that a user has an active private conversation with the
  Telegram bot capable of receiving notifications.

### User scenarios

1. **Wish archived while reserved by a giver**:
   - Giver A holds an active reservation on a wish in Owner O's wishlist.
   - Owner O archives the wish.
   - The archival succeeds immediately, and a notification intent for Giver A is recorded in the
     same operation.
   - The background dispatcher verifies that Giver A still holds the open reservation, has not
     disabled wishlist-change notifications, and has an active bot chat, then sends Giver A a
     localized Telegram notification that the wish was archived.
2. **Partial gift receipt followed immediately by archiving the remaining units**:
   - A wish requests 3 units; Giver A has reserved 2 units.
   - Owner O records receipt of 1 unit, and before the background dispatcher runs, Owner O archives
     the remaining 2 unreceived units of the wish.
   - When the background dispatcher runs, Giver A still receives the gift-receipt notification
     informing them that the wish was marked received so they can check their reservation, as well
     as the wish-archived notification.
3. **Wishlist archived and later restored with open reservations**:
   - Giver A (who is not a collaborator) holds an open reservation on a wish in Owner O's wishlist.
   - Owner O archives the wishlist and later restores it to active status (or updates its details).
   - Giver A receives notifications for both the archival and the restoration/update of the
     wishlist.
4. **Role overlap and recipient change before delivery**:
   - On a collaborative wishlist, User U is not a member (or is removed from membership) and holds
     a reservation on a wish, or is assigned as the wish's recipient before a queued notification
     is sent.
   - When the dispatcher evaluates pending notifications for that wish, it detects that User U is
     the wish recipient and suppresses any reservation-derived notification so the surprise is not
     compromised.
5. **Delivery failure isolation and retention cleanup**:
   - Giver A has blocked the Telegram bot; Giver B has an active chat.
   - Owner O marks a wish received (or archives it). The owner's action succeeds immediately.
   - The dispatcher marks Giver A's notification as failed (and deactivates Giver A's destination)
     while delivering Giver B's notification. After the retention period expires, background
     maintenance purges both finished notification records.

## Q&A

- **Why must notification intents be recorded atomically with the gift lifecycle change?**
  If notifications were sent directly during the user's request, a slow or failing Telegram API call
  would delay or break the user's action. If notifications were queued only after the transaction
  committed, a crash or restart immediately after commit would silently lose the notification,
  leaving givers with stale reservations.
- **Why should a gift-receipt notification still be sent if the wish is archived right after a
  partial receipt?**
  Archiving a partially received wish only moves the remaining unreceived units to the archive; the
  received units remain in the «Подаренные» section as a completed receipt. Givers with open
  reservations still need to know that units of the wish were received so they can reconcile their
  reservations.
- **Does archiving a wish or recording a receipt automatically cancel a giver's reservation?**
  No. Only the giver can modify or cancel their own reservation (except when an entire wishlist is
  deleted). Notifications exist specifically to inform the giver so they can decide what to do.
- **How is the recipient's surprise protected when someone has multiple roles?**
  Recipient exclusion takes precedence over giver status for any reservation-derived notification
  (gift receipt, own-reservation confirmation, or wishlist/wish notifications where the user's only
  entitlement is a reservation on that wish), evaluated both when the event occurs and immediately
  before the message is sent.
