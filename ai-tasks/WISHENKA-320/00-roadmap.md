# Roadmap: WISHENKA-320

## Task Metadata

- **Implementation language**: Python, JavaScript

## Step Status

- [x] **STEP 1: Requirements Gathering and Documentation**
  - `ai-tasks/WISHENKA-320/10-requirements.md`: one name and length contract
    for creating a wishlist and for editing its details. The name is required,
    1 to 255 characters after trimming, on both. A name that is only invisible
    marks is treated as missing. A name that is too long shows the too-long
    message. The description and the event title do not gain a new character
    ceiling; create and edit stay within what creation already accepts.
    Lists already stored with an empty name stay readable; the next save
    must supply a real name. Not a blocker for other work.
  - Implementation language determined and recorded above.
  - Correction: the description and the event title do not gain a character
    ceiling in this task. Create and edit share one rule: both stay within
    whatever creation already accepts, which today is no extra character
    ceiling. A later product decision can add a ceiling. The name rules are
    unchanged: required, 1 to 255 after trim, on create and on edit;
    invisible-only names count as missing; a too-long name uses the too-long
    message; stored empty names stay readable; the next save needs a real
    name.
- [x] **STEP 2: High-Level Architecture Design**
  - `ai-tasks/WISHENKA-320/20-architecture.md`: one name rule on
    `POST` and `PATCH` via `wishenka/wishlists/name_contract.py`, mirrored
    in `showCreate` and `settingsForm`. Missing and invisible-only names
    share the required-name error; a too-long name has its own error type.
    Description and event title stay uncapped and blank means unset.
    Stored empty names stay readable; the next save must send a real name.
    Step 3's first red signal is `tests/test_wishlist_name_contract_api.py`.
  - Correction: the submitted name, on create and on edit, is the one
    normalized string the client check accepted, with no second `trim()`.
    An omitted stored name that is already too long reports the too-long
    failure. An omitted name that is missing, blank, or invisible-only
    still reports the required-name failure. A sent name uses the shared
    normalizer for both failures. Description and event title stay uncapped.
- [x] **STEP 3: Failing Repro Test**
  - `tests/test_wishlist_name_contract_api.py`: red HTTP contract for
    create and edit. Missing, blank, and invisible-only names are
    `wishlist_name_required`. A name over 255 code points is
    `wishlist_name_too_long`. Description and event title stay uncapped
    and blank means unset. A domain-seeded empty or too-long title stays
    readable, and the next save reports the failure that title has.
  - `tests/test_wishlist_create_form_ui.py`: invisible-only names use the
    required catalog string and are not posted; a `422` of type
    `wishlist_name_too_long` uses the too-long string; an edge U+FEFF
    stays in the submitted name.
  - `tests/test_wishlist_create_form_browser.py`: the same three create
    cases in Chromium.
  - `tests/test_wishlist_settings_name_contract_ui.py`: settings name
    rules in en and ru. An invalid name is not saved. An accepted name
    is the normalized string, including an edge U+FEFF. No maxlength on
    description or event title. An empty stored name still shows the
    untitled label.
  - `tests/test_wishlist_settings_name_contract_browser.py`: the same
    settings cases in Chromium.
  - A create name that is only U+FEFF already shows the required message
    in the Node harness, because `String.prototype.trim` removes it. The
    red create signals are the other invisible marks, the too-long `422`
    type, and an edge U+FEFF kept beside a visible character.
- [x] **STEP 4: Development**
  - [x] Server name contract on POST and PATCH: missing, blank, and
    invisible-only names are `wishlist_name_required`; over 255 code points
    is `wishlist_name_too_long`. Description and event title stay uncapped.
    A stored empty or too-long title stays readable and blocks the next save.
  - [x] Mini App create and settings share `wishlistNameDecision` and submit
    that normalized name, including an edge U+FEFF. Too-long `422` uses the
    too-long catalog string. A refused save keeps the typed value.
  - [x] The old PATCH blank-name assertion now refuses a blank or over-long
    name and still allows omitting a valid stored name. A legacy empty title
    in the home overview is seeded in the database, not by clearing the name.
  - Targeted runs: name-contract API 60 passed; create validation, create UI,
    and settings UI 87 passed; create browser, settings browser, and the home
    overview case 66 passed. The full suite did not finish: one worker and
    four workers were stopped by the wall clock before a summary.
- [x] **STEP 5: Code Cleanup**
  - `ai-tasks/WISHENKA-320/40-code-cleanup.md`: Ruff and Mypy are clean, and
    the name-contract modules passed (216). No behavior change. Description
    and event title still have no character ceiling.
- [x] **STEP 6: Observability**
  - `ai-tasks/WISHENKA-320/50-observability.md`: a refused create or edit
    is the existing completed-request INFO (`method`, `path`,
    `status_code`, `duration_ms`) after the `422` is returned and before
    the middleware returns the response. That line is not a commit. The
    name, description, and event title are absent. No production log line
    was added or removed. No metric system.
- [x] **STEP 7: Technical Debt Analysis**
  - `ai-tasks/WISHENKA-320/60-tech-debt.md`: no blockers. S-2, S-4, C-1,
    T-1, T-2, C-3, and WISHENKA-296 follow-up 1 are addressed for the name
    contract. Description and event title stay uncapped as a future product
    choice, not a broken acceptance criterion. One low follow-up, not filed:
    lock the Mini App edge-space set to Python `str.isspace()`. Every new or
    changed pytest module that collects tests already has a timeout marker.
    The full suite was not started. Pre-existing failures were not re-filed.
    `doc/` was not changed.
- [x] **STEP 8: Dev Docs**
  - `doc/dev/wishlists.md`: one name rule on `POST` and `PATCH`. Required, 1 to
    255 code points after the shared edge trim. Invisible-only is
    `wishlist_name_required`; a longer name is `wishlist_name_too_long`.
    Description and event title stay uncapped; blank means unset. A stored
    empty name stays readable. An omitted stored name already over 255 is the
    too-long failure. Opening a list does not rewrite the title. A refused
    create or edit is the existing completed-request INFO after `call_next`
    returns and before the middleware returns the response. That log is not a
    commit and does not include the name, description, or event title.
  - `doc/dev/miniapp.md`: create and settings submit `decision.name` with no
    second trim, so an edge U+FEFF beside a visible character stays in the
    body. Too-long `422` uses the too-long string.
  - `doc/dev/i18n.md`: the two title-error strings follow those two `422` types
    on create and on edit.
  - `doc/dev/testing.md`: name-contract API, settings UI, and settings browser
    modules, and the create modules' edge-mark case. The full suite was not
    started.
- [x] **COMMIT: Commit Changes**

## Status Legend

- `[ ]` — step not started
- `[/]` — step in progress
- `[x]` — step completed and accepted (acceptance gate passed)

See the `td-roadmap` skill for who writes which mark and when.

## Artifacts

### STEP 1: Requirements

- `ai-tasks/WISHENKA-320/10-requirements.md`

### STEP 2: Architecture

- `ai-tasks/WISHENKA-320/20-architecture.md`

### STEP 3: Failing Repro

- Automated red test(s) under `tests/` (or N/A note in roadmap)

### STEP 4: Development

- Source code
- Tests
- Documentation updates

### STEP 5: Code Cleanup

- `ai-tasks/WISHENKA-320/40-code-cleanup.md`

### STEP 6: Observability

- `ai-tasks/WISHENKA-320/50-observability.md`

### STEP 7: Technical Debt

- `ai-tasks/WISHENKA-320/60-tech-debt.md`

### STEP 8: Dev Docs

- `doc/dev/`

### COMMIT

- No artifact recorded here beyond the `[x]` mark above. Branch name and commit hash are reported
  in chat only, never written to this file.
