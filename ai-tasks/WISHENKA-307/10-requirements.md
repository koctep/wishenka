# WISHENKA-307: Switches in settings page are not following design

## Goals

A user changing reminders and notifications on the personal settings page should see ordinary,
recognizable on/off switches that look like the rest of the Wishenka design and show at a
glance whether each option is on or off. The settings page was reworked in WISHENKA-291 as part
of the epic WISHENKA-287 (a single light and recognizable Wishenka design, shared identity from
WISHENKA-288 to 290, 291, 292 and 294). Its switches still look like default browser controls
and do not match that identity. Fixing this restores the promise of the epic: one coherent,
light, convenient interface. The ticket is a defect (Bug, priority Highest).

Implementation language: Python, JavaScript, HTML and CSS.

## Task Description

On the personal settings page, the birthday reminder option and the per-category notification
options are shown as plain default controls next to a separate text label ("Enabled" or
"Disabled"). They do not read as switches and do not follow the shared Wishenka visual identity.

The ticket contains only a screenshot and the reference "WISHENKA-291". The screenshot was not
available while writing these requirements (see Q&A). The requirement is therefore stated from
the ticket title: every on/off switch of the settings page must follow the Wishenka design.

This task changes only how the switches look and how they are exposed to the user and to
assistive technology. It adds no new feature, setting, data or rule. Saving, undo, error
handling, the list of categories and stored values stay as delivered in WISHENKA-291.

### Business entities

- **Switch:** an on/off option of the user, with a name (what it controls), a state (on or off)
  and an activity state (idle, saving, failed, state unknown, unavailable).
- **Reminder option:** the birthday reminder switch.
- **Notification category switch:** one switch per notification category of the user.
- **Viewing context:** device width, host (Telegram Mini App or browser), light or dark theme,
  language (Russian or English), input method (touch, pointer, keyboard, assistive technology).

### Functional requirements

1. **Recognizable switch.** Each option on the settings page is presented as an on/off switch
   that a user recognizes as such without reading help text, and that is consistent in shape,
   color and proportions with the shared Wishenka visual identity (accent color, rounded
   forms, spacing of other controls).
2. **All states are designed.** The switch looks deliberate and distinguishable in every state:
   - on and off;
   - keyboard focus (visible focus indication consistent with other controls);
   - disabled or unavailable;
   - pending, while the change is being saved (visible and not mistaken for on or off);
   - error, when saving failed and the previous state is shown again, and the state-unknown
     case that already exists.
3. **State is not conveyed by color alone.** On and off differ also by position or shape, so a
   user who cannot tell colors apart still sees the state. The text indication of state may
   remain, but it is consistent with the switch and never contradicts it.
4. **Comfortable touch target.** The switch and its label form a comfortable target for a
   finger (not smaller than the 44 px convention of the product), neighboring switches are not
   hit by accident, and the label text is part of the target.
5. **Assistive technology.** A screen reader announces each control as a switch (toggle) with a
   name that says what it controls and its current state (on or off), and announces changes of
   state and failures as it does today.
6. **Keyboard operation.** Every switch can be reached and changed with the keyboard alone,
   with a visible focus.
7. **Themes.** The switch, its state and its label are readable and keep sufficient contrast in
   the light theme, the dark theme and the Telegram theme, in on and off states.
8. **Languages.** All visible and announced texts of the switches exist in Russian and English
   with the same meaning and follow the selected language; long labels wrap and do not
   overlap or push the switch out of view.
9. **Behavior unchanged.** Changing a switch is saved as before: immediate saving, one pending
   change per category at a time, automatic return to the previous state on failure with the
   familiar message, handling of an unknown outcome, and the page staying usable during
   saving. The set of categories, their order, default values and stored data are unchanged.

### Non-functional requirements and constraints

- Narrow phone viewport (320 px and up): no horizontal overflow, nothing cut off, switches
  fully visible together with labels.
- Contrast of the switch, its state and labels is not weaker than the contrast checks the
  product already applies.
- Privacy is unchanged: no new text, announcement or data about the user is exposed or sent.
- Works the same in the Telegram Mini App and in a normal mobile browser.
- Existing tests and observable hooks used by them (for example the birthday reminder switch
  identifier) are not removed without replacement; the existing suite stays green apart from
  known pre-existing failures.
- Out of scope: new settings, changes of notification rules, other pages (they are covered by
  their own stories), new theme support.

## User Stories

- As a user, I see the reminder and notification options as clear on/off switches in the
  Wishenka style, so I understand them without guessing.
- As a user, I can tell whether an option is on or off at a glance, not only by color.
- As a phone user, I can tap a switch or its label easily without hitting a neighbor.
- As a keyboard or screen reader user, I can find each switch, know what it controls and its
  state, and change it.
- As a user of the dark or Telegram theme, I read the switches as comfortably as in the light
  one.
- As a Russian or English speaking user, I see the switch texts in my language.
- As a returning user, I see my choices saved and failures handled exactly as before.

## Definition of Done

1. Every switch on the settings page (birthday reminder and each notification category) looks
   like an on/off switch consistent with the shared Wishenka identity.
2. On, off, focus, disabled, pending, error and unknown states are visibly distinct; state is
   conveyed by more than color.
3. Each switch is at least 44 px high and wide enough as a target together with its label, at
   320, 360 and 375 px, with no horizontal overflow in both languages.
4. Assistive technology exposes each control as a switch with a name and on/off state; the
   control is operable by keyboard with visible focus.
5. Switch, state and label meet the product contrast level in light, dark and Telegram
   themes.
6. Russian and English texts are equivalent; long labels do not break the layout.
7. Saving, undo on failure, unknown-outcome handling, categories and stored data work exactly
   as before; existing settings tests pass.
8. An automated check reproduces the defect first (fails before the fix) and passes after it.
9. Privacy is verified unchanged.

## Q&A

- **Why this change?** The switches on the settings page, reworked in WISHENKA-291, do not
  follow the Wishenka design. Business value: the personal settings page looks and feels like
  the rest of the product (epic WISHENKA-287), and users understand and trust their reminder
  and notification choices.
- **What does the screenshot show?** Not known. The screenshot attached to the ticket was not
  available to the agent that wrote this document; the ticket text contains only the title and
  "WISHENKA-291". Assumption: the screenshot shows the default-looking checkbox controls of the
  settings page next to a separate text state. Where the screenshot and these requirements
  differ, the requirements together with the shared visual identity decide; the reviewer who
  sees the screenshot should confirm or correct this.
- **Which switches are in scope?** The birthday reminder switch and the notification category
  switches on the personal settings page. Other pages are out of scope unless they show the
  same defect, which becomes a separate follow-up.
- **Is the "Enabled / Disabled" text required?** It is not required by this task; the text may
  stay if it is consistent with the switch, since state must not rely on color alone.
- **Does behavior change?** No. Only presentation and accessibility of the switches change.
- **Which design is the reference?** The shared visual identity of WISHENKA-288 and the
  settings story WISHENKA-291.
