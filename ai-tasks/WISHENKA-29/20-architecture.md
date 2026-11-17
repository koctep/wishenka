# WISHENKA-29: Notification and reminder architecture

## Research

- `wishenka/notices/` implements a receipt-specific sender, queue and web-lifespan worker. The
  `notification_outbox` schema requires a receipt ID and deduplicates receipt plus giver. Receipt
  production already occurs inside the receipt transaction; replacing it with a parallel receipt
  producer would duplicate notices. Existing attempts, timeouts, lease guards and retention must
  remain compatible through migration.
- `user_notification_settings` and `wl_list_notification_settings` already have event-type keys;
  missing entries currently default to enabled for receipt notices. The current worker joins live
  item and list titles but does not recheck all settings and eligibility at send time.
- A wishlist has `event_date`; `users` currently has Telegram ID and language but no stored
  birthday, tracking relation or bot-start indicator. The tracker must provide a birthday
  explicitly; Telegram profile fields cannot be assumed available. WISHENKA-60 addresses outbox
  for gift lifecycle events, including archive and receipt. Receipt is already implemented; extend
  the transaction seam for the other events without creating a second receipt delivery.
- Telegram's [bot FAQ](https://core.telegram.org/bots/faq#broadcasting-to-users) describes
  per-chat and broadcast limits. The [Bot API](https://core.telegram.org/bots/api) provides a
  retry delay on throttling. Limits are configurable, not a promise of free delivery.

## Implementation Plan

1. Define closed event, preference and delivery-state types. Add migrations for a generalized
   transactional event/delivery queue and durable start/destination information. Preserve all
   existing receipt rows and deduplication keys; migrate in place or keep a unified worker with a
   compatible receipt adapter. Do not run independent receipt workers against the same row.
2. Introduce transaction-scoped event production for each supported mutation, including bot-created
   wishes, using the same SQLite transaction as the domain write. Assign stable IDs before commit;
   rollback removes both mutation and event. The receipt path continues to produce exactly one row
   per existing key. Expose a producer contract for WISHENKA-60 and share its archive/receipt
   semantics; do not enqueue a second event for those writes. Explicitly test every write path,
   including direct repository/inventory and bot flows, rather than relying on log events.
3. Add private birthday tracking through the bot and durable owner-scoped birthday entries. Add a
   deterministic, bounded scheduler for these entries and authorized dated wishlist occasions.
   Never synthesize a birthday or infer a tracking relation from another account.
4. Extend or replace the existing worker as one delivery owner for all event types. Recheck live
   recipient eligibility, roles, preference and destination before every attempt, including receipt
   attempts. Serialize rate reservations across worker processes; use one injected sender and clock.
5. Cover queue and event mutations, settings, privacy, retries, scheduler and operations before
   enabling producers. Preserve existing receipt tests and run the complete quality gate.

### Failing repro (Step 3)

Before production changes, add focused bounded tests under `tests/test_notice_delivery_repro.py`
using temporary SQLite, fake clock and Telegram sender, with no network or wall-clock sleeps. A
real mutation should create durable work and survive restart; rollback must leave neither event nor
notice. For one overlapping recipient and giver, assert that reservation-derived delivery is
suppressed while an independently safe list-change notice and neutral reminder remain eligible.
Assert actor exclusion for shared events, opt-in and opt-out for the actor's own reservation
confirmations, settings override, live revocation and bot-not-started suppression. Verify one
existing receipt notice per giver and no
second receipt source. Test 429 delay, permanent rejection, timeout/ambiguous send and a stale lease
without assuming exactly-once delivery; another eligible user must continue. Test reminder
occurrence deduplication across scheduler restarts, changed/removed dates and UTC boundaries. Add
fake private bot interactions creating, listing, editing, cancelling and deleting birthday entries;
assert owner isolation, invalid-date rejection, leap-day handling, live deletion and changed-date
suppression, duplicate scheduler scans, and actual delivery from an entered birthday. Check that no
message is generated for an absent entry or for another user's private data. Test RU/EN fallback
and privacy of text, links and logs. At least the new
mutation-to-queue and eligibility tests must fail for the intended missing behavior on current code;
keep the existing receipt tests green. Then implement only after independent review of the red run.

## Architecture

```text
Wishlist mutations / bot capture -- same SQLite transaction --> domain event + delivery intent
Gift receipt -------------------- existing transactional producer --> receipt adapter
Dated wishlist scanner ---------- occurrence uniqueness -------------> delivery intent
Private birthday bot flow ------> owner-scoped entries --> birthday scanner --> delivery intent
                                                                         |
                         preferences + roles + bot destination            |
                                      |                                   v
                              live eligibility <--- claim / fenced queue worker
                                                              |
                                     shared persistent rate permit --> Telegram sender
```

### Producers and storage

The domain service emits a typed event only after a successful meaningful change: wish create/edit,
archive, list archive, membership/collaboration change, and opted-in own-reservation
confirmation. Persist an immutable generated event ID, kind, actor, subject list/item and a minimal
version/reference in
its originating transaction; create candidate-recipient intents in that same transaction or make
fan-out idempotent with a durable cursor and unique `(event_id, destination_user_id, category)`.
No post-commit best-effort callback is the source of truth. The event records no body, capability
URL, reservation quantity or other giver identity. Do not derive event identity from timestamps.
Record removed-member target and event-time entitlement separately where necessary; delivery must
not reveal details to a user whose access has since been removed. A generic revocation message may
be sent only if it contains no list details and the target's consent permits it; otherwise skip.

Keep existing `notification_outbox` receipt uniqueness `(event_type, receipt_id, giver_user_id)`
and worker status/lease data valid across upgrades. If a generalized table is introduced, migrate
and fence cutover atomically, and verify old pending/sending/sent rows are neither lost nor sent
again. Prefer reusing and extending the existing worker and sender, not a second worker for receipt
rows. Add indexes and bounded scans; store a stable idempotency key per intent. Terminal retention
must not delete deduplication evidence before the source event or occurrence can be replayed.

### Audience, consent and privacy

A pure policy resolves candidate recipients per event, excluding actor unless explicitly specified.
For wish create/edit, use current authorized collaborators and affected givers; archive includes
holders of open reservations; membership changes target affected authorized participants/managers.
Reservation mutations affect the actor's own reservation. A transaction may produce an explicit
confirmation only for that actor when they have opted in; it never signals the action to another
giver. Suppress legacy `reservation_changed` intents, since their timing can disclose another
giver's activity even if their text is neutral. Receipt remains the existing one-per-open-holder
producer; exclude the wish recipient even when roles overlap. An owner is treated as recipient
for their own wish, taking precedence over other roles; the policy checks the specific wish and
list type, so a collaborative-list owner may be a giver for another recipient. Recipient-safe
neutral list events must not be triggered solely by protected booking state.
At send, re-evaluate live role, list/item state and relevant event: suppress inaccessible or deleted
content, a recipient who is also a giver for reservation-derived events, and stale or unauthorized
reminders. Continue to allow independently safe list changes and neutral reminders for that person
when they are otherwise eligible. Apply the list switch
for `(user, list, category)` if present, otherwise global `(user, category)`. The default is
enabled for `wishlist_changes`, `gift_received`, and `reminders`. The `reservation_changes`
category defaults to disabled: an explicit enabled choice is required both when queuing and
immediately before sending an own-action confirmation. A verified private-chat user controls the
global choice with `/reservation_confirmations on` and `/reservation_confirmations off`; bot help
makes this control discoverable. Retain the existing `gift_received` key.

Introduce a durable private-chat destination populated only by a verified private `/start` or other
explicit valid bot interaction; merely having a Telegram profile does not prove bot delivery is
possible. Existing users without that proof are skipped until they interact. A forbidden/rejected
chat becomes non-deliverable; no raw IDs, tokens, link contents or bodies are logged. Fetch the
profile language at send, map `ru*` to Russian and `en*` to English, otherwise use Russian. Render
plain-text event-specific safe templates from currently authorized data, with bounded lengths.
Do not include capability links or reservation facts for recipients; use a neutral Mini App entry
only if configured and it does not expose protected details. Suppress unsafe messages entirely.

### Birthday management and reminders

Add an authenticated, private-chat `/birthdays` interaction alongside the existing bot router.
It offers localized list, add, edit and delete actions, and cancellation without changing committed
entries. The user supplies a short label and valid month/day; the flow never requires a birth year
or another user's account. Store each entry under the verified bot principal's internal user ID;
callbacks and reads must recheck owner, chat, entry revision and active session, and reject stale
or foreign actions without revealing an entry. Display the saved date and label to that owner only.
Use bounded input, validated calendar values including February 29, and durable transaction-backed
changes. State and storage for incomplete bot input must be scoped to the owner and expire; never
log labels or dates. An owner can delete an entry and its unfinished input; account deletion work
must also remove their entries and pending state. Users can access this flow from a discoverable
bot menu action as well as the command; localized prompts describe date format and cancellation.

Each entry is a private tracking choice. It does not expose a birthday from somebody else's profile,
nor create a relationship to that person's account. Users are responsible for entering their own
reminder details; only their verified private bot destination receives the reminder. No other user
gets access to the entry or its reminder. Edits and deletes increment a revision or tombstone so an
already queued occurrence is revalidated immediately before send; a removed or changed entry is
never sent under its former values. Apply the global `reminders` preference, since no list is bound.

The scheduler scans active dated lists in bounded batches using injected UTC time. Initial default:
one reminder seven calendar days before the UTC event date, configurable via a positive list of
lead days; run hourly and cover a missed window after restart until the event date, with a unique
key `(list_id, event_date, lead_days, user_id)` across scans. Candidate trackers are current owner,
current members, and authenticated users who favorited the list, provided each has authorized
access at delivery. A changed date creates a new occurrence; old unsent occurrences are skipped by
live validation. No reminders after the event date or for deleted/undated lists. Scan explicit,
active private birthday entries and schedule each owner only. Compute the next annual occurrence
in UTC; February 29 recurs on February 28 in non-leap years. Use the same configurable lead days
and a unique `(birthday_id, revision, occurrence_year, lead_days, owner_id)` key. A restart or
repeated scan cannot create another intent for that occurrence. Never infer a birthday from a list,
profile name, or the fact that users collaborate. Recheck active entry, revision, preference and
verified destination immediately before delivery, and render only the owner's entered label and
date.

### Delivery and concurrency

The store provides `enqueue(event, recipients, transaction)`, `claim_due(now)`,
`settle(claim_token, outcome, now)` and `schedule_occurrences(now)` interfaces. Claims and shared
rate permits use SQLite `BEGIN IMMEDIATE` with unique fencing tokens and bounded leases. Use a
configurable default of 20 sends/second globally and one/second per private chat; permits are
persisted and shared across processes, with no sleeping while holding a DB transaction. Reservation
of permits, eligibility check and claim are coordinated; check eligibility again immediately before
network send and fail closed on database errors. Concurrency cannot make an already delivered
message retractable; state changes after the final check remain a documented external-send race.

`SendResult` distinguishes delivered, definitive rejection, definite retryable failure, and
ambiguous delivery. 429 observes `retry_after` at minimum; definite retry uses exponential backoff
with configurable defaults (base 30 seconds, max one hour, maximum five attempts). A blocked or
unknown chat becomes terminal and cannot stall other rows. Timeout, cancellation after send starts,
connection loss, or stale sending claim is `uncertain`, not confirmed: do not automatically resend
an uncertain attempt; expose safe aggregate counts and an explicit operator resolution path. This
is stricter than the current receipt worker's bounded ambiguous retry; preserve old queued outcomes
without treating uncertainty as success, and update legacy tests and docs to the safer contract.
Only the owner of the exact claim token can settle. Poll and cleanup loops survive transient errors
with bounded backoff; do not hold locks during network I/O. Attempts, leases, retry deadlines and
rate reservations persist across restarts. Avoid paid broadcast settings.

### Interfaces and boundaries

- `EventProducer.record(conn, event)` participates in the caller's existing domain transaction;
  `AudiencePolicy.candidates(event, snapshot)` returns typed recipient identifiers, not text.
- `NoticeStore` owns deduplication, durable scheduling, fenced claims and settlement. Eligibility
  receives current principal/list/occurrence and returns an enum, never a token-bearing log value.
- `ReminderScheduler.run_once(now)` is restart-safe and bounded; inject clock and source adapters.
- `BirthdayStore` creates, lists, updates and deletes entries under the authenticated owner, and
  exposes bounded due-candidate reads with revisions to the scheduler; no cross-owner enumeration.
- `NoticeSender.send(chat_id, text)` retains the current four outcomes; tests use an injected fake.
- Web lifespan starts a single compatible worker per process with shared SQLite coordination;
  polling bot records deliverable private interactions. Disable flag leaves queue pending. Keep
  queue and user schema migrations ordered and compatible with concurrent startup and old rows.

## Q&A

- **Why not exactly once?** Telegram may accept a send before the response is lost. An uncertain
  outcome is preserved for operator handling instead of a misleading success or automatic resend.
- **What happens to existing receipt delivery?** Its transactional producer remains authoritative;
  migration and a single worker preserve old keys and prevent duplicate receipt notices.
- **What about WISHENKA-60?** Its archive and receipt outbox requirements overlap; expose the same
  event/queue seam and avoid duplicate producers. The follow-up must inspect the delivered scope
  before extending reservation-specific producers or closing its issue.
- **What about birthdays?** The owner supplies a private label and month/day through the bot, and
  may inspect, edit or delete it. It is not a shared profile field or imported contact record.
- **How are delivery gaps visible?** Count pending, uncertain, terminal and skipped outcomes without
  recipient IDs or contents; provide bounded operator inspection/resolution without logging secrets.
