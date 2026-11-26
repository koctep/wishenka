# WISHENKA-334: Rolling the person-key change backward restores the earlier identity

## Goals

A person has an earlier identity the product assigned and a messenger
identity from Telegram. Those two identities can differ. The person-key
change moved the product's memory of that person onto the messenger
identity. It also tied each surviving invite token to its wishlist, and it
reshaped each support ticket so the ticket names only the messenger
identity.

The forward change is already checked. Rolling that change backward is
not. A maintainer who rolls it back must get the earlier identity back on
every record the forward change moved, and must get invite tokens and
support tickets back to the shape they had before. If the backward step
does not do that, the check fails.

This task adds that check. It comes from the technical-debt note on
WISHENKA-188. It is not a new screen and not a new way to share a wishlist
or contact support.

Implementation language: Python.

## User Stories

- As a maintainer rolling the person-key change backward, I have an
  automated check that a person whose earlier identity differs from their
  messenger identity is remembered by the earlier identity again.
- As that person, the private chat where the bot can reach me, a birthday
  I keep, an unfinished birthday prompt, and an unfinished support prompt
  name me by my earlier identity again. Both identities remain mine.
- As that person, a support ticket I opened before the forward change
  still has the same reference and the same time it was opened. After the
  rollback it names me as owner by my earlier identity and still names my
  messenger identity. Finding my tickets over time uses that earlier
  identity again. Removing me no longer removes the ticket by itself.
- As an owner, an invite token that survived the forward change is still
  the same token after the rollback. It no longer stores which wishlist it
  opens. Removing the wishlist no longer removes the token by itself.
- As a maintainer, the existing check of the forward change stays. This
  task adds the backward check only.

## Definition of Done

- An automated check rolls the person-key change backward for a person
  whose earlier identity is not the same as their messenger identity.
- Before the rollback, the forward change has already run. The private
  chat where the bot can reach the person, a birthday the person keeps, an
  unfinished birthday prompt, and an unfinished support prompt name the
  messenger identity. After the rollback, those same records name the
  earlier identity. The person is still the same person, and both
  identities remain on the person.
- A support ticket that existed before the forward change keeps its
  reference and the time it was opened. After the rollback it has an
  owner, and that owner is the person's earlier identity. It still carries
  the messenger identity. Finding that person's tickets over time uses the
  earlier identity again. Removing the person does not remove the ticket
  by itself.
- An invite token that the forward change kept is still present after the
  rollback, with the same token text. It does not store which wishlist it
  opens. Removing the wishlist does not remove the token by itself.
- The check fails when the earlier identity is not restored, when a
  support ticket does not return to that earlier shape, or when an invite
  token does not return to that earlier shape.
- The existing check of the forward change still passes.
- The person-key change itself is edited only when this check shows that
  the backward step does not restore the earlier identity or the earlier
  shapes of invite tokens and support tickets.

## Task Description

WISHENKA-188 moved the product's memory of a person from an earlier
identity onto the messenger identity, and it changed the shape of invite
tokens and support tickets. The forward direction is already covered by an
automated check. The backward direction has no check, so a rollback could
leave a person under the wrong identity or leave invite tokens and support
tickets in the newer shape.

The check starts from the earlier world: the two identities differ, the
records above name the earlier identity, a support ticket names both the
earlier owner and the messenger identity, and an invite token is only the
token. The forward change is applied, then rolled back. The result must
match that earlier world for the identity mapping, the support ticket, and
the invite token.

Records the forward change did not move off the earlier identity are not
part of this restoration. A reminder and an ordinary wishlist access token
already used the messenger identity. This check does not require them to
switch to the earlier identity.

### Business entities

- **Person:** someone the product already knows. The person has an earlier
  identity and a messenger identity. They can differ. Both stay on the
  person through the forward change and the rollback.
- **Remembered link:** a place the forward change moved from the earlier
  identity to the messenger identity. In this task that is the private
  chat where the bot can reach the person, a birthday the person keeps, an
  unfinished birthday prompt, and an unfinished support prompt.
- **Support ticket:** a recorded request to support. The earlier shape
  names an owner by the earlier identity and also names the messenger
  identity. The newer shape names only the messenger identity and is
  removed with the person.
- **Invite token:** the secret that opens a wishlist. The earlier shape is
  the token alone. The newer shape stores which wishlist it opens and is
  removed with that wishlist.
- **Maintainer:** the person who rolls the person-key change backward and
  needs the check before trusting that rollback.

### Boundaries

In scope:

- An automated check that rolling the person-key change backward restores
  the earlier identity on the remembered links.
- The same check restores the earlier shape of support tickets and invite
  tokens, including the token text and the ticket reference and open time
  that the forward change kept.
- The check fails when that restoration does not happen.
- A change to the person-key rollback only when the check shows the
  earlier identity or those earlier shapes are not restored.

Out of scope:

- The forward person-key change, except to keep its existing check. This
  task does not add a new forward rule.
- A shared way to run every schema change. That is WISHENKA-335.
- Any other schema change.
- Reminders and ordinary wishlist access tokens. They are not records this
  check must move back onto the earlier identity.
- Tokens and rows the forward change already dropped because they matched
  no person or no wishlist. This task does not bring those back.
- A new screen, a new support flow, or a new way to share a wishlist.

## Q&A

**Why check the backward step?** The forward person-key change is already
in use and already checked. Rolling it backward is the way back to each
person's earlier identity and to the earlier shape of invite tokens and
support tickets. Without a check, that way back can be wrong and still
look finished.

**Why must the two identities differ in the check?** When they are the
same value, a rollback that forgets to translate still looks correct. The
check uses a person whose earlier identity and messenger identity differ,
so a missed translation fails.

**Why leave the person-key change alone unless the check fails?** The
forward behavior is already accepted. This task proves the backward step.
The change is edited only when the check shows the earlier identity or the
earlier shapes are not restored.

**Why are reminders and ordinary access tokens outside the check?** The
forward change did not move them from the earlier identity onto the
messenger identity. Requiring that switch would describe a different
rollback from the one that exists.

**Are there open questions?** No. The source note is WISHENKA-188
(`ai-tasks/WISHENKA-188/60-tech-debt.md`, missing check that the person-key
rollback restores the earlier identity and the earlier shape of invite
tokens and support tickets).
