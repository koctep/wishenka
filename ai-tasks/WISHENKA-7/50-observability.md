# WISHENKA-7: Observability Implementation

## Logging

- `wishenka.web.wishlists` emits `wishlist_mutation_committed` at INFO after a successful
  transaction for creation, updates, lifecycle changes, and sharing-link resets. The
  structured `operation` field distinguishes these paths. Rejected mutations emit no
  committed event.
- `wishenka.web` already records request method, redacted path, status, and duration at
  INFO, and unhandled failures with a traceback at ERROR. Public link paths are replaced
  with a template. The Uvicorn access filter also redacts public links.
- Existing `wishenka.wishlists` domain logs report lifecycle and authorization events.
  These domain events can precede a commit; use the new committed event for counts.
- The new event contains no request body, user information, link token, or domain object.
  JSON output includes event and operation fields when `log_json` is enabled.
- Storage errors are translated at the storage boundary without retaining the original
  SQLAlchemy exception as context; engine parameter display is disabled as defense in depth.
  This prevents middleware from re-chaining token-bearing SQL parameters into error logs.

## Metrics and Monitoring

Existing request duration and status logs support latency, throughput, and error-rate
aggregation. The committed events support mutation counts grouped by operation. There is no
metrics exporter, dashboard, alert configuration, or monitoring integration in this change;
log aggregation remains a deployment concern. No resource usage metrics were introduced.

## Validation

- Automated API coverage checks committed events for create and reset, verifies a denied
  reset emits no committed event, and checks application logs for old and new link tokens.
- Existing tests cover Uvicorn path redaction and sanitized collision-exhaustion errors.
- A forced database error with a token in both parameters and its original exception is
  checked against the HTTP middleware's formatted traceback.
- Full test and static-analysis results are recorded in the execution report.

The test HTTP client logs its outgoing URL independently; it is not the production server's
access log. Clients and reverse proxies must avoid logging capability URLs in their own logs.
