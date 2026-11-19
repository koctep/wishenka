# Roadmap: WISHENKA-92

## Task Metadata

- **Implementation language**: Python 3.12+

## Step Status

- [x] **STEP 1: Requirements Gathering and Documentation**
  - `ai-tasks/WISHENKA-92/10-requirements.md`
- [x] **STEP 2: High-Level Architecture Design**
  - `ai-tasks/WISHENKA-92/20-architecture.md`
- [x] **STEP 3: Failing Repro Test**
  - `tests/test_ssrf_dns_rebinding.py`
- [x] **STEP 4: Development**
  - [x] Implemented `_pinned_ips_var` (`ContextVar`), `SSRFSafeNetworkBackend(httpcore.AsyncNetworkBackend)` (with multi-IP failover, defense-in-depth fallback resolution, and UDS blocking), and updated `SSRFSafeTransport` in `wishenka/items/ssrf.py` to pin validated IPs per request/redirect hop without rewriting `request.url`.
  - [x] Added tests for IPv6 pinning (domain and literal), multi-IP failover, concurrent `ContextVar` task isolation, defense-in-depth resolution, and UDS blocking in `tests/test_ssrf_dns_rebinding.py`; verified `make analyze` and SSRF/item test suites pass.
- [x] **STEP 5: Code Cleanup**
  - `ai-tasks/WISHENKA-92/40-code-cleanup.md`
- [x] **STEP 6: Observability**
  - `ai-tasks/WISHENKA-92/50-observability.md`
- [x] **STEP 7: Technical Debt Analysis**
  - `ai-tasks/WISHENKA-92/60-tech-debt.md`
- [x] **STEP 8: Dev Docs**
  - `doc/dev/items.md`
- [x] **COMMIT: Commit Changes**

## Status Legend

- `[ ]` — step not started
- `[/]` — step in progress
- `[x]` — step completed and accepted (acceptance gate passed)

See the `td-roadmap` skill for who writes which mark and when.

## Artifacts

### STEP 1: Requirements

- `ai-tasks/WISHENKA-92/10-requirements.md`

### STEP 2: Architecture

- `ai-tasks/WISHENKA-92/20-architecture.md`

### STEP 3: Failing Repro

- Automated red test(s) under `tests/` (or N/A note in roadmap)

### STEP 4: Development

- Source code
- Tests
- Documentation updates

### STEP 5: Code Cleanup

- `ai-tasks/WISHENKA-92/40-code-cleanup.md`

### STEP 6: Observability

- `ai-tasks/WISHENKA-92/50-observability.md`

### STEP 7: Technical Debt

- `ai-tasks/WISHENKA-92/60-tech-debt.md`

### STEP 8: Dev Docs

- `doc/dev/`

### COMMIT

- No artifact recorded here beyond the `[x]` mark above. Branch name and commit hash are reported
  in chat only, never written to this file.
