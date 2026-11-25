# Field map — price adjustment objects

Two sources throughout. **DOCS** is the Revenue Lifecycle Management developer guide, v68
PDF, swept 2026-11-24. **ORG** is the arm-picone describe sweep of 2026-11-24 plus a
read-only SOQL pass of 2026-11-25. Where they disagree the row says so.

Writability below is the org describe's `createable` / `updateable`, which is what a load
actually obeys. The guide expresses the same thing as the presence of `Create` and
`Update` in a field's Properties line, and the two agree everywhere in this map.

## PriceAdjustmentSchedule

DOCS: "Represents a series of tiered discounts based on the number of items purchased."
Available in API version 60.0 and later. 21 fields in the org describe counting the audit
set; 12 of them yours to set.

| Field | Type | Write | ORG arm-picone | DOCS |
|---|---|---|---|---|
| `Name` | string, required | C+U | present | present |
| `Description` | textarea | C+U | present | present |
| `IsActive` | boolean, required | C+U | present | present, default false |
| `ScheduleType` | picklist, required, default Volume | C+U | Volume, Term, Attribute, Bundle, Custom | same five |
| `AdjustmentMethod` | picklist, required, default Range | C+U | Range, Slab | same two |
| `EffectiveFrom` | datetime, nillable | C+U | present | present |
| `EffectiveTo` | datetime, nillable | C+U | present | present |
| `Pricebook2Id` | lookup → Pricebook2, nillable | C+U | present | present |
| `ContractId` | lookup → Contract, nillable | C+U | **present** | **absent from the guide** |
| `GlobalKey` | string, nillable | C+U | **present** | **absent from the guide** |
| `OwnerId` | lookup → Group, User | C+U | present | present |
| `CurrencyIsoCode` | picklist, nillable, default USD | C+U | 7 currencies | present |

The schedule has **no product link of any kind** — no `Product2Id`, no
`ProductSellingModelId`, no `SellingModelType`. Scope is the price book, or (ORG only) the
contract. Which products an adjustment reaches is decided on the child record.

Supported calls include `delete()` and `undelete()` (DOCS).

## PriceAdjustmentTier

DOCS: "Represents a discount tier in a price adjustment schedule." Available in API version
60.0 and later. 25 fields in the org describe; 10 of them yours to set.

| Field | Type | Write | ORG arm-picone | DOCS |
|---|---|---|---|---|
| `PriceAdjustmentScheduleId` | lookup, required | **C only** | present | present |
| `LowerBound` | double, required | C+U | present | positive integer, ≤ upper bound |
| `UpperBound` | double, nillable | C+U | present | "Not inclusive"; optional on the last tier |
| `TierType` | picklist, required | C+U | `AdjustmentPercentage`→Percentage, `AdjustmentAmount`→Amount, `OverrideAmount`→Override | same three, listed twice, first list omits OverrideAmount |
| `TierValue` | double, required | C+U | present | present |
| `EffectiveFrom` | datetime, nillable | C+U | present | present |
| `EffectiveTo` | datetime, nillable | C+U | present | present |
| `Product2Id` | lookup → Product2, nillable | C+U | present | present |
| `ProductSellingModelId` | lookup → PSM, nillable | C+U | present | present |
| `CurrencyIsoCode` | picklist, nillable, default USD | C+U | 7 currencies | present |
| `AdjustmentType` | picklist, nillable | **read-only** | `Percentage`, `Amount`, `Override` | documented with **no values** |
| `ScheduleType` | picklist, nillable, default Volume | **read-only** | five values | absent from the guide's tier section |
| `SellingModelType` | picklist, required, default OneTime | **read-only** | OneTime, TermDefined, Evergreen | same three |
| `PricingTerm` | int, nillable | **read-only** | present | null when the selling model is one-time |
| `PricingTermUnit` | picklist, nillable | **read-only** | Months, Quarterly, Semi-Annual, **Weekly**, `Annual`→**Years** | `Annual`→Years, Months only |
| `Name` | string, autonumber | read-only | `PAT-000000000n` | present |

`PriceAdjustmentScheduleId` is createable but **not** updateable: a tier cannot be moved to
another schedule. Delete and recreate.

The five read-only fields are a projection of the referenced `ProductSellingModel`, not a
copy of the parent schedule — four of the five are not fields on the schedule at all. They
are `calculated: false`, so they are platform-maintained rather than formulas.

DOCS Usage: "To use PriceAdjustmentTiers, associate them with a PriceAdjustmentSchedule.
Tiers can't overlap, and no gaps are allowed between tiers." See
`notes/price-adjustments.md` in the pack for how arm-picone's own tiers contradict the
exclusive-upper-bound rule.

## AttributeBasedAdjustment

DOCS: "Represents the association between the product selling model and the price
adjustment for product or service being sold based on its attributes." Available in API
version 60.0 and later. 25 fields in the org describe; 7 yours to set.

| Field | Type | Write | ORG arm-picone | DOCS |
|---|---|---|---|---|
| `PriceAdjustmentScheduleId` | lookup, required | C only | present | present |
| `AttributeBasedAdjRuleId` | lookup, required | C only | present | present |
| `ProductId` | lookup → Product2, required | C only | present | present |
| `ProductSellingModelId` | lookup → PSM, nillable | C only | present | present |
| `AdjustmentType` | picklist, required | C+U | `Percentage`, `Amount`, `Override` | Amount, Override, Percentage |
| `AdjustmentValue` | double, required | C+U | present | present |
| `EffectiveFrom` | datetime, **required** | C+U | present | present |
| `EffectiveTo` | datetime, nillable | C+U | present | present |
| `SellingModelType` | picklist, nillable, default OneTime | read-only | three values | same three |
| `PricingTerm` | int, nillable | read-only | present | present |
| `PricingTermUnit` | picklist, nillable | read-only | 5 values incl. Weekly, `Annual`→Years | 4 values, `Annual`→Years |
| `AttributeCount` | int, nillable | read-only | present | present |
| `ScheduleType` | picklist, nillable | read-only | **present** | **absent from the guide** |
| `AttributeAdjConditionsHash` | string, nillable | read-only | **present** | **absent from the guide** |

Note `EffectiveFrom` is required here and nillable on the tier and the schedule.

## AttributeBasedAdjRule and AttributeAdjustmentCondition

Both DOCS, both API version 60.0 and later. Neither is in the pack's 87-object describe
set — both are present in arm-picone's `discovered_not_in_seed` list and were described
live on 2026-11-25.

`AttributeBasedAdjRule`: `Name` (C+U), `OwnerId`, `UsageType` picklist `Pricing` | `Rating`
(C+U), `AttributeCount` (read-only). Supports `delete()`.

`AttributeAdjustmentCondition`: `AttributeBasedAdjRuleId` (C only), `AttributeDefinitionId`
(C+U), `Operator` (C+U, default `equals`), `ProductId` (C+U), `UsageType` (read-only), and
one typed value column per data type — `StringValue`, `IntegerValue`, `DoubleValue`,
`BooleanValue`, `DateValue`, `DateTimeValue`. **Supported calls omit `delete()` and
`undelete()`.**

`Operator` values (DOCS): `doesnotexistin`, `equals`, `existsin`, `greaterorequal`,
`greaterthan`, `lessorequal`, `lessthan`, `matches`, `notequals`.

A picklist attribute's condition uses `StringValue` — observed on all four conditions in
arm-picone, each over an `AttributeDefinition` named `Type` with `DataType` `Picklist`.
Writing the value into the wrong typed column leaves the condition inert; nothing errors.

### The attribute chain instantiated — arm-picone, 2026-11-25

One product (`01tfn000006KXZ4AAO`), one picklist attribute named `Type`, four values, four
rules, four price overrides. Each rule carries `AttributeCount` 1 and each condition holds
its value in `StringValue`.

| Rule | Condition | `AttributeBasedAdjustment` |
|---|---|---|
| `Rule_1724814105445` | `Type` equals `Flex` | `Override` 10,000 |
| `Rule_1724814147720` | `Type` equals `Pre-Prod` | `Override` 12,000 |
| `Rule_1724814176583` | `Type` equals `Prod` | `Override` 15,000 |
| `Rule_1724814263993` | `Type` equals `Gov` | `Override` 8,500 |

All four rules and all four conditions carry a null `UsageType`, and the rule names are
autogenerated from an epoch-millisecond timestamp around 2024-08-28, so the chain was built
by a tool rather than by hand.

## BundleBasedAdjustment

DOCS: "Represents the association between the product selling model and the price
adjustment for a product or service being sold as a bundle." Available in API version 60.0
and later. 26 fields in the org describe; 9 yours to set.

| Field | Type | Write | ORG arm-picone | DOCS |
|---|---|---|---|---|
| `PriceAdjustmentScheduleId` | lookup, required | C only | present | present |
| `ProductId` | lookup → Product2, required | C only | the component being adjusted | present |
| `ParentProductId` | lookup → Product2, required | C only | immediate parent | present |
| `RootBundleId` | lookup → Product2, required | C only | structural root | present |
| `ProductSellingModelId` | lookup → PSM, nillable | C only | present | present |
| `ParentProductSellingModelId` | lookup → PSM, nillable | C only | present | present |
| `RootProductSellingModelId` | lookup → PSM, nillable | C only | present | present |
| `AdjustmentType` | picklist, required | C+U | `Percentage`, `Amount`, `Override` | Amount, Override, Percentage |
| `AdjustmentValue` | double, required | C+U | present | present |
| `EffectiveFrom` | datetime, **required** | C+U | present | present |
| `EffectiveTo` | datetime, nillable | C+U | present | present |
| `SellingModelType` | picklist, nillable | read-only | three values | same three |
| `PricingTerm` / `PricingTermUnit` | int / picklist, nillable | read-only | 5 units incl. Weekly | 4 units |
| `ScheduleType` | picklist, nillable | read-only | **present** | **absent from the guide** |

The three product lookups are all required and all create-only. A bundle adjustment is
addressed by **path**, not by product: the same component can price differently under a
different root or a different immediate parent. In arm-picone all four records have
`ParentProductId` equal to `RootBundleId`, so the distinction between the two is present
in the schema and unexercised in the data.

## Where an applied adjustment lands

Three objects, none of them carrying the same field names. The quote and order describes
are in the pack; `AssetActionSrcPriceAdjustment` and `QuoteLinePriceAdjustment` were
described live in arm-picone on 2026-11-25 because the pack's seed list omits both.

| Concern | `QuoteLinePriceAdjustment` (20 fields) | `OrderItemAdjustmentLineItem` (29 fields) | `AssetActionSrcPriceAdjustment` (17 fields) |
|---|---|---|---|
| Line FK | `QuoteLineItemId` | `OrderItemId`, `OrderId` | `AssetActionSourceId`, `AssetId` |
| Cause | `PriceAdjustmentCauseId` | `AdjustmentCauseId` | `PriceAdjustmentCauseId` |
| Cause targets | `PriceAdjustmentTier`, `Promotion` | `PriceAdjustmentTier`, `Promotion` | **`Promotion` only** |
| Money in | `AdjustmentValue`, `TotalAmount` | `AdjustmentValue`, `Amount` | `AdjustmentValue` |
| Money out | `AppliedAdjustmentAmount` | `AppliedAdjustmentAmount` | `AppliedAdjustmentAmount` |
| Type | `AdjustmentType` (prefixed values) | `AdjustmentType` (prefixed values) | — |
| Source | `AdjustmentSource` | `AdjustmentSource` | `PriceAdjustmentSource` |
| Scope | `AdjustmentAmountScope` | `AdjustmentAmountScope` | — |
| Priority | `Priority` | `Priority` | `PrioritySequence` |
| Order-only | — | `TotalTaxAmount`, `TotalAmtWithTax`, `CouponCode`, `AppliedPromotionDate`, `OrderAdjustmentGroupId`, `AdjustmentBasisReferenceId` → `Coupon`, `AdjustmentTierId` → `PromotionTier`, `RelatedAdjustmentLineItemId` | — |

Shared picklists on the quote and order objects (ORG arm-picone, 2026-11-25):

- `AdjustmentSource`: `System`, `Discretionary`, `Promotion`, `Rule`
- `AdjustmentAmountScope`: `Unit`, `Total`, `UnproratedTotal`
- `AdjustmentType`: `AdjustmentPercentage`→Percentage, `AdjustmentAmount`→Amount,
  `OverrideAmount`→Override
- `AdjustmentAction`: `New`, `Existing` (read-only on both)

`AssetActionSrcPriceAdjustment` is insert-only: every field is `updateable: false`.

**`AdjustmentTierId` on the order object points at `PromotionTier`, not
`PriceAdjustmentTier`.** The price adjustment tier is reached through `AdjustmentCauseId`.
Two lookups whose names suggest the opposite of what they do.

## Downstream: an adjustment can bill and invoice on its own line

DOCS, Billing. `OrderItemAdjustmentLineItem` is a first-class billing source, not merely a
number folded into the order item's price:

- `BillingSchedule.ReferenceEntityItemId` refers to `OrderItem` **or**
  `OrderItemAdjustmentLineItem`.
- `InvoiceLine.ReferenceEntityItemId` — "The order item or adjustment item that created the
  invoice line" — refers to the same two.
- `BillingForecast.ReferenceEntityItemId` and `InvoiceLine.GroupReferenceEntityItemId`
  refer to `DebitMemoLine`, `OrderItem`, `OrderItemAdjustmentLineItem`, `OrderItemDetail`,
  `QuoteLineDetail` and `QuoteLineItem`.
- The Place Billing Schedule API's `TransactionId__std` parameter accepts an
  `OrderItemAdjustmentLineItem` id, and populates `BillingSchedule.ReferenceEntityItemId`
  when it does.

Neither `OrderItemAdjustmentLineItem` nor `QuoteLinePriceAdjustment` has a field reference
section anywhere in the 2555-page v68 guide. The first appears only in polymorphic
relationship lists and the parameter table above; the second appears on one page, inside a
sample Place Sales Transaction payload posting `QuoteLineItemId`, `Name` and `Amount: -25`
— and `Amount` is not a field on the object in arm-picone, which has `TotalAmount`.

## Adjacent, and out of scope here

- `ContractItemPrice` (API 61.0+, DOCS) carries its own `AdjustmentMethod` with the same
  Range/Slab pair, plus `DiscountType` and `DiscountValue` per its history object. It
  prices a product **on a contract** rather than above a price book list price.
  `ContractItemPriceAdjTier` is its tier child. Both are empty in arm-picone.
- `RateAdjustmentByTier` and `RateAdjustmentByAttribute` are the rate-management twins of
  the tier and attribute objects, for usage rating. `AttributeBasedAdjRule.UsageType =
  Rating` is the same rule object serving that side. Rate cards are out of scope for this
  skill.
- `PriceBookEntryDerivedPrice` (API 61.0+, DOCS) derives a price from another product or
  asset. That is a different mechanism from adjusting one.

## Read-only verification queries

Run these yourself against the org being designed for. None of them writes.

```sql
-- Every schedule, with its scope and its method.
SELECT Id, Name, ScheduleType, AdjustmentMethod, IsActive, Pricebook2Id, ContractId
FROM PriceAdjustmentSchedule ORDER BY ScheduleType

-- Does each schedule own the child type its ScheduleType implies? A Bundle or
-- Attribute schedule with PriceAdjustmentTier rows under it will not price.
SELECT PriceAdjustmentSchedule.ScheduleType, COUNT(Id)
FROM PriceAdjustmentTier GROUP BY PriceAdjustmentSchedule.ScheduleType

-- Tier bounds per product. Read every boundary against the UpperBound question
-- above: contiguity here depends on whether the bound is inclusive.
SELECT PriceAdjustmentSchedule.Name, Product2Id, LowerBound, UpperBound,
       TierType, TierValue, AdjustmentType, EffectiveFrom, EffectiveTo
FROM PriceAdjustmentTier
ORDER BY Product2Id, LowerBound

-- The attribute chain, end to end. A condition whose typed value column is null
-- for its attribute's data type is inert and raises nothing.
SELECT AttributeBasedAdjRuleId, AttributeDefinition.Name, AttributeDefinition.DataType,
       Operator, StringValue, IntegerValue, DoubleValue, BooleanValue, UsageType
FROM AttributeAdjustmentCondition ORDER BY AttributeBasedAdjRuleId

-- Which rules carry an adjustment, and which are orphaned.
SELECT AttributeBasedAdjRuleId, PriceAdjustmentSchedule.Name, AdjustmentType,
       AdjustmentValue, ProductId, AttributeCount, EffectiveFrom, EffectiveTo
FROM AttributeBasedAdjustment

-- Bundle path. ParentProductId equal to RootBundleId on every row means the
-- schema's parent/root distinction is unexercised in this org.
SELECT ProductId, ParentProductId, RootBundleId, AdjustmentType, AdjustmentValue,
       SellingModelType, EffectiveFrom
FROM BundleBasedAdjustment

-- Has anything ever actually priced through the configuration?
SELECT COUNT(Id) FROM QuoteLinePriceAdjustment
SELECT COUNT(Id) FROM OrderItemAdjustmentLineItem
SELECT COUNT(Id) FROM AssetActionSrcPriceAdjustment

-- Applied adjustments with their cause, once there are any. Note the field names
-- differ between the two objects; see the landing table above.
SELECT Id, QuoteLineItemId, AdjustmentType, AdjustmentValue, TotalAmount,
       AppliedAdjustmentAmount, AdjustmentSource, AdjustmentAmountScope,
       PriceAdjustmentCauseId, Priority
FROM QuoteLinePriceAdjustment

SELECT Id, OrderItemId, AdjustmentType, AdjustmentValue, Amount,
       AppliedAdjustmentAmount, AdjustmentSource, AdjustmentAmountScope,
       AdjustmentCauseId, Priority
FROM OrderItemAdjustmentLineItem
```
