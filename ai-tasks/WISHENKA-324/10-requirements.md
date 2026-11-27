# WISHENKA-324: Gift-receipt screens use the wishlist access they are given

## Goals

A member records that a wish was received, corrects that receipt, or
cancels it. Opening the dialog, the correction, or the cancellation is a
look. Recording, correcting, and cancelling are saves. Those saves take
an exclusive lock so two saves of the same wish do not overlap.

The three opening screens already receive read-only wishlist access, the
kind of look that leaves the exclusive lock free. They do not use that
access as an argument of the look. They store it in a hidden slot, and a
later look reads the slot.

The three save forms send a repeat key. After a successful record,
correction, or cancellation that carries that key, the list is composed
on the save itself. That look does not read the hidden slot and does not
open the shared wishlist access a save uses. A true repeat returns the
answer already stored and does not look again. Opening dialogs stay reads
on the access they already receive.

The quantity-refusal look stays. A quantity above remaining still shows
the wish card. Nothing remaining still shows the list and the gifted
section. The access that paints them is the wishlist access already given
to that screen, passed into the look as an argument. A newly opened
shared repository does not paint them.

Today that look can find the slot empty and open a new shared repository.
That opening is a hidden fallback. It runs when the repeat key is absent,
and a refused record that carries the key uses it too. It is not the list
a member sees after a successful keyed save.

This task removes the hidden slot and only that hidden fallback. It does
not remove the quantity-refusal look. The look stays and is handed the
wishlist access the screen already has, as an argument. This task does
not move the successful keyed list look off the save, and it does not
hand that look a separate access. Recording, correcting, and cancelling
stay saves on the exclusive lock. What a person sees stays the same.

This task is a technical-debt follow-up from WISHENKA-80. The read-only
openings are already in place from WISHENKA-338. This task does not put
those openings back on the exclusive lock, and it does not take that lock
off a save.

Implementation language: Python.

## User Stories

- As a member opening the receipt dialog, I see the same dialog, or the
  same blocked dialog, as today. The opening already receives read-only
  wishlist access. That access is an argument of the opening and of every
  look that opening runs, including a refresh when nothing remains. The
  screen does not store the access in a hidden slot. Today it stores the
  access, and the look finds it there.
- As a member opening the correction dialog or the cancellation dialog, I
  see the same dialog, or the same blocked dialog, as today. Each opening
  already receives read-only wishlist access. That access is an argument
  of the opening and of the look that checks the receipt. The screen does
  not store the access in a hidden slot. Today it stores the access, and
  the look finds it there.
- As a member recording a receipt, my save still takes the exclusive lock.
  The form sends a repeat key. The list I see after a successful record
  is composed on that save. It does not read a hidden slot and does not
  open the shared wishlist access a save uses. This task leaves that look
  on the save. It does not hand the list a separate access.
- As a member correcting a receipt or cancelling a receipt, my save still
  takes the exclusive lock. The form sends a repeat key. The list I see
  after a successful correction or cancellation is composed on that save.
  It does not read a hidden slot and does not open the shared wishlist
  access a save uses. This task leaves that look on the save. It does not
  hand the list a separate access.
- As a member whose quantity is above what remains, I still see the wish
  card. As a member who finds nothing remaining, I still see the list and
  the gifted section. The quantity-refusal look stays. It is handed the
  wishlist access that screen already has, as an argument. That passed-in
  access paints the wish card, the list, and the gifted section. A newly
  opened shared repository does not. A refused record that still carries
  the repeat key does not open a new shared repository because the slot
  was empty.
- As a member who repeats a receipt, a correction, or a cancellation, I
  still get one change and the same answer. The repeat returns the answer
  already stored. It does not compose the list again, and it does not read
  a hidden slot. This task does not open a new shared repository for that
  repeat.
- As a recipient, these screens still hide who promised a gift and who
  gave it. A person who is not a member is still refused. A busy save is
  still busy. A missing wish, a missing receipt, an archived wish, and an
  archived list are still refused the same way.

## Definition of Done

- Every gift-receipt opening look uses wishlist access that was handed to
  that screen as an argument. No gift-receipt screen stores that access in
  a hidden slot for a later look to find.
- The quantity-refusal look stays. A quantity above remaining still shows
  the wish card. Nothing remaining still shows the list and the gifted
  section. The access that paints them is the wishlist access already
  given to that screen, passed in. A newly opened shared repository does
  not paint them.
- No gift-receipt look opens a new shared repository because a hidden slot
  was empty. Only that hidden fallback is gone. The quantity-refusal look
  is not removed.
- Opening the receipt dialog, the correction dialog, and the cancellation
  dialog stays a read on the read-only access those openings already
  receive. This task does not put those openings on the exclusive lock.
- Recording a receipt, correcting a receipt, and cancelling a receipt stay
  saves. Each save still takes the exclusive lock. This task does not move
  a save onto read-only access.
- The list after a successful record, correction, or cancellation that
  carries the repeat key stays composed on the save. This task does not
  move that look off the save, does not hand it the shared access a save
  uses, and does not make it a separate look on the exclusive lock.
- A true repeat of that save returns the stored answer and does not
  compose the list again.
- A refused record that carries the repeat key does not open a new shared
  repository because the slot was empty. The refusal status and the
  refusal sentence stay the ones the screen already shows.
- The person sees the same dialog, blocked dialog, notice, wish card,
  list, gifted section, and archived section. Surprise rules stay as they
  are. These screens do not add a sentence, a status, or a new screen.
- A screen that only paints HTML from data it already has does not look
  up the wishlist and does not gain a hidden lookup.

## Task Description

WISHENKA-80 left gift-receipt screens able to look up the wishlist without
being given access for that look. A screen could store access in a hidden
slot. A look then used whatever the slot held. If the slot was empty, the
look opened a new shared repository, the shared wishlist access a save
uses.

WISHENKA-338 has since given the three openings read-only access: the
receipt dialog, the correction dialog, and the cancellation dialog. Those
openings still store that access in the hidden slot instead of passing it
into the look. The three save forms send a repeat key. After a successful
record, correction, or cancellation, the list is composed on the save. It
does not read the slot and does not open the shared access. A true repeat
returns the stored answer and does not compose again. Opening dialogs
stay reads.

The quantity-refusal look stays. A quantity above remaining still shows
the wish card. Nothing remaining still shows the list and the gifted
section. Today that look uses the hidden fallback whenever the slot is
empty. The fallback runs when the repeat key is absent, and a refused
record that carries the key uses it too. This task removes only that
fallback. The look is handed the wishlist access the screen already has,
as an argument. That passed-in access paints the wish card, the list, and
the gifted section. A newly opened shared repository does not.

The save path is unchanged. Recording, correcting, and cancelling still
take the exclusive lock. The list after a successful keyed save stays on
that save. This task does not move it off the save and does not hand it
the shared access. This task does not decide again which looks leave the
lock free. The openings already do. The saves still do not.

### Business entities

- **Person:** a member who can record, correct, or cancel a receipt, or a
  recipient or visitor who must not see who promised or gave a gift.
- **Wishlist and wish:** the list and the item the receipt belongs to.
- **Receipt:** the record that some quantity of a wish was received.
- **Gift-receipt screens:** opening the receipt dialog, recording a
  receipt, opening the correction dialog, correcting a receipt, opening
  the cancellation dialog, and cancelling a receipt.
- **Read-only wishlist access:** the access an opening already receives.
  A look on it leaves the exclusive lock free.
- **Shared wishlist access:** the access a save uses. The hidden fallback
  opens a new shared repository of that access when the slot is empty.
  That opening runs when the repeat key is absent, and a refused record
  that carries the key uses it too. The list after a successful keyed
  save does not. The quantity-refusal look does not keep this opening.
- **Quantity-refusal look:** the look that stays after a quantity
  refusal. A quantity above remaining shows the wish card. Nothing
  remaining shows the list and the gifted section. The look is handed
  the wishlist access the screen already has, as an argument. That
  access paints the card, the list, and the gifted section. A newly
  opened shared repository does not.
- **Repeat key:** the key the three save forms send so a repeated save is
  the same save. A successful save that carries it composes the list on
  the save. A true repeat returns the stored answer. A refused record
  that carries the key still uses the empty-slot opening today.
- **Handed access:** wishlist access given to a screen as an argument of
  that request. An opening look uses this access and does not store it
  aside. The quantity-refusal look uses the access that screen already
  has, passed in. The successful keyed list is not given a separate
  handed access.
- **Hidden slot:** a place on the request where one step stores access and
  a later look reads it. This task removes it.
- **Hidden fallback:** the opening that finds the hidden slot empty and
  opens a new shared repository. It runs when the repeat key is absent,
  and a refused record that carries the key uses it too. This task
  removes only this fallback. The quantity-refusal look stays.
- **Exclusive lock:** the lock a receipt save takes so two saves of the
  same wish do not overlap. Saves keep it. Openings stay off it. The
  successful keyed list stays on the save and is not a second lock.

### Boundaries

In scope:

- The six gift-receipt screens, and every look they run: opening checks,
  the quantity-refusal look, and the list after a record, a correction,
  or a cancellation.
- Passing the read-only access each opening already receives, as an
  argument of that opening and of the looks it runs.
- Handing the quantity-refusal look the wishlist access that screen
  already has, as an argument, so that access paints the wish card, the
  list, and the gifted section.
- Removing the hidden slot and only the hidden fallback that opens a new
  shared repository when the slot is empty.
- Leaving the list after a successful keyed record, correction, or
  cancellation on the save.

Out of scope:

- The exclusive lock on recording, correcting, and cancelling. Those stay
  saves. This task does not move them onto read-only access.
- Putting the three openings back on the exclusive lock. They already
  receive read-only access.
- Moving the list after a successful record, correction, or cancellation
  off the save, or handing that list the shared access a save uses.
- Removing the quantity-refusal look, or replacing the wish card, the
  list, or the gifted section it already shows.
- Which lock a save takes, how long a save waits, and the busy outcome
  when that wait runs out. That stays on its own follow-up.
- The answer to a repeated receipt, correction, or cancellation. It stays
  the stored answer of that save. A true repeat does not compose again.
- Other Mini App screens, including wishes, members, sharing, and the
  gifted list outside these receipt screens.
- A second copy of wishlist action rules. That stays on its own follow-up.
- A new sentence, status, screen, quantity rule, or surprise rule.
- Screens that only paint HTML from data they already have.

## Q&A

**Why is this a product problem?** Opening screens store read-only access
in a hidden slot, and a look can open a new shared repository when that
slot is empty. That empty-slot opening is a hidden fallback. It runs when
the repeat key is absent, and a refused record that still carries the key
uses it too. The quantity-refusal look stays: a quantity above remaining
still shows the wish card, and nothing remaining still shows the list and
the gifted section. Those are painted by the access already given to that
screen, passed in, not by a newly opened shared repository. The list after
a successful keyed record, correction, or cancellation is already composed
on the save, and a true repeat returns the stored answer. Opening dialogs
stay reads. The business goal is to remove the hidden slot and only that
fallback, to hand the refusal look the access the screen already has, and
to leave that successful list on the save. What the person sees stays the
same.

**Do the openings already receive access?** Yes. Opening the receipt
dialog, the correction dialog, and the cancellation dialog already
receives read-only access, from the work that left those looks off the
exclusive lock. They still store that access in the hidden slot. This
task passes it into the look. It does not put the openings back on the
lock.

**Why do the saves stay on the exclusive lock?** Recording, correcting,
and cancelling change the receipt. They already take the exclusive lock.
This task does not decide that lock again. The list after a successful
keyed save stays on that save. It is not moved off the save, and it is
not given the shared access as a separate look.

**Why does the successful list stay on the save?** The three save forms
send a repeat key. A successful record, correction, or cancellation
composes the list on the save. That look does not read the hidden slot
and does not open the shared access. Handing it that access, or lifting
it off the save, would describe a path the member does not take. The
hidden fallback is the empty-slot opening of a new shared repository. A
refused record that carries the key uses that opening today, as does a
save whose key is absent. This task removes that fallback and leaves the
successful keyed list on the save. The quantity-refusal look stays and
is handed the access the screen already has. A true repeat returns the
stored answer and does not compose the list again.

**Why is a repeated request unchanged?** A repeated receipt, correction,
or cancellation still changes the receipt once. The repeat returns the
answer already stored. It does not compose the list again, and it does
not read the hidden slot. This task leaves that replay alone.

**Why is the busy outcome unchanged?** A save that cannot take the
exclusive lock already ends as temporarily unavailable. This task does
not change that wait or that outcome. The follow-up that maps a brief
lock on the shared access stays on its own follow-up.

**Why does the quantity-refusal look stay?** The member still has to see
the same refusal. A quantity above remaining still shows the wish card.
Nothing remaining still shows the list and the gifted section. Removing
that look would drop the screen this task still requires. What goes away
is only the hidden fallback that opens a new shared repository when the
slot is empty, including when the refused record carries the repeat key.
The look is handed the wishlist access the screen already has, as an
argument. That access paints the card, the list, and the gifted section.
