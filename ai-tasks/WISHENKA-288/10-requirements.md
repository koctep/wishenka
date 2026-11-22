# WISHENKA-288: Consistent Wishenka visual identity

## Goals

Wishenka users should recognise one friendly product as they move between sections and should
understand the purpose and importance of its controls without extra explanation. A consistent,
light and airy visual identity should make everyday wishlist and gift tasks easier while preserving
the functionality users already rely on.

## Task Description

Establish the shared visual language for the redesigned Wishenka experience. The parent epic calls
for a very light background, soft pink tones, plum and cherry accents, light-looking cards, a clear
hierarchy and generous space. Cherry, wishlist and gift motifs should be restrained; heavy dark
fills must not form the basis of the interface. The parent epic includes a visual reference image.
The
result should feel coherent across the refreshed sections, including when the interface language
changes.

The implementation languages are HTML, CSS and JavaScript. This is a presentation and
interaction consistency task, not a change to wishlist, reservation, role or privacy rules.

### Scope and boundaries

- Establish a common appearance and interaction vocabulary for cards, fields, buttons, hints,
  notifications and their states in the updated experience.
- Make primary, secondary and destructive actions visually distinct while keeping equivalent
  actions recognisable and consistent across screens.
- Provide a shared foundation for the sprint's separate stories for wishlist overview, individual
  wishlists, settings, history and cross-screen usability. Those stories retain responsibility for
  their specific workflows and screen-level acceptance criteria.
- Preserve existing role-specific visibility, permissions, surprise protection, error handling,
  navigation and the outcomes of actions. The redesign must not expose private gift or reservation
  information to a role that cannot currently see it.
- The experience must remain usable in Telegram Mini App and a mobile browser. Russian and English
  are the supported languages. Do not make the brand identity dependent on either language.

### Business entities

- **User**: a person using Wishenka in an applicable role, including a wishlist owner, collaborator,
  giver or anonymous visitor; the actions available depend on that role.
- **Section**: a part of the experience where a user performs a task, such as an overview, wishlist,
  settings or history view.
- **Interface element**: a card, field, button, hint or notification that presents information or
  offers an action; it has a purpose, importance and current state.
- **Action**: a user operation which may be primary, secondary or destructive and may be available
  only in a permitted context.

## User Stories

- As a user, I recognise Wishenka when moving among updated sections and need not relearn controls.
- As a user, I can identify the main action, find secondary actions and distinguish dangerous
  actions before I choose them.
- As a user, I can tell whether an element is available, unavailable, selected or needs attention.
- As a Russian- or English-speaking user, I receive an equally understandable, recognisable
  experience without losing meaning when text length changes.
- As a mobile or Telegram Mini App user, I can read and operate the updated controls comfortably.
- As a user in any supported role, I retain the actions and privacy protections appropriate to me.

## Definition of Done

1. Updated sections share the light, airy Wishenka direction described above; cards, fields,
   buttons, hints and notifications have a coherent appearance.
2. Actions with the same meaning appear and behave consistently across updated sections. The
   principal action is identifiable, secondary actions are subordinate, and destructive actions
   cannot be mistaken for ordinary actions.
3. Available, unavailable, selected and attention-required states are distinguishable in context;
   controls remain understandable without relying solely on colour.
4. Russian and English presentations remain recognisable and readable, including longer labels;
   neither language changes the meaning or availability of an action.
5. Controls and information remain legible and operable on a phone and in Telegram Mini App;
   content and essential actions are not hidden or made unusable by the redesign.
6. Existing workflows, role-specific permissions and privacy rules remain intact. Existing action
   results, including confirmations and errors, are still communicated to the user.
7. The shared visual direction is applied to the updated experience and can be used consistently
   by the separate screen-specific stories in this sprint.

## Constraints and Assumptions

- The Jira story and its parent epic are the source for the visual direction and acceptance scope;
  the parent epic's attached image is a visual reference, not a separate functional specification.
- Existing product rules in `specs/00-high.md` and `in-docs/spec.md` remain authoritative for
  permissions, privacy and workflows, except where a later explicitly scoped story changes them.
- Accessibility and readable state distinctions support the requested clarity; the task does not
  claim certification to a particular accessibility standard.
- No requirement is inferred to change data, introduce new roles or remove a supported theme or
  existing function. Screen-specific stories and the sprint-wide usability story provide further
  acceptance of their own scope.

## Q&A

- **Why redesign?** To give users one recognisable, friendly product and make controls and actions
  easier to understand as they move across sections.
- **What visual direction is supplied?** The parent epic specifies the light palette, restrained
  motifs and a visual reference; the story requires consistency of controls and states.
- **Does this story replace the individual screen stories?** No. It establishes the common visual
  language; the other stories address their respective screen-specific user journeys.

Sources: [WISHENKA-288](https://pypost.atlassian.net/browse/WISHENKA-288),
[WISHENKA-287](https://pypost.atlassian.net/browse/WISHENKA-287), `specs/00-high.md` and
`in-docs/spec.md`.
