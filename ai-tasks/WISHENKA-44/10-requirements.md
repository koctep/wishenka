# WISHENKA-44: Persist TelegramUser to Database on Successful Authentication

## Goals

The **Wishenka** service operates as a Telegram Mini App (TMA) where users create wishlists,
reserve gifts for others, and collaborate with family and friends while strictly preserving the
secrecy of gift surprises.

In task WISHENKA-4, cryptographic verification of Telegram WebApp `initData` and session token
issuance were implemented. However, verified user profiles are not yet persisted in local storage.
Persisting user profiles upon successful authentication is essential for the following business
reasons:

1. **Persistent User Identity**:
   To associate created wishlists, items, reservations, co-author permissions, favorites, and view
   history with real user accounts, the system requires a durable, persistent user profile record.
2. **Profile Freshness and Seamless Synchronization**:
   Users frequently update their Telegram display names, usernames, or language preferences.
   The service must automatically synchronize these changes on login so that collaborators and
   gift givers always see up-to-date names and handles without manual profile management.
3. **Decoupled Internal Identity**:
   Linking sessions and domain activities to an internal user identity decouples external platform
   identifiers from internal domain logic, ensuring clean foreign key relationships and
   consistent security contexts across application features.
4. **Enabling Offline and Background Operations**:
   Features such as reminder notifications, gift delivery coordination, and bot messaging require
   accessing user profiles independently of whether a user currently holds an active browser
   session token.
5. **Safe, Idempotent Login Lifecycle**:
   Users open the Mini App repeatedly across devices and sessions. The authentication process must
   idempotently resolve existing users or onboard new users without creating duplicate accounts or
   corrupting existing state.

---

## User Stories

### US-1: Seamless First-Time Onboarding
- **As a** new Telegram user opening the Wishenka Mini App for the first time,
- **I want** the system to automatically register my account using my verified Telegram profile,
- **So that** I can immediately create and share wishlists without encountering a manual
  registration or profile setup form.

### US-2: Automatic Profile Synchronization on Returning Visits
- **As a** returning user who has updated my name or username on Telegram,
- **I want** my Wishenka profile details to update automatically when I open the app,
- **So that** my friends and gift co-authors always see my current name and contact handle.

### US-3: Binding Session Context to Internal User Identity
- **As an** authenticated user,
- **I want** my active session to be securely bound to my internal user profile identity,
- **So that** all actions I perform (adding items, reserving gifts, viewing lists) are
  accurately attributed to my account.

### US-4: Reliable Identity for Collaboration and Surprise Invariant
- **As a** wishlist collaborator or gift giver,
- **I want** all user references across lists and reservations to point to persistent user records,
- **So that** role permissions (Owner, Co-author, Gifter) and the surprise invariant are reliably
  enforced across server restarts and sessions.

### US-5: Idempotent Repeat Authentication
- **As a** user opening multiple Mini App instances or reconnecting after token expiration,
- **I want** repeated logins with the same Telegram account to safely reuse my existing profile,
- **So that** no duplicate accounts are created and my lists and reservations remain intact.

---

## Definition of Done

The task is considered done when the following observable acceptance criteria are satisfied:

### AC-1: First-Time User Registration
- When a user successfully authenticates via Telegram with an unrecognized Telegram ID:
  - A new user profile record is created in durable storage.
  - The profile stores the user's Telegram ID, first name, last name (if provided),
    username (if provided), language code (if provided), and Telegram Premium status.
  - Profile creation and last-active timestamps are recorded.
  - A unique internal user identifier is generated for the new profile.

### AC-2: Existing User Synchronization (Upsert)
- When a previously registered user authenticates with an existing Telegram ID:
  - The existing user profile is located deterministically by Telegram ID.
  - Mutable profile fields (first name, last name, username, language code, Telegram Premium
    status) are updated with the latest values from the authentication payload.
  - The profile's last-active timestamp is updated.
  - The internal user identifier remains constant; no duplicate records are created.

### AC-3: Session Linkage to User Identity
- Upon successful authentication exchange:
  - The returned session token and security context are associated with the user's internal
    identity and Telegram ID.
  - Subsequent authenticated requests can resolve both the internal user identity and Telegram
    attributes from the verified session context.

### AC-4: Atomic Operation and Fault Resilience
- The validation of credentials, user profile persistence/upsert, and session creation are
  treated as a single atomic operation:
  - If user persistence fails, the authentication exchange fails cleanly with an appropriate
    error response and no orphaned session is established.
  - Unauthenticated guest access to public wishlists remains functional without creating user
    records.

### AC-5: Complete Automated Test Coverage
- Automated tests verify:
  - Registration of new users upon first valid login.
  - Proper upsert and attribute synchronization for returning users.
  - Preservation of existing internal identity across repeated logins.
  - Correct handling of optional profile fields (null/missing last name, username, language code).
  - Proper linking of user identity in session resolution.
  - Rejection of invalid authentication payloads without user creation.
  - All tests enforce strict bounded execution timeouts per project standards.

---

## Task Description

### Business Context and Scope
The Wishenka authentication flow exchanges Telegram WebApp `initData` for an authenticated session.
This task introduces persistent user profile management to this flow:
- Define the user domain entity representing a registered system user.
- Persist verified Telegram user data during authentication exchange.
- Provide idempotent upsert logic: insert new user or update existing user attributes.
- Bind issued session tokens and authentication dependencies to the persistent user identity.

### Scope Boundaries
**In Scope**:
- User domain entity and attributes (internal ID, Telegram ID, name fields, username, language,
  premium status, timestamps).
- Business logic for user creation and updating upon successful Telegram login.
- Integration with session issuance and authentication context resolution.
- Automated tests for user persistence, upsert semantics, and session linkage.

**Out of Scope**:
- UI screens for manual profile editing or account deletion (handled in future profile epics).
- Third-party social logins or email/password authentication (Wishenka is exclusive to TMA).
- Bot notification delivery mechanisms or push notifications.
- Database migration tooling or external database servers (SQLite WAL is used per architecture).

---

## Functional & Non-Functional Requirements

### Functional Requirements
- **FR-1 (Profile Persistence)**: The system must store verified user profile details including
  unique internal user ID, external Telegram ID, first name, last name, username, language code,
  premium flag, created timestamp, and updated timestamp.
- **FR-2 (Idempotent Upsert)**: When handling authentication requests, the system must search for
  an existing user by Telegram ID. If found, update attributes; if not found, create a new record.
- **FR-3 (Optional Attribute Handling)**: The system must gracefully handle missing or omitted
  optional attributes (such as `last_name`, `username`, or `language_code`) without failure.
- **FR-4 (Session Attribution)**: The authentication context resolved for incoming requests must
  provide the caller's internal user identity in addition to their Telegram ID.
- **FR-5 (Guest Isolation)**: Public and anonymous requests must not trigger user creation or
  storage modifications.

### Non-Functional Requirements
- **NFR-1 (Performance)**: User profile lookup and upsert during authentication must execute
  with low latency (< 20ms under typical loads) to preserve fast Mini App startup time.
- **NFR-2 (Consistency & Concurrency)**: User upsert operations must be transactionally safe
  and prevent race conditions or duplicate entries even under concurrent login requests.
- **NFR-3 (Security)**: User persistence must only occur after cryptographic verification of
  Telegram signatures succeeds. Unverified data must never be written to storage.
- **NFR-4 (Language & Standards)**: Implementation in Python (3.12+), adhering to project code
  formatting, strict typing, and test timeout constraints.

---

## Business Entities

- **UserProfile**:
  - Description: Registered user account in the Wishenka service.
  - Attributes: `id`, `telegram_id`, `first_name`, `last_name`, `username`,
    `language_code`, `is_premium`, `created_at`, `updated_at`.
- **TelegramIdentity**:
  - Description: Verified credentials extracted from Telegram `initData`.
  - Attributes: `telegram_id`, `first_name`, `last_name`, `username`,
    `language_code`, `is_premium`.
- **UserSession**:
  - Description: Active authenticated interaction context.
  - Attributes: `token`, `user_id`, `telegram_id`, `created_at`, `expires_at`.

---

## Q&A / Clarifications

### Q1: Why decouple the internal user identifier from the external Telegram ID?
**A1**: Telegram IDs are external 64-bit integers managed by a third-party platform. Generating
an internal user identity establishes a clear boundary between external provider data and internal
domain relations (wishlists, items, reservations), ensuring data model integrity and future
extensibility.

### Q2: What happens when a user updates their Telegram username or display name?
**A2**: Every successful login via the Telegram Mini App performs an upsert: it updates the user's
mutable attributes (`first_name`, `last_name`, `username`, `language_code`, `is_premium`, and
`updated_at`) while keeping their internal user identifier and `telegram_id` constant.

### Q3: How are users with no username or last name handled?
**A3**: Telegram users are not required to have a username or last name. The user profile schema
treats these fields as optional (nullable), storing `None` when omitted by Telegram.

### Q4: Are anonymous visitors persisted in the user database?
**A4**: No. Anonymous guests viewing public wishlists do not provide Telegram `initData` and are
not authenticated. The system does not create user records for unauthenticated guest sessions.

### Q5: Why are database table names, SQL DDL, and migration scripts omitted from this document?
**A5**: Step 1 strictly defines business requirements, domain entities, and observable acceptance
criteria. Technical architecture decisions (such as table names, column constraints, indexing
strategies, and storage layer classes) belong to Step 2 (Architecture Design).
