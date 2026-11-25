---
name: rc-pricing-adjustments
version: '0.1.0'
description: "How price is built above list price in Revenue Cloud Advanced: PriceAdjustmentSchedule and PriceAdjustmentTier, AttributeBasedAdjustment, BundleBasedAdjustment, Range against Slab, and where an applied adjustment lands on the quote, the order and the asset. Read this BEFORE building a discount tier, an attribute-priced product or a bundle discount. Use for \"volume discount\", \"tiered pricing\", \"discount for buying more\", \"price adjustment schedule\", \"Range or Slab\", \"why is this price what it is\", \"discount by product attribute\", \"cheaper inside the bundle\", \"TierType or AdjustmentType\", \"migrating CPQ discount schedules\". Read-only: never writes to an org. Not for base price per selling model (rc-catalog-selling-models), not for usage rate cards, promotions or coupons, and not for the knowledge pack (rc-context-pack)."
---

# Price adjustments in RCA — everything above the list price

List price answers "what does this cost". Everything that makes the number on the quote
differ from it lives in a small graph of five objects, and that graph has a design that
reads backwards: the object you create first, `PriceAdjustmentSchedule`, holds no product
and no adjustment. It is a container whose `ScheduleType` decides **which child table the
pricing engine reads**. Build a `Bundle` schedule and hang tiers off it and nothing
prices, with no error to tell you why.

This skill covers how to pick that type, how to pick the second and independent setting
that changes the arithmetic (`AdjustmentMethod`), and the four near-homonym field traps
that make a correct-looking adjustment produce a wrong number. It is read-and-design
work. **Nothing here writes to an org.** Where a step needs to look at an org, it looks at
the knowledge pack's describes, or at read-only SOQL you run yourself.

## Prerequisite

The knowledge pack at `~/.claude/knowledge/revenue-cloud/` must exist. Run
`rc-context-pack` first.

This skill leans on **both halves of the pack**, and the gap between them is wider here
than anywhere else in Revenue Cloud. The v68 developer guide documents the five setup
objects well and documents the two transaction objects **not at all** — neither
`QuoteLinePriceAdjustment` nor `OrderItemAdjustmentLineItem` has a field reference section
in 2555 pages. For those, an org describe is the only source there is.

The base price this skill adjusts is the subject of `rc-catalog-selling-models`. If the
question is "why are there two prices for this product", that skill owns it; a price
adjustment is not how you express a monthly-against-annual rate.

## Routing — what varies decides `ScheduleType`

Route on **what makes the price move**, never on the object's name. The customer describes
a behaviour; the behaviour maps to one of five values; the value selects a child table.

| What makes the price vary | `ScheduleType` | Child object to create |
|---|---|---|
| How many they buy | `Volume` | `PriceAdjustmentTier` |
| How long they commit for | `Term` | `PriceAdjustmentTier` |
| A property of the product or the customer | `Attribute` | `AttributeBasedAdjustment` + rule + conditions |
| Sitting inside a bundle | `Bundle` | `BundleBasedAdjustment` |
| Logic none of the above expresses | `Custom` | your own pricing logic |

In arm-picone (2026-11-25) the three schedules partition exactly this way: the `Volume`
schedule owns all 6 `PriceAdjustmentTier` rows and the `Attribute` and `Bundle` schedules
own zero tiers between them, carrying 4 `AttributeBasedAdjustment` and 4
`BundleBasedAdjustment` rows instead. The guide never states this mapping — it documents
the four objects separately and gives `ScheduleType` only as a picklist of five values.
`Term` and `Custom` are unexercised in that org, so their child object is inferred from the
shape of the other three rather than observed.

### Reading the requirement

- **"Cheaper if they buy more"** is `Volume`. The tier bounds are quantities.
- **"Cheaper if they sign for three years"** is `Term`. Do not reach for this when the
  requirement is a different *rate* for an annual against a monthly commitment — that is a
  second selling model and a second `PricebookEntry`, covered in
  `rc-catalog-selling-models`. `Term` adjusts a price that already exists.
- **"Enterprise costs more than Flex"** is `Attribute`, when those are values of a product
  attribute rather than separate products.
- **"The add-on is 15% off with the platform"** is `Bundle`.
- **`Custom`** is the honest answer when the logic is a calculation rather than a lookup.
  Choosing it is a decision to write code; do not choose it to avoid modelling.

## The second decision: `Range` or `Slab`

`AdjustmentMethod` sits on the schedule, is independent of `ScheduleType`, defaults to
`Range`, and **changes the resulting price with an identical set of tiers**. Per the
developer guide it is the method for applying tiered pricing:

- **`Range`** — "All items receive the discount of the highest tier the quantity falls in."
  The guide's worked case, on `ContractItemPrice.AdjustmentMethod`: "suppose that you give
  a 10% discount for 50 or more items. If a customer orders 50 products, and the type is
  range, apply the 10% discount to all 50 items."
- **`Slab`** — "Items receive the discount defined for the tier they fall in." The guide's
  worked case: "suppose that you order 30 products, and the type is slab, you can apply a
  10% discount to units 1–9, a 20% discount to units 10–19, and a 30% discount to units
  20–30."

So `Range` finds one tier and applies it to every unit. `Slab` splits the quantity across
bands and prices each band at its own rate.

### The same configuration, two prices

Take arm-picone's real tiers for product `01tfn000006KXZeAAO` (observed 2026-11-25) —
100–249 at 5%, 250–499 at 10%, 500 and up at 15% — and price 300 units at a $100 list
price. What follows is arithmetic I performed from the guide's definitions, not a run I
watched: no adjustment has ever been applied in that org. The band split also reads those
bounds as inclusive, which is the open question in **Trap 4**.

**`Range`.** 300 falls in the 250–499 tier, so 10% comes off all 300 units:

```
300 x $100 x 0.90 = $27,000
```

**`Slab`.** The 300 units split across the bands, and the first 99 fall below the
schedule's floor at no discount:

```
units   1- 99    99 x $100 x 1.00 = $ 9,900
units 100-249   150 x $100 x 0.95 = $14,250
units 250-300    51 x $100 x 0.90 = $ 4,590
                                    --------
                                    $28,740
```

**$1,740 apart on a $27,000 deal, from one picklist value.** The direction is worth
holding on to: where tier values rise with quantity, `Range` always costs the customer
less than or equal to `Slab`, because the best tier reached applies retroactively to
everything. A customer who says "volume discount" and means `Slab` will read a `Range`
quote as a pricing error.

### Migrating discount schedules from CPQ

The words `Range` and `Slab` are also the two values CPQ uses on its discount schedules,
and a migration that carries the word across without re-deriving the semantics is the
classic way this breaks: the configuration imports clean, every tier matches the source,
and every price is wrong by one band. **The pack holds no CPQ source**, so this skill
cannot tell you whether the two platforms agree on what each word means. Do not assume
they do. Re-derive the intended behaviour from the customer's actual prices — price one
real historical deal both ways and match it against what was invoiced — and treat the
CPQ field value as a hint. `rc-migrate` owns the mapping; this skill owns what the RCA
side does with it.

## Workflow

### 1. Ground in the org's actual surface

```bash
python3 plugins/rc-build/skills/rc-pricing-adjustments/scripts/adjustment_surface.py <org-alias>
```

It reads the pack's describes and prints the adjustment surface for that org: which
schedule types it carries, which child object each one needs and whether that object is
present, which field sets the adjustment type on each object and in which spelling, which
tier fields are a read-only projection, and where an applied adjustment lands. It writes
nothing and touches no org.

The script reports four objects as missing from the pack's seed list —
`AttributeBasedAdjRule`, `AttributeAdjustmentCondition`, `QuoteLinePriceAdjustment` and
`AssetActionSrcPriceAdjustment`. All four exist in arm-picone; the pack's sweep does not
describe them. Describe them in the target org before building against them.

### 2. Classify the requirement, then create the schedule

One schedule per adjustment policy, not per product. The schedule carries no product link
at all — not `Product2Id`, not `ProductSellingModelId`. Its scope is `Pricebook2Id`, and
arm-picone's describe also offers `ContractId`, which the guide does not document.

Product scoping happens on the child record, which means **one schedule serves many
products with disjoint tier sets**. arm-picone's single `Volume` schedule carries three
tiers for one product and three for another (2026-11-25). Name the schedule for the policy.

### 3. Set `AdjustmentMethod` deliberately

It defaults to `Range`. A schedule left at the default because nobody decided is the most
expensive unexamined field in this graph. All three arm-picone schedules are `Range`, so
`Slab` is unexercised there and this skill cannot show you a `Slab` run.

### 4. Build the children for that schedule type

**`Volume` and `Term` — tiers.** Per the developer guide: "Tiers can't overlap, and no gaps
are allowed between tiers." Set `Product2Id` and `ProductSellingModelId` on each tier to
scope it. `PriceAdjustmentScheduleId` is createable and not updateable in arm-picone, so a
tier cannot be moved to another schedule — delete and recreate.

Read **Trap 4** below before choosing bound values. It is the highest-risk number here.

**`Attribute` — a three-record chain.** `AttributeBasedAdjRule` holds the rule;
`AttributeAdjustmentCondition` holds one condition per attribute, pointing at an
`AttributeDefinition` with an `Operator` and a value in the typed column matching the
attribute's data type; `AttributeBasedAdjustment` ties the rule to the schedule, the
product and the selling model, and carries the adjustment itself.

arm-picone's chain (2026-11-25) is the canonical shape — one product, one picklist
attribute named `Type`, four values, four rules, four price overrides:

| Rule | Condition | Adjustment |
|---|---|---|
| `Rule_1724814105445` | `Type` equals `Flex` | `Override` 10,000 |
| `Rule_1724814147720` | `Type` equals `Pre-Prod` | `Override` 12,000 |
| `Rule_1724814176583` | `Type` equals `Prod` | `Override` 15,000 |
| `Rule_1724814263993` | `Type` equals `Gov` | `Override` 8,500 |

One rule per outcome, each with `AttributeCount` 1. A picklist attribute's value goes in
`StringValue`; the wrong typed column leaves the condition inert and raises nothing.

**`Bundle` — addressed by path.** `BundleBasedAdjustment` requires three product lookups,
all create-only in arm-picone: `ProductId` is the component being adjusted,
`ParentProductId` its immediate parent, `RootBundleId` the structural root. The same
component prices differently under a different root or a different parent. In arm-picone
all four records set parent equal to root, so nested depth is present in the schema and
unexercised in the data.

### 5. Set the adjustment type in the right field, in the right spelling

This is **Trap 1** below and it is the single most likely thing to go wrong. Read it before
writing any of these records.

### 6. Date the records

`EffectiveFrom` and `EffectiveTo` on the tier let tiers inside one schedule come into
effect on different dates. arm-picone uses this: three tiers run from 2023-01-01 and three
from 2026-01-01 under one schedule whose own `EffectiveFrom` is 2023-01-01 (2026-11-25).
A tier starting later than its schedule is a working configuration.

Two things to get right. `EffectiveFrom` is **required** on `AttributeBasedAdjustment` and
`BundleBasedAdjustment`, and nillable on the tier and the schedule (both halves of the pack
agree). And all four fields are `datetime`, not `date`: arm-picone's records carry
`2023-01-01T00:00:00Z`, `T08:00:00Z` and `T20:00:00Z` across objects that all read as
"effective 1 January". An adjustment set to start at midnight UTC starts mid-afternoon the
day before in an org running US Pacific time.

### 7. Verify the design before anyone builds it

Read-only SOQL. Run these yourself; this skill does not run them for you.

Two checks decide whether the design is real. The rest of the query set — tier bounds,
the attribute chain, bundle paths — is in `references/adjustment-field-map.md`.

```sql
-- A Bundle or Attribute schedule with tiers under it will not price.
SELECT PriceAdjustmentSchedule.ScheduleType, COUNT(Id)
FROM PriceAdjustmentTier GROUP BY PriceAdjustmentSchedule.ScheduleType

-- Has anything ever actually priced? Zeros mean the design is unproven.
SELECT COUNT(Id) FROM QuoteLinePriceAdjustment
SELECT COUNT(Id) FROM OrderItemAdjustmentLineItem
```

The second is the test that matters. In arm-picone both return zero, as does
`AssetActionSrcPriceAdjustment` (2026-11-25): the setup side is fully configured and
nothing has ever been priced through it. A configuration nobody has run is a hypothesis.

## The four traps

Full field inventory with writability in `references/adjustment-field-map.md`.

### Trap 1 — `AdjustmentType` means something different on every object

A field named `AdjustmentType` exists on five objects in this graph and does not mean the
same thing on any two of them. On `PriceAdjustmentTier` it is **read-only**; the field you
set there is `TierType`. And the two spellings of the values are not interchangeable.

| Object | Field you set | Values it accepts |
|---|---|---|
| `PriceAdjustmentTier` | `TierType` | `AdjustmentPercentage`, `AdjustmentAmount`, `OverrideAmount` |
| `AttributeBasedAdjustment` | `AdjustmentType` | `Percentage`, `Amount`, `Override` |
| `BundleBasedAdjustment` | `AdjustmentType` | `Percentage`, `Amount`, `Override` |
| `QuoteLinePriceAdjustment` | `AdjustmentType` | `AdjustmentPercentage`, `AdjustmentAmount`, `OverrideAmount` |
| `OrderItemAdjustmentLineItem` | `AdjustmentType` | `AdjustmentPercentage`, `AdjustmentAmount`, `OverrideAmount` |

Which of `TierType` and `AdjustmentType` governs on the tier is not a judgement call. In
arm-picone's describe (2026-11-24) `TierType` is required, createable and updateable, while
`AdjustmentType` is createable=false, updateable=false and calculated=false — you cannot
write it. The guide agrees from the other direction: it documents `TierType` with its
values and documents the tier's `AdjustmentType` with **no possible values at all**. All 6
tiers in that org carry `TierType = AdjustmentPercentage` alongside `AdjustmentType =
Percentage`, which is the first field's *label*, maintained by the platform.

**Do:** set `TierType` on a tier and never attempt its `AdjustmentType`. Use the bare
spelling on the attribute and bundle objects, the prefixed spelling on the transaction
objects. The rule that survives: the prefixed form is the engine's and the bare form is the
definition side's.

### Trap 2 — the tier's selling-model fields are a read-only projection

`PriceAdjustmentTier` carries `ScheduleType`, `SellingModelType`, `PricingTerm` and
`PricingTermUnit`, which look like denormalised copies of the parent inviting a "which one
wins if they diverge" question. They cannot diverge by your action: all four are
createable=false and updateable=false in arm-picone's describe (2026-11-24), and the guide
lists their properties without `Create` or `Update`.

Two corrections to the natural reading of that list. Only `ScheduleType` is a field the
schedule also has. `SellingModelType`, `PricingTerm`, `PricingTermUnit`, `Product2Id` and
`ProductSellingModelId` **are not on `PriceAdjustmentSchedule` at all**, so four of the five
are not copies of anything above them — they are a projection of the
`ProductSellingModel` the tier points at, and `Product2Id` and `ProductSellingModelId` are
the tier's own writable scoping.

**Do:** scope on the child record and treat the projection as read-back. Do not build a load
file or an integration that writes those four fields; the write is dropped, not merged.
Whether the projection refreshes when the referenced selling model is edited later is
untested — they are not formula fields, so staleness is possible.

### Trap 3 — `PricingTermUnit` value `Annual` is labelled `Years`

On the tier and on both adjustment objects, the `PricingTermUnit` picklist pairs the value
`Annual` with the label `Years`. Every other value's label equals its value. Both halves of
the pack agree, so this is product-wide and not an org quirk: arm-picone's describe
(2026-11-24) shows the pairing, and the guide writes it the same way — "Possible values are
Annual—Years or Months".

**Do:** match on the API value `Annual`. A filter, validation rule, flow decision or
integration mapping written against the label matches nothing. `TierType` has the same
shape — labels `Percentage`, `Amount`, `Override` over the prefixed values — which is
exactly why Trap 1 is easy to walk into from a screenshot of the UI.

### Trap 4 — `UpperBound` is documented exclusive, and the org contradicts it

The guide is explicit twice. On `UpperBound`: "Must be a positive integer. Not inclusive.
Set this value one digit higher than the quantity you want the tier to include. For example,
if a tier's upper bound is 99, set the value of UpperBound to 100." And under Usage: "Tiers
can't overlap, and no gaps are allowed between tiers."

arm-picone's six active tiers are built as though the bound were inclusive and gaps were
allowed (observed 2026-11-25):

| Product | Tiers, `LowerBound`–`UpperBound` |
|---|---|
| `01tfn000006KYg8AAG` | 5–10, 11–15, 16–open |
| `01tfn000006KXZeAAO` | 100–249, 250–499, 500–open |

Read with an exclusive upper bound, quantity 10 falls in no tier at all — the first band
ends at 9 and the second starts at 11 — and neither set covers quantity 1. Read as
inclusive, both sets are contiguous from their floor up. Both schedules are active.

**Do:** do not settle this by reading, including by reading this skill. Price one
transaction at each boundary quantity in a sandbox and read the adjustment that comes back.
Until then treat a tier boundary as the highest-risk number in the configuration: an
off-by-one here misprices exactly one quantity per band, produces a plausible invoice, and
no validation catches it.

## Where the adjustment lands — the answer to "why is this price what it is"

An applied adjustment is recorded on three objects, and the cause lookup and the money
field are spelled differently on each (arm-picone describes, 2026-11-25).

| Concern | `QuoteLinePriceAdjustment` | `OrderItemAdjustmentLineItem` | `AssetActionSrcPriceAdjustment` |
|---|---|---|---|
| Line FK | `QuoteLineItemId` | `OrderItemId` | `AssetActionSourceId` |
| Cause | `PriceAdjustmentCauseId` | `AdjustmentCauseId` | `PriceAdjustmentCauseId` |
| Cause targets | tier, promotion | tier, promotion | **promotion only** |
| Money | `TotalAmount` | `Amount` | `AdjustmentValue` |
| Source | `AdjustmentSource` | `AdjustmentSource` | `PriceAdjustmentSource` |
| Priority | `Priority` | `Priority` | `PrioritySequence` |

`AdjustmentSource` on the quote and order objects holds `System`, `Discretionary`,
`Promotion` and `Rule` — which is how a tier-driven price is told apart from a rep's
override. `AdjustmentAmountScope` holds `Unit`, `Total` and `UnproratedTotal`. Two
consequences worth designing around:

**The tier reference does not survive into the asset.** `PriceAdjustmentCauseId` on
`AssetActionSrcPriceAdjustment` references `Promotion` only, where its quote and order
namesakes reference `PriceAdjustmentTier` as well. If "which tier produced this price" has
to be answerable after activation, capture it before the asset is created.

**An adjustment can bill on its own line.** Per the developer guide,
`BillingSchedule.ReferenceEntityItemId` and `InvoiceLine.ReferenceEntityItemId` both refer
to `OrderItem` **or** `OrderItemAdjustmentLineItem`, and the Place Billing Schedule API
accepts an `OrderItemAdjustmentLineItem` id directly. An adjustment is not only a number
folded into the order item's price.

One more rename, in the same table: `AdjustmentTierId` on the order object points at
`PromotionTier`, **not** `PriceAdjustmentTier`. The price adjustment tier is reached through
`AdjustmentCauseId`. Two lookups whose names suggest the opposite of what they do.

## Deltas — the guide and the org disagree

Recorded in full in `notes/price-adjustments.md` in the pack. The ones that change a
design:

**1. `ScheduleType` selects the child table, and the guide never says so.** Documented
above. The guide presents five picklist values and four sibling objects and leaves the
mapping to the reader.

**2. Neither transaction object has a field reference in the guide.**
`OrderItemAdjustmentLineItem` appears on 15 pages of the v68 PDF, every one a polymorphic
relationship list on another object or the Place Billing Schedule parameter table.
`QuoteLinePriceAdjustment` appears on exactly one page, inside a sample Place Sales
Transaction payload posting `QuoteLineItemId`, `Name` and `Amount: -25` — and `Amount` is
not a field on that object in arm-picone, which has `TotalAmount`. The sample is stale, or
the API accepts an alias; the pack cannot settle which.

**3. Org fields absent from the guide.** `PriceAdjustmentSchedule.ContractId` and
`.GlobalKey`; `AttributeBasedAdjustment.ScheduleType` and `.AttributeAdjConditionsHash`;
`BundleBasedAdjustment.ScheduleType`; and `Weekly` in `PricingTermUnit` on all three setup
objects. `ContractId` is the one that matters — it implies a contract-scoped adjustment
schedule alongside the price-book-scoped one, which is where contracted pricing would hang
off this graph. All three arm-picone schedules scope by `Pricebook2Id` and none sets it.

**4. The guide lists `TierType`'s values twice in one paragraph**, and the first list omits
`OverrideAmount`. A reader who stops at the first sentence concludes that override pricing
is not available on a tier. It is, in both halves of the pack.

**5. `AttributeAdjustmentCondition` cannot be deleted.** Its supported calls in the guide
omit `delete()` and `undelete()`, while its parent `AttributeBasedAdjRule` has both. Retire
an attribute rule by deleting the rule, not its conditions.

Precedence applied throughout: ORG wins for what this org has, DOCS wins for what the
product supports in general.

## Verified anchors

- **DOCS** — `PriceAdjustmentSchedule` "represents a series of tiered discounts based on the
  number of items purchased"; `PriceAdjustmentTier` "represents a discount tier in a price
  adjustment schedule". Both available in API version 60.0 and later, as are
  `AttributeBasedAdjustment`, `BundleBasedAdjustment`, `AttributeBasedAdjRule` and
  `AttributeAdjustmentCondition`. (Salesforce Pricing Standard Objects)
- **DOCS** — `AdjustmentMethod`: `Range` gives all items the discount of the highest tier the
  quantity falls in; `Slab` gives items the discount defined for the tier they fall in.
  Default `Range`. (Salesforce Pricing → PriceAdjustmentSchedule, and the worked examples on
  Transaction Management → ContractItemPrice)
- **DOCS** — Tiers can't overlap and no gaps are allowed between them; `UpperBound` is not
  inclusive and is optional on the last tier. (Salesforce Pricing → PriceAdjustmentTier, Usage)
- **DOCS** — `AttributeAdjustmentCondition.Operator` accepts nine operators, defaulting to
  `equals`; `UsageType` on the rule and the condition discriminates `Pricing` from `Rating`.
  The nine are listed in `references/adjustment-field-map.md`. (Salesforce Pricing)
- **DOCS** — `BillingSchedule.ReferenceEntityItemId` and `InvoiceLine.ReferenceEntityItemId`
  refer to `OrderItem` or `OrderItemAdjustmentLineItem`; the Place Billing Schedule
  `TransactionId__std` parameter accepts the latter. (Billing)
- **ORG arm-picone, 2026-11-24 describe** — on `PriceAdjustmentTier`, `TierType` is required
  and writable while `AdjustmentType`, `ScheduleType`, `SellingModelType`, `PricingTerm` and
  `PricingTermUnit` are createable=false and updateable=false; `PriceAdjustmentScheduleId` is
  createable and not updateable; `PricingTermUnit` pairs value `Annual` with label `Years`
  and adds `Weekly`.
- **ORG arm-picone, 2026-11-25 SOQL** — 3 schedules (`Volume`, `Attribute`, `Bundle`, all
  `Range`, all active, all scoped by one price book, none by contract); 6 tiers under the
  `Volume` schedule across 2 products; 4 `AttributeBasedAdjustment` + 4 rules + 4 conditions
  under the `Attribute` schedule; 4 `BundleBasedAdjustment` under the `Bundle` schedule; and
  **zero** rows in `QuoteLinePriceAdjustment`, `OrderItemAdjustmentLineItem`,
  `AssetActionSrcPriceAdjustment`, `ContractItemPrice` and `ContractItemPriceAdjTier`.
- **ORG arm-picone, 2026-11-25 describe** — the quote, order and asset-action adjustment
  objects rename the cause lookup, the money field, the source and the priority as tabulated
  above; `AssetActionSrcPriceAdjustment.PriceAdjustmentCauseId` references `Promotion` only
  and every field on that object is updateable=false.

## Not verified

- **No adjustment has ever been applied in arm-picone.** Three empty transaction objects,
  confirmed by count. Every claim in this skill about what the engine *computes* — Range
  against Slab arithmetic, tier boundary behaviour, which record wins when two match — rests
  on the guide's prose and the object graph, never on a run. The `Range`/`Slab` worked example
  above is arithmetic performed by me from the guide's definitions.
- **Whether `UpperBound` behaves as exclusive.** Trap 4. The guide says exclusive, the org's
  own tiers are built inclusive, and the org has never priced. This is the gap most likely to
  cost money and I could not close it from the pack.
- **`Slab`, `Term` and `Custom` are all unexercised.** All three arm-picone schedules are
  `Range`, and none is `Term` or `Custom`, so the child object for those two types is inferred
  from the other three rather than observed. A `Term` schedule carrying `PriceAdjustmentTier`
  is the reasonable reading; confirm before building on it.
- **Nested bundle depth is unexercised.** All four `BundleBasedAdjustment` rows set
  `ParentProductId` equal to `RootBundleId`, so the schema distinguishes parent from root and
  the data does not exercise it.
- **Two arm-picone bundle adjustments look like duplicates** — `00000001` and `00000002`
  share product, parent, root, type, value and `EffectiveFrom`. What the engine does with two
  matching adjustments is not something the pack answers.
- **`UsageType` is null on all four attribute rules and all four conditions.** The guide gives
  `Pricing` and `Rating` as the values and the rule's copy is writable. Set `Pricing` on new
  rules, but these four nulls are the org's only working example, so whether null behaves
  identically is untested.
- **Whether the read-only projection goes stale.** The four projected tier fields are not
  formula fields. Nothing in the pack says what happens to them when the referenced
  `ProductSellingModel` is edited afterwards.
- **arm-picone is one dev org, and a sparse one.** 3 schedules and 6 tiers is barely a
  configuration. The four traps are structural — they come from field metadata and the guide,
  which travel across orgs — but every count, every bound and every worked value here is a
  single observation from an org seeded by a tool in August 2024.

## Guardrails

- **Never create a child object that does not match the schedule's `ScheduleType`.** Tiers
  under a `Bundle` schedule do not price and raise nothing.
- **Never write `AdjustmentType` on a `PriceAdjustmentTier`.** Set `TierType`. Check the
  spelling against Trap 1's table every time; the two value sets look interchangeable and are
  not.
- **Never trust a tier boundary you have not priced.** Trap 4 is unresolved, and it is the
  one that produces a wrong invoice rather than an error.
- **Never carry `AdjustmentMethod` across from CPQ on the strength of the shared word.**
  Re-derive it from prices the customer has actually been invoiced.
- **Never map the quote adjustment to the order adjustment by field name.** The cause lookup
  and the money field are renamed, and `AdjustmentTierId` points somewhere else entirely.
- **Do not express a monthly-against-annual rate difference as a price adjustment.** That is a
  second selling model; see `rc-catalog-selling-models`.
- **Do not promote arm-picone's configuration to doctrine.** It is a dev org whose adjustment
  records were autogenerated and never used.
- **This skill writes nothing.** No records, no metadata, no org changes. If a task needs a
  write, it belongs in a skill that declares one, with a preview step and a rollback.
