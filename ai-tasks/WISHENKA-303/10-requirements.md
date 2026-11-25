# WISHENKA-303: Access model for Viewing History and protection against unauthorized wishlist disclosure

## Goals

Protect private wishlists from unauthorized enumeration and metadata disclosure through the Viewing History feature, while preserving the ability for wishlist owners, collaborative participants, and legitimate givers to record and revisit wishlists they have access to.

Currently, any authenticated user can record a view of an arbitrary non-deleted wishlist using its sequential identifier without being a member or having opened its share link, and then retrieve that wishlist's title, description, and event details from their Viewing History. Closing this gap removes a high-severity privacy and data-disclosure risk and aligns Viewing History with the access model established for Favorites in `WISHENKA-302`.

Implementation language: Python.

## User Stories

- **Wishlist Owner:** As a wishlist owner, I want my own wishlists that I view to be recorded in my Viewing History for quick navigation, and I expect that strangers who have neither membership nor my active share link cannot record views of my wishlist or read its title, description, or event details through Viewing History.
- **Wishlist Owner (access revocation):** As a wishlist owner, if I remove a participant who lacks active share-link access, or revoke/rotate my share link for non-members, I expect those users to immediately lose access to my wishlist in their Viewing History and be unable to record new views of it.
- **Participant (Co-author / Admin):** As a participant of a collaborative wishlist, I want my views of the wishlist to be recorded and shown in my Viewing History without needing a separate share link.
- **Giver (Share-link visitor):** As a giver who has opened someone's wishlist via its active share link, I want that visit to be reflected in my Viewing History so I can easily return to the wishlist later.
- **Unauthorized User (Stranger):** As a user without membership and without valid share-link access to a wishlist, I must be prevented from recording a view of it or seeing any of its metadata in Viewing History, and the system must not reveal whether that wishlist exists.

## Definition of Done

1. **Access model defined and enforced:** Recording a view of a wishlist and listing it in Viewing History are permitted only when the user is either a current member of the non-deleted wishlist (owner or collaborative participant) or has verified access via the wishlist's current active share link.
2. **Unauthorized recording blocked:** When an authenticated user without membership and without valid share-link access attempts to record a view of a wishlist, the request is denied as not found/inaccessible, no viewing history entry is created or updated, and no information about whether the wishlist exists is disclosed.
3. **Unauthorized listing blocked:** Retrieving Viewing History returns only non-deleted wishlists to which the user currently has valid access (membership or verified active share-link access).
4. **Legitimate workflows preserved:**
   - A wishlist owner can record views of their own non-deleted wishlist and see it in their Viewing History.
   - A collaborative wishlist participant (co-author or admin) can record views of the wishlist and see it in their Viewing History.
   - A giver who has opened a wishlist via its active share link can have their view recorded and see the wishlist in their Viewing History.
   - Deleted wishlists cannot be recorded in Viewing History and are not returned in Viewing History.
5. **Access revocation enforced:**
   - If a participant's membership is removed and they do not have verified active share-link access, the wishlist is no longer returned in their Viewing History and cannot be newly recorded.
   - If a participant's membership is removed but they still hold verified access via the current active share link, they retain Viewing History access via that share-link access until the share link is rotated or revoked.
   - If a wishlist's share link is rotated or revoked, non-members who only had access via the previous share link no longer see the wishlist in their Viewing History and cannot record new views until they open the new active share link.
6. **Cleanup of legacy unauthorized records:** Existing viewing history records for non-members who lack verified access via the wishlist's current active share link are purged so previously leaked entries are removed rather than merely hidden. Existing members (owners and collaborative participants) and non-members whose active share-link access is verified retain their viewing history, while legitimate givers whose prior share-link access cannot be verified can re-record a wishlist in their Viewing History simply by opening its active share link again.
7. **Surprise invariant preserved:** Viewing History continues to expose no gift reservation details or buyer identities.
8. **Automated test coverage:** Existing tests that relied on non-members recording viewing history for arbitrary wishlists without share-link access are updated to match the access model, and automated tests cover stranger denial (recording and listing), member access (including owner), giver share-link access, and revoked access (membership removal and share-link rotation).

## Task Description

### Problem

Wishlists are identified by sequential numbers and are intended to be private to their owner, collaborative participants, and givers who receive a direct share link (`specs/00-high.md`, `in-docs/spec.md`). However, Viewing History currently only checks that a wishlist exists and is not deleted when recording a view, and performs no access check when listing history. Because of this, any authenticated user can enumerate wishlist identifiers, record views of private wishlists, and read their title, description, and event details through Viewing History.

### Business and Security Decision

Two access models were evaluated (mirroring the decision in `WISHENKA-302`):
- **Option A (Membership-only):** Restrict Viewing History strictly to wishlist members (owners and collaborative participants). This would prevent givers who open a wishlist via a share link from having their recent visits tracked in Viewing History, breaking the personal recent-views experience for givers (`specs/00-high.md` section 4.1, `in-docs/spec.md` section 8.2).
- **Option B (Membership OR verified active share-link access — Selected):** Allow recording and viewing history for users who are either current members of the wishlist (owner or collaborative participant) or have verified access via the wishlist's current active share link. This aligns Viewing History with Favorites (`WISHENKA-302`), preserves the giver experience, and closes the sequential-identifier enumeration and unauthorized disclosure vulnerability.

### Main Business Entities

- **Wishlist:** A collection of wishes with a lifecycle status (active, archived, deleted), an owner, optional collaborative participants, and an active share link.
- **Member (Owner / Co-author / Admin):** A user who owns a wishlist or has been explicitly granted collaborative membership in it.
- **Giver:** A user who accesses another user's wishlist via its active share link.
- **Viewing History Entry:** A user's personal record of having recently viewed an accessible, non-deleted wishlist, displayed in their Viewing History with the wishlist's title, visit timestamp, and the user's effective role.
- **Verified Share-Link Access:** Proof that a user has legitimately opened a wishlist through its current active share link.

### Scope and Constraints

- **In scope:** Access control for recording and listing Viewing History, invalidation upon membership removal or share-link rotation/revocation, cleanup/purging of existing unverified non-member viewing history records, and updating/adding automated tests.
- **Out of scope:** Changes to Favorites access control (handled in `WISHENKA-302`), deterministic tie-breaking for equal timestamps (`WISHENKA-304`), duplicate logging cleanup (`WISHENKA-305`), browser test hardening (`WISHENKA-306`), or changes to the Surprise Invariant.
- **Non-functional (Security & Privacy):** Denial responses for unauthorized users must be indistinguishable from responses for non-existent or deleted wishlists so wishlist existence cannot be probed.

## Q&A

- **Q:** Should Viewing History be restricted to members only (Option A), or should it also allow givers who opened an active share link (Option B)?
  **A:** Option B (Membership or verified active share-link access), consistent with `WISHENKA-302` for Favorites. This keeps Viewing History useful for givers who visit shared wishlists while preventing unauthorized enumeration of private wishlists.
- **Q:** Can a wishlist owner record and see their own wishlist in Viewing History?
  **A:** Yes. Unlike Favorites (where self-favoriting is disallowed), an owner is a member of their own wishlist and may record and see views of their own wishlists in Viewing History.
- **Q:** What happens to viewing history records already stored before this change?
  **A:** Existing viewing history records for users who are neither current members (owners or collaborative participants) nor holders of verified active share-link access cannot be distinguished from unauthorized enumeration and must be purged—not merely filtered out at read time—so leaked associations do not persist. Existing members and non-members whose active share-link access is already verified retain their viewing history, and legitimate givers whose prior visits lack verified share-link access can re-record a wishlist simply by opening its active share link again.
- **Q:** What happens when access is revoked?
  **A:** If a participant is removed from a wishlist and has no verified active share-link access, or if the owner rotates/revokes the share link for non-members, affected users immediately lose visibility of that wishlist in Viewing History and cannot record new views without regaining valid access.
