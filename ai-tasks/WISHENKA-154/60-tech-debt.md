# WISHENKA-154: Technical Debt Analysis

Scope of this analysis: the deliverables of `WISHENKA-154`, a documentation-only product-decision and specification task (`10-requirements.md`, `20-architecture.md`, `40-code-cleanup.md`, `50-observability.md`, and `in-docs/spec.md` sections 3, 4.4, 5.5, 6.3, 6.4, 7.2, 7.3, and 16). No production code, database schema, UI templates, or automated tests were modified.

Verdict: **no BLOCKER for closing `WISHENKA-154`.** All six product decisions (assumptions A–D, Q6, Q8, Q11, Q12, and purchased-promise completion) are settled and reflected in `in-docs/spec.md`. Two target product rules (`FR-5` and `FR-6`) require follow-up implementation tasks, and `doc/dev/` alignment is handled in Step 8.

## Shortcuts Taken

Because `WISHENKA-154` is strictly documentation-only (`Markdown (documentation-only; no code changes)`), no code shortcuts were taken. The following scope and specification trade-offs are recorded:

- **Deferred code/UI implementation of `FR-5` (Q12 — edit-form quantity-reduction lock tightening).** `in-docs/spec.md` section 5.5 now states the target rule: authors may reduce requested quantity down to `max(1, received_quantity)` without seeing or being blocked by units occupied by giver promises, transitioning into the standard over-booked state when `received + occupied > new_requested`. Implementing this behavior in the wish edit form, backend validation, and over-booked notifications is deferred to a dedicated follow-up task.
- **Deferred code/UI implementation of `FR-6` (Shortcut E — «Завершено» completed state for purchased promises).** `in-docs/spec.md` sections 6.4 and 7.3 now define the explicit «Завершить» / «Подарок вручён» action for purchased promises on fully received wishes (releasing occupied units, excluding «Завершено» from active «Мои бронирования» counters, and stopping further receipt/undo notices). Implementing this state transition, UI action, and notification suppression is deferred to a dedicated follow-up task.
- **Temporary spec-ahead-of-code window.** Until the follow-up tasks for `FR-5` and `FR-6` are implemented, `in-docs/spec.md` describes target behavior that is not yet active in the running application (the legacy edit-form quantity lock still applies, and purchased promises on fully received wishes do not yet have a «Завершено» state).
- **`doc/dev/` updates deferred to Step 8.** Developer documentation in `doc/dev/` is not updated in Step 7; Step 8 (`td-70-dev-docs`) will align `doc/dev/` and mark `FR-5` and `FR-6` as planned/target rules.

## Code Quality Issues

No production code or test files were modified (`ruff`, `mypy`, and `pytest` are N/A). Documentation-level observations:

- **No implementation-status markers in `in-docs/spec.md`.** Per `10-requirements.md` non-functional requirements, `in-docs/spec.md` intentionally omits Jira task keys (`WISHENKA-*`) and implementation status notes. Readers of `in-docs/spec.md` alone cannot see that `FR-5` and `FR-6` are not yet implemented in code; this is mitigated by `doc/dev/` markers (Step 8) and the follow-up tasks below.
- **Cross-artifact traceability.** Because `in-docs/spec.md` omits `FR-*` identifiers, tracing spec paragraphs back to `FR-1`–`FR-6` in `10-requirements.md` relies on the section-by-section mapping in `ai-tasks/WISHENKA-154/20-architecture.md`.
- **Remaining open questions in `in-docs/spec.md` section 16.** Six unrelated technical/product questions remain open in section 16 (recipient without Telegram, support workflow without admin panel, system Share menu integration, store parser coverage, Telegram notification delivery limits, and detailed UI screens/messages); these are out of scope for `WISHENKA-154`.

## Missing Tests

- **N/A for `WISHENKA-154`:** Step 3 was `N/A — documentation-only change, no code or behavioral change`. No runtime code or test files were touched.
- **Required test coverage for deferred follow-ups (to be written in those tasks with explicit pytest timeout markers per `do-testing`):**
  - **`FR-5` (Q12):** Reducing requested quantity down to `max(1, received_quantity)` while units are occupied by promises; rejecting reduction below `received_quantity`; entering the over-booked state (`received + occupied > requested`); notifying open-promise givers; verifying no booking count or existence is leaked to authors/recipients.
  - **`FR-6` (Shortcut E):** Completing a purchased promise on a fully received wish («Завершить» / «Подарок вручён»); freeing occupied units; excluding «Завершено» from active «Мои бронирования» counters; suppressing future receipt/undo notifications for completed promises; rejecting direct completion on intended (unpurchased) promises.

## Performance Concerns

None. `WISHENKA-154` introduces no runtime code, database queries, API endpoints, or background jobs.

## Follow-up Tasks

All follow-up items below are `NON-BLOCKER` for `WISHENKA-154` (Jira issue creation is handled by the orchestrator after blocker review):

1. **`NON-BLOCKER` — Implement `FR-5` (Q12): Tighten edit-form quantity-reduction lock.** Jira: [WISHENKA-218](https://pypost.atlassian.net/browse/WISHENKA-218)
   - Remove the surprise-leaking floor based on occupied promise units in wish editing; allow reducing requested quantity down to `max(1, received_quantity)`; transition the wish to the over-booked state when `received + occupied > new_requested` and notify open-promise givers without leaking booking data to authors/recipients.
2. **`NON-BLOCKER` — Implement `FR-6` (Shortcut E): Add «Завершено» («Подарок вручён») state for purchased promises on fully received wishes.** Jira: [WISHENKA-219](https://pypost.atlassian.net/browse/WISHENKA-219)
   - Add the explicit completion action for purchased promises on fully received wishes; move the promise to closed «Завершено» state, release occupied units, exclude it from active «Мои бронирования» counters, stop future receipt/undo notices, and disallow direct completion of intended (unpurchased) promises.
3. **Step 8 of `WISHENKA-154` (`td-70-dev-docs`, not a separate Jira ticket): Align `doc/dev/`.**
   - Update relevant `doc/dev/` documents with the settled product decisions (`FR-1`–`FR-4`) and mark `FR-5` and `FR-6` as planned/target rules until their follow-up implementation tasks land.
