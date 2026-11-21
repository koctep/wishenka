# WISHENKA-114: Reliable and safe injected preview clients

## Goals

Keep product-link previews reliable across supported dependency updates, isolate user data,
and preserve security and the behavior of callers that provide their own network client.
The present integration depends on undocumented dependency behavior, so a routine upgrade can
break previews or invalidate the decision that an outbound route is safe.

Implementation language: Python, consistent with the existing application.

## User Stories

- As a wishlist owner, I want a product link to produce the same useful, editable preview after
  supported dependency upgrades, so that adding a wish continues to work without manual recovery.
- As a wishlist owner, I want simultaneous previews to remain independent, so that another
  request's cookies, credentials, headers, or response data cannot affect my preview.
- As an operator, I want every preview and redirect to keep existing destination protections,
  so that an injected client or an outbound proxy cannot bypass the application's safety rules.
- As an integrator, I want supported externally supplied clients and safe direct routes to keep
  their intended behavior and lifetime, so that previews do not close or alter resources I own.

## Definition of Done

1. Product preview continues to work for application-owned clients, standalone preview use, and
   supported caller-supplied clients. The existing metadata, editable preview, plain-text behavior,
   resource reuse, and manual fallback on failed or unsafe fetches are preserved.
2. The injected-client integration uses supported, documented dependency interfaces rather than
   relying on undocumented internal implementation details. Its supported integration contract
   and any explicit restrictions are documented for future dependency upgrades.
3. An explicitly configured safe direct route selected for a URL continues to be used. A route
   that would send requests through a proxy without the required destination safeguards is
   rejected before an unsafe outbound request, including after a redirect. An unverified route
   must not be presumed safe.
4. Existing scheme, destination, DNS and redirect checks, connection safeguards, timeouts and
   response-size limits remain effective on each outbound request. A cache hit cannot bypass
   the existing fresh destination safety decision.
5. Separate previews, including simultaneous requests and redirect chains, do not send or share
   cookies, authorization credentials, or caller-specific request data from another preview or
   from a supplied client's ambient state. The supplied client's own settings and state are not
   mutated by preview operations.
6. The application closes the resources it owns at normal shutdown and on failed startup or
   exceptional shutdown. An externally supplied client remains open and usable by its owner;
   completing or cancelling a preview does not close it. Resources for distinct application
   instances remain independently owned.
7. Automated regression checks cover supported dependency integration and upgrade-facing
   compatibility, safe direct-route selection, unsafe proxy and redirect rejection, concurrent
   isolation, and ownership on success and failure. Existing preview and security tests continue
   to pass, apart from independently documented pre-existing failures.

## Task Description

A wishlist owner's URL can be enriched from an external product page. The result is advisory and
editable; a failed lookup must leave the owner able to enter the wish manually. Existing preview
reuse reduces repeated network work, while destination validation protects the application and
its users from requests to unsafe locations.

The scope is the integration between preview requests and application-owned or externally
supplied network clients. It includes preserving safe routing, independent request state, resource
ownership, and verification across supported dependency versions. Changing the user-facing
preview workflow, product extraction rules, wish persistence, or cache policy is outside scope.

The main business entities are the wishlist owner, a submitted product link or plain text, the
external product page, an editable preview, the application operator, and an integrator who
supplies a client. A preview can follow redirects to obtain information, but every destination
remains subject to the same safety rules.

## Constraints and Assumptions

- Existing documented safety policies and application lifecycle behavior remain in force; this
  task does not authorize weaker validation for compatibility with a supplied client.
- Safe direct routing must remain usable. A route whose safety cannot be established is rejected
  rather than silently allowed; the architecture step defines how support is established.
- Request isolation applies even when several previews use the same supplied client concurrently.
  Connections may still be reused where reuse does not violate the safety and isolation rules.
- A caller owns a supplied client. The preview subsystem owns only resources it creates itself.
- Supported dependency versions and upgrade checks must be explicit; this task does not promise
  compatibility with every future version or every third-party transport.

## Q&A

- **Why change the integration?** The WISHENKA-53 debt analysis identifies dependence on
  undocumented client and proxy internals in a security-sensitive decision. An upgrade can break
  previews or undermine safe routing. See `ai-tasks/WISHENKA-53/60-tech-debt.md`.
- **May a proxy be used?** Only where the same required destination protections are demonstrably
  enforced. An unsafe or unverified route must not be used to fetch a preview.
- **Does the task eliminate all network risk?** It preserves the established safeguards; it does
  not expand scope to unrelated network or caching features.
- **What if a product page cannot be fetched safely?** Retain the existing fallback so the owner
  can add or correct the wish manually, without exposing private request data.
