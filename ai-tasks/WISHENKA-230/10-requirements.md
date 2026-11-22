# WISHENKA-230: Verify safe connection failure handling

## Goals

People adding wishes need reliable link previews without allowing a submitted link to reach
unvalidated network destinations. Existing coverage leaves uncertainty about how connections
behave when no safe address is available, all safe addresses fail, or an address is repeated.
This task improves confidence that these cases remain safe, understandable, and bounded.

## User Stories

- As a person adding a wish, I want an unavailable destination handled as a connection failure
  so that a failed preview does not appear to have succeeded.
- As an operator, I want a request with no validated destination to fail safely and produce a
  useful diagnostic so that unvalidated destinations are never contacted.
- As a maintainer, I want repeatable checks for exhausted and duplicate destinations so that
  regressions in failure handling are detected before release.

## Definition of Done

- Automated coverage establishes that a name-resolution failure producing no validated addresses
  results in a connection error and the existing no-validated-address diagnostic. No connection is
  attempted to the original unvalidated hostname.
- Automated coverage establishes that failure of every validated address produces a connection
  error and the existing all-addresses-failed diagnostic. An underlying operating-system
  connection failure is represented as a connection error.
- Automated coverage establishes that repeated occurrences of a validated address do not cause
  repeated connection attempts to that address, while distinct addresses remain eligible.
- The checks are deterministic, run without external network access, and report failures clearly.
- Existing destination security policy and connection behavior remain intact. A newly discovered
  defect is handled through the workflow before closing the task.

## Task Description

The scope is regression coverage for the connection failure cases identified in
`ai-tasks/WISHENKA-92/60-tech-debt.md`. The implementation language is Python, matching the
application and its existing automated checks. This work does not redefine the destination policy
or introduce a new preview feature.

Relevant domain concepts are a submitted link, its hostname, validated destination addresses, a
connection attempt, a connection failure, and the diagnostic available to an operator. A
connection can be attempted only to validated destinations; when no attempt can succeed, failure
must be visible rather than a misleading success.

## Non-functional Requirements

- **Security:** Preserve the boundary between validated destinations and unvalidated hostnames.
- **Reliability:** Exhausting available destinations ends in a clear connection failure.
- **Repeatability:** Verification does not depend on live DNS or external network services.
- **Efficiency:** Duplicate destinations do not cause redundant connection attempts.

## Constraints and Assumptions

- Existing security policy, error semantics, and diagnostic events are authoritative.
- The task adds focused regression coverage; it does not require live-network integration or a
  new connection strategy.
- Tests follow the repository's Python testing conventions and use bounded execution.

## Q&A

- **Why cover these cases?** The prior technical-debt review identified gaps in coverage of
  safe-connection failure paths. A regression could contact an unvalidated hostname, obscure a
  failure, or repeat work unnecessarily.
- **What happens if a check exposes a defect?** The workflow assesses it and supplies a reviewed
  failing reproduction before changing production behavior, or records a concrete blocker.
