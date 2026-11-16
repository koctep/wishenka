# WISHENKA-27: Bot entry, menu, and shared wishlist links

## Goals

Give Telegram users a clear first entry to the wishlist service and a direct path to a shared
wishlist. A recipient of a link should reach the intended list without completing a separate
registration or onboarding, while the service continues to protect gift surprises and access
rights. The implementation language is Python 3.12+; the existing Mini App is part of the user
journey.

## User Stories

- As a new or returning user, I can start the bot and understand how to use its main actions.
- As a user, I can reach list creation, my wishlists, an explanation of the service, and the
  Mini App's normal entry point from the bot menu.
- As a giver, I can follow a shared link to the intended wishlist and see the information I am
  allowed to see without a separate registration or onboarding process.
- As a person following a broken or unavailable link, I receive useful recovery guidance and can
  still use the main menu without learning private details about a list.
- As a gift recipient, I do not learn who reserved or purchased my own gift through these entry
  and navigation journeys.

## Definition of Done

1. In a private conversation, `/start` without a parameter displays a greeting and an inline menu
   with Create wishlist, My wishlists, How it works, and Open Mini App. Starting again displays a
   usable menu and does not silently save any unfinished wish.
2. Create wishlist opens the Mini App at the list creation journey; My wishlists opens the user's
   list collection; Open Mini App opens its normal entry point. The user can continue the selected
   journey in the Mini App.
3. How it works explains creating and sharing a list and how givers reserve wishes without exposing
   reservation or purchase information to the recipient.
4. A valid shared wishlist link presented through bot entry leads to that particular wishlist in
   the Mini App. It requires no separate registration or onboarding to view the list or reserve an
   available wish, subject to the product's existing access and reservation rules.
5. A missing target, malformed link, expired link, deleted list, or inaccessible target yields the
   same understandable recovery message and usable main menu. The response does not confirm whether
   a target exists or disclose private list content. A parameter-free `/start` is normal entry and
   must not be treated as a broken link.
6. The shared link gives access only as permitted by the existing product rules; merely opening it
   does not grant collaboration or editing privileges. The resulting view respects the viewer's
   role and never reveals the recipient's own reservation or purchase information.
7. User-facing greeting, menu, help, and recovery text support the product's Russian and English
   languages and follow the user's available language choice, with a usable fallback if no choice is
   available. Existing language selection and synchronization behavior is preserved.
8. Invalid input and repeated entry do not modify wishlist content or create a new wishlist merely
   by displaying the menu. Failures do not falsely claim that the requested list was opened.

## Task Description

### Functional scope

The bot is the entry point for the Telegram service. The greeting introduces the service and the
four menu actions direct the user to their named destinations. A shared wishlist entry preserves
its intended target across the transition into the Mini App. Opening or using a shared list remains
subject to the product's existing visibility and permission rules, including the surprise invariant.

The task covers the start conversation, menu actions, help content, shared-list entry, and a safe
fallback for unavailable targets. It does not implement adding wishes from bot messages,
notifications, support conversations, language-preference management, or new list-management
rules. Those are covered by other product work or existing functionality.

### Non-functional requirements

- Do not display the supplied link parameter, private list content, or hidden reservation and
  purchase details in error messages or previews.
- Unavailable or invalid targets must be indistinguishable in the user-facing error response.
- Entry and navigation must not bypass existing authentication, role, or access checks.
- Actions and recovery guidance must have clear labels and remain usable in the Telegram context.
- Avoid creating duplicate data or implicit changes as a side effect of entering the service.

### Constraints and assumptions

- The service is used through Telegram and its Mini App; no separate browser product is required.
- Russian and English are product languages. Selection and synchronization are existing or
  separately planned capabilities; this task must not introduce a new preference flow.
- A normal start with no target is distinct from a supplied but unusable target. A shared-list
  entry uses the same access and surprise rules as other ways of reaching the list.
- How the target is represented, how long a link remains valid, and how the handoff is performed
  are design decisions for the next step, constrained by these user-visible outcomes.

### Business entities

- **User:** a Telegram participant who can use the service and has an available language choice.
- **Wishlist:** a personal or shared collection with an owner and defined access permissions.
- **Shared link:** an invitation to view a particular wishlist under its existing access rules;
  it is not, by itself, a grant of editing or collaborator rights.
- **Giver:** a person who may view an accessible list and reserve an available wish.
- **Gift recipient:** a person for whom a wish is intended; their surprise must remain protected.

### Scenarios

1. A first-time user starts the bot without a target, sees the greeting and menu, and selects list
   creation. The Mini App opens at the creation journey.
2. A returning user selects My wishlists and reaches their list collection; selecting Open Mini App
   instead opens the normal entry point.
3. A link recipient starts through a valid shared-list link and reaches the specific wishlist with
   the view allowed for that person; no separate sign-up or onboarding interrupts them.
4. A user starts with an unusable target and receives the generic recovery message and menu, with
   no information that reveals whether the list exists. They may use another menu action.
5. A recipient viewing their own wish through a shared list does not see its reservation, purchase,
   or giver, including when the recipient has another role in that list.

## Q&A

- **Why is this needed?** To make the bot a usable entry point and let a shared link take a giver
  directly to the intended list while preserving privacy and minimizing friction.
- **What defines the behavior?** The product concept in `specs/00-high.md`, the functional
  specification in `in-docs/spec.md`, and the entry design in `in-docs/bot-scenarios.md`.
- **Does a link grant collaboration?** No. Viewing a shared list and collaborator membership are
  separate permissions; existing list rules determine the operations available to the viewer.
- **Does this task implement all bot journeys?** No. Wish submission and notifications are covered
  by WISHENKA-28 and WISHENKA-29; this task focuses on entry and navigation.
