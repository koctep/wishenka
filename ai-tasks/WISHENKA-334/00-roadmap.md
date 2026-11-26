# Roadmap: WISHENKA-334

## Task Metadata

- **Implementation language**: Python

## Step Status

- [x] **STEP 1: Requirements Gathering and Documentation**
  - `ai-tasks/WISHENKA-334/10-requirements.md`
  - Rolling the person-key change backward must restore each person's earlier
    identity and the earlier shape of invite tokens and support tickets. The
    forward change already has a check. The backward step does not.
- [x] **STEP 2: High-Level Architecture Design**
  - `ai-tasks/WISHENKA-334/20-architecture.md`
  - Check `unify_user_keys_and_cascades.downgrade` from the existing
    WISHENKA-188 repro file. No new migration unless that function fails
    to restore `users.id`, invite-token columns, and the support-ticket owner.
- [x] **STEP 3: Failing Repro Test**
  - `tests/test_wishenka_188_user_key_unification_repro.py` — `test_downgrade_from_unify_user_keys_restores_earlier_identity`
  - Upgrades only to `unify_user_keys_and_cascades`, then downgrades to `add_receipt_delivery_fence`. Asserts remembered links on `users.id`, invite tokens without `wishlist_id`, and support ticket `owner_id`.
- [x] **STEP 4: Development**
  - [x] Deliverable is the passing downgrade test; the migration is unchanged.
- [x] **STEP 5: Code Cleanup**
  - `ai-tasks/WISHENKA-334/40-code-cleanup.md`
  - Scope: `tests/test_wishenka_188_user_key_unification_repro.py`,
    especially `test_downgrade_from_unify_user_keys_restores_earlier_identity`.
- [x] **STEP 6: Observability**
  - `ai-tasks/WISHENKA-334/50-observability.md`
  - No new log or metric. A failed downgrade still surfaces as the existing migration error. The migration and its logs are unchanged.
- [x] **STEP 7: Technical Debt Analysis**
  - `ai-tasks/WISHENKA-334/60-tech-debt.md`
  - No new follow-up. `pytestmark = pytest.mark.timeout(30)` covers the
    downgrade test. User docs under `doc/` stay unchanged: the change is a
    test of an existing migration.
- [x] **STEP 8: Dev Docs**
  - `doc/dev/migrations.md` — Testing table records `test_downgrade_from_unify_user_keys_restores_earlier_identity` in `tests/test_wishenka_188_user_key_unification_repro.py`. The rollback-policy row already described the reversible downgrade; no new doc. Production code is unchanged.
- [x] **COMMIT: Commit Changes**

## Status Legend

- `[ ]` — step not started
- `[/]` — step in progress
- `[x]` — step completed and accepted (acceptance gate passed)

See the `td-roadmap` skill for who writes which mark and when.

## Artifacts

### STEP 1: Requirements

- `ai-tasks/WISHENKA-334/10-requirements.md`

### STEP 2: Architecture

- `ai-tasks/WISHENKA-334/20-architecture.md`

### STEP 3: Failing Repro

- Automated red test(s) under `tests/` (or N/A note in roadmap)

### STEP 4: Development

- Source code
- Tests
- Documentation updates

### STEP 5: Code Cleanup

- `ai-tasks/WISHENKA-334/40-code-cleanup.md`

### STEP 6: Observability

- `ai-tasks/WISHENKA-334/50-observability.md`

### STEP 7: Technical Debt

- `ai-tasks/WISHENKA-334/60-tech-debt.md`

### STEP 8: Dev Docs

- `doc/dev/`

### COMMIT

- No artifact recorded here beyond the `[x]` mark above. Branch name and commit hash are reported
  in chat only, never written to this file.
