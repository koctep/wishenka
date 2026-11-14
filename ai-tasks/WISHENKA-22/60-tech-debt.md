# WISHENKA-22: Technical Debt Analysis

Scope of this analysis: the deliverables of WISHENKA-22, a documentation-only
specification story. They are `10-requirements.md`, `20-architecture.md`,
`40-code-cleanup.md`, `50-observability.md`, and the text changes in
`in-docs/spec.md` (sections 7.2, 7.3, 16). No production code and no tests
were changed (`wishenka/`, `tests/`, `doc/dev` untouched; verified with
`git status --porcelain`: only `in-docs/spec.md` modified and
`ai-tasks/WISHENKA-22/` untracked in scope).

Verdict: **no BLOCKER for closing WISHENKA-22.** Every acceptance point of
the story is met. What remains is deferred work that WISHENKA-23 and
WISHENKA-24 already own, work owned by existing Debt tickets, and a small
number of product-owner decisions that no ticket carries.

## Shortcuts Taken

A specification story has no code shortcuts. The trade-offs below were taken
in the documents and are recorded here so that nobody reads them as settled
facts.

### Open product-owner assumptions (requirements A to D, Q11)

- **A.** Promise and receipt are independent facts, and receipt never closes
  a promise. This is the central decision and it matches `in-docs/spec.md`
  section 7.3 («самостоятельно завершают или отменяют свои брони»). It was
  never confirmed with the product owner in a separate step. The
  over-booked state (received plus occupied above requested, FR-3.3) is a
  direct consequence and is the most visible product effect.
- **B.** Any author with the right to edit wishes may record receipt. On a
  collaborative list that includes a co-author who is also the recipient of
  the wish (requirements Q11). The open question in `in-docs/spec.md`
  section 16 («права совместного редактора, который одновременно является
  получателем») was deliberately **not** closed. Receipt shows
  recipient-safe data only, so it opens no leak, but the rule stays
  unconfirmed.
- **C.** A receipt is final: no undo and no correction (requirements Q9).
  A mistaken tap cannot be reversed in this product version.
- **D.** «Подаренные» is for authors, not for gifters (requirements Q6, FR-5.5).
  Related open points: long-term history of a deleted list (Q8) and the
  known surprise exception of the quantity-reduction refusal in the edit
  form (Q12, exists today, not created by this story).

- **E. FR-3.6, no "completed" state for a purchased promise on a fully
  received wish.** The giver's promise stays open in the cabinet with a
  "received" marker until the giver cancels it; the product has no
  "completed" state for it. This follows from assumption A (receipt never
  closes a promise) and was taken as a product shortcut, not confirmed with
  the product owner. The marker persists indefinitely for a giver who never
  acts. Owner: WISHENKA-24 (UX), item 1.16; the decision on a "completed"
  state belongs to N3.

### Approximations in the migration plan

- **AR-3, back-fill dates.** Wishes that already have `received_quantity > 0`
  but no receipt record get one back-filled record dated by the wish's last
  update. Receipt dates before this story are approximate and may be wrong
  (an unrelated edit moves "last update"). Accepted in the architecture.
  The approximation must be visible in the WISHENKA-23 migration notes and
  must not be presented to the owner as an exact date.
- **AR-5, legacy archived rows.** The old `archive_wish_item` had no guard
  on `received_quantity`. The migration normalises fully received archived
  rows to not archived and leaves partly received ones archived. The
  derived view rule makes the display correct even without the migration.
  The residual risk is that the migration changes stored state of
  production rows irreversibly; a downgrade cannot tell which rows were
  normalised. Accepted. Action for WISHENKA-23 (item 1.3): state the
  irreversibility as accepted in the migration notes and log the number of
  normalised rows with the event `legacy_archived_rows_normalised`.

### Work-size and structure compromises

- **WISHENKA-23 is large.** The architecture bundles four things in one
  story: notification infrastructure (outbox, settings at both levels,
  worker, bot sender), domain rules, the archive split with read models,
  and routes. The architecture suggests a split into (a) notification
  infrastructure and (b) domain rules, archive split, read models and
  routes, where (b) does not depend on (a) if the producer sits behind a
  small interface with a no-op implementation first. The decision was left
  to the product owner and is **still open**. It should be taken before
  WISHENKA-23 starts its Step 1, because it changes the story's size,
  estimate and order. This is an action on the existing ticket, not a new
  ticket (see Follow-up Tasks, group 1).
- **Split of work is derived from titles.** The requirements state that the
  WISHENKA-23 / WISHENKA-24 split was derived from the Jira titles and is
  "to be confirmed with the product owner". It was not confirmed.

### Architecture points left open for the follow-ups

These were left open by design (the architecture is frozen at Step 2) and
are not defects of this story. Each has an owner (see Follow-up Tasks):

- Minimum of the notification infrastructure: both settings levels, one
  event type, default on (AR-4), settings written only by tests.
- The settings screen: out of scope for both follow-ups (architecture Q2).
- Cabinet link for a fully received wish: a fully received wish is not on
  the active list, so the link target needs a decision; recommended: omit
  the link and keep the cabinet actions (architecture Q6).
- Keep or rename the existing `item_fulfilled` event (observability notes).
  The two choices touch `tests/test_reservation_observability.py` and
  `doc/dev/reservations.md` in the same story, and the two events must not
  be emitted together for one act.
- `receipt_notice_enqueue_failed` is distinguishable from other receipt
  failures in the log. Step 2 of WISHENKA-23 must make the response
  indistinguishable from other receipt failures or document the difference
  as an accepted residual (observability notes).
- «Active» predicate (AR-1): «active» in the list and reorder rules means
  not archived and with remaining quantity above zero. The predicate
  changes for the active list and for reorder (`20-architecture.md`
  section 8 AR-1 and section 2) and must be enforced through one shared
  predicate, not repeated per query (item 1.14).
- FR-5.7 versus soft delete: the requirement says deleting a list removes
  its gifted history. List deletion is a soft delete with purge after
  `wishlist_retention_days` (`wishenka/wishlists/cleanup.py`,
  `doc/dev/wishlists.md`), and the foreign-key cascade fires only on purge.
  Until then the history stays in the database and visibility depends on
  the read model hiding it. To be verified in WISHENKA-23 Step 2 (item
  1.15).
- Storage of the database-side duplicates counter and whether the outbox row
  stores the last error class.
- Existing test `tests/test_surprise_role_context.py` asserts that the two
  notification tables do not exist (`_NOTICE_TABLES`) and checks log text
  for `notification`, `outbox`, `push` (`_NOTICE_MARKS`). It turns red as
  soon as WISHENKA-23 adds the tables or logs, for a reason that is no
  longer a leak. It must be **replaced by a stronger check**, not weakened
  or deleted (architecture Q1, observability walk-test rule).
- `doc/dev` still describes today's behaviour (archive moves the whole wish,
  notification path open). Step 8 of this story writes the new behaviour as
  **planned, deferred to WISHENKA-23 and WISHENKA-24**; the follow-up
  Step 8s turn it into current documentation.

### Accepted privacy residual

- **Summary-window timing channel.** On an otherwise idle system the INFO
  record `receipt_notice_window_summary` with non-zero counts appears after
  the window in which a receipt had open promises, and does not appear when
  it had none. The stream is operator-only, the record carries only
  system-wide counts that merge unrelated receipts, and the fixed grid with
  a minimum window blurs the time. Closing it fully would need a
  fixed-cadence noisy heartbeat, which contradicts "an idle worker writes
  nothing". It is accepted **only while logs stay operator-only**; this
  condition is the part that can silently stop being true (`LOG_LEVEL=DEBUG`
  is a normal setting and re-exposes presence).
- No metrics exporter exists in the project (`pyproject.toml`, `wishenka/`:
  no Prometheus, StatsD or OpenTelemetry). The candidate metrics of
  `50-observability.md` are defined but cannot be scraped. The choice
  (derive from logs as `reservations.md` does, or add an exporter) is open;
  the exporter decision and work are the new item N4.

## Code Quality Issues

No code changed, so there is no code-level debt. The documents have their
own weaknesses:

- **Very long artifacts.** `10-requirements.md` (445 lines),
  `20-architecture.md` (522 lines) and `50-observability.md` (439 lines) are
  long for what a specification story delivers, and the three repeat the
  same rules (FR-4.3, the closed reason set, the over-booked state). A
  follow-up reader will not read all three. Mitigation already in place: the
  rules were folded into `in-docs/spec.md` sections 7.2 and 7.3 (short, in
  Russian) and `doc/dev` is updated in Step 8. Do not shorten the files now:
  the review rounds checked them as they are, and a rewrite would reopen
  Steps 1 and 2. The risk is drift between the three copies if one is
  changed later; the single place to change a rule must be `in-docs/spec.md`.
  Not a ticket.
- **FR references were removed from `in-docs/spec.md`.** Step 5 removed inline
  FR identifiers, the Jira key and the `ai-tasks` path from the rules (the
  spec is a product document). Consequence: the spec rules can no longer be
  traced to the FR text of `10-requirements.md` except by reading both side
  by side. This is acceptable; it is noted so that a reviewer of
  WISHENKA-23 knows to compare against the requirements file.
- **Jira key left in the spec.** The trailing source line of section 7.3
  («Источник правил 7.2 и 7.3: требования FR-1 — FR-5 задачи WISHENKA-22»)
  names a Jira key and FR numbers that appear nowhere else in the spec. It
  is the only such line in the diff. Recommended: either keep it as the
  single traceability pointer (state this in the Step 8 notes) or delete it.
  A one-line decision, assigned to **this story's Step 8**; not a ticket.
- **Terminology mismatch about who sees «Подаренные».** The requirements
  say «Подаренные» is for **authors** (owner and co-author with the right to
  edit wishes; FR-5.5, assumption D). `in-docs/spec.md` section 7.2 says it
  is available to «владельцу, администраторам и участникам», while the
  receipt bullet says «администратор или участник **с правом
  редактирования**». Section 3 of the spec gives every participant the
  right to edit any wish, so the two phrases denote the same set today, but
  the qualifier «с правом редактирования» suggests a participant without
  that right, which the role table does not define. The two bullets should
  use one wording. This is a documentation edit; it is covered by
  WISHENKA-24 (the section that implements the visibility rule) or by one
  line in this story's Step 8, and is not a ticket. The wording is in the
  text this story itself edited (`in-docs/spec.md` 7.2, the receipt bullet
  at about line 262 versus the «Подаренные» bullet at about line 266), so
  the one-line fix is assigned to **this story's Step 8**, not to
  WISHENKA-24 (item 1.11).
- **Spec is ahead of the code.** Section 7.2 and 7.3 now describe behaviour
  that does not exist until WISHENKA-23 and WISHENKA-24 land (for example,
  «архивирование не предлагается» for a fully received wish; today any wish
  can be archived). This is normal for a target-state specification, but
  the window between this commit and the follow-ups is a period where the
  spec and the app disagree. Mitigated by the "planned" markers in `doc/dev`
  (Step 8).

## Missing Tests

- **Python test-timeout rule: N/A.** No test file was added or changed by
  this story (`tests/` untouched), so no test can lack a
  `pytest.mark.timeout` marker. Existing tests were not modified. This is
  not a BLOCKER.
- **Tests run:** none, because no code changed. `make analyze` was run once
  as a read-only regression check in Step 5 (clean).
- **Red tests deferred to WISHENKA-23 / WISHENKA-24.** Step 3 of this story
  is N/A (no behavioural change). The architecture
  (`20-architecture.md`, section «Failing Repro») lists the red tests owned
  by the follow-ups, each under its own Step 3. They are **not** missing
  tests of this story:
  - WISHENKA-23 (service and store level, fake sender): partial and full
    receipt; refusals (zero, negative, above remaining, archived wish,
    archived or deleted list, gifter or anonymous); over-booked state
    (create and raise refused, lower, cancel and purchase allowed);
    receipt never touches reservations; concurrency of two receipts and of
    receipt versus promise (same-process and spawned-process, pattern of
    `tests/test_booking_ceiling_r5.py`); notices (one row per giver, none
    for cancelled, non-holder or recipient, one per act, settings gate,
    text without quantities); sender failure leaves the receipt committed;
    archive split and restore; legacy rows; wish without stated quantity;
    receipt of an unpromised unit; reduction lock; surprise checks of the
    response, the «Подаренные» read model and logs; migration test
    (back-fill, normalisation, cascade); at-most-one-extra-send delivery
    test; replacement of `tests/test_surprise_role_context.py` assertions.
  - WISHENKA-24 (browser and route level): receipt screen offers 1 to
    remaining and shows a readable refusal on a lost race; partly received
    wish shows the remaining count and appears in «Подаренные»; fully
    received wish leaves the list; «Подаренные» and archive are separate;
    cabinet marker and actions for a fully received wish and no giver
    controls on the card; no booking marker for the recipient before and
    after receipt.
- **Documents have no automated check.** No Markdown lint target exists in
  the Makefile (Step 5). The consistency between `in-docs/spec.md`,
  `10-requirements.md` and `20-architecture.md` was verified by hand and by
  review only. A docs-lint target is a general project concern, not a
  follow-up of this story, and is not proposed as a ticket.
- **Known pre-existing failing tests:** none were observed in this story
  (no test run).

## Performance Concerns

No runtime change here. Concerns the follow-ups must keep in view:

- **Producer inside the writer lock.** The receipt transaction runs under
  `BEGIN IMMEDIATE` and now also reads open promises, evaluates settings per
  giver and inserts one outbox row per giver. The lock is held longer by the
  number of givers on one wish (bounded by the quantity of the wish). All
  wishes share one SQLite writer, which is the subject of the existing
  ticket WISHENKA-118.
- **Outbox worker shares the same writer.** Polling and status updates
  compete with receipts and promises for the one writer (WISHENKA-118).
- **Outbox retention is not specified.** The architecture defines `pending`,
  `sent`, `failed` and `skipped` rows and no cleanup, so the table grows
  without bound. WISHENKA-23 Step 2 must state a retention rule; WISHENKA-60
  (outbox for booking events) is the likely common place, key relation to be
  verified. If WISHENKA-60 turns out not to cover cleanup, the conditional
  item N5 applies.
- **Query predicates.** The three views (active, «Подаренные», archive) rest
  on `received_quantity` versus `quantity` comparisons plus `is_archived`,
  and the notice set needs open reservations per wish. Index needs are
  covered by WISHENKA-59 (secondary indexes for reservations), scope to be
  verified for `wl_receipts` (foreign key to the wish) and for the new
  predicates.
- **Counter plus records.** Two writes per receipt in one transaction. The
  cost is accepted (architecture Q4).
- **Hardcoded values.** None in the documents except the indicative ones the
  observability file fixes for WISHENKA-23: window minimum of 60 seconds,
  poll interval not above the window, and a bounded retry count. They must
  become settings, not literals.

## Follow-up Tasks

Classification rule: BLOCKER means something is broken, incomplete or unsafe
relative to the acceptance criteria of WISHENKA-22; deferred work is
NON-BLOCKER. **There are no BLOCKERs.** The `Jira:` field of a new item
stays `not yet created` until the sync step links it.

### Group 1. Covered by WISHENKA-23 / WISHENKA-24 (no new ticket)

Each item is part of the scope that WISHENKA-23 or WISHENKA-24 already
carries (item 1.11 is the exception: it belongs to Step 8 of this story); the pointer says where in the artifacts it is fixed. The follow-up
stories must pick them up in their own Steps 2 to 8.

| # | Item | Owner | Where fixed | Priority | Class |
| - | ---- | :---: | ----------- | :------: | :---: |
| 1.1 | Notification infrastructure minimum: outbox, user and list settings, worker, bot sender | 23 | `20-architecture.md` section 4, Q2 | High | NON-BLOCKER |
| 1.2 | Decide the split of WISHENKA-23 into (a) notification infrastructure and (b) domain rules, archive split, routes; decision before its Step 1. Action: comment on WISHENKA-23, no new ticket | 23 | `20-architecture.md` Implementation Plan, note for the product owner | High | NON-BLOCKER |
| 1.3 | Migration: receipt table, back-fill (AR-3 approximate dates), legacy archived normalisation (AR-5), cascade. Action for AR-5: document the irreversible downgrade as accepted in the migration notes and log the count with event `legacy_archived_rows_normalised` | 23 | `20-architecture.md` WISHENKA-23 step 1, section 2 | High | NON-BLOCKER |
| 1.4 | Replace `tests/test_surprise_role_context.py` (`_NOTICE_TABLES`, `_NOTICE_MARKS`) with a stronger recipient-walk check. Also update `doc/dev/verification-matrix.md` (about lines 425 to 433, the row for `test_recipient_walk_hides_booking_in_response_log_and_notice`): it states "the test database does not gain a `notification_outbox` or `user_notification_settings` table" and "Gap: none", and goes stale when the test changes. Done in the follow-up's Step 8 (not in this story, `doc/dev` is out of its scope) | 23 | architecture Q1, observability walk-test rule; `doc/dev/verification-matrix.md` | High | NON-BLOCKER |
| 1.5 | Keep or rename `item_fulfilled`; update `tests/test_reservation_observability.py` and `reservations.md` with the choice | 23 | `50-observability.md` Notes | Medium | NON-BLOCKER |
| 1.6 | `receipt_notice_enqueue_failed` must not reveal presence: indistinguishable response, or documented accepted residual | 23 | `50-observability.md` Notes | Medium | NON-BLOCKER |
| 1.7 | Duplicates counter storage, outbox last-error-class storage, outbox retention rule | 23 | `50-observability.md` Notes; retention is a gap, see Performance Concerns | Medium | NON-BLOCKER |
| 1.8 | Summary-window residual: implement the window setting (minimum 60 s, fixed grid, no heartbeat), keep DEBUG logs operator-only, state the access requirement in the dev docs | 23 | `50-observability.md` presence and timing section | Medium | NON-BLOCKER |
| 1.9 | Cabinet link target for a fully received wish (recommended: omit the link, keep actions) | 24 | architecture Q6 | Medium | NON-BLOCKER |
| 1.10 | All red tests listed under Missing Tests, each under its own Step 3 | 23, 24 | architecture «Failing Repro» | High | NON-BLOCKER |
| 1.11 | Unify wording about who sees «Подаренные» («с правом редактирования» vs «администраторам и участникам») in `in-docs/spec.md` 7.2: one-line fix in the text this story edited. Also decide the trailing «WISHENKA-22» source line of 7.3 (keep as pointer or delete) | 22 (this story, Step 8) | this file, Code Quality Issues | Low | NON-BLOCKER (done in Step 8) |
| 1.12 | Turn the "planned" notes in `doc/dev` into current documentation when the code lands (each follow-up's own Step 8) | 23, 24 | architecture Implementation Plan | Medium | NON-BLOCKER |
| 1.13 | Candidate metrics: derive from logs within the project limit of no exporter (as `reservations.md` does); the exporter option is N4. Includes the alert thresholds suggested in `50-observability.md` for WISHENKA-23 to confirm: oldest pending age above a few worker intervals, any terminal `failed` row, refused-receipt rate far above the accepted rate (possible UI defect in WISHENKA-24) | 23 | `50-observability.md` candidate metrics and "Suggested alert thresholds" | Low | NON-BLOCKER |
| 1.14 | «Active» predicate (AR-1): active = not archived and remaining above zero, for the active list and reorder; enforce through one shared predicate. WISHENKA-23 owns the predicate, WISHENKA-24 the reorder UI | 23 (predicate), 24 (reorder UI) | `20-architecture.md` section 8 AR-1, section 2 | Medium | NON-BLOCKER |
| 1.15 | FR-5.7 versus soft delete: list deletion is a soft delete, purge after `wishlist_retention_days` (`wishenka/wishlists/cleanup.py`, `doc/dev/wishlists.md`), the FK cascade fires only on purge. To be verified in WISHENKA-23 Step 2: what the gifted read model shows for a soft-deleted list | 23 | `10-requirements.md` FR-5.7; `20-architecture.md` section 2 | Medium | NON-BLOCKER |
| 1.16 | FR-3.6 UX: a purchased promise on a fully received wish has no "completed" state; the "received" marker persists until the giver cancels (assumption A, shortcut E). WISHENKA-24 designs the marker and the cabinet actions within this limit | 24 | `10-requirements.md` FR-3.6 | Medium | NON-BLOCKER |
| 1.17 | Sequencing and contract: WISHENKA-24 starts only after the contract of section 5 is fixed in WISHENKA-23 Step 4, or a stub returning the contract shape exists. Route paths and DTO names are indicative until WISHENKA-23 Step 2 and Step 8 fix them. Action: comment on both tickets | 23, 24 | `20-architecture.md` section 5 and the sequencing note in Implementation Plan | High | NON-BLOCKER |

### Group 2. Covered by an existing ticket (reference only)

Keys come from the task context. The Priority column is "existing
ticket's own": the priority of those tickets was not available to this step
and is not changed by it. "Relation to be verified" means the topic
overlap is judged from the ticket title only and the ticket scope was not
read (Jira could not be called from this step).

| # | Item | Existing ticket | Priority | Note | Class |
| - | ---- | :-------------: | :------: | ---- | :---: |
| 2.1 | Outbox and notification dispatcher: WISHENKA-23 adds its own outbox for receipt notices. Two outbox designs for two event families would be a duplicated mechanism, so WISHENKA-23 Step 2 and WISHENKA-60 must agree on one table and one worker | WISHENKA-60 | existing ticket's own | Relation to be verified; highest overlap risk of this analysis | NON-BLOCKER |
| 2.2 | Writer contention: producer inside the `BEGIN IMMEDIATE` receipt transaction and the worker updates share the one SQLite writer | WISHENKA-118 | existing ticket's own | Receipt is one more writer; no new work for this story | NON-BLOCKER |
| 2.3 | Indexes for the active, gifted, archive predicates, the notice-set query and the receipt foreign key | WISHENKA-59 | existing ticket's own | Scope for `wl_receipts` to be verified | NON-BLOCKER |
| 2.4 | Double submit of the receipt command (two taps record two receipts of 1 unit) | WISHENKA-61 | existing ticket's own | Idempotency keys; whether the receipt route is in scope to be verified. A deliberate second receipt is legal, so only a client-side or key-based duplicate guard helps | NON-BLOCKER |
| 2.5 | CSRF on the cookie mutation of the owner receipt form (same base script as the wish card) | WISHENKA-123 | existing ticket's own | The receipt screen will reuse the same script; WISHENKA-24 must not add a second CSRF path | NON-BLOCKER |
| 2.6 | Lock dictionary growth in `ItemConcurrencyCoordinator`; the receipt reuses it and adds no new lock | WISHENKA-58 | existing ticket's own | No new work for this story | NON-BLOCKER |

### Group 3. New debt needing a ticket

Only product-owner decisions and cross-cutting work that no known ticket
carries. Four items to create (N1 to N4) and one conditional item (N5, not
to be created unless confirmed). Existing tickets 23, 24, 58 to 61, 118 and
123 do not describe them. Before creating, the sync step must check by title that no
ticket for the same topic exists (key to be verified).

| # | (a) Title | (b) Why not covered by 23/24 or an existing ticket | (c) Priority | (d) Class | (e) Jira |
| - | --------- | -------------------------------------------------- | :----------: | :-------: | -------- |
| N1 | Undo or correct a gift receipt (decision and feature) | Explicitly out of scope of 22, 23 and 24 (requirements Q9, assumption C): `in-docs/spec.md` does not describe it, so the follow-ups build the act as final. A mistaken tap of a wrong quantity cannot be reversed. Needs a product decision first (what happens to notices already sent, to the dated record, to the over-booked state) | Medium | NON-BLOCKER | Jira: [WISHENKA-153](https://pypost.atlassian.net/browse/WISHENKA-153) |
| N2 | Notification settings screen (user level and per list) | Out of scope of 23 and 24 by the architecture (Q2): 23 builds storage and lookup only, rows are written by tests. Until a screen exists, FR-4.6 («giver switched the notice off») cannot be used by a real user, and AR-4 keeps the event on for everyone. Whether WISHENKA-60 includes settings is not known (key to be verified) | Medium | NON-BLOCKER | not created — covered by existing [WISHENKA-34](https://pypost.atlassian.net/browse/WISHENKA-34) «Настройки уведомлений и персональных предпочтений» (sprint 3); the settings screen belongs there |
| N3 | Product-owner decisions on open privacy and visibility points of gift receipt | A single decision record, no code: (i) confirm assumptions A to D, (ii) may gifters see a public «already gifted» label (Q6), (iii) keep gifted history after list deletion (Q8), (iv) co-author who is also the recipient, section 16 of the spec (Q11), (v) tighten the existing edit-form quantity lock that reveals occupied units (Q12). No follow-up story carries a decision; they build on the stated assumptions. The edit-form exception exists today and is not created by this story | Medium | NON-BLOCKER | Jira: [WISHENKA-154](https://pypost.atlassian.net/browse/WISHENKA-154) |
| N4 | Metrics exporter for the project: decision and implementation | The project has no Prometheus, StatsD or OpenTelemetry exporter, so the candidate metrics of `50-observability.md` cannot be scraped. WISHENKA-23 derives them from logs (item 1.13); a real exporter is cross-cutting work for the whole project and is not in the scope of 23, 24 or the known Debt tickets (key to be verified by title) | Low | NON-BLOCKER | not created — overlaps existing [WISHENKA-84](https://pypost.atlassian.net/browse/WISHENKA-84) «Экспорт метрик Prometheus/OpenTelemetry»; project-wide exporter scope to be agreed there |
| N5 | **CONDITIONAL.** Outbox retention and cleanup of `sent`, `failed` and `skipped` rows | Create **only if** WISHENKA-60 turns out not to cover outbox retention (to be confirmed by reading WISHENKA-60 and the WISHENKA-23 Step 2 result). The retention rule itself stays a WISHENKA-23 Step 2 action (item 1.7). The orchestrator must **not** create this ticket unless that is confirmed | Medium | NON-BLOCKER | conditional, do not create unless confirmed |

Items deliberately **not** ticketed:

- Outbox retention (N5): conditional, see Group 3.
- The length and overlap of the three long artifacts: mitigated by folding
  the rules into `in-docs/spec.md`; ticketing a rewrite would reopen
  reviewed steps.
- The Jira key in the spec's trailing source line and the FR references
  removed from the spec: a one-line decision assigned to Step 8 of this
  story (keep as the single traceability pointer or delete). No ticket.
- The summary-window timing channel: accepted with a stated condition
  (operator-only logs), tracked as 1.8 inside WISHENKA-23.
- A Markdown lint target for `Makefile`: a general project wish, not caused
  by this story.
- Pre-existing failing tests: none observed.

### Notes for the gate owner

- No BLOCKER. The story may close after review.
- Counts: Group 1 has 17 items (1.1 to 1.17), Group 2 has 6 items
  (2.1 to 2.6), Group 3 has 4 new tickets (N1 to N4) and 1 conditional
  item (N5).
- Step 8 of this story carries two one-line edits in `in-docs/spec.md`
  (item 1.11): the «Подаренные» wording in 7.2 and the decision on the
  trailing «WISHENKA-22» line of 7.3.
- The most valuable single action outside this story is item 1.2 (decide the
  WISHENKA-23 split before it starts) together with item 2.1 (agree one
  outbox with WISHENKA-60).
- Step 8 of this story updates `doc/dev` (planned markers) and must
  verify, not rewrite, the closure of sections 7.3 and 16 of
  `in-docs/spec.md` done in Step 4.
