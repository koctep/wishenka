# WISHENKA-80: Eliminate Full-Scan Overhead in Web Request Data Access

## Goals

Users interact with wishlists, wishes, gift reservations, gift receipts, sharing links, and user profiles through the Telegram Mini App (TMA) web interface. Every user action—such as opening a wishlist, adding or editing a wish, reserving a gift, or marking a gift as received—must feel immediate and remain responsive as the service grows.

Currently, web request handling relies on an intermediate full-state synchronization mechanism that scans broader state and computes full state differences for individual operations. As the number of wishlists, wishes, and concurrent users increases, this full-scan and diff-comparison overhead degrades response times, wastes compute and memory resources, and increases the risk of contention across concurrent user requests.

The business goals of **WISHENKA-80** are:

1. **Responsive user experience in the Mini App**:
   - Ensure web operations on wishlists, wishes, reservations, gift receipts, sharing, and profiles execute only targeted data operations without full-state scanning or diff-snapshot overhead, keeping response times fast and predictable as user data grows.
2. **Efficient resource utilization and scalability**:
   - Reduce CPU and memory overhead per web request so the service can support growing user and wishlist volumes without unnecessary load.
3. **Zero behavioral regression for end users**:
   - Preserve 100% of existing product behavior, access rules, surprise-preservation guarantees, idempotency, and error handling across all user-facing web scenarios.

## User Stories

- **US-1 (Wishlist Owner / Co-author managing wishlists and wishes)**:
  As a wishlist owner or co-author using the Mini App, I want creating, viewing, updating, archiving, and deleting wishlists and wishes to respond quickly without delays caused by scanning unrelated data, so managing my lists feels effortless.
- **US-2 (Gift Giver reserving and purchasing gifts)**:
  As a gift giver browsing a shared wishlist, I want reserving a gift, adjusting reservation quantities, and marking purchases to execute promptly and reliably without unnecessary processing overhead, while preserving the surprise for the recipient.
- **US-3 (Wishlist Owner recording gift receipts)**:
  As a wishlist owner marking gifts as received or reviewing my gifted archive, I want receipt actions to complete fast and accurately without affecting other wishlists or users.
- **US-4 (Platform Operator / Maintainer)**:
  As a platform operator, I want web request handlers to access persistent wishlist data directly through targeted operations rather than full-state diff-snapshots, so system resource usage scales with the specific operation rather than total dataset size.

## Definition of Done

1. **Elimination of Full-Scan and Diff-Snapshot Overhead**:
   - Web request workflows for wishlists, wishes, reservations, gift receipts, sharing, and profile operations perform targeted data access for the requested operation without triggering full-state scans or diff-snapshot comparisons.
2. **Full Functional Parity**:
   - All existing user-facing capabilities—wishlist CRUD, wish management, quantitative reservations, gift receipt recording, list sharing/access control, and profile/account actions—produce identical outcomes, status codes, validation errors, and surprise-isolation guarantees as before.
3. **Idempotency and Concurrency Safety**:
   - Repeated or concurrent user actions (such as duplicate reservation or receipt requests) continue to behave deterministically and safely without data corruption or duplicate side effects.
4. **Automated Verification**:
   - Existing automated test suites covering web endpoints and user scenarios pass without regression, and verification confirms that targeted data access is used for web operations.

## Task Description

- **Programming language**: Python (matching the existing application and test suite).
- **Problem**: Web endpoints currently route wishlist-related operations through an intermediate adapter that performs full-state snapshots and diff computations, introducing avoidable latency and resource overhead on every request.
- **Scope**:
  - **In scope**: All web-layer user operations interacting with wishlist domain data (wishlists, wishes, reservations, gift receipts, sharing, and profile/miniapp views).
  - **Out of scope**: New product features, changes to user-facing UI/UX, changes to business rules (such as reservation limits, surprise guarantees, or access permissions), and unrelated background bot workflows unless shared web dependencies require consistency.
- **Main Domain Entities**:
  - **User / Actor**: Wishlist Owner, Co-author / Administrator, Gift Giver, or Recipient interacting via the Mini App.
  - **Wishlist**: Personal or collaborative collection of wishes with access and sharing settings.
  - **Wish**: An item in a wishlist with metadata, required quantity, and lifecycle state.
  - **Reservation**: A gift giver's commitment to purchase a specific quantity of a wish, isolated from the recipient.
  - **Gift Receipt**: A record that a wish (full or partial quantity) has been received by the owner.

## Non-functional Requirements

- **Performance**: Per-request latency and memory usage for web operations must not scale with unrelated wishlist or global state size; full-state diff-snapshots are eliminated from web request paths.
- **Reliability & Data Integrity**: Targeted operations must preserve transactional consistency, idempotency guarantees, and concurrent access safety.
- **Security & Privacy**: Access control checks and the surprise principle (hiding reservation and giver details from recipients) must remain strictly enforced.
- **Compatibility**: External web contracts (inputs, outputs, error responses, and HTTP behavior) remain unchanged for Mini App clients.

## Constraints and Assumptions

- The implementation uses **Python**, consistent with the rest of the service.
- All existing product specifications (`specs/`, `in-docs/`) remain authoritative; this task optimizes how web operations access domain data without altering business semantics.
- Existing automated tests serve as the baseline for behavioral parity.

## Q&A

- **Q: Why is this task needed when the current web endpoints already work functionally?**
  **A:** The Jira request specifies replacing the intermediate diff-snapshot adapter in web routes with direct, targeted repository access. From a business perspective, full-state scanning and diff-snapshots add unnecessary latency and CPU/memory overhead to every user action in the Mini App. Removing this overhead keeps the app fast and responsive as user data grows, reduces server resource consumption under concurrent load, and simplifies ongoing maintenance without changing user-facing behavior.
- **Q: Does this task change any user-facing features, permissions, or API contracts?**
  **A:** No. All user scenarios, access controls, surprise-isolation rules, and client-facing contracts must remain identical.
