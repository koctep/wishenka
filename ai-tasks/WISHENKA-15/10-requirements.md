# WISHENKA-15: Vertical Wish List Display, Inline Card Expansion, and Manual Ordering

## Goals

### Context and Business Goal

The Wishenka service inside Telegram enables users to create personal and collaborative wishlists,
capture gift ideas, and share lists with friends and family while preserving the secrecy of gift
surprises.

Once wishes are added to a wishlist, both list authors (owners, administrators, and collaborative
members) and gift givers (guests and non-recipient collaborators) interact primarily with the
vertical list of wish cards. To make browsing, prioritizing, and curating a wishlist effortless on
mobile screens inside the Telegram Mini App, the product requires a structured and interactive
wish list presentation:

1. **Scannable Compact Cards**: Users need to view dozens of wishes at a glance without visual
   clutter. Each card must present essential summary information (photo or placeholder, title,
   price, category, priority, desired quantity, store indicator, and recipient designation in
   joint lists) in a clean vertical layout.
2. **Inline Card Expansion on Tap**: Tapping any card in the list must reveal its full details
   (complete description and comments, store link action, category, priority, quantity, recipient
   details, and management actions for authorized editors) directly in place without navigating
   away or losing scroll context.
3. **Manual Priority Ordering**: Wishlist authors need to curate the exact presentation sequence of
   their active wishes—placing the most desired or time-sensitive gifts at the top—using intuitive
   manual reordering controls (drag-and-drop and/or directional move buttons) that persist for all
   viewers. Product specifications explicitly favour manual ordering over complex search, filter,
   or sort menus.
4. **Safe Archiving with Gifter Awareness and Surprise Protection**: Removing a wish from the
   active list is performed via safe archiving (soft removal) rather than permanent destruction,
   so existing gifter reservations remain intact. Before archiving, the user must see a clear
   confirmation dialog explaining safe archiving and supporting the per-wishlist preference for
   warnings when an item already has a gifter, while strictly safeguarding gifter identities.
5. **Archived Items Management and Restoration**: Authors need a dedicated way on the wishlist
   screen to inspect archived wishes and restore any archived item back to the active list.

---

## Task Description

### Target Environment and Language

- **Implementation language**: Python and JavaScript.
- **Runtime environment**: Telegram Mini App interface within the Wishenka platform.

### Main Business Entities and Concepts

1. **Wish Card (Compact and Expanded States)**:
   - The visual representation of a wish item within a wishlist.
   - **Compact State**: Default scannable summary showing thumbnail image (or visual placeholder),
     title, formatted price and currency, category, priority indicator, desired quantity badge (when
     greater than one), target recipient badge (in collaborative wishlists), and external store
     indicator.
   - **Expanded State**: Inline detailed view toggled by tapping the card. Reveals the full
     multi-line description/comment, direct action to open the external store link, complete
     metadata badges, and (for authorized editors on an active wishlist) item management actions.
2. **Manual Display Order**:
   - The custom sequence of active wish cards defined by wishlist authors.
   - Determines the exact vertical order in which active wishes appear to owners, collaborators,
     and external gift givers.
3. **Safe Archiving and Confirmation Dialog**:
   - Moving an active wish to the archive hides it from the active gift showcase without deleting
     the wish or cancelling existing gifter reservations.
   - Includes a confirmation dialog before archiving that explains the archive behavior and
     respects the wishlist's gifter-warning preference (notifying the author if the item is
     currently reserved, when enabled, without ever disclosing who reserved it).
4. **Archived Wishes Section**:
   - A secondary view or collapsible section accessible to wishlist authors where archived wishes
     are listed and can be restored to the active wishlist.
5. **Surprise Invariant**:
   - Core product rule: a gift recipient must never see gifter identities, purchase statuses, or
     individual reservation details on compact or expanded cards (aside from the explicit,
     anonymous gifter-presence warning during archiving when that option is enabled).

---

## User Stories

- **US-1 (Scannable Vertical List)**: As a wishlist viewer (author or guest), I want to see active
  wishes arranged in a clean vertical list of compact cards showing the photo, title, price, and
  category, so that I can quickly scan the gift ideas on a mobile screen.
- **US-2 (Inline Expansion on Tap)**: As a wishlist viewer, I want to tap a compact wish card to
  expand its full description, external store link, and details directly within the list, and tap
  again to collapse it, so that I can inspect gift requirements without leaving my scroll position.
- **US-3 (Manual Reordering)**: As an authorized wishlist editor (owner, administrator, or member
  of an active wishlist), I want to manually change the order of wish cards using drag-and-drop or
  up/down move controls, so that the most important gifts appear first to everyone viewing the
  list.
- **US-4 (Safe Archiving Confirmation with Optional Gifter Warning)**: As an authorized wishlist
  editor, I want to see a confirmation dialog when archiving a wish that explains the item will be
  moved to the archive and optionally warns me if a gifter has already reserved it (according to
  my wishlist preference), so that I do not accidentally disrupt a gifter's plans.
- **US-5 (Viewing and Restoring Archived Wishes)**: As an authorized wishlist editor, I want to
  view archived wishes in a dedicated section and restore any archived wish back to the active
  list, so that I can bring back previously postponed gift ideas without re-entering them.
- **US-6 (Role-Based Protection and Surprise Secrecy)**: As a guest or gift giver opening a shared
  wishlist, I want to browse cards in the author's custom order and expand card details without
  seeing any editing, reordering, or archiving controls; and as a gift recipient, I want gifter
  identities and reservation details to remain hidden from me on the wish list.

---

## Functional Requirements

### 1. Vertical Wish List Display and Card Anatomy

- **Vertical List Layout**:
  - Active wishes belonging to a wishlist are displayed as a single-column vertical list of cards
    ordered according to their saved manual display order.
  - When a wishlist has no active wishes, an informative empty-state message is displayed (with a
    prompt for authors to add their first wish).
- **Compact Card Anatomy**:
  - Every wish card renders in the compact state by default and displays:
    1. **Thumbnail or Placeholder**: The product image if available, or a clean visual fallback
       placeholder when no image is provided or when an external image fails to load.
    2. **Title**: The wish title, clearly legible and truncated gracefully if overly long in the
       compact view.
    3. **Formatted Price**: The approximate price and currency symbol/code when specified (omitted
       cleanly if no price is set).
    4. **Category Badge**: The item category label when specified.
    5. **Priority Indicator**: Visual indication when priority is non-default (e.g., high priority
       "very wanted" or low priority).
    6. **Quantity Badge**: When desired quantity is greater than 1, a badge indicating the total
       requested piece count (e.g., "6 pcs").
    7. **Collaborative Recipient Badge**: In collaborative wishlists, a badge indicating who the
       gift is designated for (a specific member, a named external person, or general/shared).
    8. **External Store Badge**: The recognized store or domain name when an external product link
       is attached.

### 2. Inline Card Expansion on Tap

- **In-Place Toggle Behavior**:
  - Tapping the body or header of a compact wish card expands the card inline directly within the
    vertical list without page reload or screen navigation.
  - Tapping the expanded card header/toggle area collapses the card back to its compact state.
  - Interactive action buttons inside the card (such as opening an external store link, editing,
    reordering, or archiving) must execute their specific action without unintentionally toggling
    the card's expansion state.
- **Expanded Card Content**:
  - Full, untruncated wish title.
  - Full multi-line description and author comments (e.g., size, color, delivery notes).
  - Prominent external store link call-to-action button (when a product URL is present) that opens
    the store page safely in an external browser tab/window.
  - Complete metadata summary: category, priority level, desired quantity, and recipient
    designation (in collaborative wishlists).
  - **Editor Management Actions** (visible only to authorized editors on an active wishlist):
    - Action to open the detailed edit form for the wish.
    - Action to initiate safe archiving of the wish.
    - Controls to move/reorder the wish within the active list.

### 3. Manual Ordering Controls

- **Authorized Roles and State**:
  - Manual reordering is available exclusively to authenticated wishlist authors (Owner,
    Administrator, and Member) when the parent wishlist is in the active state.
  - Guests, gift givers, and viewers of archived wishlists never see reordering handles or move
    buttons.
- **Interaction Mechanisms**:
  - Authorized editors can reorder active wish cards using:
    - **Directional Move Controls**: Accessible "Move Up" and "Move Down" controls on cards (with
      the "Move Up" control disabled on the first card and "Move Down" disabled on the last card)
      to guarantee reliable operation across all mobile touchscreens and assistive technologies.
    - **Drag-and-Drop Gesture**: Pointer/touch drag handle allowing direct card repositioning in
      the vertical list.
- **Persistence and Synchronization**:
  - Whenever the author changes the card order, the updated sequence of active wishes is persisted
    immediately without requiring a full page reload.
  - Subsequent views of the wishlist by the owner, co-authors, and external gift givers reflect
    the exact saved custom order.
  - Newly created wishes and wishes restored from the archive are appended to the end of the
    current active order.
  - If saving the new order fails due to a network or validation error, the interface restores the
    previous valid card order and displays a clear error message.

### 4. Safe Archiving Confirmation Dialog and Gifter Warning Option

- **Confirmation Before Archiving**:
  - Triggering the archive action on an active wish (from the expanded card or the edit view)
    presents an explicit confirmation dialog before performing the state change.
  - The dialog clearly communicates that archiving moves the wish out of the active gift list into
    the archive (where it can be restored later) rather than permanently deleting it, and that any
    existing reservations remain preserved for gifters.
- **Optional Gifter Warning Setting**:
  - In accordance with product specifications, wishlists support a preference for whether to warn
    the author before archiving a wish that already has an active or purchased reservation.
  - On first archiving (or via the confirmation dialog option), the author can choose whether such
    warnings about the presence of a gifter should be shown.
  - When the gifter-warning preference is enabled and the wish being archived has one or more
    locked units (active or purchased reservations), the confirmation dialog displays an explicit
    warning that someone has already reserved or purchased this gift.
  - **Strict Surprise Boundary**: Even when the gifter warning is shown, the dialog must **never**
    reveal the identity, username, or personal details of the gifter.
- **Completion of Archiving**:
  - Confirming the dialog archives the wish, smoothly removes it from the active vertical list,
    and updates the archived wishes section.
  - Cancelling the dialog leaves the wish untouched in its current position in the active list.

### 5. Archived Items Section and Restoration

- **Viewing Archived Wishes**:
  - For authorized wishlist authors (Owner, Administrator, Member), the wishlist screen provides
    access to an "Archived Wishes" section (e.g., a collapsible section or toggleable view below
    the active list) when one or more archived wishes exist.
  - Archived wishes are clearly distinguished visually from active wishes and do not participate in
    manual reordering.
  - External guests and non-member gift givers do not see the archived wishes section on the
    wishlist showcase.
- **Restoring an Archived Wish**:
  - On an active wishlist, authorized authors can trigger a "Restore" action on any archived wish.
  - Restoring the wish moves it back to the end of the active vertical wish list, preserves any
    existing reservations, and immediately makes its card expandable and reorderable again.

### 6. Role-Based Visibility and Surprise Invariant

| Role / Context | View Custom Order | Expand Inline | Reorder | Edit & Archive | Archive Section |
| --- | :---: | :---: | :---: | :---: | :---: |
| **Owner (Active)** | Yes | Yes | Yes | Yes | Yes |
| **Admin / Member (Active)** | Yes | Yes | Yes | Yes | Yes |
| **Guest / Gifter** | Yes | Yes | No | No | No |
| **Any Role (Archived List)** | Yes | Yes | No | No | Read-only |

- **Surprise Invariant Enforcement**:
  - When the viewer is the recipient of a wish (always true for the Owner on a personal wishlist,
    and true for the designated member on a collaborative wishlist), neither the compact card nor
    the expanded card may disclose reservation counts, remaining available quantities, purchase
    flags, or gifter identities.
  - Non-recipient viewers (external guests, gift givers, and collaborative members who are not the
    designated recipient of that specific wish) see item availability for gift coordination.

---

## Non-Functional and UX Requirements

1. **Mobile Responsiveness in Telegram Mini App Viewport**:
   - The vertical card list, inline expansion panels, reordering controls, and confirmation dialog
     must fit comfortably within narrow mobile viewports (320px to 430px width) without horizontal
     overflow.
   - All interactive controls (expand/collapse areas, move up/down buttons, drag handles, archive
     and restore buttons) must provide touch targets of at least 44x44 pt.
   - The layout must respect the bottom clearance required by the fixed quick-add bar so the last
     wish card and archived section are never obscured.
2. **Smooth Inline Toggle and Visual Feedback**:
   - Expanding and collapsing a card must occur instantaneously with clear visual state indicators
     (such as a directional chevron and expanded/collapsed state indication).
   - Reordering, archiving, and restoring must update the list dynamically without full-page
     refreshes or loss of scroll position.
3. **Accessibility**:
   - Card expansion toggles must be keyboard and screen-reader accessible with descriptive labels
     and announced expansion state.
   - Manual move controls ("Move up", "Move down") must have explicit accessible labels so users
     relying on assistive technologies can reorder items without requiring complex drag gestures.
   - The archiving confirmation dialog must use accessible dialog semantics and focus management.
4. **Content Security and XSS Safety**:
   - All user-supplied and extracted text fields (titles, descriptions, categories, store names,
     recipient names) must be strictly escaped when rendered in compact cards, expanded details,
     and confirmation dialogs to prevent Cross-Site Scripting (XSS).
   - External product links must open safely in a separate browser context with referrer and
     window isolation.

---

## Definition of Done and Acceptance Criteria

### Scenario 1: Viewing Compact Wish Cards in Custom Order
- **Given** an active wishlist containing multiple wishes with photos, prices, categories,
  quantities, and custom display order
- **When** any user (owner, collaborator, or guest) opens the wishlist in the Mini App
- **Then** the wishes are rendered vertically in the exact saved display order, and each compact
  card displays its thumbnail (or placeholder), title, formatted price/currency, category badge,
  quantity badge (when > 1), and recipient badge (in collaborative lists).

### Scenario 2: Inline Card Expansion and Collapse on Tap
- **Given** a user viewing the vertical list of compact wish cards
- **When** the user taps on a compact wish card
- **Then** the card expands inline in place (without navigating to another page), revealing the
  full description/comment, full metadata, external store link button, and (if the user is an
  authorized editor on an active wishlist) edit, reorder, and archive controls; and tapping the
  card toggle again collapses the details.

### Scenario 3: Manual Reordering by Authorized Editor
- **Given** an owner, administrator, or member viewing an active wishlist with 3 wishes `[A, B, C]`
- **When** the editor moves wish `C` above wish `B` (or drags `C` to the first position)
- **Then** the new order is persisted immediately, the UI reflects the updated order without page
  reload, and subsequent reloads by both the author and guests display the wishes in the new
  order.

### Scenario 4: Safe Archiving Confirmation with Gifter Warning Option
- **Given** an authorized editor viewing an active wish that has an active reservation by a gifter
- **When** the editor initiates the "Archive" action on that wish
- **Then** a confirmation dialog appears explaining that the wish will be moved to the archive
  while keeping reservations intact, allows configuring/respecting the gifter-warning preference,
  warns that the gift is currently reserved by a gifter (when warning is enabled) without exposing
  the gifter's identity, and moves the card to the archive only upon confirmation.

### Scenario 5: Viewing and Restoring Archived Wishes
- **Given** an authorized editor on an active wishlist that has at least one archived wish
- **When** the editor opens the archived wishes section and clicks "Restore" on an archived wish
- **Then** the wish is removed from the archived section and appended to the end of the active
  vertical wish list with all its data and reservations preserved.

### Scenario 6: Guest Isolation and Surprise Invariant
- **Given** a guest viewing a wishlist via public link, or a recipient viewing their own wishlist
- **When** they inspect compact and expanded wish cards
- **Then** the guest sees no edit, reorder, archive, or archived-section controls, and the
  recipient never sees gifter identities or reservation counts on their wishes.

---

## Out of Scope

- Search, filtering by category/priority, or automatic sorting (by price, date, or name) within a
  wishlist (explicitly excluded by product specification Section 5.4).
- Gifter reservation creation, quantity modification, and purchase marking controls on the card
  (covered by dedicated gift reservation tasks).
- Marking wishes as "Received / Gifted" and the separate "Gifted" archive section (covered by
  dedicated gift fulfillment tasks).
- Telegram Bot chat notifications sent to gifters after an item is archived (covered by
  notification tasks).

---

## Q&A

- **Q1: Why provide both directional move buttons (Up/Down) and drag-and-drop for manual ordering?**
  **A1**: Mobile touch screens inside Telegram have varying scroll inertia, and screen-reader
  users cannot easily perform touch drag gestures. Providing explicit Up/Down move controls
  alongside drag-and-drop ensures 100% reliability, accessibility, and precision on all devices.

- **Q2: Does warning the author during archiving that a wish has an active reservation violate the
  Surprise Invariant?**
  **A2**: Product specification (`in-docs/spec.md`, Section 5.5) explicitly defines this per-list
  warning option as a conscious, opt-in exception to total reservation secrecy so authors do not
  unknowingly archive a gift someone has already bought. However, the gifter's identity and
  personal details remain strictly confidential and are never disclosed.

- **Q3: Where does a restored wish appear in the manual order?**
  **A3**: A wish restored from the archive is placed at the end (tail) of the active wish list so
  it does not disrupt the author's curated top-priority items. The author can then move it to any
  desired position.
