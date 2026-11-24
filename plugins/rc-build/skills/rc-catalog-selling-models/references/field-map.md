# Field map — selling models, price and lineage

Two sources throughout. **DOCS** is the Revenue Lifecycle Management developer guide,
v68 PDF, swept 2026-11-24. **ORG** is the arm-picone describe sweep of 2026-11-24. Where
they disagree the row says so.

## ProductSellingModel

Defines one method by which a product is sold (DOCS, Salesforce Pricing). Available in API
version 60.0 and later. A product can have several.

| Field | Type | ORG arm-picone | DOCS |
|---|---|---|---|
| `Name` | string, required | present | present |
| `SellingModelType` | picklist, required, default OneTime | OneTime, TermDefined, Evergreen | same three |
| `PricingTerm` | int, nillable | present | present; must be null when the model is one-time |
| `PricingTermUnit` | picklist, nillable, restricted | Months, Quarterly, Semi-Annual, **Weekly**, Annual | Months, Quarterly, Semi-Annual, Annual |
| `Status` | picklist, required, default Draft | Draft, Inactive, Active | same three |
| `DoesAutoRenewAssetByDefault` | boolean, required, default false | **present** | **absent from the guide** |

15 fields in the org describe, counting the audit set.

Lifecycle rules (DOCS, Revenue Management Deployment → Salesforce Pricing Additional
Information): an active or inactive model can't be deleted; a draft one can be deleted
after all references are removed; status can't move back to Draft from Active or Inactive.

## ProductSellingModelOption

A junction object between ProductSellingModel and Product2 (DOCS). Available in API
version 60.0 and later.

The guide documents this object **twice**, with different field lists, and only one of
them matches an RCA org.

| Field | Salesforce Pricing section (DOCS) | Product Catalog Management section (DOCS) | ORG arm-picone |
|---|---|---|---|
| `Product2Id` | documented | — | present |
| `ProductSellingModelId` | documented | — | present |
| `ProrationPolicyId` | documented | — | present |
| `IsDefault` | documented, "requires Industries EPC" | documented, no caveat | present |
| `Description` | documented | — | **absent** |
| `DisplayName` | documented | — | **absent** |
| `Increment` | documented | — | **absent** |
| `Maximum` | documented | — | **absent** |
| `Minimum` | documented | — | **absent** |

14 fields in the org describe. The Product Catalog Management list is the one that matches.

`Minimum`, `Maximum` and `Increment` are the term-bounding fields — minimum, maximum and
step in pricing term units for a subscription term (DOCS). Without them, the way to bound
a term in an RCA org is to publish only the selling models you want sold.

DOCS ordering rule: "Product and product selling model must be a part of the product
selling model option before you create values in a price book entry."

## PricebookEntry

Represents an association between a Pricebook2 and a Product2 (DOCS). Available in API
version 60.0 and later.

| Field | ORG arm-picone | Note |
|---|---|---|
| `Pricebook2Id` | reference → Pricebook2, required | can't be changed on update (DOCS) |
| `Product2Id` | reference → Product2, required | can't be changed on update (DOCS) |
| `ProductSellingModelId` | reference → ProductSellingModel, nillable | this is what makes two prices for one product legal |
| `CurrencyIsoCode` | picklist: AUD, GBP, CAD, EUR, JPY, CHF, USD, default USD | org's currency set |
| `UnitPrice` | currency, required | only settable when `UseStandardPrice` is false (DOCS) |
| `UseStandardPrice` | boolean, default false | must be true on the standard price book (DOCS) |
| `IsActive` | boolean, default false | entries are deactivated, never deleted (DOCS) |
| `IsDerived` | boolean, required, default false | see `PriceBookEntryDerivedPrice` |

18 fields in the org describe. Effective grain of a price: **price book × product ×
selling model × currency**.

## Where billing frequency lives — three names for one idea

All ORG arm-picone, 2026-11-24. The guide's Order Item and Quote Line Item field sections
document none of these names; `BillingFrequency2` appears in the v68 PDF only inside
sample order payloads.

| Object | Field | Values |
|---|---|---|
| `QuoteLineItem` | `BillingFrequency` | MilestonePlan, Weekly, Monthly, Quarterly, Semi-Annual, Annual |
| `OrderItem` | `BillingFrequency2` | the same six |
| `AssetStatePeriod` | `BillingFrequency` | the same six |

The paired rename: `QuoteLineItem.BillingReference` → `OrderItem.BillingReference2`.

`OrderItem` also carries `BillingTerm` (int) and `SubscriptionTerm` (int); per DOCS the
unit of the subscription term is read from
`OrderItem.ProductSellingModel.PricingTermUnit`, available in API version 61.0 and later.

Changing the frequency after the fact is gated by `BillingTreatment.CanChangeBillingFrequency`
(boolean, default false — DOCS and ORG agree), and the amendment is recorded as
`BillingSchedule.SubCategory = BillingFrequencyChange`.

## Term fields that carry the Weekly delta

ORG arm-picone. Each of these picklists holds Months, Quarterly, Semi-Annual, **Weekly**,
Annual:

- `ProductSellingModel.PricingTermUnit`
- `QuoteLineItem.PricingTermUnit`
- `QuoteLineItem.SubscriptionTermUnit`
- `Asset.RenewalTermUnit`

`BillingSchedule.BillingTermUnit` carries the parallel extra value **Week**, alongside
OneTime, Day, Month, Quarter, Semi-Annual, Year and BillingMilestonePlan.

## The lineage chain

ORG arm-picone unless marked.

| Object | Points at the product | Points at the selling model |
|---|---|---|
| `Asset` | `Product2Id` | — (no selling-model field) |
| `AssetStatePeriod` | via `AssetId` | — (carries `BillingFrequency`, `SegmentType`) |
| `AssetAction` | via `AssetId` | — (carries `Type`, `CategoryEnum`, `Subtype`) |
| `AssetActionSource` | via `AssetActionId` | `ProductSellingModelId` |

So the product is the identity of what the customer owns, and the selling model is a
property of each event in its history.

`AssetAction.Type` (ORG): Generate, Change, Cancel, Convert.
`AssetAction.CategoryEnum` (ORG): Initial Sale, Upsells, Downsells, Cross-Sells,
Cancellations, Transfers, Terms And Conditions Changes, Renewals, Upgrades, Downgrades,
Swaps, Other.
`AssetAction.Subtype` (ORG): StartDateAdjustment, TransferFrom, TransferTo, Rollback,
FieldAmendment, SwapIn, SwapOut, UpgradeFrom, UpgradeTo, DowngradeFrom, DowngradeTo.

`Asset` also holds `ParentId` and `RootAssetId` (both → Asset) for bundle structure, and
the renewal controls `DoesAutomaticallyRenew`, `RenewalTerm` and `RenewalTermUnit`.

## Lifecycle API signatures

All DOCS, Transaction Management.

| Action | Required input | Produces |
|---|---|---|
| `initiateAmendment` | `amendAssetIds`, `amendStartDate`, `amendOutputType`, `quantityChange` | amendment quote or order against the same asset |
| `initiateRenewal` | `renewAssetIds`, `renewOutputType` | renewal record; available in API version 60.0 and later |
| `initiateCancellation` | `cancelAssetIds`, `cancelStartDate`, `cancelOutputType` | cancellation record; all assets in a request must belong to the same price book |
| Initiate Swap (POST) | `swapGroups`, `swapStartDate`, `outputRecordType` | amendment quote and order; API version 66.0 inputs |
| Initiate Upgrade (POST) | asset details | original asset gets an Upgrade-category action; **a new asset is created** with a linked action |

None of them accepts a target product on an existing asset. That is the whole reason a
product clone cannot be undone with an amendment.
