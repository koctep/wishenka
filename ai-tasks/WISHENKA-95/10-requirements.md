# WISHENKA-95: Verify complex IPv6 and redirect safety

## Goals

People adding wishes need reliable link previews without allowing a supplied link to reach
restricted network destinations. Existing security coverage leaves uncertainty about uncommon
IPv6 forms and longer redirect paths. This task strengthens confidence that preview safety
continues to hold for those cases and that a redirect loop terminates.

## User Stories

- As a person adding a wish, I want a safe link to produce a preview even when its destination
  uses a supported IPv6 representation or a safe sequence of redirects.
- As an operator, I want restricted destinations rejected at every redirect hop so that a public
  starting link cannot be used to access protected network resources.
- As an operator, I want redirect loops to terminate within the existing limit so that a preview
  request cannot run indefinitely.
- As a maintainer, I want repeatable coverage of these cases so a regression is detected before
  release.

## Definition of Done

- Automated checks cover 6to4 and Teredo IPv6 prefixes, scoped IPv6 addresses, and alternative
  zero-compressed IPv6 representations. The checks distinguish allowed and restricted cases
  according to the existing destination policy, including equivalent address representations.
- Automated checks cover a multi-hop redirect chain with safe intermediate destinations and a
  restricted later destination. The restricted destination is rejected before it is contacted.
- Automated checks cover a safe multi-hop redirect chain and establish that it can complete within
  the existing redirect limit.
- Automated checks cover a circular redirect and verify bounded termination at the existing limit.
- Checks are repeatable without relying on external network availability and report failures clearly.
- Existing preview behavior and security policy remain intact; any discovered defect is addressed
  or explicitly reported through the workflow before this task is closed.

## Task Description

The scope is expanded regression coverage for link-preview destination safety, focusing on IPv6
address representations and redirect chains identified in WISHENKA-54. The work uses Python,
matching the existing application and test suite. It does not introduce a new product feature,
change the destination policy, or alter the redirect limit merely to satisfy the checks.

Relevant domain concepts are a submitted link, its resolved destination, a preview request, the
sequence of redirect destinations, and the configured destination safety policy. A preview may
follow a safe destination, but a restricted destination must not be contacted regardless of its
position in the sequence. Equivalent representations are assessed by the same policy.

## Non-functional Requirements

- **Security:** Preserve the existing restrictions on destination addresses throughout a request.
- **Reliability:** Redirect loops terminate in bounded time and do not yield a misleading success.
- **Repeatability:** Verification is deterministic and does not depend on public network services.

## Constraints and Assumptions

- Existing policy and redirect limits are authoritative; this task does not redefine which address
  classes are allowed or what the numerical limit should be.
- The task covers safety and termination, not real-network integration or performance measurement.
- Tests use the repository's established Python testing conventions.

## Q&A

- **Why expand these cases?** The existing coverage identified in
  `ai-tasks/WISHENKA-54/60-tech-debt.md` does not establish behavior for these address forms or
  deeper redirect paths; regressions could undermine safe previews.
- **What happens to newly exposed defects?** The workflow assesses and resolves defects needed for
  the acceptance criteria, or records a concrete blocker rather than treating a failing check as
  successful coverage.
