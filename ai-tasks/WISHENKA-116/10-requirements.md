# WISHENKA-116: Bound JSON-LD Traversal Overhead

## Goals

A person adding a product link should receive a useful preview even when a merchant page has
wide, deeply nested, malformed, or deliberately expensive structured data. Limit avoidable
processing and temporary memory use so that one response cannot consume disproportionate
resources or impair other previews. Preserve the product information and priority users already
see for supported inputs.

## User Stories

- As a person adding a wish, I want supported product details to appear consistently, so the
  imported title, image, description, and price do not change merely because traversal is safer.
- As a person adding a link with problematic structured data, I want the preview to finish with
  available fallback information, so I can continue creating the wish.
- As a service operator, I want processing and temporary resource usage to remain bounded for
  adversarial pages within the existing response-size limit, so one page cannot monopolize
  preview capacity.
- As a maintainer, I want reproducible measurements and regression coverage, so the bounds and
  the preservation of extraction behavior remain verifiable after future changes.

## Definition of Done

1. Measure the current and revised processing of representative wide graphs and graphs with many
   product candidates and nested type values, all within the existing response-size limit.
   Record the input sizes, environment, commands, resource measures, results, and comparison.
2. Define and document explicit, testable bounds for traversal work and temporary traversal
   storage. The bounds must cover the width of an individual container as well as repeated type
   inspection across product candidates; a response-size cap alone is not the resource bound.
3. Automated regression checks demonstrate the bounds on adversarial wide and repeated-type
   inputs, including cases at and beyond relevant limits. Checks use deterministic work or storage
   measures where possible and avoid depending only on wall-clock timing.
4. Supported inputs retain the same product discovery order, selected product and extracted
   preview fields as before. Cover multiple candidates, nested arrays and objects, type forms,
   graph containers, multiple scripts, and first usable offer and fallback precedence.
5. Preserve existing node and depth limit behavior, earlier results when a limit is reached, and
   safe fallback for malformed, missing, or over-limit structured data. Changes to these
   externally visible outcomes require separate product approval.
6. Existing response-size enforcement and network safety remain effective; the work does not
   permit larger responses or remote context/reference retrieval.
7. Relevant existing preview and JSON-LD regressions pass, and new measurements and checks are
   documented sufficiently for another maintainer to reproduce them.

## Task Description

The preview consumes product information supplied in a linked page. Its structured data can
contain product candidates, nested type descriptions, and other page metadata. Product discovery
and type recognition have existing depth and visited-node limits, but a very wide container may
cause temporary allocation before a limit is applied, and many candidates may repeat bounded
inspection. A page within the permitted response size can therefore incur avoidable overhead.

The scope is the resource cost of discovering and recognizing products in page-supplied JSON-LD,
its measurement, and behavior-preserving verification. The existing preview is responsible for
using supported product data and falling back to other page metadata or manual entry when needed.
Changing supported marketplaces, response-size limits, unrelated decoding policies, network
security, executor scheduling, or the product data model is outside this task.

The implementation language is Python. Existing documented discovery and nested type limits are
20,000 visited nodes and depth 128. These are observable compatibility constraints for this
work, not a request to introduce a different product selection policy. Remote contexts and
`@id` references remain unresolved. Measurements must state any assumptions and distinguish
resource bounds from observations made on a particular machine.

## Q&A

- **Why limit this work?** Predictable preview resource use protects availability and lets users
  continue when a linked page is unusually complex or hostile. This reason is inferred from the
  task description and the existing [technical debt analysis](../WISHENKA-56/60-tech-debt.md).
- **Which details must remain stable?** The order in which existing supported product candidates
  are considered, selected preview fields, limits and fallbacks, including earlier results on
  limit exhaustion.
- **What counts as evidence of improvement?** Reproducible before-and-after measurements plus
  deterministic tests for the documented resource bounds; a fast run alone is insufficient.
- **Are user-facing limits or network policies being expanded?** No. Existing response-size and
  safety policies apply unchanged.
