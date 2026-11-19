# WISHENKA-180: Supported Transactional Interface for NoticeStore

## Goals

Keep notification and reminder delivery reliable and maintainable as the storage layer evolves. By eliminating hidden coupling between the notification worker, reminder processing, and private internal storage state, future storage changes can be validated and shipped safely without risking silent regressions, broken transaction guarantees, or loss of delivery atomicity.

## User Stories

- As a maintainer, I want reminder scheduling and reminder delivery coordination to interact with the notice store exclusively through a supported public boundary, so that internal storage details can evolve without breaking notification delivery.
- As a product operator, I want reminder scheduling and delivery to preserve the exact same atomic state transitions and retry/eligibility guarantees, so that users never receive duplicate, partial, or prematurely settled reminders.

## Definition of Done

1. Reminder scheduling and reminder delivery coordination no longer reach into private internal storage attributes of the notice store.
2. All transactional operations for reminder scheduling and reminder delivery (claiming, refreshing, and settling reminders) are performed through a supported, public notice store interface.
3. Transactional atomicity (all-or-nothing persistence per operation, with exclusive write serialization where required) is preserved without behavioral regressions.
4. Existing notification, reminder scheduling, and reminder delivery behavior remains unchanged for end users.
5. Existing automated test coverage continues to pass, and the supported boundary is verifiable without relying on private store internals.

## Task Description

### Problem Statement

Currently, the notification delivery worker and reminder processing reach past the notice store's public boundary to access its private underlying storage attribute in order to coordinate reminder scheduling and transactional reminder lifecycle operations. This creates tight, unsupported coupling to internal storage details (identified as Follow-up 3 in `WISHENKA-29`).

### Programming Language

- **Python**

### Functional Requirements

1. **Public Boundary for Reminder Lifecycle**: The notice store must provide a supported public interface for reminder scheduling coordination and reminder delivery lifecycle operations (claiming due reminders, re-validating eligibility/content before send, and settling delivery outcomes).
2. **Removal of Private Store Coupling**: Notification worker and reminder processing flows must use only the supported public interface rather than accessing private internal store attributes.
3. **Behavioral Equivalence**: Reminder scheduling, eligibility checks, rate-limiting, backoff/retry timing, and outcome settlement must behave identically to the current system.

### Non-Functional Requirements

1. **Transaction Atomicity**: Every reminder lifecycle operation must retain its atomic transactional guarantees (including immediate write-lock semantics for SQLite persistence) so concurrent workers cannot claim or settle the same reminder inconsistently.
2. **Maintainability and Encapsulation**: Callers of the notice store must not depend on how the notice store internally holds or manages its underlying persistence handle.
3. **Testability and Regression Safety**: All existing tests for receipt notices, service reminders, scheduling, and observability must remain green.

### Scope and Constraints

- **In scope**: The boundary between the notice store, notification worker, and reminder scheduling/delivery modules, plus associated tests.
- **Out of scope**: Changing reminder business rules, notification templates, rate-limit policies, retention/purge policies, or database schemas.

### Domain Entities (High-Level)

- **Notice Store**: The domain boundary responsible for durable persistence and atomic state transitions of queued notifications and reminders.
- **Notice Worker**: The coordinator that drains due gift notices and reminders and delegates delivery.
- **Reminder Scheduler**: The component that scans upcoming occasions and enqueues due reminder work.
- **Reminder Lifecycle**: The atomic stages of a reminder's delivery—claiming due work, refreshing eligibility and rendered content, and settling the send outcome.

## Q&A

- **Why is this technical debt being addressed?**
  - Relying on private internal attributes bypasses the notice store's encapsulation boundary, making storage refactoring error-prone and harder to validate. Exposing a supported interface preserves clean module boundaries and protects transactional integrity. (Source: `ai-tasks/WISHENKA-29/60-tech-debt.md`, Follow-up 3).
