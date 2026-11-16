# Telegram bot scenario design

## Overview

[Bot journeys and notifications](../../in-docs/bot-scenarios.md) is the functional specification
for the planned bot menu, shared-list entry, wish submission, and notification policy. It records
user-visible outcomes and acceptance examples for WISHENKA-27, WISHENKA-28, and WISHENKA-29.
WISHENKA-26 supplies this design only; it does not implement those flows or add a runtime API.

## Architecture

The planned bot adapter receives entry parameters or user input and delegates authorization and
changes to domain services. The Mini App independently checks access to shared-list targets. A
wish draft requires explicit confirmation and a fresh authorization check before saving.
Notification policy evaluates each person's roles and preferences before choosing content, links,
or previews. The wish recipient must not learn about protected reservation or purchase activity,
including through the existence or timing of a message.

The existing gift receipt notice path already uses a transactional outbox and worker. Its actual
interfaces, delivery behavior and limitations are documented in [Gift receipt](gift-receipt.md).
The scenario design does not imply that other notification events use that path today. See the
[task architecture](../../ai-tasks/WISHENKA-26/20-architecture.md) for conceptual boundaries.

## Usage

Use the functional specification when implementing or reviewing the subsequent tasks. Its
acceptance examples cover invalid links, target selection, failed saves, overlapping roles and
notification preferences. Token encoding, draft lifetime, retry behavior and reminder timing are
explicitly deferred there. Each implementation task should introduce its own behavioral tests.
No new callable functions, endpoints, or setup commands are introduced by this design task.

## Configuration

This task adds no configuration. The existing receipt notice worker's token, enablement and retry
settings are described in [Gift receipt configuration](gift-receipt.md#configuration). Do not
assume those settings configure the planned menu, draft, or other event types.

## Troubleshooting

- For an unavailable receipt notice worker, check the disabled reason and token configuration in
  [Gift receipt troubleshooting](gift-receipt.md#troubleshooting).
- If a proposed notification could reveal protected activity through its content, destination,
  preview, occurrence, or timing, suppress it and review the policy in the functional specification.
- For missing bot menu or draft behavior, consult the subsequent implementation tasks; this design
  does not establish that those flows have been deployed.
