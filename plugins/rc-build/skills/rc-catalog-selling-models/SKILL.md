---
name: rc-catalog-selling-models
version: '0.1.0'
description: "How to model products and selling models in Revenue Cloud Advanced: the monthly/annual pattern, when one product needs two selling models and when one selling model with a different billing frequency is enough, why cloning Product2 to get a second price destroys asset lineage and renewals, how to keep the selling-model library small and reusable, and how price hangs off PricebookEntry.ProductSellingModelId. Read this BEFORE designing an RCA catalog, creating a ProductSellingModel, or deciding how to sell the same thing monthly and annually. Use for \"sell this monthly and annually\", \"the monthly and annual thing\", \"two products or two selling models\", \"should I duplicate the SKU for the annual price\", \"billing frequency vs pricing term\", \"where does the price live in RCA\", \"PricebookEntry ProductSellingModelId\", \"why did the renewal create a new asset\", \"how many selling models should we have\". Read and design only: it never writes to an org. Not for CPQ-to-RCA migration (rc-migrate), not for bundles, price adjustment schedules or billing schedules, and not for building the knowledge pack (rc-context-pack)."
---

# Products and selling models in RCA

The catalog decision that costs the most to reverse is the one that looks smallest: how
you get two prices for the same thing. Cloning `Product2` into "Widget Monthly" and
"Widget Annual" renders correctly in the catalog, prices correctly on the quote, and
fails twelve months later — because amendment, renewal and cancellation are addressed by
asset (developer guide), and an asset points at exactly one product (arm-picone describe,
2026-11-24).

This skill covers the shape of that decision: what a selling model is for, what a billing
frequency is for, and where the price attaches. It is read-and-design work. **Nothing
here writes to an org.** Where a step needs to look at an org, it looks at the knowledge
pack's describes, or at read-only SOQL you run yourself.

## Prerequisite

The knowledge pack at `~/.claude/knowledge/revenue-cloud/` must exist. Run
`rc-context-pack` first.

This skill leans on **both halves of the pack**. The object graph and the API version
floors come from the developer guide; what a given org actually exposes comes from its
fingerprint, and the two disagree in ways that change the design (see **Deltas** below).
Without a fingerprint of the org you are designing for, treat every ORG line here as
arm-picone's configuration and not as yours.

## Routing

Pick one. The question is never "monthly or annual" — it is which of three things varies.

| The customer's requirement | What varies | Shape |
|---|---|---|
| Same commitment, invoice cut more often (annual deal, billed quarterly) | Invoice cadence only | **One** selling model; set billing frequency on the transaction line |
| Annual costs less per month than monthly (a commitment discount) | Price per unit of time | **Two** selling models on **one** product |
| 1-year and 3-year at the same annual rate | Number of terms | **One** selling model; set the subscription term on the line |
| No end date, cancel any time | Term exists or not | A separate **Evergreen** selling model |
| Different entitlement, different line on the invoice | What the customer gets | **Two** products |

The failure mode this table exists to prevent is reaching for row five when row two is the
answer.

### The three questions, in order

1. **Does the price per unit of time change?** If annual is cheaper per month than
   monthly, that is a different pricing term, and a different pricing term is a different
   selling model.
2. **Does only the invoice cadence change?** Then the pricing term is unchanged. Keep one
   selling model and vary the billing frequency on the line.
3. **Does what the customer receives change?** Only then is it a second product.

## Workflow

### 1. Ground in the org's actual surface

```bash
python3 plugins/rc-build/skills/rc-catalog-selling-models/scripts/selling_model_surface.py <org-alias>
```

It reads the pack's describes and prints the selling-model surface for that org: the
`ProductSellingModel` picklists, which `ProductSellingModelOption` fields exist, where the
price attaches, and which of the three places billing frequency lives are present. It
writes nothing and touches no org.

Run it for the org you are designing for. If that org has no fingerprint in the pack, say
so in the design rather than assuming arm-picone's shape.

### 2. Classify each requirement with the routing table

Do this per product family before writing any records. The classification is the design;
everything after it is data entry.

### 3. Shape the selling-model library — small, canonical, shared

Selling models are **not** per-product. A `ProductSellingModel` record is referenced by
every product that sells on those terms, through `ProductSellingModelOption`, and then
again by price book entries, quote lines, order items and asset action sources.

Two reasons to keep the library small, both verified:

- **You cannot clean it up later.** Per the developer guide, you can't delete an active or
  an inactive product selling model, you can only delete a draft one after removing all
  references, and you can't move a model back to Draft from Active or Inactive. A
  per-product selling model is a permanent record.
- **It is the join key of the whole price side.** One model shared by a few hundred
  products is one row to reason about when pricing goes wrong.

In arm-picone (swept 2026-11-24) the whole catalog runs on **nine** canonical models —
One-Time, plus Term and Evergreen crossed with Monthly, Quarterly, Semi-Annual and Annual.
The usage is lopsided and that is healthy: 258 One-Time, 37 Term Annual, 15 Term Monthly,
9 Evergreen Monthly, 1 Evergreen Annual.

Name them for the terms, not for the product: `Term Annual`, not `Additional API Annual`.

### 4. Attach the product to each selling model

`ProductSellingModelOption` is the junction between `Product2` and `ProductSellingModel`
(developer guide). One row per combination the product is sold on.

Order matters. Per the developer guide's Salesforce Pricing considerations: *"Product and
product selling model must be a part of the product selling model option before you create
values in a price book entry."* Create the junction first, the price second.

Set `IsDefault` on exactly one option per product — the guide states a product can have
only one default, and that setting one is optional. The default is what a sales surface
reaches for when the rep does not choose.

### 5. Hang the price off the selling model

Price lives on `PricebookEntry`, and the selling model is what makes two prices for one
product legal. Per the developer guide, `PricebookEntry.ProductSellingModelId` is a
nillable lookup to `ProductSellingModel`; the guide's own create example is:

```json
{
  "ProductSellingModelId": "0jPxx0000000005EAA",
  "Product2Id": "01tLT00000A0YTlYAN",
  "IsActive": true,
  "Pricebook2Id": "01s1W000000SYXNQA4",
  "UnitPrice": "100.00"
}
```

So the grain of a price is **price book × product × selling model × currency**. That is
the whole mechanism: the annual price and the monthly price are two rows that differ only
in `ProductSellingModelId`, over one `Product2Id`.

Two guide rules that bite during load: the standard price for a product must be loaded
before any custom price, and a price book entry can never be deleted — only deactivated
with `IsActive`.

### 6. Worked case — Additional API in arm-picone

Observed in arm-picone, 2026-11-24. One product, three selling models, three price book
entries:

| Product | Selling model | SellingModelType | PricingTerm / Unit | UnitPrice | IsDefault |
|---|---|---|---|---|---|
| Additional API | Term Annual | TermDefined | 1 / Annual | 15,000 | true |
| Additional API | Term Monthly | TermDefined | 1 / Months | 1,500 | false |
| Additional API | Evergreen Monthly | Evergreen | 1 / Months | 2,000 | false |

Read the economics off the table: 1,500 × 12 = 18,000 against 15,000 annual, a 16.7%
commitment discount, and Evergreen priced 33% above the termed monthly for the privilege
of cancelling. Three different prices per month of service. That spread is exactly what
makes this row two of the routing table and not row one — no billing-frequency setting can
produce it, because billing frequency changes when you invoice, not what a month costs.

One `Product2`, so one asset lineage: the selling model on the next transaction changes,
the identity of the thing the customer owns does not. I did not watch that move execute
in this org — see **Not verified** before promising it to a customer.

### 7. Verify the design before anyone builds it

Read-only SOQL. Run these yourself; this skill does not run them for you.

```sql
-- One product should have several models, not several products one model each.
SELECT Product2.Name, ProductSellingModel.Name, ProductSellingModel.SellingModelType,
       ProductSellingModel.PricingTerm, ProductSellingModel.PricingTermUnit, IsDefault
FROM ProductSellingModelOption
WHERE Product2.Name = 'Additional API'

-- Every option should have a price; an option without one is a dead end at quoting.
SELECT Product2.Name, ProductSellingModel.Name, UnitPrice, CurrencyIsoCode, IsActive
FROM PricebookEntry
WHERE Product2.Name = 'Additional API'

-- Library size. A number near the product count means the library sprawled.
SELECT COUNT(Id) FROM ProductSellingModel WHERE Status = 'Active'

-- Near-duplicate products: the clone anti-pattern, visible by name.
SELECT Id, Name, ProductCode FROM Product2
WHERE Name LIKE '%Monthly%' OR Name LIKE '%Annual%'
```

The last one is the test that matters. A hit list means someone already solved a pricing
problem with a product.

## The anti-pattern: a second `Product2` for the second price

It is tempting because it works in every step you can see on day one. The catalog shows
two entries, the rep picks one, the quote prices, the order activates. What it breaks is
the part nobody tests during a build.

**Asset lineage is per product.** `Asset.Product2Id` points to one product, and in
arm-picone (2026-11-24) `Asset` carries no selling-model field at all. The selling model is
recorded one level down, on `AssetActionSource.ProductSellingModelId`, per transaction.
So the object graph says: the product is the identity of the thing the customer owns, and
the selling model is a property of each event in its history.

**The lifecycle APIs take asset IDs, not product IDs.** Per the developer guide,
`initiateAmendment` takes `amendAssetIds`, `initiateRenewal` takes `renewAssetIds`, and
`initiateCancellation` takes `cancelAssetIds`. There is no input on any of them for "and
change it to this other product".

**Moving between products is a different operation entirely.** Per the developer guide,
Initiate Swap exchanges one product for another; Initiate Upgrade moves a lower-tier
product to a higher-tier one, and in doing so the original asset receives an asset action
with an Upgrade category while *a new asset is created* with a linked action. In
arm-picone, `AssetAction.CategoryEnum` and `AssetAction.Subtype` carry the matching
values — Swaps, Upgrades, Downgrades, and `SwapIn`/`SwapOut`/`UpgradeFrom`/`UpgradeTo`.

Put together, the consequence of cloning the product. The left column is what the object
graph and the API signatures support; the right column is what the guide states for
Upgrade and what the swap subtypes imply for the rest.

| With two selling models on one product | With two products |
|---|---|
| Monthly → annual is an amendment on the existing asset | A swap or an upgrade, producing a second asset |
| One asset, one renewal, one history | Two asset lineages to reconcile |
| `AssetAction` totals roll up on one asset | Totals split across a cancellation and a new sale |
| One price book entry to re-price | Two, which drift apart |

The renewal is where it surfaces. `initiateRenewal` renews the asset it is given, on the
product that asset holds, and nobody discovers the annual clone was never connected to the
monthly asset until the first renewal cycle runs.

## Deltas — the guide and the org disagree

Found while verifying this skill against arm-picone (describe sweep 2026-11-24) and the
Revenue Lifecycle Management developer guide (v68 PDF, swept 2026-11-24). Full field
inventory in `references/field-map.md`.

**1. `ProductSellingModelOption` has no `Minimum`, `Maximum` or `Increment` here.** The
guide's Salesforce Pricing section documents the object with `Description`, `DisplayName`,
`Increment`, `Maximum` and `Minimum`, and attaches the "requires Industries EPC" caveat to
`IsDefault` alone. In arm-picone the object has 14 fields — the audit set plus
`ProductSellingModelId`, `Product2Id`, `ProrationPolicyId` and `IsDefault` — and none of
the five. The guide's *Product Catalog Management* section documents only `IsDefault`, with
no EPC caveat, and that section matches the org. **Design consequence:** you cannot bound
the subscription term on the option in an RCA org without EPC. Constrain the term by
offering specific selling models instead.

**2. `OrderItem` uses `BillingFrequency2`; `QuoteLineItem` uses `BillingFrequency`.** Both
hold the same six values in arm-picone — MilestonePlan, Weekly, Monthly, Quarterly,
Semi-Annual, Annual — under different API names, and `OrderItem` has no field named
`BillingFrequency` at all. The same rename hits `BillingReference` → `BillingReference2`.
The guide documents neither name in its Order Item or Quote Line Item field sections;
`BillingFrequency2` appears in the PDF only inside sample order payloads. A third spelling
exists downstream: `AssetStatePeriod.BillingFrequency`, without the `2`. **Design
consequence:** any quote-to-order field mapping, flow or integration that carries billing
frequency across breaks silently, and no document warns you.

**3. `ProductSellingModel.PricingTermUnit` offers Weekly here.** The guide lists Months,
Quarterly, Semi-Annual and Annual. arm-picone's describe adds **Weekly**, and the same
extra value shows on `QuoteLineItem.PricingTermUnit`, `QuoteLineItem.SubscriptionTermUnit`
and `Asset.RenewalTermUnit`. **Design consequence:** weekly terms are available in this
org; confirm in the target org's describe before designing on them, because the guide does
not promise them.

**4 (bonus). `ProductSellingModel.DoesAutoRenewAssetByDefault` is undocumented.** The field
exists in arm-picone as a required boolean defaulting to false, and the string does not
appear anywhere in the v68 guide PDF. It sits exactly where a selling-model design wants
it — the renewal default travels with the terms. Treat it as real but unpromised, and set
it deliberately rather than inheriting the default.

Precedence applied throughout: ORG wins for what this org has, DOCS wins for what the
product supports in general.

## Verified anchors

- **DOCS** — A product can have multiple product selling models. (developer guide,
  Salesforce Pricing → ProductSellingModel; object available in API version 60.0 and later)
- **DOCS** — `ProductSellingModelOption` is a junction object between ProductSellingModel
  and Product2. (Salesforce Pricing → ProductSellingModelOption)
- **DOCS** — Product and product selling model must be part of the product selling model
  option before price book entry values are created. (Revenue Management Deployment →
  Salesforce Pricing Additional Information)
- **DOCS** — An active or inactive product selling model can't be deleted, and its status
  can't be moved back to Draft. (same section)
- **DOCS** — `PricebookEntry.ProductSellingModelId` is a nillable lookup to
  ProductSellingModel; standard price loads before custom prices; entries are deactivated,
  never deleted. (Salesforce Pricing → PriceBookEntry)
- **DOCS** — The unit of `OrderItem.SubscriptionTerm` is read from
  `OrderItem.ProductSellingModel.PricingTermUnit`, available in API version 61.0 and later.
  (Transaction Management Fields on Order Item)
- **DOCS** — `initiateAmendment`, `initiateRenewal` and `initiateCancellation` take asset
  IDs (`amendAssetIds`, `renewAssetIds`, `cancelAssetIds`). Initiate Swap exchanges one
  product for another with linked asset actions; Initiate Upgrade gives the original asset
  an Upgrade-category action and **creates a new asset** linked to it. The guide states the
  new asset for Upgrade; it does not say so in as many words for Swap.
  (Transaction Management → Resources, Actions)
- **DOCS** — Access to `BillingTreatment` needs the Billing Admin permission set; its
  `CanChangeBillingFrequency` boolean defaults to false. (Billing → BillingTreatment)
- **ORG arm-picone, 2026-11-24** — `ProductSellingModel`: `SellingModelType` is OneTime,
  TermDefined or Evergreen; `PricingTermUnit` adds Weekly; `Status` is Draft, Inactive or
  Active; `DoesAutoRenewAssetByDefault` is present.
- **ORG arm-picone, 2026-11-24** — Additional API sells on three selling models over one
  `Product2`, with the prices in the worked case above. Nine canonical selling models
  across the catalog.
- **ORG arm-picone, 2026-11-24** — `Asset` holds `Product2Id` and no selling-model field;
  `AssetActionSource` holds `ProductSellingModelId`.

## Not verified

- **I did not observe an amendment that changes the selling model on a live asset.** The
  lineage argument above rests on the object graph and the lifecycle API signatures, not on
  a run I watched. Before promising a customer that monthly → annual is a clean amendment,
  execute it once in their sandbox and read the resulting `AssetAction` and
  `AssetActionSource` rows.
- **Whether arm-picone has Industries EPC.** The org has `IsDefault`, which the guide marks
  EPC-dependent, and lacks `Minimum`/`Maximum`/`Increment`, which the guide does not mark.
  One of those two facts means the guide's EPC marking is on the wrong field; I could not
  settle which from the pack alone.
- **Whether the nine-model library in arm-picone is a deliberate standard or an accumulation.**
  It reads as deliberate — the naming is consistent and the reuse is high — but that is an
  inference from the data, not something the org records. Ask before copying it as doctrine.
- **arm-picone is one org.** Every ORG line here is a single observation. The three deltas
  are the kind that hold across orgs, and none of them is confirmed in a second org yet.

## Guardrails

- **Never create a second `Product2` to carry a second price.** That is the one mistake
  this skill exists to stop. If a reviewer proposes it, the counter-argument is the asset
  lineage table above, not taste.
- **Never map `BillingFrequency` straight from quote to order.** It is `BillingFrequency2`
  on `OrderItem`. The same goes for `BillingReference`.
- **Do not design the subscription-term floor or ceiling on `ProductSellingModelOption`**
  in an RCA org without EPC. The fields are not there.
- **Do not read the Salesforce Pricing field lists as what your org has.** They carry the
  Industries superset. Check the describe.
- **Do not activate a selling model you are unsure about.** Draft is the only status you
  can delete from.
- **This skill writes nothing.** No records, no metadata, no org changes. If a task needs a
  write, it belongs in a skill that declares one, with a preview step and a rollback.
