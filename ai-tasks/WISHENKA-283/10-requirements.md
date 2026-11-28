# WISHENKA-283: Parallel suite keeps three language checks green

## Goals

Wishenka is Russian and English. A person who opens a shared list or an
invite with no account, a person who receives an occasion reminder, and a
person who opens the Mini App home must still see the language rules below.

Maintainers prove those rules by running the check suite together with the
other checks, four at a time (`PYTEST_JOBS=4`). During WISHENKA-98 that run
printed FAILED for the three checks named below, then stopped after 600
seconds at 47 percent, before any failure detail was printed. On base commit
`7ef1b53`, and again on the WISHENKA-98 tree, each of the three checks passed
twice when run alone.

Passing alone is not the product rule. Stopping the full suite at 600 seconds
is not the outcome. The three checks must finish green while other checks run
beside them.

This is a Debt item (3 points, Medium, labels `failing-test` and
`tech-debt`). Implementation language: Python.

## User Stories

- As an **anonymous visitor** of a public share link or an invite link, I see
  the page in the language I asked for on the link, otherwise in my browser
  language when that language is Russian or English, otherwise in English.
  Opening the page does not create an account for me.
- As a **person who receives an occasion reminder**, I receive English when
  my stored language is missing or unsupported, and I still receive English
  when my account has no stored language even if my Telegram language is
  Russian. Refreshing that reminder keeps the same English text.
- As that person, a delivery problem that is not a missing language is still
  a failure. It is not replaced by an English reminder.
- As a **Mini App user** on the home screen, I see the shared Russian and
  English labels for settings, the home title, create wishlist, viewing
  history, and my wishlists. The home shell uses that shared catalog.
- As a **maintainer**, I can trust a suite run with other tests in parallel
  (`PYTEST_JOBS=4`) to show the three checks below as passed. A run that only
  passes them alone, or a run cut off at 600 seconds, does not give me that
  trust.

## Definition of Done

1. **Share and invite language.** For both a public share link and an invite
   link, with no account created by the visit:
   - no language on the link and no browser language yields English;
   - an explicit Russian tag on the link (`ru-RU`) yields Russian;
   - an explicit English tag on the link (`en-US`) yields English even when
     the browser language is Russian;
   - an unsupported tag on the link (`de`) yields the browser language when
     that language is Russian, and English when the browser language is
     absent;
   - a Russian browser language and no tag on the link yields Russian;
   - an unsupported browser language yields English.
2. **Occasion reminder language.** When the stored language is unsupported,
   the occasion reminder is English, and a refresh of that reminder stays
   English. When the account has no stored language, the reminder and its
   refresh stay English even if the Telegram language is Russian. A failure
   that is not a missing language (the standing check removes the delivery
   destination) is still reported as a failure.
3. **Mini App home labels.** The home page carries the shared Russian and
   English catalog. Settings, the home title, create wishlist, viewing
   history, and my wishlists match that catalog in both languages. The Mini
   App script reads those labels from the shared catalog (`nav.settings`,
   `miniapp.home.title`, `miniapp.home.create_wishlist`,
   `miniapp.home.viewing_history`, `miniapp.home.my_wishlists`) and does not
   keep a separate home-only dictionary.
4. **Parallel proof.** These three checks pass in one suite run that also
   runs other tests with `PYTEST_JOBS=4`. All three live in
   `tests/test_i18n_unit.py`:
   - `test_anonymous_share_and_invite_locale_priority_chain`
   - `test_reminders_fallback_to_en_for_missing_user_locale_and_legacy_schema`
   - `test_miniapp_js_localizes_home_nav_shell_and_settings_label`
5. **Alone is not enough.** Each check passing twice in isolation, on
   `7ef1b53` or on the WISHENKA-98 tree, does not close this task.
6. **Cutoff is not the outcome.** A full-suite run that stops at 600 seconds
   and 47 percent, before failure detail is printed, is not a pass and is
   not the fix.
7. **Left to other tasks.** WISHENKA-357, WISHENKA-298, and WISHENKA-311 are
   not fixed here. `wishenka/web/static/app.js` does not gain the substring
   `receipt`.

## Task Description

### Problem

The three checks guard language for anonymous share and invite pages, for
occasion reminders when language is missing, and for the Mini App home shell.
They already pass when run alone. On the parallel suite run during
WISHENKA-98 they were reported FAILED, and the run then ended at the 600
second limit at 47 percent with no failure detail. The cause is not diagnosed
in this step. The baseline commit on the ticket is `7ef1b53`. This step
records that incident and does not re-run the full suite.

### Scope

- The language rules in the Definition of Done stay true.
- A maintainer sees the three named checks pass while other tests run in
  parallel (`PYTEST_JOBS=4`).

### Constraints

- Do not accept isolation-only success as the close of this task.
- Do not accept a 600-second full-suite timeout as the fix.
- Do not fix WISHENKA-357, WISHENKA-298, or WISHENKA-311 in this task.
- Do not edit `wishenka/web/static/app.js` to add the substring `receipt`.
- Supported interface languages stay Russian and English. English remains the
  fallback when the requested language is missing or unsupported.

### Non-goals

- A new language, a new share page, a new reminder kind, or a new home label.
- Raising the suite time limit so a hung run counts as success.
- Repair of WISHENKA-357, WISHENKA-298, or WISHENKA-311.
- Any edit of `wishenka/web/static/app.js` that introduces `receipt`.
- Other failing checks from the sprint.

### Main entities

- **Anonymous visitor** — a person who opens a public share link or an invite
  link and has no account. The visit must not create one.
- **Language choice** — the tag on the link, then the browser language, then
  English. Only Russian and English are shown.
- **Reminder recipient** — the person who should get an occasion reminder.
  Missing or unsupported stored language, and an account with no stored
  language, yield English. A real delivery failure stays a failure.
- **Occasion reminder** — the message about an upcoming list event, including
  the same text when the reminder is refreshed.
- **Mini App home** — the shell the signed-in person sees first, including
  navigation and the settings label, taken from the shared catalog.
- **Parallel suite run** — the maintainer's run of these checks together with
  other checks at `PYTEST_JOBS=4`. That run is the proof this task requires.

## Q&A

- **Q:** Why does this task exist?
  **A:** Maintainers must be able to trust that anonymous share and invite
  language, English occasion reminders when language is missing, and the
  Mini App home labels still hold when the suite runs with other tests.
  During WISHENKA-98, `make test PYTEST_JOBS=4` printed FAILED for the three
  checks and then stopped at 600 seconds and 47 percent before any traceback.
  Each check passed twice alone on `7ef1b53` and on the WISHENKA-98 tree.
  Alone is not enough, and the timeout is not the fix.

- **Q:** What must stay true for a visitor with no account?
  **A:** On both the share link and the invite link, the link's language wins
  over the browser language, and the browser language wins over English.
  Unsupported languages fall through that chain to English. The visit does
  not create an account.

- **Q:** What must stay true for occasion reminders?
  **A:** Missing or unsupported stored language yields an English reminder,
  including when the account has no stored language and the Telegram language
  is Russian. Refresh keeps that English text. A failure that is not a
  missing language is still a failure.

- **Q:** What must stay true on the Mini App home?
  **A:** Settings, the home title, create wishlist, viewing history, and my
  wishlists come from the shared Russian and English catalog. The home script
  uses that catalog.

- **Q:** Which other work stays outside this task?
  **A:** WISHENKA-357, WISHENKA-298, and WISHENKA-311. Also any addition of
  the substring `receipt` to `wishenka/web/static/app.js`.
