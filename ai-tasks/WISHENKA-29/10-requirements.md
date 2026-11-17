# WISHENKA-29: Notifications and reminders

## Goals

Keep participants informed about relevant wishlist activity and approaching occasions through the
Telegram bot, even when delivery is temporarily unavailable. Preserve the recipient's surprise
and let each participant control which messages they receive. A delivery failure must not undo the
underlying wishlist or gift action.

## User Stories

- As a collaborator or giver, I receive relevant changes to a shared wishlist so I can act on them.
- As a giver, I learn when a gift is marked received and decide what to do with my own reservation.
- As a user tracking an occasion, I receive an appropriate reminder before its date.
- As a user, I can privately add, inspect, change and remove birthdays I choose to track.
- As a user, I can rely on my global and per-list notification choices being respected.
- As a wish recipient, I never learn that a gift was reserved or purchased through notifications,
  including when I also act as a collaborator or giver.
- As an operator, I can identify unsuccessful delivery and safely resume service without disclosing
  private message contents or sending repeated messages as a normal recovery action.

## Definition of Done

1. Eligible users receive Telegram notifications for meaningful wish creation or edits,
   collaboration and membership changes, wish or list archival, reservation changes and gift
   receipt, according to the audience rules below. The actor is excluded unless the event is an
   explicit confirmation intended for that actor.
2. A receipt produces at most one notice for each eligible holder of an open planned or purchased
   reservation for that receipt. The notice identifies the wish and receipt, but gives no
   quantities, other givers, excess-reservation hints, or automatic reservation changes. Existing
   receipt behavior is preserved without creating a second notice for the same holder and receipt.
3. Reminders for approaching wishlist events and birthdays use dates and relationships that the
   user is authorized to track. No reminder is inferred from missing dates or fabricated birthday
   data. Repeated scheduling or restart does not routinely issue the same reminder twice for the
   same person, occasion, and reminder occurrence.
   A user can create a private birthday reminder with a label and month/day, list their reminders,
   change either value, and delete or stop tracking it without opening the Mini App. Creating a
   reminder is an explicit choice by its owner; no other user can see or manage that reminder.
   Invalid dates are rejected without losing the prior value, and a reminder without an explicit
   date is never scheduled. Deletion or change prevents delivery of an obsolete queued reminder.
4. Notification category choices are applied per user; an explicit list-specific choice overrides
   the global choice for that list. Existing receipt preferences continue to work. When a category
   has no saved choice, the implementation must document and consistently apply its default.
5. The wish recipient is excluded from reservation, purchase, cancellation and receipt-derived
   notifications about their own wish, even when they hold another role. Suppress a notification
   if its existence, timing, text, link or preview could reveal such an event. Neutral reminders
   are independent of protected activity. Links expose only information the recipient may view.
6. Delivery handles Telegram throttling and temporary failures with delayed retry and bounded
   attempts; a persistent or non-deliverable destination does not prevent delivery to other users.
   Delivery progress survives service interruption. An ambiguous send outcome is not represented as
   a confirmed delivery and recovery must avoid knowingly sending duplicates.
7. Event and reminder deliveries are evaluated for current eligibility and notification preferences
   before sending; removed access, an invalid destination, or a disabled preference cannot disclose
   list information. A user who has not started the bot or otherwise lacks a deliverable destination
   is skipped without blocking the originating action.
8. Receipt, reservation, wishlist and collaboration changes succeed independently of a subsequent
   delivery failure. Ordinary retries and repeated processing do not generate duplicate event
   notices.
9. Messages use the user's supported language, Russian or English, with a consistent fallback when
   the language is unavailable. Logs and operational feedback do not expose bot credentials,
   capability links, message bodies, reservation details or unnecessary personal information.
10. Automated checks demonstrate recipient exclusion under overlapping roles, preference precedence,
    receipt deduplication, event and reminder eligibility, retries and throttling, recovery after
    interruption, and independence of the underlying action from delivery outcomes.

## Task Description

### Scope and boundaries

This work covers the delivery and eligibility of Telegram service notifications for relevant
wishlist events and upcoming occasions. It includes durable handling of work, retry, throttling,
deduplication and safe operation. The existing receipt notice workflow is a compatibility baseline,
not a second source of identical notices. Story WISHENKA-60 separately addresses transactional
outbox delivery for reservation events; the implementation must coordinate with that scope and
must not claim guarantees for an event until its triggering change is reliably represented.

Notification preference screens, profile and account deletion are separate work; this task respects
available choices and documents defaults. This task supplies a minimal private birthday tracking
flow because there is no existing birthday source. Each user enters only a label and month/day for
an occasion they choose to track; this is their private reminder, not a claim that another account
has shared a birthday or granted access. It is never exposed to other users. A missing list event
date likewise produces no event-date reminder. A user may stop tracking a birthday at any time.

### Audience and message rules

- **Wish created or edited:** relevant authorized collaborators and affected givers, excluding the
  actor, receive only authorized list and wish information and no reservation information.
- **Reservation or purchase changed:** notify affected givers only where action is relevant; never
  notify the wish recipient or reveal other givers. A person's own action does not trigger an
  unsolicited confirmation.
- **Archived wish or list:** notify affected collaborators and holders of open reservations, except
  the actor. A recipient receives only an independently safe list change, never a message whose
  trigger or content discloses protected reservation activity.
- **Gift receipt:** notify each eligible open reservation holder under criterion 2; the recipient
  is excluded even if also a reservation holder.
- **Collaboration changes:** notify affected participants and authorized managers, excluding the
  actor, only with information they are permitted to see.
- **Approaching event or birthday:** notify users who track that occasion, subject to their
  preferences and authorization; disclose the occasion and date only where authorized.
- **Birthday management:** a private bot interaction lets the owner add, view, edit and delete
  their own labeled month/day entries. No birth year, account linkage, contact import or public
  sharing is needed. The owner can cancel an incomplete change without losing existing entries.

### Timing and reliability assumptions

The existing product specification leaves exact reminder lead times, category defaults, retry
limits and delivery guarantees open. Choose and document deterministic, configurable defaults
appropriate to the product, and make them testable without real time delays. Interpret dates
consistently and document the timezone and treatment of overdue or changed occasions. Do not send
reminders solely because of reservation activity. A delivery provider can accept a message while
its response is lost, so exactly-once external delivery cannot be promised; handle that uncertainty
explicitly rather than describing it as a confirmed success or guaranteeing no duplicate ever.
Birthday entries recur annually in UTC. For February 29, the occurrence is February 28 in years
without a leap day; a change to a birthday invalidates old unsent occurrences and a deletion
prevents further delivery. Document the selected lead times and show the entered date to the owner.

## Business Entities and Constraints

- **Participant:** a user with a relationship to a list or wish, language, destination and choices.
- **Wishlist and wish:** an authorized shared context, with a recipient whose surprise is protected.
- **Reservation and receipt:** giver-specific intent and an independently recorded receipt; neither
  should be disclosed to the recipient through notification behavior.
- **Occasion:** a dated event or birthday a user is entitled and has chosen to track.
- **Private birthday entry:** its owner's chosen label and month/day; the owner alone controls it.
- **Notification preference:** a global category choice, optionally overridden for a wishlist.
- **Notification:** a message for a particular eligible participant about one event or occurrence,
  with a delivery outcome that may be pending, successful, failed or uncertain.

Functional scope follows `specs/00-high.md`, `in-docs/spec.md`, and
`in-docs/bot-scenarios.md`. Python 3.12+ is the implementation language. No exact external delivery
promise or change to gift and reservation semantics is implied.

## Q&A

- **Why is this needed?** Participants need timely, relevant information without checking the app,
  while the recipient's surprise and the user's notification choices remain protected.
- **What happens if Telegram is unavailable?** The underlying action remains complete; delivery is
  retried when safe, and an uncertain outcome remains distinguishable from confirmed delivery.
- **Who wins when roles overlap?** The recipient restriction for a particular wish takes precedence
  over collaborator or giver roles for any reservation-derived message.
- **Are lead times and defaults fixed by the specification?** No. They must be chosen, documented
  and verified consistently, not presented as existing product decisions.
- **How are birthdays obtained?** Each tracker explicitly enters and controls a private labeled
  month/day; no absent profile data or external contacts are inferred or imported.
