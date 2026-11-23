# WISHENKA-296: No empty wishlist is created when the user leaves the creation flow

## Goals

A user who only looked at "Create wishlist" and changed their mind must not end up with a new,
unwanted, empty wishlist. Today every such visit leaves clutter on the home screen that the user
never asked for and has to clean up (the owner can now delete a list, WISHENKA-295, but should not
need to). A list must appear only as the result of a deliberate decision: the user supplies the
data the form asks for and explicitly confirms. This keeps the user in control of their own
lists and keeps the lists section trustworthy (every list in it is one the user chose to make).

Implementation language: Python, JavaScript, HTML and CSS.

## Task Description

Reported behaviour (Bug, Jira WISHENKA-296): the user opens the wishlists section, presses
"Create wishlist", fills in nothing, leaves the creation flow (closes it or goes back) and finds
a new empty wishlist in the list. The reporter expects that leaving or cancelling creates
nothing, that a list appears only after explicit confirmation and satisfaction of the form's
validation rules, and that this is identical in the Telegram Mini App and in a plain mobile
browser. The reporter prescribes neither the cause nor the fix.

### Facts found in the product (see Q&A for sources)

- There is currently no creation form and no confirmation step. Pressing "Create wishlist"
  itself creates an empty active personal list at once and opens it (Q&A, Fact F1).
- This is not an accident: the functional specification (in-docs/spec.md 4.2) and the
  developer documentation state that a tap on "Create" automatically creates an empty personal
  list and takes the user to its wishes. This bug therefore reverses a documented product rule
  (Q&A, D1).
- Wishlist entry points: the Mini App home screen button is the only place that creates a list.
  The bot never creates a list itself; its "Create wishlist" buttons only open the Mini App. The
  server-rendered web pages (HTMX) contain no wishlist creation (Q&A, F3).

### Business entities

- **User (future owner):** the person who wants a new personal list.
- **Creation flow:** the sequence from pressing "Create wishlist" until the user confirms or
  leaves. It shows the form fields of a new list.
- **Wishlist details entered at creation:** title (required), description, event name and event
  date (optional) as defined for list settings (in-docs/spec.md 4.2, 4.3; doc/dev/miniapp.md,
  settings fields).
- **Explicit confirmation:** the user's deliberate "Create" action on the form.
- **Cancellation:** any way of leaving the flow without confirming: a "Cancel" action, the back
  control, closing the app or the Telegram window, reloading, switching to another screen.

### Functional requirements

1. **Nothing is created before confirmation.** Pressing "Create wishlist" opens the creation
   flow and creates no list. A wishlist exists only after the user explicitly confirms the form
   with valid data.
2. **A clear form with Create and Cancel.** The flow shows the fields of a new list, a "Create"
   action and a "Cancel" action. The title is required (Q&A, D2); description, event name and
   event date are optional. Creation-time validation of the title (non-blank, 1-255
   characters) is new behaviour: today the limit is only documented, not enforced for lists
   (Q&A, F4). The event date follows the existing settings behaviour (Q&A, F5).
3. **Validation before creation.** "Create" with a missing or invalid title (empty, blank,
   or over the allowed length of 255 characters) does not create a list; the user stays in the flow, sees a
   clear message next to the problem and keeps everything they have typed. The same applies to invalid
   optional fields.
4. **Leaving without confirming creates nothing.** Cancel, back, closing the flow, closing the
   Mini App or browser tab, reloading, switching to another section, or losing the connection
   at any moment before the confirmation leaves the account with exactly the lists it had
   before. This holds both for an untouched form and for a partly filled form.
5. **No data survives a cancellation.** Whatever was typed into a cancelled flow is not saved as
   a list. The next time the user opens the flow the form is empty (a remembered draft is out of
   scope).
6. **Successful creation works as before for the user.** After a confirmed, valid creation the
   list exists with the entered details, it is active, personal and owned by the user, it
   appears in "My wishlists" at once, and the user is taken to its page where the first wish can
   be added. The list gets the same tokens, links and defaults as any list created today.
7. **Failure of creation.** If the confirmed creation fails (network, server), no list is shown
   as created, the user sees the existing "could not create" message, keeps the typed data and
   can retry. When the user saw a failure because the server rejected or failed the request, a
   retry does not produce a second list. Known limitation: if the request succeeded but the
   response was lost, a retry can create a second list, because the creation request has no
   idempotency key today (Q&A, F6); this is not solved by this task.
8. **Double-submit protection remains.** Several quick taps on "Create" (and on the entry button),
   pressing Enter in the form, and any mix of taps and Enter presses, produce at most one list
   and at most one creation request. The existing protection against
   repeated taps must not be weakened (constraint; the Debt WISHENKA-312 re-checks the guard and
   the test `test_create_wishlist_burst_sends_a_single_post` after this bug is fixed).
9. **Reopening the section.** After a cancelled or abandoned flow, reopening the wishlists
   section (also after reloading or restarting the app) shows no list that came from the
   cancellation. Lists created through confirmed creation remain.
10. **All entry points behave the same.** The home-screen "Create wishlist" button and any
    other place inside the app that offers creation lead to the same flow with the same rules.
    The deep link from the bot (the "Create wishlist" buttons of the bot menu and of the bot's
    "no list available" message, start parameter `create`) keeps its current behaviour: the app
    opens on the home screen and the form is not opened automatically (no new behaviour,
    Q&A D9). Opening the app through that link and leaving creates no list. The bot itself never
    creates a list.
11. **Leaving works without Telegram controls.** The in-app "Cancel" works on its own, without
    any Telegram-provided control, and returns the user to the home screen. Browser back,
    Telegram's close or back control, closing the tab and reload in the middle of the form
    create nothing (Q&A D6, D8).
12. **Same in Mini App and in a plain mobile browser.** Behaviour, texts and validation are
    identical in the Telegram Mini App and in a mobile browser opened outside Telegram, in both
    languages and all themes.
13. **Texts, accessibility, touch.** All new visible and announced texts (form labels,
    "Create", "Cancel", validation messages) exist in Russian and English with the same
    meaning. The form and its buttons are reachable by keyboard and screen reader; after
    cancelling or creating the user lands on a screen where the next step is obvious (home
    screen after cancel, the new list after creation); touch targets are at least 44 px; no
    horizontal overflow at 320 px width.
14. **Other behaviour unchanged.** Editing list settings, archiving, deleting (WISHENKA-295),
    restoring, sharing, favorites, history and surprise secrecy are not changed. Lists that were
    already created empty before the fix are left as they are (no automatic cleanup, Q&A, D4).

### Non-functional requirements and constraints

- Works identically in the Telegram Mini App and a mobile browser.
- The reservation secrecy invariant (specs/00-high.md 4.3) is unaffected: the creation flow shows
  no reservation information.
- The user data typed in a cancelled flow is not stored or sent anywhere.
- The double-submit protection stays (requirement 8).
- Existing tests stay green except where they assert the old click-time creation; such tests are
  updated to the new behaviour as part of this task, and their intent (a burst of taps sends one
  creation request) is preserved.
- Lists that already exist with an empty title (created before the fix) keep being shown with
  the existing "untitled wishlist" fallback name; that fallback stays for them (Q&A D4). For
  lists created after the fix it is no longer reachable (Q&A D2 consequences).
- Out of scope: saved drafts, templates, creating a collaborative list directly at creation,
  clean-up of already existing empty lists, creating lists from the bot, changes to retention,
  deletion or archive rules.

## User Stories

- As a user, I press "Create wishlist" and can change my mind without leaving any trace, so my
  lists stay as I want them.
- As a user, I fill in a title and confirm, so my new list appears and I can add the first wish.
- As a user, I get a clear message if the title is missing and do not lose what I typed.
- As a user who opens the Mini App through the bot's "Create wishlist" button and closes it
  immediately, I still get no list.
- As a user, I tap "Create" several times in a hurry and still get exactly one list.
- As a Russian or English speaking user on Telegram or on a plain mobile browser, I get the same
  flow and texts.

## Definition of Done

1. Closing or leaving the empty creation flow (Cancel, back, closing the app/tab, reload) creates
   no list; the number of the user's lists is unchanged (acceptance 1).
2. Cancelling or leaving after partial filling creates no list (acceptance 2).
3. Explicit "Create" with valid data creates exactly one list with the entered details and shows
   it in "My wishlists" and opens it (acceptance 3).
4. "Create" with an invalid or missing title creates nothing and keeps the typed data with a
   clear message.
5. After cancellation, reopening or reloading the section shows no list that came from the
   cancelled flow (acceptance 4).
6. The home-screen creation button behaves per 1-5; the bot's deep link opens the home screen
   and nothing is created; the bot creates no list itself.
7. The behaviour, texts and validation are identical in the Telegram Mini App and a plain mobile
   browser, in Russian and English (acceptance 5).
8. A burst of taps on "Create", Enter-key submits, or any mix of the two produces at most one
   list and at most one creation request.
9. A failed creation shows a failure message, creates no list and can be retried without a
   duplicate.
10. Automated checks reproduce the defect first (fail before the change) and pass after; archive,
    delete, restore and settings behaviour and their tests remain green.
11. The documents and tests named in D1 (in-docs/spec.md 4.2 and UC-01, doc/dev/miniapp.md goal 1
    and "Frictionless Creation", the click-time creation tests) are updated to the new rule as
    part of this task; Step 8 may edit in-docs/spec.md as well as doc/dev.

## Q&A

- **Why this change?** Jira WISHENKA-296: unrequested empty lists appear when the user merely
  leaves the creation flow; a list must exist only after explicit, valid confirmation. Business
  reason: the user's control over their own data and a clean lists section.
- **F1 (fact, root cause). Where does the empty list come from?** The home button handler creates
  the list on the click itself: it sends a creation request with an empty body and then opens the
  new list (wishenka/web/static/miniapp.js:379-383; button `home-create-btn`, the click goes
  through the double-tap guard `withPending`/`pending`, miniapp.js:87-105, 379). The server
  accepts an empty body: the title and all fields are optional (`WishlistInput`,
  wishenka/web/routes/wishlists.py:34-40; `create_wishlist` route :177-204) and the service
  creates an active list with the empty title (wishenka/wishlists/service.py:585-649). So there
  is no form to cancel; "leaving the form" in the report is leaving the new list's page, which
  already exists. The "Back" button of that page is wired inside `showList` to `showHome` (miniapp.js:777),
  so going back only shows the home screen and cannot undo the creation.
- **F2 (fact). Is this by design?** Yes. in-docs/spec.md 4.2: "При создании вишлиста через
  Mini App автоматически создаётся пустой личный список. Пользователь сразу попадает на
  страницу желаний ... Название, описание, событие и другие настройки могут задаваться
  позднее." UC-01 (spec.md:417) matches. doc/dev/miniapp.md goal 1 and section "Frictionless
  Wishlist Creation" (lines 12, 435-441) and the test docstring in
  tests/test_cross_screen_comfort_browser.py:473 ("WISHENKA-296 may change this flow") record the
  same. The bug and the specification therefore conflict; see D1.
- **F3 (fact). Entry points.** Mini App home button: miniapp.js:379. Deep link `startapp=create`:
  miniapp.js:976-984 only opens the home screen and focuses the first button, it creates
  nothing. Bot: `bot.capture.btn_create_wishlist` opens the Mini App with the `create` start
  parameter (wishenka/bot/capture.py:182-190); bot menu "Create wishlist" does the same
  (in-docs/bot-scenarios.md:15, entry table row "Create wishlist"; bot menu button `create`,
  wishenka/bot/entry.py:88); the bot has no code that creates a wishlist. Server-rendered
  pages (wishenka/web/templates, routes) have no creation; the only creation endpoint is
  `POST /api/wishlists`. Hence requirements address the Mini App flow (which also runs in a plain
  mobile browser) and the deep link; bot creation scenarios do not exist.
- **D1. Reverse spec 4.2?** Decision taken in autonomous run; flagged for product-owner
  confirmation: yes, because the ticket text demands that no list appears without explicit
  confirmation and no product owner is reachable in this run. Consequence: the new rule is
  "creation happens only after explicit confirmation of a valid form", and the following
  artifacts that state the old rule are updated as part of this task: in-docs/spec.md 4.2
  (lines 80-84, including "title may be set later" at line 84), in-docs/spec.md UC-01 (line
  417), doc/dev/miniapp.md goal 1 "Frictionless Creation" (line 12) and the section
  "Frictionless Wishlist Creation" (lines 435-441), in-docs/bot-scenarios.md:15 (the bot's "Create
  wishlist" row says it opens the Mini App "at the list creation flow"; reworded to "opens the
  Mini App at the home screen, where creation starts"), and the tests that assert click-time
  creation: tests/test_cross_screen_comfort_browser.py:465-473 (burst test and its docstring) and
  tests/test_home_overview_ui.py:887 (asserts `POST /api/wishlists` with body `{}`); other tests
  that use the creation endpoint directly are rechecked in Step 3. Step 8 may therefore edit
  in-docs/spec.md as well as doc/dev. specs/00-high.md is not contradicted: its list-creation
  statements (line 60, "unlimited number of personal wishlists") say nothing about creating
  empty lists automatically.
- **F4 (fact). Title limits.** The 1-255 limit for a list title appears only in documentation
  (doc/dev/miniapp.md:447). In code `WishlistInput.name` is a plain optional string
  (wishenka/web/routes/wishlists.py:37); a 255-character limit exists only for wish titles
  (wishenka/items/schemas.py:32, 57). So title validation at creation is new behaviour; making
  the settings edit (PATCH, routes/wishlists.py:455+) follow the same rule is out of scope and is
  a follow-up candidate.
- **F5 (fact). Event date.** The optional event date is a date-time chosen with a
  `datetime-local` input, interpreted as UTC and sent as an ISO-8601 UTC timestamp, or sent as
  empty to mean no event (miniapp.js:673-702; doc/dev/miniapp.md:449-451). No server or client
  rule limits it to past or future dates or to a range. The creation form uses the same
  behaviour; no new date constraint is introduced.
- **F6 (fact). No idempotency key.** `POST /api/wishlists` has no idempotency key
  (routes/wishlists.py:177-204), so a retry after a lost response can create a duplicate.
- **D2. What is the "form's validation"?** The ticket speaks of "validation rules" of the form,
  but no form exists. Decision taken in autonomous run; flagged for product-owner confirmation:
  the form has one required field, the title (non-blank, 1-255 characters; new behaviour, F4),
  plus the optional description, event name and event date. Alternatives considered:
  (a) minimal confirm step with no fields (a "Create an empty list?" dialog): simplest and keeps
  near one-tap creation, but there is nothing to validate, the user can confirm by habit and
  still produce empty lists, and it does not match "satisfying the form's validation rules";
  (b) form with an optional title: allows empty lists again, so the clutter the bug is about
  remains possible with one extra tap;
  (c) form with no required fields: same drawback as (b).
  The required non-blank title was chosen because it is the minimal input that makes every
  created list meaningful and gives the ticket's validation rules something to check.
  Consequences: creation is no longer one tap; "title may be set later" (in-docs/spec.md:84) no
  longer holds for creation; the placeholder `Мой вишлист` and the
  `miniapp.common.untitled_wishlist` fallback become unreachable for lists created after the fix
  (they remain for lists created earlier with an empty title).
- **D3. What does "Cancel" lead to?** The home screen with the lists as they were. Reason:
  the user came from there.
- **D4. Existing empty lists?** Not touched; no automatic cleanup or migration. The owner can
  delete them (WISHENKA-295). Reason: the ticket is about new creations; removing user data
  automatically is risky.
- **D5. Drafts?** Not preserved after cancel (requirement 5). Reason: simplest rule meeting
  "reopening shows no lists created by cancellation".
- **D6. Reload or closing the app in the middle of the form?** Counts as cancellation: nothing
  is created, nothing is kept.
- **D7. Double-submit constraint.** The guard and `test_create_wishlist_burst_sends_a_single_post`
  (tests/test_cross_screen_comfort_browser.py:465) describe the click-time creation; they must
  stay meaningful after the change (one request per burst of taps on the confirming "Create");
  Debt WISHENKA-312 re-checks them after this bug lands.
- **D8. Plain mobile browser vs Mini App.** The product already serves the same Mini App page
  to both; the requirement is that nothing in the new flow depends on Telegram-only features
  (for example a Telegram-provided back button) for the guarantee "leaving creates nothing".
  With no creation before confirmation, every exit is safe by construction in both.
- **D9. Deep link.** `startapp=create` keeps landing on the home screen with focus on the first
  button; the form is not opened automatically. Reason: no new behaviour is needed to satisfy the
  ticket, and nothing is created by opening the link.
- **Sources.** Jira WISHENKA-296; specs/00-high.md (4.1-4.2 list creation and safe removal,
  4.3 surprise secrecy); in-docs/spec.md 4.2, 4.3, 8, UC-01; in-docs/bot-scenarios.md "Entry and
  navigation"; doc/dev/miniapp.md sections 1 and 2; code references above.
