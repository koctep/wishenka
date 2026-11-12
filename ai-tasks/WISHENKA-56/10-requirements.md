# WISHENKA-56: Reliable Preview Text and Nested Product Metadata

## Goals

Help a wishlist owner add a product by link with readable, accurate suggested details even when
the source uses an older text encoding or places product data in nested structured metadata.
Reliable suggestions reduce manual correction while retaining the ability to enter details by
hand when a source cannot be interpreted.

## User Stories

- As a wishlist owner, I want product names and descriptions in Cyrillic to remain readable when
  I add a link to a page using a supported legacy encoding.
- As a wishlist owner, I want available product information to be suggested when a catalogue
  places it inside a deeply nested structured graph.
- As a wishlist owner, I want to review and change suggested fields or enter them manually if the
  source does not supply reliable information.

## Definition of Done

1. Automated, network-independent examples verify readable Cyrillic preview fields from pages
   encoded in Windows-1251 (including its CP1251 alias) and KOI8-R. Examples cover declarations
   in response headers, page metadata, absent declarations, and disagreement between declarations
   where the correct interpretation can be established from the test input.
2. Conflicting, missing, unknown, or malformed encoding declarations are handled deterministically
   without an unhandled error. The chosen behavior and its limitations are documented; no universal
   ability to infer the intended encoding from arbitrary ambiguous bytes is assumed.
3. Automated examples representative of e-commerce catalogues verify extraction from nested and
   multi-level Schema.org JSON-LD `@graph` structures, including product details and available
   offer data. Irrelevant nodes and malformed structured data do not prevent graceful handling.
4. Existing supported metadata sources, field precedence, manual correction and fallback behavior
   continue to work. Missing or unusable information does not prevent manual entry.
5. Existing protections and limits on fetching and processing external pages remain effective,
   including safe destination checks, response size limits, and bounded handling of invalid or
   deeply nested input. Tests do not require access to live external catalogues.

## Task Description

The current preview flow enriches a wish from a product link, but older page encodings can yield
unreadable text, particularly when a response header and page declaration disagree. Catalogue
metadata may also place products and offers in nested graphs. The task covers the interpretation
of supported page text and confidence in extracting such structured product details; it does not
change wishlist ownership, purchase or reservation rules, or introduce new preview fields.

The implementation language is Python 3.12+. A **wish** is a user's desired item with editable
details. A **source page** supplies optional metadata. A **preview** is a suggested title, image,
price, currency, description, store, or link that the user can inspect and correct. A **product**
and its **offer** are source-page descriptions from which available suggestions can be derived.

## Q&A

- **Why is this needed?** Accurate product suggestions make link-based wish creation quicker and
  avoid forcing users to repair garbled text or fill in details available on the source page.
- **What happens when signals conflict?** Use a deterministic, documented interpretation policy;
  ambiguous bytes alone cannot guarantee the source author's intent. Preserve a usable fallback
  when trustworthy content is unavailable.
- **Does this require live catalogue access?** No. Representative local examples can establish
  expected behavior without depending on a third-party site.
