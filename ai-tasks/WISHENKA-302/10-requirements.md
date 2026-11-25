# WISHENKA-302: Access model for Favorites and protection against unauthorized wishlist disclosure

## Goals

Protect private wishlists from unauthorized enumeration and metadata disclosure through the Favorites feature, while preserving the core product capability for participants and givers to bookmark wishlists they legitimately have access to.

Currently, any authenticated user can add an arbitrary non-deleted wishlist to Favorites using its sequential identifier without being a member or having opened its share link, and then read that wishlist's title, description, and event details from their Favorites list. Closing this gap removes a high-severity privacy and data-disclosure risk while keeping the Favorites experience intact for legitimate users.

Implementation language: Python.

## User Stories

- **Participant (Co-author / Admin):** As a participant of a collaborative wishlist, I want to add the wishlist to my Favorites and see it in my Favorites list for quick access, without needing a separate share link.
- **Giver (Share-link visitor):** As a giver who has opened someone's wishlist via its active share link, I want to add that wishlist to my Favorites and see it in my Favorites list so I can return to it easily.
- **Wishlist Owner:** As a wishlist owner, I expect that strangers who have neither membership nor my active share link cannot add my wishlist to their Favorites or read its title, description, or event details; and if I remove a participant who lacks active share-link access, or revoke/rotate my share link for non-members, those users lose access to my wishlist in their Favorites.
- **Wishlist Owner (self-favorite guard):** As a wishlist owner, I cannot add my own wishlist to Favorites (existing rule preserved).
- **Unauthorized User (Stranger):** As a user without membership and without valid share-link access to a wishlist, I must be prevented from adding it to Favorites or seeing any of its metadata, and the system must not reveal whether that wishlist exists.

## Definition of Done

1. **Access model defined and enforced:** Adding a wishlist to Favorites and viewing it in Favorites are permitted only when the user is either a current member/participant of the non-deleted wishlist (excluding the owner) or has verified access via the wishlist's current active share link.
2. **Unauthorized addition blocked:** When an authenticated user without membership and without valid share-link access attempts to add a wishlist to Favorites, the request is denied as not found/inaccessible, no favorite entry is created, and no information about whether the wishlist exists is disclosed.
3. **Unauthorized listing blocked:** Listing Favorites returns only non-deleted wishlists to which the user currently has valid access (membership or active share-link access).
4. **Legitimate workflows preserved:**
   - A collaborative wishlist participant (member or admin) can add the wishlist to Favorites and retrieve it in Favorites.
   - A giver who has opened a wishlist via its active share link can add the wishlist to Favorites and retrieve it in Favorites with the `favorite` role.
   - An owner is still prevented from adding their own wishlist to Favorites, and deleted wishlists cannot be added or listed.
5. **Access revocation enforced:**
   - If a participant's membership is removed and they do not have active share-link access, the wishlist is no longer returned in their Favorites and cannot be re-added.
   - If a wishlist's share link is rotated/revoked, non-members who only had access via the previous share link no longer see the wishlist in their Favorites and cannot re-add it until they open the new share link.
6. **Cleanup of legacy unauthorized records:** Existing favorite records for users who lack both membership and verified share-link access are purged so previously leaked entries are removed rather than merely hidden. Because prior share-link visits were not tracked before this access model, legacy favorite records for non-members cannot be distinguished from unauthorized enumeration and are all purged; legitimate givers can re-add the wishlist simply by opening its active share link again.
7. **Surprise invariant preserved:** Favorites continue to expose no gift reservation details or buyer identities.
8. **Automated test coverage:** Existing tests that relied on non-members favoriting arbitrary wishlists without share-link access are updated to match the access model, and automated tests cover stranger denial (add and list), participant access, giver share-link access, and revoked access (membership removal and share-link rotation).

## Task Description

### Problem

Wishlists are identified by sequential numbers and are intended to be private to their owner, collaborative participants, and givers who receive a direct share link (`specs/00-high.md`, `in-docs/spec.md` section 4.5). However, Favorites currently only checks that a wishlist exists, is not deleted, and does not belong to the caller. Because of this, any user can enumerate wishlist identifiers, add private wishlists to Favorites, and read their `name`, `description`, `event_title`, and `event_date`.

### Business and Security Decision

Two access models were evaluated:
- **Option A (Membership-only):** Restrict Favorites strictly to wishlist members/participants. This would make the `favorite` role for givers unreachable and contradict `in-docs/spec.md` section 8.1 ("User can save others' wishlists to favorites for quick access") and the Mini App onboarding guidance ("Open someone's shared wishlist link and add it to favorites to keep it handy").
- **Option B (Membership OR verified share-link access — Selected):** Allow Favorites for users who are either current members/participants of the wishlist or have verified access via the wishlist's current active share link. This preserves the Giver bookmarking workflow while closing the sequential-ID enumeration and unauthorized disclosure vulnerability.

### Main Business Entities

- **Wishlist:** A collection of wishes with a lifecycle status (active, archived, deleted), an owner, optional collaborative participants, and an active share link.
- **Participant (Member / Admin):** A user explicitly granted membership in a collaborative wishlist.
- **Giver:** A user who accesses another user's wishlist via its active share link.
- **Favorite Entry:** A user's personal bookmark linking them to an accessible, non-deleted wishlist of another user, displayed in their Favorites list with their effective role.
- **Verified Share-Link Access:** Proof that a user has legitimately opened a wishlist through its current active share link.

### Scope and Constraints

- **In scope:** Access control for adding and listing Favorites, invalidation upon membership removal or share-link rotation, cleanup/migration of existing unauthorized favorite records, and updating/adding automated tests.
- **Out of scope:** Access control for Viewing History (tracked separately in `WISHENKA-303`), changes to the Surprise Invariant, or introducing social features such as friend lists or public user directories (`specs/00-high.md` section 5).
- **Non-functional (Security & Privacy):** Denial responses for unauthorized users must be indistinguishable from responses for non-existent or deleted wishlists so wishlist existence cannot be probed.

## Q&A

- **Q:** Should Favorites be restricted to `is_member` only (Option A), or should it allow givers who opened a share link (Option B)?
  **A:** Option B (Membership or verified share-link access). Restricting Favorites to `is_member` only would break the primary product use case for Givers described in `specs/00-high.md` and `in-docs/spec.md` section 8.1, where users save friends' shared wishlists for quick access. Option B closes the sequential-ID enumeration vulnerability while keeping the `favorite` role functional for legitimate share-link visitors.
- **Q:** What happens to favorite records already stored before this change?
  **A:** Because prior share-link visits were not tracked before this access model, legacy favorite records for non-members cannot be distinguished from unauthorized enumeration and must all be purged—not merely filtered out at read time—so leaked associations do not persist in storage. Existing members retain their favorites, and legitimate givers can re-add a wishlist simply by opening its active share link again.
- **Q:** What happens when access is revoked?
  **A:** If a participant is removed from a wishlist or the owner rotates/revokes the share link, affected users must immediately lose visibility of that wishlist in Favorites and must not be able to re-add it without regaining valid access.
- **Q:** Does this task also fix the analogous gap in Viewing History?
  **A:** No. Viewing History is tracked separately in `WISHENKA-303` (`ai-tasks/WISHENKA-292/60-tech-debt.md`, item 1), though the access model chosen here establishes a consistent pattern.
