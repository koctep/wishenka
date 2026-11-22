# WISHENKA-291: Personal settings and notification management

## Goals

People should understand and confidently control their profile language, birthday and reminders,
and notification preferences. Clear grouping and feedback should prevent unintended changes and
help people distinguish account-wide choices from exceptions for a single wishlist. A destructive
account action must be clearly separated and understood before it is confirmed.

Implementation language: Python, JavaScript, HTML and CSS.

## Task Description

The settings experience presents existing personal preferences and account controls to an
authenticated user in the Mini App. This task improves clarity and usability while preserving the
established behavior and privacy rules in the product specification. It covers the settings screen
and the feedback needed to understand the result of an action; it does not introduce new
notification categories, delivery channels, account-deletion rules, or a new way to authenticate.

### Business entities

- **User profile:** the person's chosen language and optional birthday, including whether a
  preference was supplied by the person or automatically obtained where applicable.
- **Global notification preference:** the person's default enabled or disabled choice for a
  supported type of notification across wishlists, plus the account-wide birthday reminder choice.
- **Wishlist preference:** an optional enabled or disabled choice for a supported notification
  type for one accessible wishlist; absent an individual choice, the global choice applies.
- **Account deletion:** an action initiated by the account owner, with a warning, an impact summary,
  an opportunity to cancel and explicit confirmation before irreversible consequences.

### Functional requirements

1. Present language, birthday, birthday reminders, global notifications, individual wishlist
   notification settings and account deletion in identifiable, logically grouped sections.
   Explain that global settings are defaults and individual wishlist choices take precedence.
2. Show which of Russian and English is selected and allow the person to choose either. A
   successful explicit selection takes effect immediately and remains the person's choice across
   subsequent visits, bot replies and notification delivery, as specified for the product.
3. Show the current birthday or that it is not set. Allow a valid day and month with an optional
   year to be saved, and allow the person to clear it. Explain the optional year and the priority
   of an explicit choice over later Telegram synchronization. Invalid dates must be rejected
   without overwriting the last saved date, with a useful explanation.
4. Show the enabled or disabled state of birthday reminders and allow it to be changed separately
   from the birthday itself. Turning reminders off must not erase saved birthday information.
5. For each existing global notification type, show a comprehensible name and its enabled or
   disabled state, and let the user change it. Existing types cover wishlist and wish changes,
   reservation updates, gift receipt, occasion reminders and birthday reminders. These choices
   must preserve the product's restrictions on what a recipient may learn about gifts.
6. For each accessible wishlist and each supported list-specific type, identify the wishlist and
   type, expose the current individual choice as enabled, disabled or inheriting the global
   setting, and indicate the resulting effective enabled or disabled state. Changing or removing
   an override affects that list and type only; other lists and global choices remain unchanged.
   When no lists are available, show a clear empty state.
7. Make the result of a successful change clear and distinguish saving or pending work from a
   confirmed saved state. If a change fails, explain the failure and make it possible to retry;
   do not represent an unsuccessful change as saved or leave a misleading displayed preference.
   Saved values and effective states must be consistent on reopening the screen.
8. Separate account deletion from routine preference controls. Before confirmation, explain that
   deletion is irreversible and summarize affected personal wishlists, shared wishlists to be
   transferred or removed, and the person's active or purchased reservations to be cancelled.
   Do not disclose other people's protected reservation information. Allow cancellation without
   deletion and require explicit confirmation; only the authenticated account owner can delete
   that account. Communicate success or failure clearly.
9. Provide equivalent meaning and complete labels, instructions, states, confirmations and error
   feedback in Russian and English. Preserve usable navigation back to the rest of the Mini App.

### Non-functional requirements and constraints

- The screen must remain usable on a narrow phone viewport and in the Telegram Mini App and a
  normal mobile browser, including with longer Russian and English text. Labels and actions must
  remain readable without obscuring controls or requiring horizontal scrolling.
- Controls must be distinguishable beyond color, have understandable labels and states, and be
  operable using keyboard and assistive technology. Feedback must be perceivable without relying
  solely on visual changes.
- Preserve the surprise invariant: recipient-facing settings and feedback must not reveal the
  existence, details or identity of another person's reservation or purchase.
- Personal preferences are private to the authenticated person. A person may change only their
  own profile and notification choices and may access individual settings only for eligible lists.
- Existing notification precedence, delivery eligibility, language synchronization, explicit
  birthday priority and deletion consequences remain unchanged. No new performance target is
  imposed; ordinary interaction must give timely visible feedback.

## User Stories

- As a user, I can choose Russian or English and see my selection reflected throughout the
  experience, so I can use the service in my preferred language.
- As a user, I can enter or clear my birthday, including without a year, and understand that my
  manual choice will not be overwritten by Telegram, so I control my personal information.
- As a user, I can pause birthday reminders without losing dates, and see whether they are on.
- As a user, I can set notification defaults and make exceptions for one wishlist, while seeing
  which choice applies, so I receive the messages I want.
- As a user, I can see whether a change succeeded or failed and try again when needed, so I do not
  mistake an unsaved preference for an active one.
- As an account owner, I can understand and confirm or cancel deletion before it happens, so I do
  not accidentally lose personal data or affect shared lists.

## Definition of Done

1. In both supported languages, each profile and notification section is findable and explains
   its purpose. Every supported type visibly and accessibly communicates its current state.
2. Switching language immediately updates the experience and persists according to the product
   language rules. A failed change does not falsely indicate success.
3. A valid birthday with or without year can be saved and cleared, invalid input is explained, and
   explicit changes survive subsequent synchronization and reopening.
4. Birthday reminders can be turned on and off without deleting dates; the saved state is shown
   after reopening.
5. Global preferences can be changed independently; for each accessible wishlist, individual
   enabled, disabled and inherited settings show their effective state and follow precedence.
   Changing one does not silently change unrelated settings. An empty list state is understandable.
6. Each change has discernible pending, success and failure feedback where applicable; failed
   operations do not claim success or misrepresent the persisted state and can be retried.
7. Account deletion is visually separate; its warning, impact summary, cancellation and explicit
   confirmation work in both languages and retain existing authorization and deletion rules.
8. Phone-sized views in both languages have legible text, accessible labels and states, usable
   controls and no obstructed content or horizontal overflow; existing journeys continue to work.
9. No recipient-facing content reveals protected reservation or purchase information.

## Q&A

- **Why this change?** The Jira business goal is confident management of personal preferences
  without accidental changes; clear grouping and feedback address that need.
- **What is the source of truth for inherited behavior?** `specs/00-high.md`, `in-docs/spec.md`
  sections 9–11, and `in-docs/bot-scenarios.md` describe preference precedence, personalization,
  notification privacy and account deletion. This task does not replace those rules.
- **Are additional channels or notification categories requested?** No. The scope is clarity and
  safe use of existing choices, not changing what the service sends.
