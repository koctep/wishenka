# WISHENKA-128: Define and Verify Data Migration Rollback Policy and Lifecycle Edge Cases

## Goals

Protect stored user and operational data from accidental destruction during rollbacks, establish a clear and consistent policy for which data-structure changes can be reversed versus which are one-way, and verify key operational lifecycle scenarios (repeated startup, unsupported storage targets, and offline change-script generation).

The business value is operational safety and predictability: operators and developers know exactly when a rollback is safe, are prevented from accidentally wiping all wishlist data, receive clear guidance when a change is irreversible, and have automated verification that startup and offline inspection behave reliably.

## User Stories

- **As a product operator**, I want a clear policy stating which data-structure changes are reversible and which are one-way, so that I do not attempt an unsafe rollback during an incident and know when to restore from a backup instead.
- **As a product operator**, I want a rollback to the empty pre-baseline state to be guarded against accidental execution, so that all stored wishlist data cannot be wiped unintentionally.
- **As a product operator or developer**, I want irreversible changes to refuse rollback with a clear, human-readable explanation, so that I immediately understand why the rollback stopped and what alternative action to take.
- **As a product operator**, I want repeated application startups on an already up-to-date data store to be safe and idempotent, so that restarts and rolling deployments do not re-apply changes or emit misleading state-change events.
- **As a product operator**, I want unsupported storage targets to be rejected cleanly with an explicit error, so that misconfigured deployments fail fast before corrupting or misinterpreting data.
- **As a product operator**, I want offline change-script generation to work reliably without a live data store connection, so that I can audit or review pending changes prior to deployment.
- **As a developer**, I want automated tests covering the rollback policy and operational lifecycle edge cases, so that future changes cannot silently break rollback safety or startup guarantees.

## Definition of Done

- Every existing data-structure revision has an explicit, documented rollback classification (reversible or one-way) consistent with data-preservation requirements.
- Rolling back the baseline initialization revision is safeguarded so it refuses or explicitly warns against destroying all stored data by default.
- All one-way revisions that refuse rollback fail with clear, descriptive, actionable messages explaining why rollback is not supported.
- Reversible revisions roll back cleanly as defined by the policy.
- Automated verification covers:
  - Rollback policy behavior across reversible, one-way, and baseline revisions.
  - Idempotent repeated startup on an already up-to-date data store (no-op upgrade, no duplicate legacy-adoption event).
  - Clean rejection of unsupported (non-supported backend) storage addresses.
  - Offline change-script generation without a live store connection.
- All relevant documentation reflects the finalized rollback policy.

## Task Description

Following the introduction of versioned data-structure migrations, the rollback (downgrade) policy across existing revisions remained incomplete and untested:
- Most revisions lacked an explicit policy declaration distinguishing reversible changes from one-way changes.
- The baseline revision's rollback path could drop all core wishlist data without any guard or warning.
- Several one-way revisions refused rollback without clear, consistent user-facing explanations.
- Several operational edge cases—idempotent second startup, rejection of unsupported storage addresses, and offline change-script generation—lacked automated verification.

This task establishes the business rules for migration rollbacks, adds the necessary safeguards and clear refusal messages, and ensures automated test coverage for both the rollback policy and the untested operational lifecycle paths.

**Implementation language:** Python.

### Functional Requirements

1. **Rollback Policy Classification**
   - Every data-structure revision in the history must be explicitly classified as either **reversible** or **one-way (irreversible)**.
   - Revisions that remove or alter historical structures in a way that cannot be reversed without data loss or structural impossibility under the supported storage engine must be classified as one-way.
   - Reversible revisions must state any data-loss side effects (e.g., discarding transient queue or state data) if applicable.

2. **Baseline Rollback Safeguard**
   - Rolling back the initial baseline revision (which would destroy all core wishlist data) must not execute silently.
   - By default, it must either refuse to run with a clear explanation or require an explicit opt-in safeguard/warning before destructive removal can proceed.

3. **Clear Refusal Messages for One-Way Revisions**
   - Every one-way revision that refuses rollback must emit a clear, human-readable message explaining why the change cannot be reversed and directing operators to use backup restoration when reverting to an earlier state.

4. **Lifecycle Edge-Case Behavior & Verification**
   - **Idempotent Repeated Startup**: Starting against an already migrated data store must perform no schema changes, preserve all data, and not emit legacy-adoption events a second time.
   - **Unsupported Storage Target Rejection**: Providing a storage address for an unsupported backend must fail cleanly with a clear error before attempting migration operations.
   - **Offline Mode**: Generating migration output in offline mode (without connecting to a live database) must complete without error and emit the expected change statements.

### Non-Functional Requirements

- **Data Safety**: Accidental execution of a rollback command must never silently destroy core user data.
- **Clarity & Actionability**: Refusal and validation errors must clearly communicate the reason and recommended operational action (e.g., backup restoration).
- **Determinism & Repeatability**: Repeated startups and offline script generation must behave deterministically.
- **Test Reliability**: Automated tests must be self-contained, bounded in execution time, and compliant with project testing standards.

### Constraints and Assumptions

- The implementation language is Python.
- Scope is limited to the wishlist data-migration rollback policy, refusal/guard behavior, documentation of the policy, and automated tests for rollback policy and the specified lifecycle edge cases.
- User-facing wishlist, bot, and notification features are out of scope.
- Production rollbacks across one-way revisions are handled operationally by restoring from a backup rather than automated downgrade.

### Main Entities and Interactions

- **Product Operator**: Deploys updates, inspects offline change scripts, and relies on clear rollback rules and safeguards during incident response.
- **Developer**: Authors and maintains data-structure revisions in accordance with the documented rollback policy.
- **Data-Structure Revision**: A versioned step in the product's data evolution, classified as reversible or one-way.
- **Wishlist Data Store**: Persistent storage for user wishlists and related operational state, protected against accidental data loss and inconsistent startup states.

## Q&A

- **Why is this task needed?** Without an explicit rollback policy and safeguards, an operator or developer attempting a rollback can either hit unexplained failures mid-chain or accidentally destroy all stored wishlist data. Additionally, key operational paths (repeated startup, unsupported storage addresses, offline mode) need automated verification to prevent regressions.
- **Are user-facing features affected?** No. This task only governs migration rollback rules, safety guards, operator-facing error messages, and lifecycle test coverage.
- **How are irreversible rollbacks handled in production?** By restoring a database backup taken prior to the upgrade, rather than running automated downgrade steps.
