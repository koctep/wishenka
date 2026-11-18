# WISHENKA-154: Product Decisions on Open Privacy and Gift Receipt Visibility Questions — Architecture

## Research

Inspected the current repository documentation and task requirements:

- [`ai-tasks/WISHENKA-154/10-requirements.md`](../../ai-tasks/WISHENKA-154/10-requirements.md): Defines six settled product decisions (`FR-1` through `FR-6`) covering assumptions A–D (item i), no public «already gifted» label for gifters (item ii / Q6), gifted history deletion on list deletion (item iii / Q8), co-author/recipient rights and surprise boundaries (item iv / Q11), target rule for tightening the edit-form quantity-reduction lock (item v / Q12), and target rule for a «completed» state on purchased promises after full receipt (item vi / shortcut E).
- [`in-docs/spec.md`](../../in-docs/spec.md):
  - **Section 3 (`Пользователи и роли`, lines 45–60)** and **Section 4.4 (`Совместная работа`, lines 92–101)**: Define roles (`Владелец`, `Администратор`, `Участник`, `Даритель`, `Получатель`) and collaborative list rules, but do not yet state the role-separation rule when a co-author is also a wish recipient.
  - **Section 5.5 (`Редактирование и удаление`, lines 179–190)**: Describes wish editing and archiving, but does not yet document the target rule for requested-quantity reduction (`max(1, received_quantity)` floor without revealing occupied units).
  - **Section 6.3 (`Видимость бронирования`, lines 217–231)** and **Section 6.4 (`Мои бронирования`, lines 232–241)**: Cover recipient-hidden booking fields, available remainder display for gifters, and active booking counts in «Мои бронирования».
  - **Section 7.2 (`Получение`, lines 250–270)**: Already captures most receipt rules, including author-only «Подаренные» visibility (line 266) and deletion/archiving behavior (line 269), though line 266 still says «только для чтения» without noting active-list receipt cancellation/correction (`WISHENKA-153`), and does not explicitly state that gifters see no public «уже подарено» badge or received count.
  - **Section 7.3 (`Влияние на бронирования`, lines 271–284)**: States on line 275 that givers «самостоятельно завершают или отменяют свои брони», while line 282 states «Купленная бронь при получении не завершается», without defining the explicit «Завершено» («Подарок вручён») action for purchased promises.
  - **Section 11.2 (`Каскадные правила по вишлистам и бронированиям`, lines 375–388)**: Already specifies permanent deletion of «Подаренные» when personal lists or solo collaborative lists are deleted.
  - **Section 16 (`Открытые вопросы и решения при реализации`, lines 455–472)**: Line 460 still lists «Как разграничивать права совместного редактора, который одновременно является получателем подарка.» as an open question.
- [`specs/00-high.md`](../../specs/00-high.md): Confirms the core surprise and privacy invariants and role definitions.

## Implementation Plan

This is a **documentation-only** task (`Markdown (documentation-only; no code changes)`). No Python, HTML, JS, CSS, database schema, or test code is modified.

1. Update [`in-docs/spec.md`](../../in-docs/spec.md) section by section according to the Architecture plan below so that all six product decisions (`FR-1`–`FR-6`) are unambiguously reflected in the functional specification.
2. Keep `in-docs/spec.md` free of internal Jira task keys (`WISHENKA-*`) and low-level implementation details, while clearly distinguishing target rules whose code/UI implementation is planned separately (decisions (v) and (vi)).
3. Verify Markdown formatting against `lsr-markdown` and cross-check every section against `FR-1`–`FR-6` and Definition of Done in `10-requirements.md`.

**Mandatory — Failing Repro (next Step 3):** `N/A — documentation-only change, no code or behavioral change`. This task modifies only `in-docs/spec.md` (and workflow documentation artifacts). No runtime code, API endpoints, templates, or automated tests are changed; Step 4 verification is a manual specification consistency and formatting review.

## Architecture

### Document Structure and Dependencies

[`in-docs/spec.md`](../../in-docs/spec.md) serves as the single functional specification of product behavior. Its sections have clear cross-section dependencies that must stay consistent:

```text
Section 3 & 4.4 (Roles & Collaboration)
  └─> defines co-author / recipient separation (FR-4)
        ├─> Section 6.3 (Booking Visibility): recipient-safe views & no public "already gifted" badge (FR-2, FR-4)
        └─> Section 7.2 (Receipt): author receipt rights & author-only "Подаренные" (FR-1, FR-2, FR-3, FR-4)
              ├─> Section 5.5 (Wish Editing): quantity reduction floor = max(1, received) -> over-booked state (FR-5)
              ├─> Section 7.3 (Impact on Bookings): over-booked state & purchased promise completion (FR-1, FR-6)
              │     └─> Section 6.4 (My Bookings): completed promises excluded from active count (FR-6)
              └─> Section 11.2 (Cascade Deletion): "Подаренные" deleted with wishlist (FR-3)
Section 16 (Open & Closed Questions)
  └─> moves co-author/recipient question from open to closed (FR-4.4)
```

### Architectural Patterns and Principles

- **Single Source of Product Truth:** All six settled decisions live in their corresponding functional sections of `in-docs/spec.md` rather than in ad-hoc notes.
- **Invariant-First Specification:** Every rule upholds the surprise invariant (no booking/giver/purchase data leaked to any recipient, including co-author recipients) and the booking-privacy rule (no received counts or «already gifted» badges shown to gifters on active wishes).
- **Target-Rule Clarity without Implementation Coupling:** Decisions (v) and (vi) (`FR-5`, `FR-6`) are written as clear product rules in `in-docs/spec.md` without Jira keys, database columns, or endpoint names.
- **No Unnecessary Churn:** Sections that already match settled decisions (such as Section 11.2) are verified and left untouched unless a clarification is needed.

### Section-by-Section Update Plan for `in-docs/spec.md`

| Section | Lines | Requirement(s) | Planned Update |
| --- | --- | --- | --- |
| **3. Пользователи и роли** | 45–60 | `FR-4.1`, `FR-4.2`, `FR-4.3` | Clarify that an author (owner, administrator, or member) who is also the recipient of a wish keeps full author rights on that wish under full surprise protection, and cannot act as a gifter on that wish (while acting as a normal gifter on other wishes in the same list). |
| **4.4. Совместная работа** | 92–101 | `FR-1.2`, `FR-4.1`–`FR-4.3` | Add explicit collaborative rule: a co-author who is a wish recipient may edit, archive/restore, and record/correct receipt for that wish without seeing bookings or giver data, and cannot book a wish where they are the recipient. |
| **5.5. Редактирование и удаление** | 179–190 | `FR-5.1`–`FR-5.4` | Document the target product rule for editing requested quantity: an author may reduce requested quantity down to `max(1, received_quantity)` without seeing or being blocked by occupied units; if `received + occupied > new_requested`, the wish enters the over-booked state and open-promise givers are notified to adjust or cancel their promises. |
| **6.3. Видимость бронирования** | 217–231 | `FR-2.1`, `FR-2.2`, `FR-4.2` | Clarify that recipient-safe hiding applies equally when the recipient is a list co-author, and that gifters/anonymous viewers never see «Подаренные», received quantities, or a public «уже подарено» badge on active wish cards (they see only the available remainder or «Забронировано»). |
| **6.4. Мои бронирования** | 232–241 | `FR-6.3` | Clarify that the active bookings counter includes open promises (intended and purchased) and excludes cancelled and completed (`Завершено`) promises. |
| **7.2. Получение** | 250–270 | `FR-1.2`–`FR-1.4`, `FR-2.1`–`FR-2.3`, `FR-3.1`–`FR-3.2` | Update line 266 to reflect active-list receipt cancellation/correction (while archived lists remain read-only) and confirm «Подаренные» is strictly author-only; explicitly state that gifters see no public «уже подарено» badge on active cards and see the receipt marker only in «Мои бронирования» when holding an open promise on a fully received wish; confirm deleted lists permanently delete «Подаренные» while archived lists keep it read-only. |
| **7.3. Влияние на бронирования** | 271–284 | `FR-1.1`, `FR-6.1`–`FR-6.5` | Keep the rule that receipt never auto-closes or modifies promises and that over-booked state is valid; define the target «Завершено» («Подарок вручён») completion action for a **purchased** promise on a fully received wish (freeing occupied units, removing it from active cabinet counts, and stopping further receipt/undo notices), while intended (unpurchased) promises on a fully received wish can only be cancelled, reduced, or marked purchased first. |
| **11.2. Каскадные правила по вишлистам и бронированиям** | 375–388 | `FR-3.1` | Verify consistency only (lines 377 and 384 already state permanent deletion of «Подаренные» / receipt history on list deletion); no edit expected unless wording alignment is needed. |
| **16. Открытые вопросы и решения при реализации** | 455–472 | `FR-4.4` | Remove «Как разграничивать права совместного редактора, который одновременно является получателем подарка.» from the open questions list and add a corresponding closed-question entry under `### Закрытые вопросы (перенесены в согласованные требования)` referencing sections 3, 4.4, 6.3, and 7.2. |

## Q&A

- **Q1. Should `in-docs/spec.md` mention `WISHENKA-154`, `WISHENKA-153`, or that code for FR-5/FR-6 is not yet implemented?**
  A. No. Per `10-requirements.md` Non-functional Requirements, `in-docs/spec.md` must stay free of internal Jira task keys and implementation details. It should state the settled product rules cleanly; follow-up implementation tasks for `FR-5` and `FR-6` are tracked in Step 7 (`60-tech-debt.md`) and Jira.

- **Q2. Does Step 3 (Failing Repro) require any test file?**
  A. No. `WISHENKA-154` is strictly documentation-only (`Markdown`), so Step 3 is `N/A — documentation-only change, no code or behavioral change`.

- **Q3. Are any changes needed in `doc/dev/` during Step 2 or Step 4?**
  A. No. `in-docs/spec.md` is the target functional specification for this task. Any developer-documentation alignment in `doc/dev/` is evaluated in Step 8 (`td-70-dev-docs`).
