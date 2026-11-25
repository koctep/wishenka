# WISHENKA-228: Public share and invite links cannot be probed past the request limit

## Goals

Wishlist owners rely on unguessable share links and collaborator invites. Those links stay
open without sign-in so a giver or an invitee can act immediately. The service already caps
how often one visitor may open a share link, open an invite, or accept an invite, and a
refusal does not say whether the secret is valid.

That cap can still be bypassed. A visitor can ask only whether a share or invite address
exists, without loading the page. Those existence checks reach the same links and can show
whether the secret is valid, but they do not spend the visitor's allowance. Guessing can
therefore continue past the limit that was introduced to stop it.

The same promise fails if the visitor is identified wrongly. This task also confirms two
identity cases: a trusted front proxy that names the visitor directly, and a request whose
visitor cannot be identified at all. Either case must still be limited.

Implementation language: Python.

## User Stories

- **Wishlist owner:** As a wishlist owner, I want every attempt to discover my share link or
  a collaborator invite, including a check that only asks whether the address exists, to
  count toward the same per-visitor limit, so guessing cannot slip past the protection.
- **Giver:** As a giver opening a share link in the usual way, I want ordinary visits to keep
  working inside the existing allowance. If I exceed it, I want a clear request to wait, and
  I do not want that refusal to reveal anything about other people's secrets.
- **Invited collaborator:** As someone using an invite, I want an existence check of that
  invite to be limited the same way as opening it. A normal open and a normal acceptance stay
  available while I am inside the allowance.
- **Operator:** As an operator who trusts the front proxy, I want the limit to follow the
  visitor the proxy names when it does not provide a forwarded chain, so people behind the
  proxy are limited individually rather than as the proxy itself.
- **Operator:** As an operator, I want requests whose visitor cannot be identified to remain
  limited, so a missing address is not an unlimited channel for probing secrets.

## Definition of Done

1. An existence check for a public share link and for an invite link consumes the same
   per-visitor allowance as opening that link. The allowance is the one already shared by
   share views, invite views, and invite acceptance.
2. Existence checks are counted before the service answers whether the secret is valid.
   Checks for unknown or invalid secrets count the same as checks for valid ones.
3. Once the allowance is used up, a further existence check is refused the same way as a
   further page open. The visitor is told to wait, and the refusal does not reveal whether
   the secret exists, is active, or has expired.
4. Ordinary use inside the allowance still succeeds. Opening a valid share link, opening a
   valid invite, and accepting an invite are not blocked merely because existence checks are
   now counted.
5. When the operator trusts the front proxy, and the proxy attests a visitor address without
   a forwarded chain, that attested visitor is who the limit charges. Distinct attested
   visitors have distinct allowances. The proxy's own connection is not the identity.
6. When no visitor address can be determined, the request is still limited. Such requests
   share one allowance, so each unidentifiable request does not become a new visitor.
7. Automated checks cover existence checks on share and invite links, including past the
   allowance and for a secret that does not exist; the trusted-proxy case where only the
   direct visitor address is attested; and requests with no determinable visitor address.
   Existing limit behavior remains in force for normal opens, invite acceptance, untrusted
   caller-supplied addresses, and recovery after the waiting period.

## Task Description

### Problem

Public share links (`/share/{token}`) and collaborator invites (`/invite/{token}`, including
acceptance) are reachable without prior sign-in. [WISHENKA-88](../WISHENKA-88/10-requirements.md)
limits how often one visitor may use those entry points so guessing and flooding are slowed
without adding a sign-in step. The follow-up comes from the technical-debt note on that work
(`ai-tasks/WISHENKA-88/60-tech-debt.md`).

The limit applies to opening a share link, opening an invite, and accepting an invite. It
does not apply when the visitor only checks whether the share or invite address exists. That
check is a HEAD request to `/share/{token}` or `/invite/{token}`. It can still distinguish a
valid secret from an unknown one, and it does not consume the allowance. Probing by existence
check therefore bypasses the protection.

Two identity cases belong to the same promise and are not confirmed today:

- **Trusted proxy, visitor named directly.** If the deployment trusts its front proxy and
  the proxy supplies the visitor's address without a forwarded chain, the limit must follow
  that visitor. Charging the proxy connection instead would make every visitor behind the
  proxy share one allowance.
- **Unknown visitor.** If the service cannot see who connected, the request must still
  consume an allowance. Otherwise that traffic is unlimited.

### Functional requirements

- A HEAD existence check of `/share/{token}` and of `/invite/{token}` is in scope of the
  public-link request limit on the same terms as opening those links with a normal retrieval.
- Accepting an invite stays in scope exactly as it is today. This task does not add a new
  acceptance rule and does not treat an existence check of acceptance as a new entry point.
- Counting does not depend on whether the secret is valid.
- A refusal stays uninformative. It does not disclose existence, activity, or expiry, and it
  tells the visitor to wait. The visitor recovers when the existing waiting period ends.
- Visitor identity stays as it is for ordinary requests, and the two edge cases are required
  behavior:
  - By default the visitor is the party on the connection the service sees. Addresses
    supplied by the caller are ignored.
  - When proxy trust is on, a forwarded chain still identifies the visitor as it does today.
  - When proxy trust is on and there is no forwarded chain, the visitor address the proxy
    attests directly is the identity used for the allowance.
  - When no address can be determined, one shared unknown-visitor allowance applies.

### Non-functional requirements

- **Security:** Closing the existence-check bypass must not weaken the existing limit, must
  not disclose secret-link state in a refusal, and must not start trusting caller-supplied
  addresses unless proxy trust is already enabled.
- **Fairness:** Separately identified visitors keep separate allowances, including when a
  trusted proxy names them directly.
- **Legitimate use:** Counting existence checks must not add a sign-in step or a challenge.
  Opens and invite acceptance inside the allowance stay available.
- **Confirmability:** Automated checks lock the three gaps so a later change cannot silently
  reopen an unlimited probe or a mis-attributed visitor.

### Constraints and assumptions

- Implementation language is Python, consistent with the application.
- The allowance size, the time window, and the choice to trust the front proxy remain the
  existing operator settings. This task does not retune them.
- Existence checks share the current per-visitor allowance with page opens and invite
  acceptance. They do not receive a separate budget.
- An existence check that is still inside the allowance may show the same validity outcome
  as opening the link. The protection is that probes are counted and refusals stay
  uninformative, which is already the rule for page opens.
- "No determinable visitor address" means the service has no connection peer to attribute.
  Those requests share one allowance rather than each counting as a fresh visitor.

### Out of scope

- Public wishlist reads other than the share page, the invite page, and invite acceptance.
- Changing how the wait message is presented for in-app partial updates.
- Reinterpreting a forwarded address chain when a proxy appends addresses.
- Sharing one allowance across multiple server processes.
- Paths that are not the share link, the invite link, or invite acceptance, including a
  trailing slash or extra path segments.
- Changing how share and invite secrets are generated.

### Main entities

- **Share link:** Unauthenticated entry a giver uses to open a wishlist.
- **Invite link:** Unauthenticated entry a prospective collaborator uses to preview an
  invite. Accepting the invite remains a separate action on that invite.
- **Existence check:** A HEAD request that asks whether a share or invite address exists
  without loading the page. For the limit, it is the same kind of access as opening that
  link.
- **Visitor:** The party the allowance is charged to. Identified by the direct connection,
  by a trusted proxy's attestation, or as unknown when no address exists.
- **Request allowance:** The existing cap on how many public-link requests one visitor may
  make in the configured interval, and the wait imposed after it is exceeded.

## Q&A

- **Why must existence checks be limited?** They answer the question a guesser cares about —
  whether a secret link is valid — and today they do so without spending the allowance from
  WISHENKA-88. The business outcome is that probing a share or invite link is limited no
  matter which of these two ways the visitor asks.
- **Why not require sign-in on these links?** Instant access without registration is a
  product invariant. The limit has to hold for every way of asking about the link.
- **Why include the proxy and unknown-visitor cases?** A limit that can be avoided by how
  the visitor is named does not protect the secret. These are the identity gaps bundled with
  the existence-check bypass. Other proxy-chain and public-read gaps are separate work.
- **Do allowed existence checks hide whether a link is valid?** No. Inside the allowance, an
  existence check may show the same validity outcome as opening the link. After the
  allowance is spent, the refusal must not show that outcome.
