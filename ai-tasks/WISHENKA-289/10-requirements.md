# WISHENKA-289: Convenient wishlist overview and navigation

## Goals

Wishenka users should immediately understand which wishlists are available to them on the home
screen, tell apart their own lists, collaborative lists, and saved favorites at a glance, and begin
creating a new wishlist without friction.

Key user value:

- Users see all accessible wishlist categories clearly organized on the home overview.
- Users reach viewing history, active gift reservations, and personal settings in one direct step.
- Empty sections look intentional rather than broken and clearly guide the user on what to do next.
- The entire overview is comfortable to scan and operate one-handed on a mobile phone.

## Task Description

Redesign the home overview experience of the Telegram Mini App so that returning and first-time
users can quickly locate relevant wishlists, recognize their role on each list, navigate to key
supporting screens, and understand empty sections in both Russian and English.

The implementation languages are Python, JavaScript, HTML, and CSS (covering bilingual UI copy,
client overview presentation, and home navigation layout). This task focuses on the home overview
user experience and does not alter underlying permission rules, reservation privacy, or list
creation submission behavior.

### Scope and boundaries

In scope:

- Clear visual and structural distinction between the home sections: **My wishlists**
  («Мои вишлисты»), **Collaborating** («Совместные»), and **Favorites** («Избранные»), plus
  conditional visibility of **Recently deleted** («Недавно удалённые») when the owner has lists
  inside the recovery retention window.
- Scannable wishlist summary cards where the list title (or localized untitled fallback),
  user ownership or role indicator, and primary open action are immediately clear, while secondary
  card actions (such as removing a list from favorites or restoring a deleted list) are visually
  subordinate and unmistakable.
- Prominent, low-friction entry point to start creating a new wishlist while keeping the existing
  creation trigger contract compatible until WISHENKA-296 updates the creation submission flow.
- Direct, single-step home navigation to **My reservations** («Мои бронирования») with its
  active reservation counter, **Viewing history** («История просмотров»), and **Settings**
  («Настройки»).
- Informative empty states across **My wishlists**, **Collaborating**, and **Favorites** that
  explain why a section is empty and suggest a clear next step.
- Mobile-first ergonomics, clean text wrapping, touch-friendly controls, and natural wording in both
  Russian and English, preserving the shared light visual identity from WISHENKA-288.

Out of scope (owned by sibling sprint stories or excluded by product rules):

- Individual wishlist detail screen, item list, link sharing panel, and member management
  (WISHENKA-290).
- Personal settings screen internals (WISHENKA-291).
- Viewing history screen internals (WISHENKA-292).
- Cross-screen empty, loading, and error feedback polish outside the home overview (WISHENKA-294).
- Owner wishlist deletion with confirmation flow (WISHENKA-295).
- Preventing premature empty-wishlist creation when exiting the creation flow without wishes
  (WISHENKA-296).
- Social friend lists, user subscriptions, public user directories, search or tag filtering within
  lists, split payments, and standalone non-Telegram web accounts.

### Business entities

- **User**: an authenticated Wishenka user who may act as an owner, administrator, collaborator,
  or favorite-saving giver across different wishlists.
- **Home Overview**: the main entry screen showing navigation to supporting areas, the user's
  reservations summary, and categorized wishlist sections.
- **Wishlist Section**: a distinct thematic group on Home representing one user relationship with
  lists (**My wishlists**, **Collaborating**, **Favorites**, and conditional **Recently deleted**).
- **Wishlist Summary Card**: a scannable card representing one wishlist with its title,
  ownership or role badge, optional non-sensitive context, and permitted actions.
- **Reservations Summary Card**: a dedicated home entry displaying the count of distinct wishes on
  which the user holds an open (planned or purchased) reservation and linking to the reservations
  cabinet.
- **Empty State Guidance**: an explanatory block inside an empty section communicating why no lists
  appear and what action the user can take next.

## User Stories

- As a user with several lists, I want **My wishlists**, **Collaborating**, and **Favorites** to
  be visually distinct and clearly titled so that I can find the right list immediately.
- As a mobile user, I want each wishlist card to show its title, my role, and its main action
  cleanly so that I can scan and open lists comfortably with one hand.
- As a user wanting to make a new list, I want a clear, prominent creation button on the home
  screen so that I can start creating a wishlist in one step.
- As a gift giver or returning user, I want direct home access to **My reservations**, **Viewing
  history**, and **Settings** without searching through hidden menus.
- As a user viewing an empty section, I want to understand why there are no lists there and what I
  can do next so that the screen never feels broken or incomplete.
- As an owner who recently deleted a list, I want a separate **Recently deleted** section showing
  remaining retention days and a restore action so that I can recover an accidentally deleted list
  without confusing it with active lists.
- As a Russian- or English-speaking user, I want natural, consistent wording that fits on a phone
  screen without overlap, clipping, or horizontal scrolling in either language.
- As a gift recipient, I expect the home screen never to reveal reservation statuses, giver
  identities, or gift purchase details on my wishlists.

## Functional Requirements

### FR-1: Section organization and distinction

- The home screen presents active wishlists in three clearly separated, visually distinguishable
  sections:
  1. **My wishlists** («Мои вишлисты»): active wishlists owned by the user.
  2. **Collaborating** («Совместные»): active wishlists where the user participates as an
     administrator or collaborator.
  3. **Favorites** («Избранные»): external wishlists saved by the user where the user is neither
     owner nor active collaborator.
- Role precedence stays enforced: if a collaborator or administrator also saves that wishlist as a
  favorite, the list appears in **Collaborating** with its operational role rather than being
  duplicated or downgraded into **Favorites**.
- When the user owns soft-deleted wishlists still inside the retention window, a separate
  **Recently deleted** («Недавно удалённые») section appears on Home with clear visual separation
  from active lists. When no recoverable deleted lists exist, this section stays hidden.

### FR-2: Card scannability and action clarity

- Every active wishlist card displays:
  - The wishlist title, using a clear localized untitled fallback when the list has no custom name.
  - A recognizable, localized role/ownership badge (**Owner / Владелец**,
    **Admin / Администратор**, **Collaborator / Соавтор**, or **Favorite / Избранное**).
  - A clear primary interaction to open the wishlist, visually prioritized over any secondary card
    action.
- Cards in **Favorites** provide a subordinate, unambiguous action to remove the wishlist from
  favorites so the user clearly understands they are removing the bookmark rather than deleting
  another person's list.
- Cards in **Recently deleted** display the list title (or untitled fallback), the remaining days
  until permanent deletion, and a clear **Restore** («Восстановить») action with explicit in-flight
  and outcome feedback (restored, retention expired, or restore failure).

### FR-3: Prominent wishlist creation entry point

- A primary **Create wishlist** («Создать вишлист») control sits prominently near the top of the
  home screen so starting a new list takes a single tap without scrolling past long list sections.
- Launching the Mini App with a creation intent continues to surface or focus the creation entry
  point without unexpected behavior.
- The existing creation trigger behavior remains compatible so WISHENKA-296 can later refine
  creation submission and empty-list exit behavior without breaking home entry flows.

### FR-4: Single-step navigation to key sections

- **My reservations** («Мои бронирования») appears as a clear, scannable entry card on Home
  showing the user's count of distinct wishes with open (planned or purchased) reservations.
  - If the reservations summary cannot be loaded or is unavailable, the wishlist sections on Home
    still render and remain usable.
- **Viewing history** («История просмотров») and **Settings** («Настройки») are directly reachable
  from the home navigation bar in one tap, styled consistently as secondary navigation actions
  subordinate to **Create wishlist**.

### FR-5: Helpful empty states

- When **My wishlists**, **Collaborating**, or **Favorites** has no items, the section remains
  visible and shows an intentional, readable empty state that explains:
  - **Why it is empty** (for example: no personal wishlists created yet; no invitations to
    collaborative lists accepted yet; no shared wishlists bookmarked yet), and
  - **What to do next** (for example: use Create wishlist to start a personal list; ask a list
    owner for an invitation link to co-edit; open someone's shared wishlist and save it to
    favorites).
- Empty-state blocks use calm, intentional presentation consistent with the light Wishenka identity
  so they never resemble error banners or missing data.

### FR-6: Mobile ergonomics, bilingual clarity, and privacy

- **Mobile usability**: At typical smartphone widths, navigation controls, cards, badges, and
  actions fit cleanly without horizontal page overflow, overlapping controls, or clipped labels.
  Interactive targets are comfortably sized for touch interaction, and long wishlist titles wrap
  gracefully without pushing role badges or buttons off-screen.
- **Bilingual parity**: Both Russian (`ru`) and English (`en`) versions preserve equal clarity,
  action hierarchy, and layout stability, including longer Russian labels.
- **Visual continuity and accessibility**: Reuses the light palette, surface distinction, button
  hierarchy, and visible keyboard focus indicators established in WISHENKA-288.
- **Privacy and Surprise Invariant**: No card or section on Home reveals reservation counts, buyer
  identities, or purchase statuses for wishes where the user is or could be a recipient; only the
  **My reservations** summary reflects the user's own active reservations.

## Definition of Done

1. **My wishlists**, **Collaborating**, and **Favorites** are visually and semantically distinct on
   the home screen; **Recently deleted** appears only when the owner has recoverable deleted lists,
   and collaborator-favorited lists follow `Owner > Admin > Collaborator > Favorite` precedence.
2. Every wishlist card communicates the list title, user role/ownership badge, and primary open
   action at a glance; secondary actions (removing from favorites, restoring a deleted list) are
   visually subordinate and unambiguous in meaning.
3. **Create wishlist** stands out as the primary action on Home and remains compatible with the
   existing creation trigger contract; **My reservations** (with open distinct-wish count),
   **Viewing history**, and **Settings** are each reachable from Home in one step.
4. Empty states for **My wishlists**, **Collaborating**, and **Favorites** explain both why the
   section is empty and what the user can do next in natural Russian and English copy.
5. On mobile viewports in both Russian and English, navigation, cards, badges, and empty states
   remain legible, touch-friendly, and free from horizontal overflow, overlap, or truncation.
6. Existing role access rules, non-blocking fallback if the reservations card fails, keyboard focus
   visibility, and the Surprise Invariant remain fully preserved.

## Constraints and Assumptions

- Authoritative domain rules for roles, favorites, retention windows, viewing history, and surprise
  protection come from the high-level product concept and the functional specification.
- Visual direction and shared action hierarchy come from parent epic WISHENKA-287 and completed
  foundation story WISHENKA-288.
- Sibling stories WISHENKA-290 through WISHENKA-296 own their respective sub-screens, delete
  confirmations, cross-screen polish, and creation-exit fixes; WISHENKA-289 avoids duplicating or
  breaking those interfaces.

## Q&A

- **Why refine Home separately from WISHENKA-288?** WISHENKA-288 established the shared visual
  palette and semantic button tokens across shells; WISHENKA-289 applies them specifically to Home's
  layout, card scannability, navigation clarity, and empty-state guidance.
- **Why keep the existing creation trigger compatible?** WISHENKA-296 owns changing what happens
  when a user exits creation without adding wishes. Keeping the Home trigger compatible prevents
  rework and keeps the sprint stories cleanly decoupled.
- **Should an empty Recently deleted section show guidance?** No. Showing it only when recoverable
  deleted lists exist keeps the home overview uncluttered during everyday use.
- **Are search or filters part of this story?** No. Per the product concept, in-list search and
  complex filtering are out of scope; clear categorization and scannable cards solve list finding.
