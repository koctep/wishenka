# WISHENKA-93: Configurable Link-Preview Network Safety and Size Policy

## Goals

Wishenka allows wishlist owners and collaborators to add wishes from product links in the
Telegram Mini App and Telegram Bot, automatically retrieving page metadata for a preview while
protecting internal infrastructure (SSRF prevention) and server memory (response-size limits).

Today, the outbound link-preview payload size limit, permitted URL schemes, and blocked IP
network ranges are fixed defaults rather than configurable per deployment. Adjusting any of
these boundaries for staging, automated CI verification, or hardened production environments
requires editing and redeploying application source code.

The business and operational goal is to let platform operators configure these three link-preview
safety parameters via deployment configuration (including environment variable overrides) without
code changes, while preserving fail-closed defaults out of the box and keeping all existing SSRF
and user fallback guarantees intact.

## User Stories

- As a platform operator, I want to configure the maximum link-preview response size, permitted
  URL schemes, and blocked IP network ranges via deployment settings and environment overrides, so
  I can adapt security and resource policies across development, staging, CI, and production
  without modifying source code.
- As a platform operator, I want invalid or malformed safety configuration values to fail fast
  during startup/configuration loading, so a misconfigured deployment never starts with silently
  disabled or weakened link-preview protections.
- As a security engineer, I want unconfigured deployments to keep the existing hardened defaults
  and baseline protections against private, loopback, link-local, cloud-metadata, and non-public
  addresses, embedded credentials, and unsafe redirects, so configurability never creates an
  insecure default posture.
- As a security engineer, I want every link-preview flow (web requests, bot link capture,
  redirect hops, and cached preview revalidation) to enforce the active configured policy
  consistently, so no alternate entrypoint or cached entry can bypass configured restrictions.
- As a wishlist owner or collaborator adding a wish by URL, I want normal merchant link previews
  to behave identically under default settings, and blocked or oversized links to degrade safely
  to manual wish entry without crashes or technical errors.

## Definition of Done

1. **Deployment-Configurable Policy Parameters**:
   - Operators can override each of the three link-preview policy parameters independently via
     deployment configuration and environment variables:
     1. Maximum allowed response body size in bytes.
     2. Permitted outbound URL schemes.
     3. Blocked IPv4 and IPv6 network ranges in CIDR notation.
   - Overriding one parameter leaves the defaults for the other parameters intact.
2. **Backward-Compatible Fail-Closed Defaults**:
   - When no overrides are supplied, the service enforces the existing default policy:
     - Maximum response body size: 2 MiB (2,097,152 bytes).
     - Permitted URL schemes: `http` and `https`.
     - Blocked network ranges: all currently restricted IPv4 ranges (`0.0.0.0/8`, `10.0.0.0/8`,
       `100.64.0.0/10`, `127.0.0.0/8`, `169.254.0.0/16`, `172.16.0.0/12`, `192.0.0.0/24`,
       `192.0.2.0/24`, `192.168.0.0/16`, `198.18.0.0/15`, `198.51.100.0/24`, `203.0.113.0/24`,
       `224.0.0.0/4`, `240.0.0.0/4`, `255.255.255.255/32`) and IPv6 ranges (`::/128`, `::1/128`,
       `fc00::/7`, `fe80::/10`, `ff00::/8`).
3. **Strict Startup Validation (Fail-Fast)**:
   - Response size overrides must be strictly positive whole-number byte counts; zero, negative,
     non-numeric, or blank values are rejected explicitly at configuration load rather than
     disabling size bounds.
   - Permitted URL scheme overrides must form a non-empty subset of supported web transport
     schemes (`http` and `https`), matched case-insensitively; empty sets, blank entries, or
     unsupported/unsafe schemes (such as `file`, `ftp`, `javascript`, or `data`) are rejected at
     configuration load.
   - Blocked network range overrides must contain valid IPv4 or IPv6 CIDR entries; malformed or
     blank entries are rejected explicitly at configuration load rather than silently ignored.
4. **Consistent End-to-End Policy Enforcement**:
   - The active configured limits and rules govern all link-preview entrypoints, including web /
     Mini App preview requests, Telegram Bot link capture, and revalidation of cached previews.
   - Configured payload limits govern both early header-based size rejection and streaming byte
     counting during response download.
   - Configured permitted schemes and blocked CIDR ranges govern initial URLs, direct IP literals,
     DNS-resolved addresses, and every hop in HTTP redirect chains.
   - Cached hostname resolutions and cached link previews do not allow a destination that violates
     the active configured policy to bypass validation.
5. **Preserved SSRF and Product Security Invariants**:
   - Regardless of configuration overrides, baseline SSRF defenses remain active: non-global,
     private, loopback, link-local, cloud-metadata, multicast, reserved, and unspecified
     addresses (including IPv4-mapped IPv6 forms), non-IP-network local sockets, and embedded
     URL credentials remain blocked, and connections continue to bind only to validated
     destination addresses.
   - Policy blocks and oversized responses continue to fall back gracefully to manual wish entry
     and preserve recipient surprise and wishlist privacy invariants.
6. **Verification**:
   - Automated checks verify out-of-the-box defaults, independent environment overrides for size
     limits, URL schemes, and blocked CIDR ranges, fail-fast rejection of invalid configuration
     values, and consistent enforcement across fetch, redirect, and preview flows without
     regressions in existing SSRF protections.

## Task Description

### Problem and Business Context

When a user submits a link to create a wish, Wishenka fetches the remote document to extract
product title, image, description, and price metadata. To prevent Server-Side Request Forgery
(SSRF) and memory-exhaustion attacks, the service restricts permitted URL schemes, blocks internal
and special-use IP ranges, and caps downloaded payload sizes. Because those limits are currently
static application constants, operators cannot adjust them per deployment environment without
editing source code.

The implementation language is Python.

### Functional Scope

- **In Scope**:
  - Externalizing the link-preview maximum response size, permitted URL schemes, and blocked
    IPv4/IPv6 CIDR ranges into deployment configuration with environment variable override support.
  - Preserving exact existing defaults when no overrides are provided.
  - Validating overrides fail-fast and fail-closed when configuration is loaded.
  - Propagating the active policy consistently across all outbound link-preview requests,
    redirects, streaming size checks, and cached-preview validations.
- **Out of Scope**:
  - Runtime UI, user preferences, or admin/bot commands to change SSRF rules dynamically without
    deployment reconfiguration/restart.
  - Configuring DNS cache lifetimes or capacities, or changing pinned-connection mechanics.
  - Modifying HTML/structured-data extraction rules, supported marketplaces, or preview schemas.
  - Allowing deployments to bypass baseline SSRF protections to reach local or private addresses.

### Non-Functional Requirements

- **Security (Fail-Closed)**: Default deployments preserve the current hardened boundary; invalid
  overrides fail startup/load immediately; baseline SSRF invariants remain non-bypassable.
- **Backward Compatibility**: Existing deployments with no new configuration continue operating
  with unchanged limits, schemes, blocked ranges, and user-facing fallback behavior.
- **Reliability**: Blocked destinations or oversized pages never cause unhandled server errors.
- **Auditability**: Policy rejections (disallowed scheme, blocked IP/CIDR, or response size
  exceeded) continue to record structured security/operational events without leaking secrets.

### Main Domain Entities

1. **Link-Preview Network Safety Policy**: Active deployment parameters defining maximum payload
   bytes, allowed URL schemes, and blocked IPv4/IPv6 CIDR ranges.
2. **External Link Preview Request**: Service-initiated fetch for a user-supplied wish URL and
   any subsequent HTTP redirect destinations.
3. **Safe Fallback Preview**: Degraded wish-creation outcome allowing manual entry when a fetch
   is blocked or exceeds the configured payload size limit.

### Constraints and Assumptions

- Policy settings are deployment-level operational configuration applied when the application or
  worker configuration is loaded; live hot-reloading without restart is not required.
- Link previews support web HTTP/HTTPS content only; non-HTTP protocols remain unsupported.
- Operators supplying blocked network ranges provide valid IPv4 or IPv6 CIDR notation.

## Q&A

- **Why make these SSRF and size limits configurable if the defaults already work?**
  - This resolves follow-up debt from the
    [WISHENKA-54 technical debt analysis](../WISHENKA-54/60-tech-debt.md). Operators need
    environment-specific control across development, staging, CI, and production (for example,
    restricting production previews to `https` only, tightening or tuning the response-size
    budget, or blocking custom internal/partner CIDR ranges) without modifying code.
- **Do unconfigured deployments change behavior?**
  - No. Default behavior remains identical: 2 MiB (2,097,152 bytes) response-size limit, `http`
    and `https` schemes allowed, and the full existing IPv4/IPv6 blocked-network list enforced.
- **What happens if an operator configures an invalid value (such as `0` bytes, an empty scheme
  list, `file`, or a malformed CIDR)?**
  - Configuration loading fails fast and explicitly with a validation error so the service cannot
    start in an exposed or ambiguous state.
- **Can configuration overrides disable baseline SSRF protections to permit `localhost` or
  private subnets?**
  - No. Configurability supports operational policy tuning while keeping baseline non-global,
    loopback, private, link-local, cloud-metadata, credential-stripping, and redirect-chain SSRF
    invariants active.
- **Are DNS cache tuning settings or live admin controls included in this task?**
  - No. DNS cache sizing and expiration belong to separate work, and SSRF safety rules are
    deployment-level configuration rather than runtime user or admin controls.
