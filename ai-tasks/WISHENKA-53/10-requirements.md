# WISHENKA-53: Efficient repeated link previews

## Goals

Reduce unnecessary external requests and connection setup when a wishlist owner repeatedly
previews a product link. This should make adding a wish more responsive and reduce traffic to
external stores while retaining the safe, editable preview experience.

Implementation language: Python 3.12+, matching the existing application.

## User Stories

- As a wishlist owner, I want a repeated product link preview to return the same useful product
  information promptly, so that revisiting or editing a wish does not repeat avoidable work.
- As a wishlist owner, I want an unavailable or unsupported product page to leave me able to
  enter or correct the wish manually.
- As an operator, I want repeated lookups to reuse appropriate resources and avoid needless
  external requests, without weakening protection against unsafe destinations.

## Definition of Done

1. A successful URL preview can be reused for a subsequent identical effective product URL
   within a bounded freshness period without another external fetch. Separate submissions and
   users can benefit when the source data is safe to share.
2. Different effective URLs are not confused. Input-specific fields and caller edits are not
   leaked or overwritten by data from an earlier request. Plain text retains its existing
   behavior and does not trigger external fetching.
3. Reused preview information expires after a finite period; the next request retrieves fresh
   data. Stored preview information and connection resources have finite limits and are released
   when no longer needed or when the application stops.
4. Repeated uncached external requests can reuse eligible connections during the application's
   lifetime, instead of creating an independent connection resource for every request.
5. Existing scheme, destination and redirect safety checks, response size and timeout limits,
   and failure handling remain effective. Reuse must not allow unsafe or stale destination
   information to bypass those protections. Requests do not share external cookies, credentials,
   or private user-specific responses between users.
6. An unavailable, blocked, oversized, timed-out or otherwise failed lookup retains the existing
   manual-entry fallback; a transient failure is not reused as a successful product preview and
   can recover on a later attempt.
7. Automated checks demonstrate reuse, expiry and capacity behavior, different URLs, resource
   lifecycle, unchanged fallbacks and safety, and isolation of caller-specific data. Existing
   preview behavior remains covered by the project's quality checks.

## Task Description

The preview flow automatically enriches a wish with product information where available, and
otherwise presents a manual form. Existing task records identify repeated previews and
short-lived outbound resources as causes of avoidable network round trips and connection setup.
The scope is the existing application preview flow and its outbound product-page lookups;
changing wish persistence, presentation, product extraction rules, or introducing a distributed
cache service is not required by the business goal.

Business entities are the wishlist owner, the submitted product URL or plain text, the external
product page, and the preview containing fields such as title, image, price, store and link.
Preview information may become stale as a store changes its page; it is advisory and remains
editable by the owner. Reuse does not make a preview a saved wish.

## Q&A

- **Why reduce repeated fetches?** Repeated UI previews and submissions currently repeat network
  round trips and connection setup, increasing latency and external traffic. See the WISHENKA-11
  and WISHENKA-14 technical debt records.
- **What is identical?** The same effective URL after the existing normalization rules, including
  any remaining query distinctions. No broader equivalence between products is assumed.
- **What freshness and capacity limits apply?** The task specifies bounded reuse but no numeric
  values. The design must select and document practical defaults and verify expiration and bounds.
- **Are failed results reused?** No. Retrying a failed lookup must allow recovery rather than
  prolonging a temporary outage or an unsafe decision.
- **Are caches shared across application processes or restarts?** This is not a business
  requirement. A bounded per-application lifetime is sufficient; availability does not depend on
  cross-process sharing.
- **Does reuse relax URL safety?** No. In particular, name resolution and redirects must not be
  reused in a way that permits a forbidden destination or bypasses existing validation.
