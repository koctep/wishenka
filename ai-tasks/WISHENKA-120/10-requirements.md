# WISHENKA-120: Verify busy wish responses

## Goals

Protect the reliability and privacy of wish editing when a wish is temporarily busy. Automated
coverage should detect regressions in the existing retryable response before they reach users.

## User Stories

- As a person editing a wish, I want to know when a temporary conflict prevented my changes,
  so I can retry without re-entering the information I submitted.
- As a gift giver, I want my identity kept private when another person's edit cannot be saved.
- As an API consumer, I want a clear temporary-unavailability response when a wish is busy,
  so I can distinguish a retryable conflict from a successful change.

## Definition of Done

- The existing item operation's busy response is covered: it returns HTTP 503 and the established
  busy detail, without exposing a giver identifier.
- The existing wish-edit submission's busy response is covered: it returns HTTP 503, retains the
  edit modal and submitted fields, and displays the established busy sentence.
- The automated checks have an explicit bounded timeout.
- The checks exercise the existing behavior; changing production behavior is outside this task.

## Task Description

WISHENKA-57 added handling for inventory contention, but its HTTP responses were not covered by
route tests. This task closes that coverage gap for item operations and edit submissions.
The domain entities are the wish, the person submitting its changes, and the gift giver whose
identity must remain private. Python is the implementation language for the automated checks.

## Q&A

- **Why test these paths?** A transient conflict should not appear successful, lose submitted
  work, or reveal a giver's identity; the existing handling needs regression protection.
- **Is behavior being redesigned?** No. This is a coverage-only follow-up; the existing response
  and user-facing sentence are the contract.
- **Source:** `ai-tasks/WISHENKA-57/60-tech-debt.md`, HTTP 503 route coverage follow-up.
