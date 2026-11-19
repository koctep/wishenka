# WISHENKA-177: End-to-end verification of Telegram bot menu transitions to Mini App

## Goals

Ensure that a Telegram user moving from the bot's main menu into the Mini App reliably reaches the
exact destination promised by each menu action, without accidental data creation or broken recovery
when something goes wrong. While individual bot menu generation and standalone Mini App journeys are
already covered separately, there is no end-to-end verification across the boundary between the bot
menu and the Mini App. Closing this gap protects users against silent drift between what the bot
offers and what the Mini App opens.

The implementation language is Python 3.12+.

## User Stories

- As a user starting the bot, I want selecting the list-creation action from the bot menu to open the
  Mini App on the creation screen without automatically creating an empty or unwanted wishlist.
- As a returning user, I want selecting the "My wishlists" action from the bot menu to open my
  personal collection in the Mini App so I can immediately see and manage my lists.
- As a user, I want selecting the "Open Mini App" action from the bot menu to open the standard Mini
  App home screen.
- As a Russian- or English-speaking user, I want these bot-to-Mini-App transitions to work
  consistently in my language.
- As a user who arrives with an invalid or corrupted launch parameter, I want the service to recover
  safely without crashing, exposing private information, or creating unwanted data, while still
  letting me use the Mini App.

## Definition of Done

1. End-to-end verification exercises the actual Mini App launch targets produced by the bot menu for
   all three navigation actions (`create`, `collection`, and `home`) using a prepared user session.
2. Following the `create` action opens the Mini App's list-creation screen and does not create any
   new wishlist merely from navigating to that screen.
3. Following the `collection` action opens the user's wishlist collection screen in the Mini App and
   does not create any new wishlist merely from navigating.
4. Following the `home` action opens the standard Mini App home screen and does not create any new
   wishlist merely from navigating.
5. The menu-to-Mini-App transition behavior is verified for both supported product languages:
   Russian (RU) and English (EN).
6. Launching the Mini App with an invalid or malformed navigation parameter triggers safe recovery:
   the user receives a usable, non-failing outcome without private data exposure or implicit
   wishlist creation.

## Task Description

### Functional scope

This task covers automated end-to-end acceptance verification of the handoff from the Telegram bot
menu into the Mini App:

- Obtaining the navigation targets for the `create`, `collection`, and `home` menu actions from the
  bot entry flow.
- Opening those targets in the Mini App under a prepared, authenticated user session.
- Verifying that each destination displays its intended screen and that navigation alone produces no
  implicit wishlist creation.
- Covering both Russian and English user language contexts.
- Verifying safe recovery when an invalid launch parameter is supplied.

This task does not change product behavior or add new user-facing features unless a discrepancy
between the bot menu and Mini App entry is uncovered; its purpose is end-to-end verification of the
existing contract established in WISHENKA-27.

### Non-functional requirements

- Verification must be deterministic and repeatable without requiring manual intervention or live
  external Telegram infrastructure.
- Safe recovery checks must confirm that invalid parameters do not leak private wishlist data or
  confirm whether hidden targets exist.
- Verification must not leave behind side effects or mutate shared user state outside isolated test
  runs.

### Constraints and assumptions

- Russian and English are the supported product languages.
- A prepared user session represents an existing Telegram participant interacting with the bot and
  Mini App.
- How the user session is seeded, how the Mini App is hosted during verification, and how assertions
  are structured are architectural and implementation decisions for subsequent steps.

### Business entities

- **User:** A Telegram participant with an established session and a language preference (Russian or
  English).
- **Bot Menu:** The set of navigation actions presented by the bot after entry, including list
  creation (`create`), personal wishlist collection (`collection`), and standard Mini App entry
  (`home`).
- **Mini App Screen:** The user-facing destination within the Mini App corresponding to the selected
  bot menu action or safe recovery state.
- **Wishlist:** A user's gift list that must only be created through an explicit user action, never
  solely by navigating from the bot menu.

### Scenarios

1. **Create transition:** A user with a prepared session in RU or EN selects the `create` action from
   the bot menu. The Mini App opens on the list-creation screen, and the user's wishlist count
   remains unchanged.
2. **Collection transition:** A user with a prepared session in RU or EN selects the `collection`
   action from the bot menu. The Mini App opens on the user's wishlist collection screen, and no new
   wishlist is created.
3. **Home transition:** A user with a prepared session in RU or EN selects the `home` action from
   the bot menu. The Mini App opens on its standard home screen, and no new wishlist is created.
4. **Invalid parameter recovery:** A user with a prepared session launches the Mini App with an
   invalid or unrecognized navigation parameter. The Mini App recovers safely to a usable state
   without exposing private information or creating a wishlist.

## Q&A

- **Why is this needed?** To close the verification gap identified in `WISHENKA-27` tech debt
  (`ai-tasks/WISHENKA-27/60-tech-debt.md`): currently the bot menu and Mini App are verified in
  isolation, so a mismatch in launch targets or an accidental write-on-entry could go undetected.
- **What defines the expected behavior?** The entry and navigation requirements from `WISHENKA-27`
  (`ai-tasks/WISHENKA-27/10-requirements.md`), the product concept in `specs/00-high.md`, and the
  bot scenarios in `in-docs/bot-scenarios.md`.
- **Does this task cover shared wishlist links or gift reservations?** No. Shared-link viewing,
  reservations, and invitation confirmation are already covered by existing end-to-end checks; this
  task focuses specifically on the bot menu's `create`, `collection`, and `home` transitions, RU/EN
  coverage, absence of implicit wishlist creation, and invalid-parameter recovery.
