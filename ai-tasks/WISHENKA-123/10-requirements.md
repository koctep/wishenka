# WISHENKA-123: Reliable and safe giver actions

## Goals

Allow a giver to use wish-card controls reliably when session security is still being prepared.
Avoid presenting a security preparation failure as a refusal by the wish recipient, while keeping
booking operations protected and preserving existing authorization rules.

## User Stories

- As a giver using a cookie session, I want an early click to be handled only when session security
  is ready, so a temporary initialization delay does not cause a misleading booking refusal.
- As a giver, I want a preparation failure to leave the booking unchanged and be distinguishable
  from a recipient's genuine refusal.
- As a recipient, I want prohibited booking actions to retain their current refusal behavior.
- As an authorized bearer-token client, I want booking operations to continue working without a
  cookie-session security header.

## Definition of Done

- When a giver action is initiated before cookie-session security is ready, the mutation waits
  until the security token is available; it is never sent without the required token.
- If token preparation fails, no unprotected cookie-session mutation is sent and the booking is
  unchanged. The failure is not displayed as a recipient's booking refusal.
- A security-token rejection is not presented as a recipient's booking refusal.
- A genuine recipient authorization rejection retains the existing refused notice and card
  refresh behavior.
- Security token values are not embedded in the HTML delivered to the client.
- Authorized bearer-token requests remain valid without the cookie-session security header.
- Delayed initialization, initialization failure, security-token rejection, genuine recipient
  rejection, and bearer authorization are covered by automated checks.

## Task Description

Cookie-session security preparation can finish after the giver interacts with a wish card. A
premature action currently fails security validation and is incorrectly described as a refused
booking. The scope is giver-card mutation behavior and its error classification; existing booking
rules, recipient permissions, and security requirements remain in force.

The business entities are the giver, recipient, wish card, and booking. The selected implementation
languages are JavaScript for browser behavior, HTML templates where necessary, and Python for
existing automated test infrastructure.

## Q&A

- **Why is this needed?** A legitimate early interaction should not fail or falsely imply that the
  recipient refused a booking while session security is still being prepared.
- **What happens when preparation fails?** The booking remains unchanged and no unprotected
  cookie-session request is sent; recovery or error presentation must not imply recipient refusal.
- **What is unchanged?** Recipient authorization, bearer authentication, and token confidentiality
  remain intact. See `ai-tasks/WISHENKA-19/60-tech-debt.md` for the original finding.
