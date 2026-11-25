---
name: rc-context-pack
version: '0.1.1'
description: "Ground any session in verified facts about Salesforce Revenue Cloud Advanced (RCA, formerly Revenue Lifecycle Management) before making any claim about it. Read this BEFORE asserting how RCA works — which object holds what, which fields and picklist values exist, how selling models, bundles, pricing, billing or amendments behave, what the Place Sales Transaction API accepts, or which API version introduced a feature. Also installs the pack to ~/.claude/knowledge/revenue-cloud/, fingerprints a live org, checks cheaply whether the pack has gone stale, and regenerates it. Use for \"ground me in Revenue Cloud\", \"how does RCA handle X\", \"is this RCA claim right\", \"fingerprint the org\", \"what's enabled in this org\", \"install/refresh the Revenue Cloud context pack\", \"which objects do I need for pricing\", and before any other rc-* skill runs. Not for building on Revenue Cloud or migrating from CPQ (rc-build, rc-migrate), and not for writing skills (rc-authoring-loop)."
---

# Revenue Cloud context pack — ground before you claim

Revenue Cloud Advanced moves fast and its object model is large, partly protected, and
gated by module and API version. A plausible-sounding answer generated from memory is the
single biggest source of wasted implementation effort in this domain. This skill exists so
that every claim about RCA traces to one of two sources:

- **DOCS** — the Salesforce Revenue Lifecycle Management Developer Guide. Authoritative for
  what the product supports in general, and for the API version a feature landed in.
- **ORG** — a `describe` against a real org. Authoritative for what *this customer* actually
  has: which modules are on, which fields and picklist values exist, what is customised.

Where the two disagree, ORG wins for anything about the customer, DOCS wins for anything
about the product. Never resolve a disagreement by averaging them, and never fill a gap
from memory. If neither source answers the question, say so.

## The pack

The pack lives outside this plugin, at `~/.claude/knowledge/revenue-cloud/`, so that every
rc-* plugin and every non-Claude agent reads the same copy. Plugins are cached on install
and cannot reference files outside their own directory, so a shared home-directory location
is the only way to share this.

```
~/.claude/knowledge/revenue-cloud/
├── MANIFEST.json              # what was swept, when, from where, with checksums
├── docs/                      # fetched developer-guide sources
│   └── <module>/...
├── orgs/
│   └── <alias>/
│       ├── fingerprint.json   # machine-readable: modules on, objects present, API version
│       ├── FINGERPRINT.md     # human-readable summary
│       └── describe/<Object>.json
└── notes/                     # hand-written doctrine learned on real implementations
```

`notes/` is the part that makes the pack worth more than the docs. Docs tell you what the
product does. Notes tell you what broke at 2am. Append to it; never let a script overwrite it.

## Routing

Decide which half of the pack answers the question before doing anything else.

| The question is about | Use | If missing |
|---|---|---|
| What RCA supports in general, API versions, object/field reference | DOCS | run `sweep_docs.py` |
| What a specific org has, is enabled, is customised | ORG | run `sweep_org.py --org <alias>` |
| Why something failed in practice, a workaround, a trap | `notes/` | answer from DOCS+ORG, then write the note |

## Workflow

### 1. Check the pack exists and is fresh

```bash
python3 scripts/check_staleness.py
```

It reports the pack's age, the API version it was built against, and whether the live
org's API version has moved past it. It makes no network calls beyond a single version
probe. Treat anything older than one Salesforce release (roughly four months) as stale
and offer to re-sweep. Do not silently use a stale pack.

If the pack does not exist, build it: run step 2 and step 3 before answering anything.

### 2. Sweep the docs

```bash
python3 scripts/sweep_docs.py --out ~/.claude/knowledge/revenue-cloud
```

Fetches the developer guide module indexes and the full PDF, stores them with a SHA-256
per source, and writes `MANIFEST.json`. See `references/doc-sources.md` for the source
list and what each one is authoritative for. Never add a source to the sweep that is not
published by Salesforce; third-party blogs go in `notes/` clearly marked as such.

### 3. Fingerprint the org

```bash
python3 scripts/sweep_org.py --org <alias> --out ~/.claude/knowledge/revenue-cloud
```

Read-only. It describes every object in the seed list (see `references/module-map.md`),
records which are present and which are absent, extracts picklist values for the fields
that drive behaviour, and follows child relationships to discover objects the seed list
missed. Absence of an object is a finding, not an error: it usually means that module is
not provisioned.

The output format, and how to read it, is in `references/org-fingerprint-format.md`.

In a chat session with no shell, do the same work with the Salesforce MCP tools:
`getObjectSchema` for the describes and `soqlQuery` for record counts. Write the results to
the same paths by hand. Never invent a field name to fill a gap in a describe.

### 4. Answer, with provenance

Every factual claim about RCA carries where it came from. In prose that means naming the
source; in a generated artifact it means a reference line. The three shapes:

- "Per the developer guide, `ProductSellingModel.SellingModelType` accepts OneTime, TermDefined and Evergreen."
- "In this org, `PriceAdjustmentSchedule.ScheduleType` has Volume, Term, Attribute, Bundle and Custom."
- "Not covered by the pack. I'd need to describe `<Object>` or check the guide before answering."

The third shape is the one that matters. Use it.

## Verified anchors

These were confirmed against a live org describe and are safe to rely on as a starting
point. They are a starting point, not the model: re-verify against the target org.

- **Catalog** — `ProductCatalog` (CatalogType: Sales, ServiceProcess) contains
  `ProductCategory`. `Product2` is still the product.
- **Selling model** — `ProductSellingModel` carries SellingModelType (OneTime, TermDefined,
  Evergreen), PricingTerm, PricingTermUnit and DoesAutoRenewAssetByDefault. Pricing,
  bundling and ramps all hang off the selling model, not off the product alone. This is the
  single biggest shape difference from CPQ.
- **Bundles** — `ProductComponentGroup` (min/max components, nestable via ParentGroupId)
  plus `ProductRelatedComponent`, which carries ParentProductRole (Bundle, Set, AddOn),
  ChildProductRole, IsComponentRequired, IsDefaultComponent, IsQuantityEditable,
  QuantityScaleMethod (Constant, Proportional) and DoesBundlePriceIncludeChild.
- **Pricing** — `PriceAdjustmentSchedule` (ScheduleType: Volume, Term, Attribute, Bundle,
  Custom; AdjustmentMethod: Range or Slab) with `PriceAdjustmentTier`, plus
  `AttributeBasedAdjustment` and `BundleBasedAdjustment`.
- **Billing** — `BillingSchedule` is the spine: BillingTermUnit, BillingType (Advance,
  Arrears), BillingMethod (OrderAmount, Evergreen, Usage), Status, InvoiceGroupType
  (Default, BillingSchedule, Custom) with CustomInvoiceGroupKey for invoice grouping, and
  Category/SubCategory recording why the schedule exists — Original, Renewal, Cancellation,
  Amendment, and subcategories including SwapIn, SwapOut, UpgradeTo, DowngradeFrom,
  DeltaPriceAmend, SimplifiedRenewal, AsIsRenewal, BillingFrequencyChange.
- **Errors** — `RevenueTransactionErrorLog` is where failed transactions land. Check it
  before concluding that an API call succeeded.

## Guardrails

- Revenue Cloud has been renamed more than once. When a user says Revenue Cloud, RLM,
  Revenue Lifecycle Management or Agentforce Revenue Management, confirm which object model
  they mean before answering. Legacy Salesforce CPQ is a different product entirely.
- A feature existing in the guide does not mean it is enabled in the org. Check the
  fingerprint before designing around it.
- Some Revenue Management objects are protected and non-extensible. Check the deployment
  reference before promising a custom field on one.
- Never write to the org from this skill. It reads and reports. Building belongs to
  `rc-build`, migration to `rc-migrate`.
