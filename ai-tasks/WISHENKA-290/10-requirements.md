# WISHENKA-290: Clear specific wishlist view and management

## Goals

Wishlist owners, administrators, collaborators, and viewers should immediately understand the
contents and context of an open wishlist, update list details without losing focus on the wishes
themselves, and share the list with gift givers or invite collaborators without confusing the two
actions.

Key user value:

- Users conveniently browse wishes and immediately see the list title, their role, description,
  and occasion details.
- Owners and administrators clearly see where to edit the list title, description, event name, and
  event date, with unmistakable save, cancel, and outcome feedback.
- Sharing the public gift-selection link with givers is clearly separated from inviting a
  collaborator to co-edit the list, and participant roles and member actions are self-explanatory.

## Task Description

Redesign the specific wishlist view and management workspace in the Telegram Mini App so that
opening a wishlist presents a clear hierarchy: identity and role first, the wishes section as the
primary focus, and well-organized management sections for list settings, public sharing, and
collaborative member administration in both Russian and English.

The implementation languages are Python, JavaScript, HTML, and CSS (covering bilingual UI copy,
individual wishlist view presentation, and management section layout). This task improves visual
clarity, information hierarchy, and control comprehension on the individual wishlist view without
changing underlying permission rules, token security, or reservation privacy.

### Scope and boundaries

In scope:

- Clear wishlist header and overview area displaying return navigation to the home overview, the
  wishlist title (or localized untitled fallback), the user's current role badge, optional list
  description, optional occasion title and date, and the favorite toggle for non-owners.
- Primary prominence of the wishes section so viewing and working with wishes remains the main
  focus of the screen and is never visually overshadowed by administrative forms.
- Clear, non-distracting presentation of wishlist metadata settings (title, description, event
  title, and event date) for owners and administrators, with distinct save and cancel actions and
  explicit confirmation or error feedback that preserves unsaved edits on failure.
- Unmistakable visual and textual separation between **Public gift-selection sharing** (for gift
  givers who view wishes and reserve gifts) and **Collaborator invitation sharing** (for co-authors
  who add and edit wishes), including link copy, Telegram sharing, and link replacement or
  revocation actions.
- Self-explanatory participant list and member management controls showing each participant's name
  and localized role (**Owner / Владелец**, **Admin / Администратор**,
  **Collaborator / Соавтор**), with clear role promotion/demotion (for the owner) and member
  removal actions (per role permissions).
- Preservation of all existing wishlist management, archived-list restoration, favorite toggling,
  public gift-link viewing, and collaborator invitation preview and acceptance flows.
- Mobile-first ergonomics, clean text wrapping, touch-friendly controls, and natural wording in
  both Russian and English, adhering to the light visual identity established in WISHENKA-288.

Out of scope (owned by sibling sprint stories or excluded by product rules):

- Home screen wishlist overview, section categorization, and home top navigation (WISHENKA-289).
- Personal account settings and notification preferences screen (WISHENKA-291).
- Viewing history screen layout and controls (WISHENKA-292).
- Cross-screen loading, empty-state, and feedback harmonization outside the specific wishlist
  workspace (WISHENKA-294).
- Owner permanent/soft wishlist deletion action and confirmation flow (WISHENKA-295).
- Preventing premature empty-wishlist creation when exiting the creation flow without adding
  wishes (WISHENKA-296).
- In-list search, tag or category filtering, sorting controls, split payments, and social feeds.

### Business entities

- **Wishlist Workspace**: the dedicated view of a single wishlist showing its header context,
  wishes section, and role-gated management controls.
- **Wishlist Header Context**: the top summary of the wishlist containing its title (or untitled
  fallback), the viewer's role badge, description, occasion name and date, return navigation, and
  non-owner favorite action.
- **Wishes Section**: the primary content block of the wishlist displaying the wishes and status
  guidance so users focus on gift items first.
- **Wishlist Settings**: the editable metadata of an active wishlist (title, description, event
  title, event date) available to the owner and administrators.
- **Public Gift-Selection Link**: a shareable link intended for gift givers that grants read and
  gift-reservation access without granting editing privileges or exposing recipient surprises.
- **Collaborator Invitation Link**: a revocable link intended for co-authors that invites a user
  to join the wishlist as a collaborator with wish-editing permissions.
- **Wishlist Participant (Member)**: a user associated with the wishlist in a specific role
  (**Owner**, **Admin**, or **Collaborator**), displayed with role-appropriate administrative
  actions.

## User Stories

- As a user opening a wishlist, I want to immediately see the list title, my role on the list, the
  description and event details, and the wishes section so that I understand what list I am viewing
  and can focus on its wishes right away.
- As a wishlist owner or administrator, I want the list settings (title, description, event, and
  date) to be clearly organized and visually subordinate to the wishes section so that settings do
  not distract from everyday wish viewing.
- As a wishlist owner or administrator editing list settings, I want the save and cancel actions
  to be easy to distinguish and the result of saving or cancelling to be immediately clear so that
  I never wonder whether my changes were applied.
- As a wishlist owner or administrator, I want the public link for gift givers and the invitation
  link for collaborators to be clearly separated and explained so that I never accidentally invite
  a gift giver as a co-author or send a view-only link to a co-author.
- As a wishlist owner or administrator, I want to see all current participants with their localized
  roles and understand what each member action (make admin, remove admin, remove member, revoke or
  replace link) does without needing external instructions.
- As a non-owner viewing a wishlist, I want a clear action to add or remove the list from my
  favorites and a clean read-only view without administrative clutter.
- As a Russian- or English-speaking mobile user, I want all labels, hints, links, and member rows
  on the wishlist screen to wrap cleanly and remain easy to tap on a phone screen.
- As a gift recipient, I expect the wishlist view and management workspace never to reveal who
  reserved or purchased any gift for me.

## Functional Requirements

### FR-1: Immediate wishlist identity, role, and wishes priority

- Opening a specific wishlist immediately presents:
  - A clear back action to return to the home overview.
  - The wishlist title, or a localized untitled fallback when no title has been set.
  - A prominent, localized role badge indicating the user's relationship to the list
    (**Owner / Владелец**, **Admin / Администратор**, **Collaborator / Соавтор**, or
    **Favorite / Избранное** when applicable).
  - The wishlist description and optional occasion context (event title and formatted event date)
    when present, displayed in a scannable, non-cluttered layout.
  - For authenticated users who are not the owner, a clear secondary action to add the wishlist to
    favorites or remove it from favorites with immediate status feedback.
- The **Wishes** («Желания») section appears immediately after the wishlist header context as the
  primary content area of the screen, before any administrative settings, sharing panels, or
  member management sections.

### FR-2: Non-distracting wishlist settings with clear save, cancel, and feedback

- For active wishlists where the user is an **Owner** or **Admin**, the wishlist settings section
  allows editing:
  - **Title** («Название»)
  - **Description** («Описание»)
  - **Event** («Событие»)
  - **Date** («Дата»)
- The settings section is visually structured as a clean, well-bounded management card or panel
  that does not overpower the wishes section above it.
- Each setting field has an explicit, readable label and helper structure so the user immediately
  knows where to change the title, description, event name, or event date (and that event and
  date remain optional).
- **Save vs Cancel distinction**:
  - The primary **Save settings** («Сохранить настройки») action uses primary emphasis.
  - The **Cancel** («Отмена») action uses secondary emphasis and is visually separated from save
    so the user cannot confuse saving with discarding edits.
- **Outcome clarity**:
  - Saving valid changes persists the updated metadata, refreshes the visible wishlist header
    details (title, description, event context), and announces a clear confirmation message.
  - Cancelling discards unsaved form edits and restores the current saved values of the wishlist.
  - If saving fails, the user's entered values remain intact in the form and an explicit error
    message informs the user that changes were not saved but are still in the form.

### FR-3: Unmistakable separation of public sharing vs collaborator invitation

- For active wishlists managed by an **Owner** or **Admin**, sharing and invitation controls are
  presented in two clearly distinct purposes that cannot be confused:
  1. **Sharing the wishlist with gift givers (public gift-selection link)**:
     - Clearly titled and explained as the public link for givers who view wishes and reserve
       gifts while keeping surprises secret.
     - Provides a read-only link field, a **Copy link** («Скопировать ссылку») action, a primary
       **Share via Telegram** («Поделиться в Telegram») action, and a subordinate action to
       **Replace public link** («Заменить публичную ссылку») that invalidates the old public link
       with clear confirmation feedback.
  2. **Inviting a collaborator (co-author invitation link)**:
     - Clearly titled and explained as the invitation link for co-authors who will join the list
       and gain permission to add and edit wishes.
     - Grouped with collaborator/member management so its administrative nature is obvious.
     - Provides its own read-only link field, **Copy link**, **Share via Telegram**, and a
       subordinate **Revoke invitation** («Отозвать приглашение») action that rotates the invite
       token and invalidates previous invitation links with clear confirmation feedback.
- On the public gift-selection view, viewers continue to see the public sharing panel for the
  wishlist without any collaborator invitation or administrative controls.

### FR-4: Self-explanatory participant roles and member management actions

- For active wishlists managed by an **Owner** or **Admin**, the member management section clearly
  presents the current participants and their roles:
  - Each participant row displays the participant's display name and a localized role badge
    (**Owner / Владелец**, **Admin / Администратор**, or **Collaborator / Соавтор**) rather than
    raw internal role codes or unformatted text strings.
  - A short explanatory subtitle or hint clarifies what participants and roles can do (co-editing
    wishes as a collaborator vs managing settings and participants as an administrator).
- **Role-appropriate member actions**:
  - **Owner controls**: for any non-owner participant, the owner sees a clear role-change action
    (**Make admin / Назначить администратором** for a collaborator, or
    **Remove admin / Снять права администратора** for an administrator).
  - **Removal controls**: for a regular collaborator, managers see a clearly styled destructive
    action (**Remove member / Удалить участника**) that is visually distinct from role-change and
    sharing buttons.
  - Every member management action (role promotion/demotion, member removal, invitation link
    revocation) provides immediate status feedback on completion or failure.

### FR-5: Archived state and existing workflows preservation

- When a wishlist is archived:
  - A clear read-only archived notice is shown, and active settings/sharing/member mutation forms
    are hidden.
  - Owners and administrators see a clear **Restore wishlist** («Восстановить вишлист») action
    with outcome feedback.
- All existing journeys connected to a specific wishlist remain intact:
  - Recording viewing history when opening a wishlist.
  - Opening a public gift-selection link and reserving available wishes (when permitted by role
    and recipient rules).
  - Previewing and confirming a collaborator invitation link to join a wishlist.
  - Managing wish items, gift receipts, and archived wishes on the server-rendered wishlist detail
    view.

### FR-6: Mobile ergonomics, bilingual clarity, and Surprise Invariant

- **Mobile usability**: At smartphone viewport widths, the wishlist header, role badge, wishes
  section, settings fields and buttons, link fields and share buttons, and participant rows fit
  cleanly without horizontal page overflow, overlapping controls, or clipped labels. All
  interactive buttons and inputs are comfortably sized for touch interaction.
- **Bilingual parity**: Russian (`ru`) and English (`en`) interfaces use natural, unambiguous copy
  for headings, helper descriptions, field labels, role badges, buttons, and status announcements.
- **Visual continuity**: Uses the shared light Wishenka palette, surface hierarchy, semantic
  primary/secondary/destructive button styling, and visible keyboard focus outlines from
  WISHENKA-288.
- **Surprise Invariant**: Nothing in the wishlist header, wishes overview, settings, sharing
  panels, or participant list reveals reservation counts, giver identities, or purchase statuses
  to a user who is or may be the gift recipient.

## Definition of Done

1. Opening a wishlist immediately displays the return button, wishlist title (or localized
   untitled fallback), user role badge, optional description and event details, and places the
   **Wishes** section first before any administrative sections.
2. Wishlist settings (title, description, event, date) are presented in a clean, non-distracting
   section for owners and administrators; **Save settings** and **Cancel** are visually distinct,
   saving updates the displayed header and announces confirmation, cancelling restores saved
   values, and failed saves preserve user input with an explicit error notice.
3. Public gift-selection link sharing and collaborator invitation link sharing are visually and
   textually distinct with clear explanatory copy, copy/share actions, and public-link replacement
   or invite-link revocation feedback.
4. Participant rows display each member's name, localized role badge, and role-permitted actions
   (promote/demote admin for owner, destructive remove member for collaborators) that are
   understandable without external instructions.
5. In both Russian and English on mobile viewports, all sections, forms, link panels, and member
   rows render cleanly without horizontal overflow, text overlap, or undersized touch targets.
6. Existing wishlist management, favorite toggling, archived-list restoration, public gift viewing
   and reservation, collaborator invitation acceptance, and Surprise Invariant protections remain
   fully intact.

## Constraints and Assumptions

- Authoritative domain rules for roles (`Owner`, `Admin`, `Collaborator`, `Giver`, `Recipient`),
  collaborative permissions, capability links, and the Surprise Invariant come from the product
  concept and functional specification.
- Visual identity, light palette tokens, and semantic button hierarchy come from parent epic
  WISHENKA-287 and completed foundation story WISHENKA-288.
- Owner wishlist deletion with confirmation is owned by WISHENKA-295 and creation-exit empty-list
  handling is owned by WISHENKA-296; WISHENKA-290 keeps existing workflows compatible for those
  sibling stories.

## Q&A

- **Why keep the wishes section above settings and sharing?** Users open a wishlist primarily to
  view or manage wishes. Keeping wishes at the top prevents administrative controls from
  overwhelming the main content while keeping settings, sharing, and member controls easy to reach
  below.
- **How are public sharing and collaborator invitations prevented from being confused?** Each has
  its own dedicated heading, plain-language explanation of who the link is for and what permissions
  it grants (secret gift reservation for givers vs co-editing wishes for collaborators), and
  separate link replacement/revocation controls.
- **Does this story add wishlist deletion?** No. Deleting a wishlist with confirmation is covered
  by sibling story WISHENKA-295.
