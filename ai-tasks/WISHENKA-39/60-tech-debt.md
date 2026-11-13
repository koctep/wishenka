# WISHENKA-39: Technical Debt Analysis

## Shortcuts Taken

No shortcut was taken. The deliverable is the six checks in
`tests/test_booking_ceiling_r5.py`. Product behavior stays as it is.
No lock, no isolation change, and no edit to `execute_wish` or
`create_reservation`.

The module follows `ai-tasks/WISHENKA-39/20-architecture.md`. The
process lifecycle is the R2 spawn, barrier, queue, join, and
terminate sequence, copied so the racing write can be
`execute_wish`. That copy is the plan for this task. It is not a
crutch and not a later extraction.

Crowd size, free units, repetitions, load rounds, and the internal
waits are the bounds that plan names. They live only in the test
module.

## Code Quality Issues

No code-quality debt. Product modules were not changed. The new test
module has no unused imports, no unused variables, no commented-out
code, and no debug prints. Its longest line is 99 characters, under
the 100-character project limit. Step 5 recorded a clean
`make analyze` run.

Balance reads use `service._items`, the same private map the shared
inventory tests already use. Gifter ids and the named constants are
the architecture bounds, not product values left hardcoded.

## Missing Tests

No missing test for this task. The six checks are present:

- `test_one_copy_one_unit_each` — five gifters, one store, one unit
  each.
- `test_many_copies_one_unit_each` — the same shape, one process per
  gifter.
- `test_one_copy_whole_remainder` — five gifters, one store, each
  asks for the whole remainder.
- `test_many_copies_whole_remainder` — the same shape, one process
  per gifter.
- `test_repeated_contention_many_copies` — three starts of each
  shape, including a wish that already has one occupying unit.
- `test_load_profile_one_copy_and_many_copies` — two rounds of both
  shapes on one store and two rounds on many copies.

Timeout markers are present. Line 28 sets
`pytestmark = pytest.mark.timeout(120)`. Each test also sets its own
mark, and that closer mark is the bound: 30, 60, 30, 60, 90, and 120
seconds. Barrier, join, drain, and terminate waits are bounded. A
missing timeout is not debt here.

`doc/dev/verification-matrix.md` still says row R5 has no load
harness. Pointing that row at these tests is Step 8 of this task. It
is not a missing test and not a follow-up.

Further locking and isolation stay on WISHENKA-49. This task does
not add them.

Step 5 ran this module only. All six tests passed. No pre-existing
failure was observed, so there is no `NON-BLOCKER — pre-existing`
entry.

## Performance Concerns

No performance concern for this task. The load profile is a short
series that checks the ceiling. It sets no response-time target and
no throughput target. Five gifters stay inside the existing
`busy_timeout`. A wider crowd that exhausts that wait is the locking
work WISHENKA-49 already owns. There is no new performance
follow-up.

## Follow-up Tasks

There is no new follow-up.

The checks this task delivers are not follow-ups. Updating
`doc/dev/verification-matrix.md` so row R5 names these tests is Step
8 of WISHENKA-39, not a later ticket. Further locking stays on the
existing story WISHENKA-49.
