# WISHENKA-182: Support Diagnostic Context Scalability and Consistent Bot User Initialization

**Programming Language:** Python

## Goals

This technical-debt task addresses two reliability and maintainability gaps identified during the implementation of the Telegram support channel (`WISHENKA-30`):

1. **Predictable support submission performance and concurrency:** Submitting a support message must remain fast and non-blocking for other users even as the total number of wishlists and share/invite links in the platform grows. Collecting diagnostic metadata and redacting sensitive capability links from user support text must not degrade linearly with total platform data volume or hold exclusive write access longer than necessary.
2. **Consistent user language preservation and notification readiness across all private bot flows:** Regardless of which bot command or flow a user enters (onboarding/help, wishlist capture, birthday reminders, or support), the system must recognize the user consistently, preserve any previously stored language preference, and keep the user's private notification destination active without duplicated, diverging initialization logic.

## User Stories

- **As a Wishlist Owner / Bot User**, when I submit a support request, I want my message to be processed promptly without delays caused by other users' wishlists, while still ensuring any private wishlist or invite links I paste are redacted before reaching support operators.
- **As a Platform Operator**, I want support ticket preparation to avoid scanning all platform-wide capability tokens inside a write-locked operation so that concurrent bot and web operations are not stalled as the platform scales.
- **As a Returning Bot User**, when I interact with any private bot feature (entry commands, wishlist capture, birthday management, or support), I want my stored language preference to be consistently preserved and my private notification destination to remain active.
- **As a Maintainer**, I want private-chat user recognition and notification destination activation to follow one shared, consistent behavior across all bot routers so that fixes and privacy guarantees apply uniformly.

## Task Description

### Scope

1. **Support Diagnostic Context & Capability Redaction (`support` bot flow):**
   - Eliminate full-platform scans of all wishlist, share, and invite tokens during support diagnostic context collection.
   - Ensure capability redaction in support messages continues to protect sensitive tokens (standard public/invite tokens, capability URL paths, Mini App startapp parameters, and any user-scoped tokens) without performing unbounded platform-wide reads inside a write transaction.
2. **Unified Private-Bot User Initialization & Destination Activation (`entry`, `support`, `birthdays`, `capture` bot flows):**
   - Unify the repeated pattern across the private bot routers that:
     - verifies the interaction is a private chat with an identified Telegram user,
     - resolves or creates the internal user record while preserving any existing stored language preference,
     - suppresses sensitive user-attribute logging in private-bot contexts, and
     - activates/updates the user's private notification destination.
   - Preserve each flow's existing behavior around pre-resolved user records (e.g., from locale middleware) and any flow-specific side effects (such as clearing superseded support sessions on `/start` or `/help`).

### Out of Scope

- Changing the support ticket message format, rate-limiting rules, or delivery destinations.
- Modifying the account deletion scope (tracked separately in `WISHENKA-35`).
- Changing the user-facing language selection rules or adding new locales.
- Altering group-chat capture behavior (where private-chat destination activation does not apply).

## Functional Requirements

1. **Capability Redaction Preservation:**
   - Support messages sent to operators must continue to redact capability tokens, share URLs, invite URLs, and Mini App startapp tokens before delivery.
   - Redaction must cover both standard-format capability references and any tokens scoped to the submitting user's own wishlists/access, without leaking secrets.
2. **Diagnostic Context Accuracy:**
   - Support tickets must continue to include accurate per-user diagnostic summary counts (active wishlists, archived wishlists, collaborative memberships, active draft presence, and bot destination status).
3. **Consistent Private-Bot User Initialization:**
   - All private bot routers (`entry`, `support`, `birthdays`, `capture`) must share a single unified initialization path for private-chat user resolution and notification destination activation.
   - If a user record was already resolved earlier in the request lifecycle (e.g., via middleware), the initialization path must reuse it rather than redundantly re-querying or overwriting it.
   - When creating or updating a user record from a Telegram update, any existing stored language preference must be preserved consistently across all four routers.
   - Private notification destination activation must occur only in private chats where the chat identifier matches the sender's Telegram user identifier.

## Non-Functional Requirements

1. **Scalability & Lock Contention:**
   - Preparing a support ticket must not perform unbounded full-table/full-platform token scans.
   - Any remaining token lookup or redaction work must be scoped or executed outside exclusive write transactions so write-lock duration stays constant ($O(1)$ with respect to total platform wishlists).
2. **Privacy & Logging:**
   - Private-bot user resolution must continue to suppress sensitive personal-data fields in operational logs, matching existing privacy guarantees.
3. **Backward Compatibility:**
   - Existing bot commands, callbacks, support ticket formatting, and test contracts must remain functionally unchanged.

## Constraints and Assumptions

- **Language:** Python (existing backend and bot stack).
- **Zero-Regression Guarantee:** All existing bot tests (including support, entry, birthdays, capture, and i18n suites) must continue to pass without weakening privacy or redaction assertions.
- **No Schema Breaking Changes:** Requirements must be satisfied within the existing application data model unless strictly necessary.

## Main Entities (Business Domain)

- **Bot User (Principal):** A Telegram user interacting with the bot in a private chat, possessing an internal identity, Telegram identity, and a stored language preference.
- **Bot Notification Destination:** The verified private-chat endpoint associated with a Bot User for receiving notifications.
- **Support Ticket & Diagnostic Context:** A user-submitted support inquiry paired with a sanitized, metadata-only summary of the user's account state.
- **Capability Token:** A secret bearer token granting public view or invite access to a wishlist, which must never be exposed in support tickets.

## Definition of Done

1. Support ticket preparation no longer scans all platform wishlists or capability token tables, and no unbounded reads occur inside the support write transaction.
2. Capability redaction in support messages continues to mask all standard capability patterns and user-scoped tokens verified by automated tests.
3. Private-chat user resolution and notification destination activation across `entry`, `support`, `birthdays`, and `capture` use a single shared mechanism.
4. Stored user language preferences are consistently preserved across all four bot routers, with automated test coverage verifying this behavior.
5. Existing and newly added automated tests pass under the repository's quality gate.

## Q&A

- **Q:** Why was this task created?
  **A:** It was identified as Follow-up 2 in the technical debt analysis of `WISHENKA-30` (`ai-tasks/WISHENKA-30/60-tech-debt.md`) to prevent SQLite write-lock contention from growing with total platform wishlists and to eliminate duplicated, inconsistent user/destination initialization across bot routers.
