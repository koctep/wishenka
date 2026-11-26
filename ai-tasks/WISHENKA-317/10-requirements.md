# WISHENKA-317: Focus and accessibility of the wishlist delete panel

## Goals

An owner who confirms deletion after a wishlist can no longer be restored is
returned to the home screen. Today that failure is only something the owner
can see. It is not announced, and keyboard focus stays on the delete
confirmation even though that panel is no longer on the page. The owner is
left without a clear place to continue.

On the same screen, the delete confirmation and the wishlist settings form
each have a Cancel. In Russian and in English those two controls share one
accessible name, so a screen-reader user scanning the buttons, and a person
using speech control, cannot tell which Cancel discards the settings and
which one closes the delete confirmation.

This task makes the failure announced on the home screen, moves focus to that
screen, and gives the delete confirmation's Cancel its own accessible name in
both languages. It comes from the wishlist deletion work (WISHENKA-295): the
focus and announcement gap, the shared Cancel name, and the missing coverage
for both. It is not a blocker for other work. Who may delete, what deletion
does, and the retention promise stay as they are.

Implementation language: JavaScript for the owner's experience in the client,
Python for the Russian and English accessible name.

## User Stories

- As an owner, when I confirm deletion and the wishlist can no longer be
  restored, I hear that the deletion did not complete and my place on the
  page is the home screen, so I am not left on a panel that has gone.
- As an owner who uses a keyboard, that same outcome leaves me on the home
  screen heading, so I can continue from the screen I am actually looking at.
- As an owner who uses a screen reader or speech control, the Cancel that
  closes the delete confirmation has its own name in my language, so I do not
  confuse it with the Cancel that discards settings changes.
- As an owner, cancelling deletion still changes nothing, and a deletion that
  succeeds still returns me to the home screen with the success I already
  know.
- As a Russian or English speaking owner, the new accessible name matches the
  language I selected and means the same thing in both.

## Definition of Done

1. When the owner confirms deletion and the wishlist can no longer be
   restored, the home screen is shown, the delete confirmation is gone, and
   the failure is announced on that home screen. A visible status alone does
   not satisfy this.
2. In that same outcome, keyboard focus is on the home screen heading, the
   heading a successful deletion already uses. Focus is not left on the
   removed confirmation and does not fall to the page background.
3. The failure wording the owner already sees for this outcome stays. No
   success message is shown. The list is not deleted again.
4. The delete confirmation's Cancel has its own accessible name in Russian
   and in English. That name is not "Cancel" and not "Отмена".
5. The settings form's Cancel keeps the accessible name "Cancel" in English
   and "Отмена" in Russian. Its visible label stays the same.
6. While the delete confirmation is open, the two Cancels can be told apart
   by their accessible names in both languages, including by a speech command.
7. Cancelling or leaving the confirmation still changes nothing. A successful
   deletion still returns the owner to the home screen, announces success, and
   focuses the home screen heading. Any other failure still keeps the
   confirmation open, announces the failure there, and returns focus to the
   confirm choice.
8. An interface check covers the outcome in item 1 and item 2 in Russian and
   in English. A browser check covers that same outcome and the distinct
   accessible name in item 4, in both languages.
9. The work does not block other work. Deletion rules, the retention promise,
   and who may delete stay as they are.

## Task Description

WISHENKA-295 let the owner delete their own wishlist from its settings, after
an explicit confirmation, and return to the home screen when deletion
succeeds. One outcome was left unfinished for people who do not rely on sight
alone. If the owner confirms and the wishlist can no longer be restored, the
product already sends the owner back to the home screen and shows a failure
as a status. That failure is not announced, and focus is left on the
confirmation that has been removed. Separately, the confirmation's Cancel and
the settings form's Cancel share one accessible name in both languages.

The business need is that the owner who cannot restore the list is told, and
knows where they are, and that the two Cancels are distinguishable. This task
does not change the deletion itself.

### Business entities

- **Owner:** the only person who may delete a wishlist and who sees the
  delete confirmation in the wishlist settings.
- **Wishlist:** the list named in the confirmation. This task cares about the
  case where that list is already deleted and can no longer be restored.
- **Delete confirmation:** the panel that names the wishlist, warns about the
  consequences, and offers confirm and Cancel. Cancel closes the panel and
  leaves the list unchanged.
- **Settings form:** the form for the wishlist title, description, and event.
  Its Cancel discards unsaved edits. It is on the screen together with the
  delete confirmation.
- **Home screen:** the list of the owner's wishlists. Its heading is the place
  a successful deletion already leaves keyboard focus.
- **Failure for a list that can no longer be restored:** the message the owner
  already sees as a status in this outcome. It says the deletion could not be
  completed, nothing was changed, and the owner may try again. This task
  makes that same message announced.
- **Accessible name:** the name assistive technology and speech control use
  for a control. It may be more specific than the visible label.

### Functional requirements

1. **Announced failure on the home screen.** When the owner confirms deletion
   and the wishlist can no longer be restored, the owner is taken to the home
   screen and the delete confirmation is no longer there. The failure is
   announced on the home screen in the selected language. The owner still
   sees it. Seeing it without an announcement is not enough. The announcement
   is not attached to the confirmation that has already been removed.
2. **Focus on the home screen.** In that same outcome, keyboard focus moves to
   the home screen heading, the same heading a successful deletion already
   focuses. The heading can receive focus. Focus does not remain on the
   removed confirmation and does not drop to the page background.
3. **The failure wording stays.** The announced and visible failure stays the
   one the owner already gets for this outcome: the deletion could not be
   completed, nothing was changed, and the owner may try again. It is not a
   success, and it does not say the list was deleted just now. Russian and
   English keep the meaning they already have.
4. **The list is unchanged by this refusal.** Confirming in this outcome does
   not delete the wishlist again, does not start a new retention period, and
   does not restore it. Other lists and the owner's profile stay untouched.
5. **A distinct accessible name for the delete Cancel.** The visible label of
   that Cancel stays "Cancel" in English and "Отмена" in Russian. Its
   accessible name, in the selected language, is:
   - English: Cancel deleting "{title}"
   - Russian: Отменить удаление «{title}»
   "{title}" is the wishlist title already shown in the confirmation. If the
   wishlist has no title, the accessible name uses the product's existing name
   for an untitled wishlist. The accessible name is not "Cancel" and not
   "Отмена".
6. **The settings Cancel stays.** The settings form's Cancel keeps the visible
   label and the accessible name "Cancel" in English and "Отмена" in Russian.
   While the delete confirmation is open, the two Cancels are present
   together and their accessible names differ in both languages.
7. **Cancel still changes nothing.** Choosing the delete Cancel, or leaving
   the confirmation without confirming, does not delete the wishlist and does
   not change its wishes, members, links, or settings. Focus returns to the
   control that opens the confirmation, as it does today.
8. **Success and other failures stay.** A successful deletion still takes the
   owner to the home screen, shows and announces the existing success, and
   focuses the home screen heading. A failure for any other reason still
   leaves the confirmation on the page, announces the existing failure there,
   and returns focus to the confirm choice so the owner can try again.
9. **Languages.** The announcement and both accessible names follow the
   selected language. Russian and English carry the same meaning. The visible
   confirmation, including both choices, stays readable as WISHENKA-295
   already requires.
10. **Coverage.** An interface check shows, in Russian and in English, that
    the outcome in requirements 1 and 2 announces the failure on the home
    screen and places focus on the home screen heading. A browser check shows
    the same outcome and shows that the delete Cancel's accessible name is
    the one in requirement 5, distinct from the settings Cancel, in both
    languages.

### Non-functional requirements

- A screen-reader user hears the failure without having to hunt for the
  status, and lands on the home screen heading.
- A speech-control user can address the delete Cancel by its own accessible
  name while the settings Cancel is also on the screen.
- The announcement and the focus move happen as part of returning to the home
  screen, with no extra step for the owner.
- No new personal data is shown, stored, or sent. The title inside the
  accessible name is the owner's own wishlist title, already shown in the
  confirmation. Surprise secrecy is unchanged.
- The experience is the same in the Telegram Mini App and in a normal mobile
  browser. Themes, touch targets, and layout stay as they are.
- This work is not a blocker for other work. It does not change the speed or
  the outcome of deletion.

### Constraints and assumptions

- WISHENKA-295 remains the source of the deletion rules. WISHENKA-316 remains
  the source of the single retention rule. This task only finishes the
  announcement, the focus, and the accessible name.
- The failure wording for a wishlist that can no longer be restored stays the
  wording the owner already sees. This task does not replace it with the
  sentence used when a restore is refused.
- The visible labels "Cancel" and "Отмена" stay on both controls. Only the
  delete confirmation's accessible name changes.
- Out of scope: who may delete; the retention period; repeating a deletion
  that is still restorable; log wording; a delete control on the plain web
  list screen; notices to gifters; favorite or history rows; cross-browser
  engines beyond the browser coverage this product already uses for the Mini
  App; changing the settings Cancel; changing success or the other failure
  paths.
- Assumption: "announced" means assistive technology speaks the failure
  because it is part of the home screen the owner is on, not because the owner
  can read a status with their eyes.
- Assumption: the accessible names in requirement 5 are the product wording.
  They include the wishlist title so two lists, and the two Cancels, stay
  distinct.

## Q&A

- **Why is this needed?** An owner who confirms deletion when the wishlist can
  no longer be restored is sent home, but the failure is only visible and
  focus is left on a panel that is gone. The delete Cancel and the settings
  Cancel also share one accessible name in Russian and in English, so
  assistive technology and speech control cannot tell them apart. Source:
  Jira WISHENKA-317, from the WISHENKA-295 follow-up on that focus gap, that
  shared name, and the missing coverage. The follow-up is not a blocker.
- **What should stay the same?** Who may delete, what a successful deletion
  does, the retention promise, the visible Cancel labels, the settings
  Cancel's accessible name, cancel-without-change, the success return to the
  home screen, and the other failures that keep the confirmation open.
- **Which message is announced?** The failure the owner already sees as a
  status for this outcome. The wording does not change. It must be announced
  on the home screen, not only shown.
- **Where does focus go?** To the home screen heading, the same place a
  successful deletion already leaves the owner.
- **What is the delete Cancel's accessible name?** English: Cancel deleting
  "{title}". Russian: Отменить удаление «{title}». The visible label stays
  "Cancel" / "Отмена". An untitled wishlist uses the product's existing
  untitled name.
- **Does the plain web list screen gain a delete control?** No. That remains
  a separate product decision.
- **What was decided without a further product question?** The ticket states
  the outcome: announce the failure, move focus off the removed panel, give
  the delete Cancel its own accessible name in both languages, and add
  interface and browser coverage. The names above are fixed so both languages
  mean the same thing and include the wishlist title. The visible labels stay,
  because the ticket asks for an accessible name.
