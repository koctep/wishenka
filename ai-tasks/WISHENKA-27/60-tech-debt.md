# WISHENKA-27: Technical Debt Analysis

## Shortcuts Taken

- The entry router sends fixed `home`, `create`, and `collection` intents to the Mini App.
  Creation is an explicit action in the existing home view; entering the intent does not create
  data. This follows the approved design and is not a temporary write-on-entry shortcut.
- Reverse proxies are outside the application's logging configuration and must separately redact
  capability paths and query strings, as recorded in `50-observability.md`.

## Code Quality Issues

- The legacy `/share/{public_token}` route passes an anonymous caller to
  `get_wishlist_by_public_token` in `wishenka/web/routes/sharing.py`. The resulting giver
  projection reaches `wishenka/web/templates/partials/item_card.html`, which renders available
  quantity or a reserved label. An unidentified recipient with the same capability can therefore
  infer reservation state. This path predates WISHENKA-27; the new Mini App `/view` route uses a
  recipient-safe anonymous projection. Consolidating these projections and testing anonymous and
  recipient views is already covered by open Jira debt WISHENKA-63.

## Missing Tests

- The fake Telegram transport checks localized button labels and distinct targets; browser tests
  exercise public links, reservations, recovery, and invitation confirmation. There is no browser
  acceptance test that follows the bot's `create`, `collection`, and `home` button URLs into the
  Mini App and checks the named destination and absence of implicit writes. Add this boundary test
  to protect against launch URL and dispatcher contracts drifting apart.
- The latest full suite reported 877 passing tests; no pre-existing failures were reported. Test
  timeout markers were audited in Step 5, with explicit markers for all 873 then-collected tests;
  Step 6 added tests to marked modules.

## Performance Concerns

- No measured performance regression or new throughput target was identified for this task. The
  separate polling receiver must run as a single consumer per bot token as documented in the design.

## Follow-up Tasks

1. **NON-BLOCKER — pre-existing, High:** Protect anonymous `/share/{public_token}` HTML from
   exposing reservation state to an unidentified recipient; compare output before and after a
   reservation and verify identified giver and recipient views. Existing scope covers safe public
   projections and anonymous/recipient tests. The suggested High priority reflects the surprise
   invariant; the existing Jira issue is currently Medium.
   Jira: [WISHENKA-63](https://pypost.atlassian.net/browse/WISHENKA-63).
2. **NON-BLOCKER, Medium:** Add end-to-end checks that feed the bot's three Mini App navigation
   URLs to a seeded browser session, verify their intended destinations, and ensure navigation alone
   never creates a wishlist. Include both supported menu languages and invalid launch recovery.
   Jira: [WISHENKA-177](https://pypost.atlassian.net/browse/WISHENKA-177).

The independent blocker review must determine whether any remaining issue violates the acceptance
criteria. No additional implementation blocker is asserted by this debt analysis.
