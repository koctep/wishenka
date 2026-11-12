# WISHENKA-56: Technical Debt Analysis

## Shortcuts Taken

Encoding inference uses fixed Russian-language frequency heuristics over a bounded sample.
CP1251 and KOI8-R can both decode the same bytes, so a plausible result is not proof of the
source encoding. The deterministic header precedence can retain an incorrectly declared
single-byte encoding. Low-confidence inputs use replacement decoding, and users may correct
the resulting preview manually.

JSON-LD support remains a bounded subset: it does not expand remote contexts or dereference
`@id` references. Product discovery and type inspection use fixed depth and node limits;
valid products beyond those limits can be missed. These choices follow the architecture.

## Code Quality Issues

The decoding policy includes fixed scoring thresholds and a hand-maintained list of Russian
letter sequences. They are not calibrated against a broad, versioned catalogue corpus. The
node and depth limits are fixed constants in the traversal functions. Changes to these values
require reviewing their behavior and regression coverage together.

## Missing Tests

The offline tests cover representative legacy encodings, conflicting declarations, malformed
labels, nested graphs, limit behavior, fallbacks and response size enforcement. They do not
establish accuracy across arbitrary languages, short ambiguous samples or real-world catalogues.
The new test module has an explicit 30-second timeout. The latest full run passed 387 tests.

One earlier `make test` run passed all 386 tests but the pytest process then exited with a
segmentation fault. Subsequent `make test` and `make check` runs exited successfully. The
untracked `core` file identifies an aarch64 pytest Python process and is preserved for diagnosis;
`gdb` is unavailable in this environment. The cause and whether the crash predates this change
are unknown; no failing test node or baseline reproduction has been identified. Do not classify
the crash as pre-existing based only on the successful reruns.

## Performance Concerns

Each Product candidate can perform its own bounded type traversal. The traversal limits cap
visited nodes, but adding a wide list to the explicit stack occurs before the next node-budget
check; the upstream response-size limit bounds input bytes but not directly the stack allocation.
The decoder can construct multiple decoded copies of a response for its fallback candidates.
Worker offload, executor saturation and cancellation are tracked by
[WISHENKA-113](https://pypost.atlassian.net/browse/WISHENKA-113).

## Follow-up Tasks

- **NON-BLOCKER — Medium: Investigate the intermittent pytest exit crash** using
  the preserved `core`, environment details and bounded repeated runs at the task base and current
  revision. Establish cause and whether it is introduced by this task before deciding its status.
  Jira: [WISHENKA-115](https://pypost.atlassian.net/browse/WISHENKA-115)
- **NON-BLOCKER — Medium: Calibrate encoding recovery.** Evaluate short, mixed-language and
  ambiguous examples against a representative, legally usable corpus; measure incorrect guesses
  and improve or configure the confidence policy while retaining deterministic fallback.
  Jira: [WISHENKA-117](https://pypost.atlassian.net/browse/WISHENKA-117)
- **NON-BLOCKER — Medium: Bound traversal overhead.** Measure and bound stack allocation and
  repeated type inspection for adversarial graphs within the response-size limit.
  Jira: [WISHENKA-116](https://pypost.atlassian.net/browse/WISHENKA-116)
