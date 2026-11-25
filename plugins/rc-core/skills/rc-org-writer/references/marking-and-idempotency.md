# Marking and idempotency — what the org lets you prove

Sources: PLATFORM field metadata from a v68 describe across the 109 objects the pack
seeds, and the Revenue Lifecycle Management developer guide, v68 PDF, swept 2026-11-24.
Counts of objects are counts of the seed list, not of anyone's data.

The question this file answers: when this skill creates a record, what on that record
proves it was us? The answer is object by object, and for most objects it is **nothing**.

## The survey

Across the 109 objects the pack seeds and describes, PLATFORM (v68 describe):

| | Objects |
|---|---|
| a createable, `unique`, `idLookup` field exists — a real upsert key | 17 |
| no unique key, but `Name` is createable | 22 |
| neither — `Name` is autonumbered, read-only or absent | 70 |

70 of 109 can carry no marker on the record at all. That is the governing fact of this
contract, and the reason the run log is a first-class artifact rather than a convenience.

## Tier 1 — a real key

These 17 carry a field that is createable, unique and idLookup, so an upsert on it is
exactly once. Of the 17, **13 use a standard field** and 4 depend on a field that exists
in one org and is not part of Revenue Cloud:

**`GlobalKey`, 3 objects.** `PriceAdjustmentSchedule`, `Pricebook2`,
`ProductRelationshipType`. Createable, updateable, unique, idLookup, 80 characters. The
natural candidate, and it does resolve authorship and idempotency together — on three
objects. It is not a general mechanism; the pack shows it on nothing else.

**`Code`, 10 objects.** `AttributeCategory`, `AttributeDefinition`, `AttributePicklist`,
`AttributePicklistValue`, `ProductCatalog`, `ProductCategory`, `ProductClassification`,
`ProductComponentGroup`, `UnitOfMeasureClass`, `UsageResource`. Same properties.
Undocumented in the guide on `ProductComponentGroup` (see `rc-bundles`), present and
unique nonetheless.

**Org-specific, 4 objects.** `CreditMemo.CreditMemoNumber` is a document number the
platform assigns, not something to write. `Product2.Integration_Key__c` and
`Website_Request_Id__c` on `Order` and `Quote` are **custom fields in one org**. Do not
build the contract on them: a spec that keys `Product2` on `Integration_Key__c` works in
one org and fails everywhere else. If a target org has an equivalent, a spec may use it,
and must say so in `purpose`.

**`Product2` has no standard upsert key.** `ExternalId`, `ProductCode` and
`StockKeepingUnit` are all createable and updateable and all three are `unique: false,
idLookup: false` — plain text despite the names. `Name` is idLookup and not unique. So a
product cannot be upserted safely on a standard field, which makes products the most
dangerous thing a spec can create in a demo org.

## Tier 2 — a writable Name and nothing unique

22 objects. A reserved prefix in `Name` marks authorship and is queryable, so teardown can
find the records. It does **not** give idempotency: `Name` being idLookup without being
unique means a second apply can create a second record with the same name and the platform
will not object. Idempotency on tier 2 is query-then-skip, which is adequate for a single
operator and is not safe against two runs at once. Say so rather than implying otherwise.

Examples a build skill meets: `ProductSellingModel`, `AttributeBasedAdjRule`,
`ProductComponentGroup` is tier 1 via `Code`, and `Product2` sits here in practice.

## Tier 3 — nothing fits on the record

70 objects, and they are overwhelmingly the junctions and children a build skill creates
most of. The ones that matter here, with why the marker fails:

| Object | `Name` | Consequence |
|---|---|---|
| `PriceAdjustmentTier` | autonumber | tiers cannot be marked; inherit from the schedule |
| `ProductRelatedComponent` | createable false | components cannot be marked; inherit from the group or the bundle |
| `ProductSellingModelOption` | autonumber | the junction cannot be marked |
| `PricebookEntry` | not createable | prices cannot be marked |
| `AttributeBasedAdjustment` | autonumber | inherit from the rule or the schedule |
| `BundleBasedAdjustment` | autonumber | inherit from the schedule |
| `AttributeAdjustmentCondition` | autonumber | and it cannot be deleted at all — see below |
| `ProductCategoryProduct` | autonumber | the junction cannot be marked |

### Inheritance, and where it holds

A tier-3 record is ours when the record it hangs off is ours **and it cannot be moved
off it**. `PriceAdjustmentTier.PriceAdjustmentScheduleId` is required and createable but
not updateable — PLATFORM (v68 describe) — so a tier created under our schedule stays
under our schedule for life. That is a sound inheritance: delete the schedule's tiers at
teardown and you are deleting only ours.

It fails in one shape, and it is the shape that matters in a demo org. A
`ProductRelatedComponent` requires `ParentProductId`, and that parent is a `Product2`
which may well be pre-existing demo material. Such a component is ours by creation and
hangs off something that is not, so nothing on or above the record proves authorship. For
those, the log is the only evidence, and the spec should prefer attaching to a group this
run also created.

### `AttributeAdjustmentCondition` cannot be deleted

Per the developer guide, its supported calls omit `delete()` and `undelete()`, while its
parent `AttributeBasedAdjRule` has both. A spec that creates conditions cannot tear them
down directly: teardown deletes the rule and relies on the cascade, which is **not
verified** — nothing in the pack confirms the conditions go with it. Treat a spec that
creates attribute conditions as not cleanly reversible, and say so in its `purpose`.

## Create-only fields make correction a delete

A field that is createable and not updateable cannot be fixed in place. Known cases, all
PLATFORM (v68 describe):

| Field | Object |
|---|---|
| `PriceAdjustmentScheduleId` | `PriceAdjustmentTier` (2026-11-24) |
| `ParentProductId`, `ChildProductId`, `ChildProductClassificationId`, `ParentSellingModelId` | `ProductRelatedComponent` (2026-11-25) |
| `ParentProductId` | `ProductComponentGroup` (2026-11-25) |
| `MainProductRoleCat`, `AssociatedProductRoleCat` | `ProductRelationshipType` (2026-11-25) |
| `PriceAdjustmentScheduleId`, `AttributeBasedAdjRuleId`, `ProductId`, `ProductSellingModelId` | `AttributeBasedAdjustment` (2026-11-24) |
| `ProductId`, `ParentProductId`, `RootBundleId`, and the three selling-model lookups | `BundleBasedAdjustment` (2026-11-24) |

Read-only fields are a second class: `ParentProductRole`, `ChildProductRole`,
`UnitOfMeasureId` on `ProductRelatedComponent`, and the whole selling-model projection on
`PriceAdjustmentTier` (`ScheduleType`, `SellingModelType`, `PricingTerm`,
`PricingTermUnit`, `AdjustmentType`). A spec must not set these; verify must not report
them as differences when the platform fills them in.

## What verify has to tolerate

Field-by-field comparison between the spec and the org will differ for reasons that are
not errors. From the two build skills written so far:

- **Read-only projections fill themselves in.** A `PriceAdjustmentTier` comes back with
  `ScheduleType`, `SellingModelType`, `PricingTerm`, `PricingTermUnit` and
  `AdjustmentType` populated from the schedule and the selling model, none of which the
  spec set.
- **Labels are not values.** `PricingTermUnit` value `Annual` is labelled "Years"; every
  one of the nine role values differs from its label. Compare API values.
- **Defaults appear.** `QuantityScaleMethod` defaults to `Proportional`,
  `IsComponentRequired` and friends to `false`.
- **Numbers normalise.** A `double` sent as `5` returns as `5.0`.

Report these as *expected differences*, listed, rather than filtering them out silently. A
verify that prints nothing is indistinguishable from a verify that did not run.
