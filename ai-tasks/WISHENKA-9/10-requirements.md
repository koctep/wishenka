# WISHENKA-9: Favorite Wishlists and Viewing History in Telegram Mini App

## Goals

The **Wishenka** service enables Telegram users to manage personal wishlists, collaborate with family and friends on joint lists, and coordinate gifts via public links while strictly preserving the secrecy of surprises.

As users accumulate wishlists across different contexts, several usability challenges arise:
1. **Navigational Clarity**: Users cannot easily distinguish between lists they own, lists they co-edit as administrators or collaborators, and external lists they follow or gift to.
2. **Fast Return to Gifts without Social Subscriptions**: The product explicitly avoids a heavyweight friends/follower network. Gift givers need a frictionless way to bookmark important wishlists (e.g., family, friends, colleagues) and return to recently browsed lists without repeatedly digging through Telegram chat histories.
3. **Role Awareness**: Users need clear visual badges on their main screen indicating their relationship and permission tier for every list (Owner, Admin, Member, Favorite) so they know immediately what actions they are allowed to perform.

This task delivers the business requirements for the Mini App home screen list categorization, role badges, favorites management, and the recently viewed history section.

## Task Description

### Business Context and Scope
The Mini App home screen serves as the central hub for the user. It brings together:
- Personal wishlists created by the user.
- Collaborative wishlists where the user has been invited as an administrator or member.
- External wishlists saved as favorites for fast gift tracking.
- Visual role badges on each list item indicating the user's role.
- Quick navigation to a dedicated "Viewing History" section showing recently opened wishlists.
- Fast creation entry point for new wishlists.

Out of scope for this task:
- Gift reservation and purchase workflows (covered by separate gift coordination tasks).
- "My Reservations" count card deep integration.
- Public website or non-Telegram web interfaces (Wishenka operates strictly within Telegram Bot and Telegram Mini App).
- Social networking features (friend lists, user profile following, social feeds).

### Main Business Entities and Concepts

1. **Wishlist Representation**:
   - A list of desires with a title, status (active or archived), and access context.
2. **User Roles and Badges**:
   - **Owner (Владелец)**: The creator and primary controller of the wishlist.
   - **Administrator (Администратор)**: A trusted manager with editing and member management rights.
   - **Member / Collaborator (Соавтор / Участник)**: A participant permitted to add and edit wishes, but not list-level settings.
   - **Favorite (В избранном)**: A bookmarked external wishlist saved by the user for ongoing viewing and gift selection.
3. **Favorites (Избранное)**:
   - A personal collection of references to other people's wishlists that the user wishes to keep easily accessible on their main screen.
4. **Viewing History (История просмотров)**:
   - A personal, chronological log of recently opened wishlists. Allows the user to find recently viewed wishlists even if they were not explicitly added to Favorites.
5. **Surprise Secrecy (Тайна сюрприза)**:
   - Fundamental privacy invariant: regardless of how a wishlist is opened (home screen, favorites, or viewing history), a recipient must never see reservation details, giver identities, or purchase states for their own gifts.

### Target Environment and Language
- **Implementation language**: Python and JavaScript.
- **Runtime environment**: Telegram Mini App and FastAPI backend within the existing Wishenka architecture.

### Constraints and Assumptions
- Follows the product specification (`in-docs/spec.md`, Section 8) and high-level concepts (`specs/00-high.md`).
- Adheres to the permission model and role definitions established in `WISHENKA-6` and management interface foundation in `WISHENKA-8`.
- No separate friends or subscription mechanism is to be introduced.
- History and favorites are strictly private to each Telegram user.

## User Stories

- **US-1**: As a Telegram user opening the Mini App, I want to see all my own, collaborative, and favorited wishlists in a unified overview with clear role badges, so that I immediately understand my relationship to each list.
- **US-2**: As a gift giver viewing someone else's public wishlist, I want to save it to my Favorites, so that I can quickly return to it later from my main screen without asking for the link again.
- **US-3**: As a user, I want to remove a wishlist from my Favorites when I no longer need quick access to it, so that my main screen stays relevant and uncluttered.
- **US-4**: As a user, I want to view a dedicated "Viewing History" section from the home screen, so that I can easily revisit wishlists I recently browsed even if I forgot to favorite them.
- **US-5**: As a user, I want to click any entry in my viewing history to open that wishlist directly.
- **US-6**: As a user, I want the ability to clear my viewing history, so that I can maintain my personal privacy.
- **US-7**: As a wishlist owner or recipient, I want my surprise gifts and reservations to remain strictly hidden whenever I or anyone else views wishlists through the main screen, favorites, or history.

## Definition of Done

1. **Unified Home Screen List with Role Badges**:
   - The main screen displays a unified list of wishlists accessible to the user:
     - Own wishlists (created by user);
     - Collaborative wishlists (where user is Administrator or Member);
     - Favorited wishlists (external wishlists saved by the user).
   - Each item in the list displays a clear role badge or text marker:
     - `Owner` («Владелец») for own wishlists;
     - `Admin` («Администратор») for collaborative wishlists with admin privileges;
     - `Member` («Соавтор») for collaborative wishlists with member privileges;
     - `Favorite` («Избранное») for saved external wishlists.
   - When the user has no wishlists or favorites, an empty-state message is displayed along with a prominent action to create a new wishlist.
   - All badges and list items are keyboard and screen-reader accessible with descriptive text labels.

2. **Favorites Management**:
   - An authenticated user viewing an external wishlist can toggle its favorite status:
     - If not favorited: an action to "Add to Favorites" is available.
     - If already favorited: an action to "Remove from Favorites" is available.
   - A user cannot favorite their own wishlist (own wishlists are already present under the Owner role).
   - A user can remove a wishlist from Favorites either directly from the main list or from the wishlist view.
   - Removing a wishlist from Favorites does not delete the wishlist, change its contents, or affect other users.
   - If a favorited wishlist is subsequently archived or deleted, or its link is invalidated:
     - The main screen handles the state gracefully without breaking the view.
     - Opening the list informs the user of its unavailable status and offers to remove it from Favorites.

3. **Viewing History Tracking and Access**:
   - When an authenticated user opens a wishlist (via public link, collaborator invitation, or direct navigation), the event is recorded in the user's viewing history.
   - The home screen provides an explicit entry point to navigate to the "Viewing History" section.
   - The viewing history presents recently opened wishlists in reverse chronological order (most recently visited list at the top).
   - Re-visiting a wishlist updates its position to the top of the history without creating duplicate entries for the same list.
   - Viewing history is bounded to a reasonable maximum count (e.g., up to 20 recent wishlists) so that it remains performant and compact.
   - Selecting any wishlist in the history navigates directly to that wishlist.
   - An option to clear the viewing history is available to the user.
   - If a wishlist in the history has been deleted or is no longer accessible, tapping it displays a clear message rather than an unhandled error.

4. **Privacy and Surprise Secrecy**:
   - Viewing history and favorites entries never reveal reservation counts, buyer identities, or surprise gifts to any user who is the designated recipient of those gifts.
   - A user's favorites and viewing history are confidential to that user and never disclosed to list owners or other collaborators.

5. **Session Continuity and Zero-Onboarding**:
   - External visitors viewing a public gift link can browse without mandatory onboarding or registration.
   - For authenticated Telegram users, favorites and viewing history persist across Mini App reloads and sessions.
   - Errors during network requests (e.g. adding to favorites or loading history) provide clear user feedback without claiming success or leaving the UI in an inconsistent state.

## Q&A

- **Q: Why does the product have Favorites and Viewing History instead of a friends list or user subscriptions?**
  **A**: Per the core specification (`in-docs/spec.md`, Section 8.2), Wishenka deliberately avoids social networking overhead (following users, friendship requests, public profiles). Gift giving is event-driven and situational. Favorites and viewing history provide the exact utility needed—quick access to the lists a person cares about—with zero social friction.

- **Q: Can a user add their own wishlist to Favorites?**
  **A**: No. The user's own wishlists already appear prominently on the main screen with the "Owner" badge. Adding an own list to favorites would be redundant.

- **Q: What role badge is shown if a user is both a Collaborator (Member or Admin) and marks a list as Favorite?**
  **A**: The functional collaboration role (`Admin` or `Member`) takes precedence because it defines what the user is allowed to edit. The UI may additionally show a favorite indicator, but must never downgrade the displayed role to merely "Favorite".

- **Q: How does Viewing History interact with the Surprise Secrecy rule?**
  **A**: Viewing history simply remembers the identity and title of recently visited wishlists. Opening a wishlist through the history view enforces all existing privacy rules: if the viewer is the recipient of any wish in that list, reservation statuses and giver information remain completely hidden.

- **Q: Does clearing viewing history affect Favorites or the wishlists themselves?**
  **A**: No. Clearing viewing history only clears the user's local/server browsing log. It has no effect on saved Favorites, wishlist contents, or memberships.
