# WISHENKA-98: Expand International Currency Recognition and Foreign E-Commerce Price Extraction

## Goals

Wishlist users frequently add gift links from cross-border and regional online stores (Chinese,
European, British, Japanese, Turkish, Georgian, and Armenian retail platforms) in addition to
domestic marketplaces. When a user pastes a product URL, the wishlist service automatically
previews the item's title, image, price, and currency so that both wishlist owners and gift givers
have accurate budget expectations without tedious manual data entry.

Previously, automated product metadata extraction and verification focused primarily on domestic
and major reserve currencies (`RUB`, `USD`, `EUR`, `KZT`, `BYN`) and standard numeric formats.
Regional and international e-commerce sites commonly display prices using additional currency codes
and symbols (`CNY`, `GBP`, `JPY`, `TRY`, `GEL`, `AMD`), localized number formatting (such as
European dot thousand separators with comma decimals or multi-group thousand separators), and
nested or range-based structured pricing offers. If these formats are misinterpreted or ignored,
the wish card either loses price/currency information or displays an inaccurate value (for
instance, misreading `1.299,99` or `12,800` by orders of magnitude).

The business goals of **WISHENKA-98** are:

1. **Accurate cross-border price and currency auto-fill**:
   - Recognize and normalize target international currencies (`CNY`, `GBP`, `JPY`, `TRY`, `GEL`,
     `AMD`) from their ISO codes, currency symbols, and common localized abbreviations alongside
     existing supported currencies.
2. **Error-free interpretation of localized price numbers**:
   - Accurately determine the numeric value of prices formatted with European, Anglo-Saxon, and
     spaced thousand/decimal separators so gift givers see the true product cost.
3. **Reliable extraction from complex merchant offer structures**:
   - Extract valid product prices and currencies when foreign online stores publish multi-offer,
     nested, or price-range product metadata on their pages.
4. **Comprehensive automated regression protection**:
   - Establish thorough automated verification covering international currencies, localized number
     separators, complex offer structures, and foreign e-commerce product page scenarios.

## User Stories

- **US-1 (Wishlist Owner / Co-author adding international store links)**:
  As a wishlist author adding a gift link from an international or regional online store (pricing
  in `CNY`, `GBP`, `JPY`, `TRY`, `GEL`, or `AMD`), I want the preview card to automatically
  populate the correct numeric price and standardized 3-letter currency code so I do not have to
  enter or correct the price and currency manually.
- **US-2 (Gift Giver reviewing wish cost)**:
  As a gift giver browsing a wishlist, I want prices imported from European, Asian, or regional
  stores with localized thousand and decimal separators (such as `1.299,99 €`, `¥ 12,800`, or
  `1 450,50 ₺`) to be parsed to their exact numeric amounts without order-of-magnitude distortion,
  so I can accurately assess the gift budget.
- **US-3 (Wishlist Owner adding multi-variant products)**:
  As a wishlist author pasting a link to a product page that lists multiple variations, price
  ranges, or nested pricing specifications in its structured page metadata, I want the service to
  extract a valid representative price and currency rather than leaving the price blank.
- **US-4 (Platform Maintainer / QA Engineer)**:
  As a platform maintainer, I want an automated verification suite covering international currency
  symbols/codes, localized number formats, and foreign e-commerce metadata structures so future
  changes to product preview extraction cannot regress international store support.

## Definition of Done

1. **International Currency Normalization**:
   - Product preview extraction recognizes and normalizes the target international currencies into
     standard 3-letter uppercase ISO 4217 codes:
     - Chinese Yuan (`CNY`) — ISO code and common symbols/designations (such as `¥`, `CN¥`, `RMB`,
       `元`, `юан`).
     - British Pound (`GBP`) — ISO code and symbol (`£`).
     - Japanese Yen (`JPY`) — ISO code and explicit Yen designations (`JP¥`, `円`, `йен`, `иен`),
       with deterministic disambiguation when the shared `¥` symbol is used alongside explicit page
       currency metadata or standalone fallback rules.
     - Turkish Lira (`TRY`) — ISO code, symbol (`₺`), and common designations (`TL`, `лир`).
     - Georgian Lari (`GEL`) — ISO code, symbol (`₾`), and common designations (`лари`).
     - Armenian Dram (`AMD`) — ISO code, symbol (`֏`), and common designations (`драм`, `dram`).
   - All previously supported currencies (`RUB`, `USD`, `EUR`, `KZT`, `BYN`) continue to be
     recognized without regression.
2. **Localized Numeric Price Parsing**:
   - Prices formatted with European thousand dots and decimal commas (e.g., `1.299,99` or
     `1.234.567,89`) are parsed to their exact numeric value (`1299.99`, `1234567.89`).
   - Prices formatted with Anglo-Saxon thousand commas and decimal dots (e.g., `1,299.99` or
     `1,234,567.89`) are parsed to their exact numeric value (`1299.99`, `1234567.89`).
   - Whole-number prices with thousand separators and no fractional part (e.g., `12,800` in `JPY`
     or `15.000` / `1,234,567`) are distinguished from 2-digit decimal fractions (e.g., `12,50` or
     `12.50`) and parsed as whole thousands (`12800`, `15000`, `1234567`).
   - Prices containing standard, non-breaking, or thin whitespace thousand separators (e.g.,
     `12 990,50`) and surrounding currency symbols/labels are accurately extracted.
   - Zero or negative amounts are rejected as invalid prices.
3. **Complex Structured Product Pricing Extraction**:
   - Product preview extraction resolves price and currency from complex structured page metadata,
     including:
     - Aggregate offer blocks specifying lowest and highest offer prices when a single fixed price
       is absent.
     - Nested price specification blocks (single or list of price specifications) attached to an
       offer.
     - Multi-offer lists or graphs where the first valid positive price and its associated currency
       are selected cleanly.
     - Combined price-and-currency strings inside structured price fields or social preview tags
       when a dedicated currency field is missing.
4. **Automated Verification for Foreign E-Commerce Scenarios**:
   - Automated tests verify unit and end-to-end metadata extraction across realistic foreign and
     regional e-commerce product page fixtures covering `CNY`, `GBP`, `JPY`, `TRY`, `GEL`, and
     `AMD`, European and Anglo-Saxon number separators, and complex structured pricing layouts.
   - All existing and newly added automated checks pass without regressions.

## Task Description

### Problem and Background

During the technical debt audit of the product link preview subsystem (`WISHENKA-12`, tracked as
follow-up `WISHENKA-98`), several gaps in international e-commerce coverage were identified:

1. Regional currencies frequently used by users ordering from neighboring or cross-border markets
   — specifically Turkish Lira (`TRY`), Georgian Lari (`GEL`), and Armenian Dram (`AMD`) — were not
   fully represented alongside `CNY`, `GBP`, and `JPY` in currency symbol and text normalization.
2. When product prices use European punctuation (`1.299,99` or `15.000`) or Anglo-Saxon thousand
   commas without decimals (`12,800`), naive separator replacement can confuse thousand separators
   with decimal points.
3. International e-commerce platforms frequently publish product prices inside nested structured
   metadata (such as aggregate price ranges, nested price specification nodes, or offer arrays)
   rather than a flat single offer field.
4. Automated test coverage lacked comprehensive foreign e-commerce extraction scenarios exercising
   these currencies, localized numeric formats, and structured offer variations end-to-end.

### Programming Language

- **Python**

### Functional Requirements

1. **Expanded Currency Code & Symbol Recognition**:
   - Support normalization of `CNY`, `GBP`, `JPY`, `TRY`, `GEL`, and `AMD` (in addition to `RUB`,
     `USD`, `EUR`, `KZT`, `BYN`) from standalone currency attributes, inline price strings, and
     localized currency names/symbols.
   - When an explicit structured currency code (such as `JPY` or `CNY`) accompanies a price that
     also contains an ambiguous symbol (such as `¥`), the explicit structured currency code takes
     precedence.
2. **Localized Number Format Disambiguation**:
   - Correctly interpret numbers containing both thousand separators and decimal separators in
     either order (`.` then `,`, or `,` then `.`).
   - Correctly interpret numbers containing repeated identical separators (e.g., `1.000.000` or
     `1,000,000`) as thousand groupings.
   - Correctly interpret a single comma or dot separator by examining the fractional/grouping digit
     pattern so that 2-digit fractional cents (`99,95`, `99.95`) and 3-digit thousand groupings
     (`12,800`, `15.000`) are resolved accurately.
3. **Structured Offer Metadata Extraction**:
   - Support single offers, arrays of offers, aggregate offers with low/high price boundaries, and
     nested price specification objects in structured product metadata.
   - Fall back to social preview price/currency tags or inline price-currency text extraction when
     primary structured fields omit either price or currency.

### Non-Functional Requirements

- **Performance**: Price and currency parsing must remain lightweight and execute in sub-millisecond
  time per field without adding external network calls.
- **Determinism**: Given any input string or product page document, currency normalization and
  numeric extraction must produce deterministic, locale-independent results regardless of the host
  operating system's locale settings.
- **Backward Compatibility**: All existing domestic marketplace and link preview behaviors must
  continue working identically.

### Scope and Boundaries

- **In scope**:
  - Currency normalization and inline detection for `CNY`, `GBP`, `JPY`, `TRY`, `GEL`, `AMD` (plus
    existing `RUB`, `USD`, `EUR`, `KZT`, `BYN`).
  - Localized numeric price parsing for European, Anglo-Saxon, and whitespace-separated formats.
  - Complex structured pricing extraction (aggregate offers, nested price specifications,
    multi-offer arrays, inline price+currency fallback).
  - Automated unit and integration tests for international currencies and foreign e-commerce page
    fixtures.
- **Out of scope**:
  - Live exchange-rate conversion between currencies (wishes store price in the original extracted
    or user-selected currency).
  - Headless browser rendering for client-side JavaScript stores (tracked in `WISHENKA-99`).
  - Externalizing marketplace tracking rules to configuration files (tracked in `WISHENKA-96`).

### Main Business Entities

- **Product Preview**: The extracted summary of an external store link, including title,
  description, image, numeric price, normalized currency code, store brand, and fallback status.
- **Money Amount (Price & Currency)**: A positive numeric price value paired with an uppercase
  3-letter ISO 4217 currency code (`RUB`, `USD`, `EUR`, `KZT`, `BYN`, `CNY`, `GBP`, `JPY`, `TRY`,
  `GEL`, `AMD`).
- **Structured Product Offer**: Merchant-published pricing metadata on an e-commerce page that may
  represent a single price, a price range (aggregate offer), or nested price specifications across
  one or more variants.

### Constraints and Assumptions

- When a product page provides a price range (aggregate offer), the lowest available positive price
  is used as the preview price (falling back to the highest price if lowest is unavailable).
- When a single dot or comma separates a non-zero integer prefix from exactly three trailing digits
  (e.g., `12,800` or `15.000`), e-commerce pricing conventions treat it as a thousand separator,
  whereas one or two trailing digits (e.g., `12,5` or `12,50`) represent decimal fractions.

## Q&A

1. **Why is expanding international currency and number format parsing needed from a business
   perspective?**
   - Wishlist users frequently share links to global and regional online stores (e.g., AliExpress,
     Amazon UK/DE/JP, Trendyol/Turkish stores, Georgian and Armenian retailers). If the service
     fails to recognize their currencies (`CNY`, `GBP`, `JPY`, `TRY`, `GEL`, `AMD`) or misreads
     European/Anglo-Saxon thousand separators, users either see corrupted prices (off by a factor
     of 1,000) or must fill in price and currency manually, degrading the core convenience of
     link-based wish creation.
2. **How should the shared `¥` symbol be handled between Chinese Yuan (`CNY`) and Japanese Yen
   (`JPY`)?**
   - Whenever the page provides an explicit currency code or unambiguous marker (`JPY`, `JP¥`, `円`
     vs `CNY`, `CN¥`, `RMB`, `元`), that explicit designation takes precedence. When only a bare
     `¥` symbol is present with no disambiguating code, a consistent default (`CNY`) is used.
