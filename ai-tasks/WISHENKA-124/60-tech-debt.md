# WISHENKA-124: Technical Debt Analysis

Scope: `tests/browser_support.py`, `tests/conftest.py`, `tests/test_browser_prerequisites.py`, the
`browser` marker and `@pytest.mark.browser` in `tests/test_wishlist_management_browser.py` and
`tests/test_wishlist_sections_ui.py`, Makefile target `deps-browser` (`Makefile:24-35`),
`pyproject.toml` (`websockets>=13.0` at line 35, `markers`), `.github/workflows/ci.yml`
(step at lines 28-30) and `doc/dev/testing.md`. Compared against `20-architecture.md`.

Timeout markers (grep over the four test files of this task): each declares a module-level
`pytestmark = pytest.mark.timeout(...)`: `test_browser_prerequisites.py:28` (30 s),
`test_wishlist_management_browser.py:19` (45 s), `test_wishlist_sections_ui.py:36` (60 s). Both
browser tests also use the session fixture, whose setup falls under the same marker. No
timeout-marker BLOCKER.

Pre-existing failures: none. The full suite was green at the start of this step (512 passed, per
the task brief; not re-run here, no code changed).

## Shortcuts Taken

- **CI browser name is not verified.** `ci.yml` runs only `make deps-browser` (lines 28-30) and
  relies on the browser preinstalled on `ubuntu-latest`. The roadmap says the presence of a
  browser was confirmed in the ubuntu-24.04 image list, but no real CI run has happened, and the
  architecture itself states that the software list does not give the name or `PATH` location
  (`20-architecture.md`, "Chromium/Chrome на GitHub-hosted runner"). It is therefore unproven that
  one of `chromium`, `chromium-browser`, `google-chrome-stable`, `google-chrome` is on `PATH` and
  passes the probe. The first CI run decides. The failure is loud (exit 2 or 3 with an actionable
  message), not silent.
- **Fallback `browser-actions/setup-chrome` is documented but not wired.** The architecture table
  lists it as the "CI, fallback" path (pinned by commit SHA, output passed through
  `WISHENKA_CHROMIUM_BIN`). `ci.yml` has no such step, and `doc/dev/testing.md` ("CI") does not
  mention it. This matches the architecture wording ("only if the image stops containing
  Chrome"), but nobody has verified that `@v2` and the SHA are current.
- **The apt branch of `deps-browser` was never executed here.** `Makefile:26-34` (Debian check
  through `/etc/os-release`, `sudo` selection, `apt-get update`, `apt-get install -y chromium`,
  re-probe) was exercised only by `make -n` and by the already-installed dev box path (rc 0
  through the probe). The "exit 2, then install" path has no automated or manual evidence.
  The recipe also has no way to test it in a hermetic way.
- **Duplicated CDP code remains in both browser tests** (`ws.recv(timeout=15)` helper and
  `connect(...)` setup, for example `test_wishlist_management_browser.py:61,121` and
  `test_wishlist_sections_ui.py:337,431`). This is the explicit architecture decision
  ("общий CDP-код остаётся дублированным"), recorded here so it is not forgotten.
- **Textual checks for config artifacts.** CI and Makefile are verified by regex over text
  (`test_ci_installs_browser_between_deps_and_check`, `test_pyproject_declares_browser_marker`
  accepts any marker string starting with `browser`). They catch removal, not a wrong command.

## Code Quality Issues

- **`browser_support.py` is a test-support module used as a production-like CLI** (`main()`,
  exit codes 0/2/3) and invoked as `python -m tests.browser_support` from the Makefile. This
  couples a Makefile target to the `tests` package layout (`tests/__init__.py` must stay). It is
  a deliberate architecture choice (single resolution point), not a defect.
- **`snap` detection by substring.** `_failure_lines` (`browser_support.py:107`) treats any
  probe detail containing `"snap"` (case-insensitive) as a snap problem. A broken non-snap
  browser whose stderr happens to mention "snap" (for example a snapshot message) gets a
  misleading hint. The condition is only a hint, never a decision.
- **`candidate_names()` is a function returning a literal tuple**, while the names are also
  repeated in `doc/dev/testing.md` ("Поиск браузера") and the architecture. Three places to edit
  when a name is added; only the code is checked by tests.
- **The `Makefile` recipe embeds shell logic** (one long `if` across continuation lines, inline
  `. /etc/os-release`). It works, but it is dense and portable only to POSIX `sh`; readability
  would improve with a small script or by letting `browser_support` print the install decision.
- **`test_browser_prerequisites.py` uses two subprocess timeouts larger than or equal to the
  module marker**: `_nested_pytest` uses `timeout=60` (`test_browser_prerequisites.py:313`) while the module
  marker is 30 s, so the inner timeout is unreachable; pytest-timeout fires first and the
  subprocess is not necessarily cleaned up by `subprocess.run` in that case. Low risk, noted
  for tidiness.

## Missing Tests

- No test or manual evidence for the apt branch of `deps-browser` (see Shortcuts). A test would
  need a fake `apt-get`/`sudo`/`os-release` in a temporary `PATH`; the recipe reads
  `/etc/os-release` from a fixed path, so it is not injectable today.
- No test that a missing or unusable explicit `WISHENKA_CHROMIUM_BIN` makes `deps-browser` skip
  apt (the recipe has `[ -z "$$WISHENKA_CHROMIUM_BIN" ]`, `Makefile:28`); only the Python CLI
  exit codes are tested.
- No test that the two browser tests actually carry `@pytest.mark.browser` (the marker is only
  declared in `pyproject.toml`; applying it is checked by nobody). `-m browser` selecting zero
  tests would go unnoticed.
- No test for `CI` truthiness beyond the documented values (`""`, `0`, `false`, `no`): for
  example `False` with other casing is covered by `casefold`, but values like `off` count as CI.
  This is by definition in the architecture and documented in `doc/dev/testing.md`.
- The snap-confinement scenario (a working snap Chromium whose `--version` passes but whose
  launch fails on the `tmp_path` profile) is documented and warned about, but not reproducible
  here and not tested; the "snap path (confinement ...)" message is covered only for string
  classification.
- No test for the real browser on the CI runner (cannot be done locally).

## Performance Concerns

- **Worst-case probe time can approach the test timeout.** `find_candidates` may return up to
  four candidates, each probed with a 10 s limit (`browser_support.py:18`), and the probing runs
  inside session-fixture setup, which is counted by the first browser test's marker: 4 x 10 s = 40 s
  of the 45 s budget of `test_wishlist_management_browser.py:19`. Only reachable when several
  candidates hang, which is unlikely, and the failure would still be a timeout rather than a
  silent pass. A typical probe takes a fraction of a second.
- The probe runs once per session (session-scoped fixture) and once per `make deps-browser`; no
  caching across runs. Acceptable.
- `deps-browser` starts a Python process (`python -m tests.browser_support`) in CI and again at
  the end of the apt branch; negligible.

## Deviations from Architecture

No functional deviations found. Verified against `20-architecture.md`:

- Components, signatures, exit codes 0/2/3, session fixture behaviour (ok / skip / `pytest.fail(...,
  pytrace=False)`), de-duplication by `abspath`, no `PATH` fallback for an explicit variable,
  CI step order (`make deps`, `make deps-browser`, `make check`), `websockets>=13.0`, `browser`
  marker, `test`/`check` independent of `deps-browser`: all implemented as designed.
- Not-yet-done items that the architecture allows or defers: the setup-chrome fallback is not
  wired (allowed: "only if needed"); verification items the architecture marked "check on Step 4"
  (exact CI browser name and path, `apt-cache policy chromium-browser` on Ubuntu 24.04, `@v2`
  and SHA of setup-chrome) were not performed as live checks, because no CI/Ubuntu environment is
  available here.
- Documentation: `doc/dev/testing.md` is the planned minimal Step 4 version; the rest is Step 8
  scope (see below).

## Hardcoded Values

- **Candidate names** `chromium`, `chromium-browser`, `google-chrome-stable`, `google-chrome`
  (`browser_support.py:46`). Does not include Chrome for Testing, Brave, Edge or macOS/Windows
  paths; Linux-only by intent.
- **Probe timeout** `DEFAULT_PROBE_TIMEOUT = 10.0` (`browser_support.py:18`): a parameter of
  `probe` and `check_chromium`, but the fixture and the CLI always use the default and there is
  no environment override. A slow cold start on a loaded runner (snap first launch, antivirus)
  could exceed it.
- **stderr truncation to 300 characters** (`browser_support.py:98`): the cause of a failed probe
  can be cut off in the message.
- **apt only on Debian**: the recipe requires `ID=debian` in `/etc/os-release` and `apt-get`
  (`Makefile:28-29`). Ubuntu, Debian derivatives (for example Mint, Raspberry Pi OS report
  `ID=raspbian`/`linuxmint`), Fedora, Alpine and macOS get only a check and instructions. Package
  name `chromium` is hardcoded.
- **Environment variable names** `WISHENKA_CHROMIUM_BIN`, `WISHENKA_SKIP_BROWSER_TESTS`, `CI`
  and the exact opt-out value `1` / falsy CI set (`browser_support.py:16-19`).
- **`websockets>=13.0`** is deliberately narrower than the minimum that provides `websockets.sync`
  (11.0); recorded in the architecture Q&A, not a defect.
- **`ubuntu-latest`** is a moving alias (`ci.yml:12`), so the preinstalled browser set can change
  without a commit in this repository.
- **Python 3.12** in `ci.yml:21` is outside this task's scope.

## Documentation Debt (for Step 8)

These are planned Step 8 scope, not technical debt:

- `doc/dev/infrastructure.md` §2.1 (command table: add `make deps-browser`), §7.2 (CI steps:
  add the browser step), §8 (troubleshooting: no browser, snap shim, probe timeout).
  `grep -n chromium doc/dev/infrastructure.md` currently finds nothing.
- Expand `doc/dev/testing.md` from the minimal Step 4 version (for example the setup-chrome
  fallback procedure, the CI browser verification once known).

## Follow-up Tasks

There are no BLOCKER items. Every item below is NON-BLOCKER; none prevents Step 8, the commit,
or closing WISHENKA-124.

1. **NON-BLOCKER:** Verify the browser on a real CI run after merge: record the resolved path and
   Jira: [WISHENKA-135](https://pypost.atlassian.net/browse/WISHENKA-135)
   version from the "Install browser for UI tests" step log. If no candidate passes, wire
   `browser-actions/setup-chrome` (pinned by SHA, `WISHENKA_CHROMIUM_BIN` from `chrome-path`) as
   designed. Also run `apt-cache policy chromium-browser` on Ubuntu 24.04 to confirm the snap
   statement in the architecture.
2. **NON-BLOCKER:** Execute and cover the apt branch of `deps-browser`: run it once on a clean
   Jira: [WISHENKA-136](https://pypost.atlassian.net/browse/WISHENKA-136)
   Debian container or VM without Chromium, and make the recipe testable (injectable
   `os-release` path or moving the install decision into `browser_support`), then add tests for
   the `WISHENKA_CHROMIUM_BIN` guard and the Debian-only rule.
3. **NON-BLOCKER:** Add small tests: both browser tests carry the `browser` marker
   Jira: [WISHENKA-137](https://pypost.atlassian.net/browse/WISHENKA-137)
   (`pytest --collect-only -m browser` selects exactly them); tighten the marker declaration
   check; remove the unreachable 60 s subprocess timeout vs 30 s marker mismatch.
4. **NON-BLOCKER:** Make the probe more robust: optional `WISHENKA_BROWSER_PROBE_TIMEOUT` (or
   Jira: [WISHENKA-138](https://pypost.atlassian.net/browse/WISHENKA-138)
   a shared total budget so that four hanging candidates cannot consume the browser test's
   45 s marker), longer stderr excerpt (or log the full text), and a stricter snap hint.
5. **NON-BLOCKER, already ticketed:** Untracked 197,693,440-byte `core` file in the repository
   root (`ls -l core`: modified Nov 12 07:09; not matched by `.gitignore`, `git check-ignore core`
   prints nothing). It is the item recorded as follow-up 2 of WISHENKA-111 and ticketed as
   WISHENKA-126; not duplicated here. Reminder for `td-99-commit`: stage files by explicit path
   so `core` is never added.
