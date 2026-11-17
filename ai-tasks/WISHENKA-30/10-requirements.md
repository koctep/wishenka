# WISHENKA-30: Support and feedback channel in the Telegram bot

## Goals

Give users a direct, accessible way inside the Telegram bot to ask questions, report problems, or
submit product feedback without leaving Telegram or using an external support portal. Deliver each
support request together with safe user diagnostic context to the support team (administrators or a
dedicated support chat) so issues can be understood and diagnosed quickly without building a
separate administrative web panel. Preserve all existing bot journeys—including menu navigation,
wish capture from messages, birthday reminders, and the gift-surprise invariant—so that asking for
help never creates unintended wish drafts or exposes hidden gift activity. The implementation
language is Python 3.12+.

## User Stories

- As a user, I can open help or support from the Telegram bot (`/help` or the bot menu) to learn
  how the service works and start a message to customer support.
- As a user, I can write and send a question, bug report, or feedback message in a private chat
  with the bot and receive a confirmation with a ticket reference when it is delivered.
- As a user, I can cancel an unfinished support request at any time without sending a ticket,
  creating a wish draft, or altering my wishlists and reminders.
- As a user, while I am composing a support message, the text or link I send is treated as my
  support inquiry rather than a new wish draft, and once I finish or cancel, normal wish capture
  works again.
- As a support operator or administrator, I receive each submitted support request in the
  designated support destination along with the user's diagnostic context so I can identify the
  account and troubleshoot without a web administration panel.
- As a gift recipient or giver, I can rely on the support flow never disclosing hidden reservation
  statuses, giver identities, purchase facts, or private wishlist access links.

## Definition of Done

1. In a private conversation with the bot, a user can access help and support via the `/help`
   command as well as through the bot menu (`How it works` and a dedicated support action). The
   help view explains how the service works (preserving existing guidance on wishlists, surprise
   protection, and reservation confirmation controls) and offers a clear way to contact support.
   A user may also initiate a support request directly by command or menu action.
2. Initiating a support request places the user's private conversation into an explicit support
   input flow (or accepts a direct command message) with clear instructions on what to send and
   how to cancel. While the user is in the support input flow, plain-text messages or links sent
   by the user are handled as the support message and do not trigger wish capture or create a wish
   draft.
3. The user can cancel an active support input session before submission via an explicit cancel
   action or `/cancel`. Cancellation or session expiration sends no support ticket, creates no wish
   draft, preserves existing wishlists and birthday reminders, and returns the conversation to
   normal bot operation. Starting `/start` or switching to another explicit bot command exits or
   supersedes the unfinished support prompt without silently submitting it.
4. Empty messages, unsupported non-text payloads, and messages exceeding the allowed length limit
   are rejected with clear guidance in the user's language, keeping the user able to submit a
   valid message or cancel. Per-user rate limiting prevents rapid repeated ticket submissions from
   flooding the support channel and informs the user when they must wait before sending another
   request.
5. Submitting a valid support message delivers a ticket to the configured support destination
   (designated support chat or administrator recipients) and confirms receipt to the user with a
   ticket reference identifier. Each delivered ticket includes:
   - The ticket reference identifier and submission timestamp.
   - The user's submitted support message text.
   - Safe diagnostic context for the requester: internal user identifier, Telegram user
     identifier, username and display name (when available), effective interface language, and
     high-level account summary counts (such as active wishlist count and notification destination
     readiness) useful for troubleshooting.
6. Support tickets, diagnostic context, user-facing responses, and operational logs must never
   expose secret capability links or tokens (shared wishlist tokens or collaborator invitation
   tokens), private contents of wishlists, or protected gift-surprise information (reservations,
   buyer identities, purchase statuses, or gift receipt details hidden from the recipient).
   Operational logs must not contain the body of support messages, personal profile fields, or bot
   credentials.
7. If the support destination is not configured or delivery to the support channel fails, the bot
   does not claim that the request was sent. Instead, the user receives an honest, understandable
   message in their language explaining that support is currently unavailable or asking them to
   try again later, without crashing the bot or corrupting user data.
8. All user-facing help, support prompts, validation messages, confirmations, cancellation notices,
   and failure messages support Russian and English using the user's stored language preference or
   Telegram language fallback.
9. Existing bot capabilities—`/start` (with or without shared-link parameters), `How it works`,
   `/birthdays`, `/reservation_confirmations on|off`, and private wish capture—continue to work as
   specified whenever the user is not actively entering a support message.

## Task Description

### Functional scope

The Telegram bot serves as the contact point for user support (`specs/00-high.md` Section 2.1,
`in-docs/spec.md` Section 12 and UC-12). A user in a private chat can read service help, start a
support request, enter their question, bug report, or feedback, and either submit or cancel it.
When submitted, the service packages the user's message with safe diagnostic metadata and forwards
it to the configured support destination (a dedicated support chat or administrator recipients),
then confirms submission to the user.

This task covers the user-facing `/help` and support entry actions, the interactive support
submission and cancellation flow, coexistence with wish capture and birthday input flows, abuse
protection, diagnostic context collection, and ticket delivery to the support destination. It does
not include a web-based administrative panel, external helpdesk integration, or automated AI
support replies.

### Non-functional requirements

- **Privacy and surprise preservation:** Diagnostic context must be strictly metadata-only and
  safe. Never include capability tokens, wishlist item details, or reservation and purchase data.
  Application logs must omit user message contents, personal identifiers, and credentials.
- **Truthful delivery reporting:** A ticket is confirmed to the user only after delivery to at
  least one configured support destination succeeds. Unconfigured or unreachable support channels
  produce a clear unavailable notice rather than a false success message.
- **Abuse resistance:** Enforce bounded message length, bounded active session lifetime, and
  per-user submission rate limits so a single user cannot overwhelm administrators or the support
  chat.
- **Isolation of chat flows:** Private chat text input must have deterministic precedence so an
  active support session never leaks into wish capture, and an expired or cancelled support session
  never blocks subsequent wish capture.
- **Localization:** Full support for Russian and English across all user-facing messages, consistent
  with existing bot localization rules.

### Constraints and assumptions

- User interaction with the support flow occurs only in verified private chats with the bot. A
  group or channel chat may be used only as the configured target destination that receives
  forwarded support tickets.
- No separate administrative web interface is permitted (`in-docs/spec.md` Sections 12 and 14);
  administrators receive tickets directly in Telegram.
- Russian and English are the supported user languages; language preference management itself is
  handled by existing product mechanisms.
- Exact message length bounds, support session expiration time, rate-limit intervals, ticket
  reference format, and configuration parameters for the support destination are design decisions
  for Step 2, provided they are deterministic, documented, and testable.

### Business entities

- **Requester (User):** A Telegram participant interacting with the bot in a private conversation
  who seeks help or submits a support inquiry.
- **Support Session:** A temporary, user-scoped state indicating that the requester's next text
  message in the private chat is intended for support rather than wish capture, subject to
  cancellation or expiration.
- **Support Ticket:** A submitted support inquiry identified by a ticket reference, combining the
  requester's message text, submission timestamp, and diagnostic context.
- **Diagnostic Context:** Safe, non-sensitive summary information about the requester's account and
  bot state (identifiers, language, and aggregate counts) attached to a support ticket for faster
  troubleshooting.
- **Support Destination:** The configured administrator recipient(s) or dedicated Telegram support
  chat that receives submitted support tickets.

### Scenarios

1. **Help and support initiation from menu or `/help`:** A user sends `/help` or selects the help /
   support option in the bot menu. The bot displays how the service works and offers an action to
   contact support. Selecting the support action prompts the user to describe their issue or
   question and shows a cancel option.
2. **Successful support ticket submission:** While in the support flow, the user sends a message
   describing a problem (including a product URL that failed to parse). Instead of starting a wish
   draft, the bot delivers a support ticket with the message and the user's diagnostic context to
   the configured support destination, exits the support session, and replies to the user with a
   confirmation and ticket reference.
3. **Cancellation and return to wish capture:** A user starts a support request, changes their
   mind, and presses Cancel (or sends `/cancel`). The bot confirms cancellation without sending a
   ticket. The user then sends a wish title, and normal wish capture creates a wish draft as usual.
4. **Validation and flood protection:** A user in the support flow sends an empty/unsupported
   message or a message exceeding the maximum length; the bot explains the limitation and lets them
   try again or cancel. If the user submits tickets too rapidly, the bot informs them that they
   have reached the submission limit and must wait before sending another ticket.
5. **Support destination unavailable:** A user submits a support message when the support channel
   is unconfigured or unreachable. The bot informs the user that the message could not be delivered
   right now and does not falsely report that a ticket was created.

## Q&A

- **Why is this needed?** Users need a straightforward way to report issues or ask questions
  directly inside Telegram, and administrators need enough user context to diagnose problems
  without a web admin panel (`specs/00-high.md`, `in-docs/spec.md` Section 12 and UC-12).
- **Why not treat every plain-text message as either a wish or support automatically?** Plain text
  and links in private chat are already used for quick wish capture (`WISHENKA-28`). Requiring an
  explicit command or button action to enter support mode prevents normal wish ideas from being
  sent to support and prevents support questions (including problematic URLs) from creating unwanted
  wish drafts.
- **What diagnostic context is safe to include in a ticket?** Account identifiers (internal and
  Telegram ID, username/display name), language code, bot destination state, and high-level
  aggregate counts (such as number of wishlists). Secret capability tokens, private wishlist items,
  and reservation or purchase details must never be included.
- **Does this task build a two-way live chat ticketing system or web dashboard?** No. In accordance
  with `in-docs/spec.md` Section 12, no administrative web panel is required; tickets are forwarded
  to administrators or a dedicated support chat in Telegram with the user's context.
