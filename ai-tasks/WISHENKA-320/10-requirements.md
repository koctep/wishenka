# WISHENKA-320: One name contract for a wishlist

## Goals

Creating a wishlist already requires a real name. Editing the same wishlist
can still wipe that name, and a name that is too long can be described as if
it were missing. A name made only of invisible marks looks blank to guests
and does not fall back to the usual untitled name. The description and the
event title are already accepted at creation with no extra character ceiling.
Editing must follow that same acceptance. This task does not choose a ceiling.

This task makes the name rule the same when a wishlist is created and when
its details are saved later, keeps the description and the event title inside
whatever creation already accepts, and tells the person the truth when the
name is too long. Wishlists that already have an empty name stay as they are
until someone saves them again. The work is not a blocker for other work.

Implementation language: Python for accepting or refusing wishlist details,
JavaScript for the create and edit experience in the Mini App.

## User Stories

- As an owner, I give a new wishlist a name I can see, so guests never open
  a list that looks untitled by accident.
- As an owner or an administrator, I cannot save the wishlist details without
  a real name, so a later edit cannot return the list to a blank name.
- As an owner, when my name is longer than allowed, I am told that it is too
  long, so I know to shorten it rather than to fill in a name I already typed.
- As an owner, a name made only of invisible marks is treated as no name, so
  the list is not stored with a title that looks empty.
- As an owner, I can still leave the description and the event title empty,
  and a later save accepts the same text creation already accepts, with no
  extra character ceiling added by this task.
- As an owner of a wishlist that already has an empty name, I can still open
  it under the usual untitled name, and the next save asks me for a real name.
- As a Russian or English speaking owner, in the Telegram Mini App or in a
  plain mobile browser, I get the same name rule and the same meaning.

## Definition of Done

1. Creating a wishlist stores a name of 1 to 255 characters after trimming.
   A missing, blank, or invisible-only name creates nothing and shows that
   the name is required.
2. Saving wishlist details follows that same name rule. Clearing the name, or
   replacing it with an invisible-only name, does not save and shows that the
   name is required. The stored wishlist stays unchanged.
3. A name longer than 255 characters is refused on create and on edit, in
   the app and by the service. The person sees that the name is too long, not
   that the name is missing, and keeps what they typed.
4. The description and the event title stay optional. Create and edit share
   one rule: each stays within whatever creation already accepts. Today that
   is no extra character ceiling. This task does not choose a ceiling. A
   later product decision can add one. Empty or spaces-only still means the
   field is not set.
5. A wishlist already stored with an empty name stays readable under the
   usual untitled name. Nothing renames or deletes it. The next save of its
   details succeeds only when that save supplies a real name.
6. The service refuses the same invalid names that the app refuses, including
   a save that bypasses the app. Description and event title follow the same
   acceptance creation already uses, with no extra character ceiling. The app
   and the service count a name's length the same way.
7. Checks cover the service, the create and edit experience, and a browser
   session: required name, invisible-only name, and a too-long name with the
   too-long message, on create and on edit, in Russian and in English. They
   also cover that the description and the event title stay within what
   creation already accepts, with no extra character ceiling on either.
8. The work does not block other work. Who may edit, event dates, sharing,
   and surprise secrecy stay as they are.

## Task Description

Creating a wishlist requires a name of 1 to 255 characters after spaces at
the ends are removed. That rule stops at creation. The owner, or an
administrator of a shared wishlist, can still save the details with the name
cleared. The description and the event title have no extra character ceiling
at creation, and this task does not add one. A name that is too long can be
reported as if the name were missing.
A name made only of invisible marks — zero-width spaces, word joiners,
byte-order marks, and right-to-left or left-to-right marks — is accepted,
displays as blank, and does not use the usual untitled name.

The product problem is one contract for the name of a wishlist, and the same
acceptance for the description and the event title that creation already
uses. Guests and the owner should see a name that was deliberately chosen,
and the same name should be accepted or refused whether it is entered at
creation or changed later. Description and event title stay inside that
existing acceptance. Today there is no extra character ceiling, and this task
does not choose a number. A later product decision can add a ceiling. This
follows the wishlist creation work (WISHENKA-296): the required name, the
wrong message for a long name, invisible-only names, and lists left with an
empty name. It is not a blocker for other work.

### Business entities

- **Owner:** the person who creates the wishlist and may edit its details.
- **Administrator:** a person the owner has allowed to manage the wishlist,
  including its details. The name rule applies to their saves as well.
- **Wishlist name:** the title guests and the owner see. Required whenever
  details are saved.
- **Description:** optional notes for guests.
- **Event title:** optional short name of the occasion, separate from the
  wishlist name.
- **Untitled name:** the usual fallback shown when a stored wishlist has no
  name. It stays for those existing lists only.
- **Create:** the confirmed creation of a new wishlist.
- **Edit:** a later save of the wishlist's details.

### Functional requirements

1. **One name rule.** On create and on edit, the name is required. After
   spaces at the ends are removed, it must be from 1 to 255 characters. A
   character is one Unicode code point, the same counting the product already
   uses for a wishlist name. Spaces in the middle count. The app and the
   service apply this rule before anything is stored.
2. **Invisible-only names are missing names.** If, after removing spaces at
   the ends, every remaining character is an invisible mark, the name is
   refused as missing. The marks covered are zero-width spaces, word joiners,
   byte-order marks, and right-to-left and left-to-right marks, including a
   mix of those marks and spaces. The person sees that a name is required.
   The invisible text is not stored. A name that also contains a visible
   character is a real name and is kept as entered, marks included.
3. **The too-long message.** When the trimmed name is longer than 255
   characters, create and edit do not save. The message says the name is too
   long. It must not say the name is missing. This is true in the app before
   the save, and when the service refuses a name the app did not catch.
4. **Description follows creation.** The description stays optional. Create
   and edit share one rule: it stays within whatever creation already
   accepts. Today that is no extra character ceiling. This task does not
   choose a ceiling. A later product decision can add one. Empty or
   spaces-only is allowed and means no description.
5. **Event title follows creation.** The event title stays optional and
   separate from the wishlist name. Create and edit share one rule: it stays
   within whatever creation already accepts. Today that is no extra character
   ceiling. This task does not choose a ceiling. A later product decision can
   add one. Empty or spaces-only is allowed and means no event. The event
   date is unchanged.
6. **Who must follow the rule.** The owner on create, and the owner or an
   administrator on edit. A member who cannot edit details, a guest, and the
   bot cannot rename a wishlist by this task. Who is allowed to edit does not
   change.
7. **Lists that already have an empty name.** They stay stored and stay
   readable under the usual untitled name. There is no cleanup and no
   automatic rename. The next save of that wishlist's details succeeds only
   when the save includes a real name under rules 1 and 2. A save that would
   leave the name empty is refused, even if the person only meant to change
   the description or the event. After a real name is saved, later saves may
   change the other details and keep that name.
8. **Lists already stored with an invisible-only name.** They are not
   rewritten and not deleted. They can still look blank until the next save.
   That next save must replace the name with a real name, under the same rule
   as an empty name. The untitled fallback is not newly applied to them.
9. **What the person experiences.** Invalid input does not create a wishlist
   and does not change an existing one. Typed text stays in the form. The
   message sits with the field that is wrong, in Russian and in English, with
   the same meaning. Create and edit behave the same in the Telegram Mini App
   and in a plain mobile browser. Leaving without saving still changes
   nothing.
10. **The service is the backstop.** A direct save that skips the app is held
    to the same name rule, and to the same description and event-title
    acceptance creation already uses. The app does not describe a service
    refusal of a too-long name as a missing name. This task does not add a
    length refusal for the description or the event title.
11. **Other behaviour stays.** Optional description and event title may still
    be cleared when the name remains valid. Event dates, sharing, deletion,
    archive, favorites, history, and surprise secrecy are unchanged. A name
    the app accepts for length is not refused by the service for length.

### Non-functional requirements and constraints

- The same name rule and messages apply in the Telegram Mini App and in a
  plain mobile browser, in Russian and in English.
- The person keeps what they typed when a save is refused.
- Length is counted the same way in the app and in the service, after the
  same trimming of spaces at the ends.
- Surprise secrecy is unchanged. A wishlist name, description, and event title
  are not reservation information.
- This work is not a blocker for other work.
- Out of scope: renaming or deleting wishlists that already have an empty or
  invisible-only name; changing how those invisible-only names are displayed
  before the next save; drafts; making the description or the event title
  required; choosing a character ceiling for the description or the event
  title; event-date rules; wish-field lengths; a second wishlist when a
  creation response is lost; who may edit the details.

## Q&A

- **Why this change?** Guests should see a name the owner chose. Creation
  already demands that, and editing can undo it. A blank-looking name and a
  wrong "missing name" message make the list look broken or send the person
  to fix the wrong problem. One contract removes that gap. Source: the
  follow-up from WISHENKA-296, and the creation rule in `in-docs/spec.md`
  section 4.2.
- **Why is the name required on edit, not only on create?** A list that could
  be cleared after creation would bring back the untitled and blank-looking
  titles creation was changed to stop. The edit is the same details, so it
  keeps the same name.
- **Why administrators as well as the owner?** An administrator may already
  manage wishlist settings (`in-docs/spec.md` section 4.4). If only the owner
  were held to the rule, an administrator could still clear the name. The
  rule follows the save, not a single role. Who may open that save does not
  change.
- **Why reject an invisible-only name instead of storing it stripped?** The
  person still has not provided a visible name. Stripping it and saving an
  empty name would hide that. They see that a name is required, as with a
  blank field. Marks mixed with a visible character are kept, because the
  name no longer looks blank and this task does not rewrite ordinary text.
- **Why no new ceiling for the description and the event title?** Creation
  already accepts both with no extra character ceiling, and the product
  description of a wishlist does not state a number for either field. Create
  and edit therefore share that acceptance. This task does not choose a
  ceiling. A later product decision can add one.
- **What happens to wishlists that already have an empty name?** They stay.
  They remain readable under the usual untitled name. Nobody migrates or
  deletes them. The next save of their details must include a real name.
  That matches the creation decision to leave older empty lists in place
  while stopping new ones.
- **What is a character?** One Unicode code point, counted after trimming
  spaces at the ends. That is the count creation already uses, so a name of
  255 ordinary letters stays valid and 256 does not. The app and the service
  must not disagree on that count.
- **What stays optional?** Description, event title, and event date.
  Spaces-only description or event title means "not set". Only the name
  becomes required on edit. No extra character ceiling is added for the
  description or the event title.
