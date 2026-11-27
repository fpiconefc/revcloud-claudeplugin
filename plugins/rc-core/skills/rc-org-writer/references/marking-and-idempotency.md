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

## Why the spec looks the way it does

Two design choices that the body states without arguing, recorded here with the argument.

### `@alias` rather than the alternatives

A spec is written before anything exists, so it cannot name Ids: they are assigned by the
platform during apply. Every relationship is therefore declared against an `alias` that
another record in the same spec carries, and written `@alias` wherever an Id would go.

`@alias` rather than the alternatives, for three reasons. A Salesforce Id is 15 or 18
alphanumeric characters and can never begin with `@`, so a reference is impossible to
confuse with a literal — which lets the validator flag a literal Id as the mistake it
usually is. YAML's own anchors and aliases (`&name`, `*name`) look right and are wrong: they
copy a *value* at parse time, and what is needed is a reference to a record that does not
exist yet. And `${alias}` collides with shell and templating tools that a spec will pass
through.

### A constrained YAML subset

Scripts here run with no third-party dependencies, and PyYAML is not available. The spec is
therefore a deliberately small YAML subset: mappings, one nested level, lists of mappings
under `lookups` and `records`, scalars, and `>` for the purpose block. No anchors, no flow style, no
multi-line scalars elsewhere. `validate_spec.py` errors with a line number on anything
outside it rather than guessing — a spec is a contract document, and a parser that guesses at
a contract is worse than one that refuses.

## Resolving a record the spec does not create

A `lookups` entry identifies an existing record by a `where` clause rather than an Id, so the
spec stays portable between orgs. Whether that clause is trustworthy is the same question as
tier 1 above, asked from the other direction.

**A stable key** is a field that is createable, unique and idLookup — the 17 objects listed
above, of which 13 use the standard `Code` or `GlobalKey`. A `where` on one of those resolves
to the same record in any org that has it, and nothing can quietly make it ambiguous later.

**A soft key** is anything else, and it is the common case for the object specs reference
most. `Product2` has no standard unique field at all: `ProductCode`, `StockKeepingUnit` and
`ExternalId` are each `unique: false, idLookup: false` — PLATFORM (v68 describe). A query on
`ProductCode` returning exactly one row is a fact about the org right now, not a constraint
the platform will keep.

The contract handles that in three parts rather than forbidding it:

1. **Preview fails unless the clause matches exactly one record.** Zero and two are both
   errors. This is the only moment the resolution is allowed to be ambiguous, and it is
   resolved by stopping.
2. **Apply pins the resolved Id in the run log.** Verify and teardown read that Id and never
   re-run the `where`. A second product acquiring the same code afterwards cannot redirect a
   later phase at a record the run never touched.
3. **The validator warns once per lookup, not once per reference.** A spec with two products
   and ten components produces two warnings rather than twenty, which is what keeps the
   warning worth reading.

Looked-up records never enter the log as created rows, so teardown cannot reach them. That is
structural: the delete list is the log, and they are not in it.

Fields usable in a `where` clause must be filterable; the validator checks that against the
describe and rejects a clause naming a field the object does not have.

## Why there is no upsert

Tier 1 objects carry a unique, idLookup key, and Salesforce offers an upsert against exactly
that kind of field. The cycle does not use it, for a reason worth stating rather than
leaving as an omission.

**An upsert that finds an existing record updates it.** That record was created by some
earlier run, or by a person, and the ownership rule {D} never modify or delete a record this
run did not create {D} has no exception for "but it matches my key". Upsert and that rule
cannot both hold. The cycle keeps the rule.

What replaces it is weaker and honest. `apply.py` inserts. A second run against the same spec
is caught by preview's existence query, and if preview is skipped the platform's unique index
refuses the insert:

> duplicate value found: GlobalKey duplicates value on record with id: ...

Observed 2026-11-26 by re-running a spec whose schedule already existed: apply stopped there
and created nothing. So **a second run cannot duplicate, and it is an error rather than a
no-op.** A caller wanting re-runnable behaviour tears down and re-applies, which is the same
answer the cycle gives for correction.

### What the no-op does and does not mean

Preview classifies a record that already exists as a **no-op** when it matches the spec field
for field, and as a **conflict** when it differs. Two limits on that, both of which belong in
the caller's head.

**It is only available where a record has a unique key.** Those are the tier-1 objects, and
they are the only ones where "does this already exist?" has an answer that does not depend on
the log. A tier-3 record carries nothing to find it by, so the log remains its sole authority
and no no-op is possible for it.

That asymmetry has a consequence a spec runs into immediately. A spec with a keyed parent and
unkeyed children — a schedule and its tiers, a group and its components — cannot be
half-skipped. If the parent is a no-op and the children cannot be checked, applying would
create the children a second time, so preview stops instead of reporting a clean no-op. The
fix is to tear the earlier run down from its log and re-apply, or to split the spec.

**A no-op is not idempotency in the strong sense.** It says the state matches *now*. It does
not say this run produced it, and it cannot: a record another run created, or one a person
edited into a matching state, is indistinguishable from one this spec made. What the no-op
buys is the knowledge that applying would change nothing — which is what the caller wanted
to know, and is weaker than "this ran before".

## Why there is no update path

Apply creates. Correction deletes and recreates. **The cycle has no phase that modifies a
record, including one it created itself**, and the guardrail is absolute rather than a
default with exceptions, because "update is fine when I am sure" is how a write cycle stops
being reversible. A delete-and-recreate leaves the log the authority on what exists; an
in-place edit leaves the log describing a record that no longer matches it.

The create-only fields make this cheap most of the time — a tier's schedule lookup, every
product lookup on a component, both role categories on a relationship type. Those could not
be edited anyway.

**The case that argues against the rule** is real: create a schedule inactive, load its
tiers, then activate it so the configuration is never live half-built. That flip is an update
to a record this run created, and the contract does not express it.

**It is out of scope, and the same result is available.** Build the spec inactive, preview,
apply, verify, then have a human activate the one field having read the verify output. That
is a decision made with the evidence in hand rather than a step a script performs, which is
the right shape for the moment a configuration goes live — note it in `purpose` so the next
reader knows the spec alone does not leave the org finished.

What this rules out is a spec that is a sequence of states. That needs a different contract,
and inventing one inside a build skill is how the loosest standard wins.

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
  **five** fields the spec never set — `AdjustmentType`, `ScheduleType`, `SellingModelType`,
  `PricingTerm` and `PricingTermUnit` — projected from the schedule and the selling model.
  Observed on a real create, API v68. `ProductRelatedComponent` has three of its own
  (`ParentProductRole`, `ChildProductRole`, `UnitOfMeasureId`), and the attribute and bundle
  adjustment objects four or more each; `verify.py` carries the per-object list.
- **Autonumbered names arrive unasked.** A tier's `Name` came back `PAT-0000000007`. The
  sequence does not reset when records are deleted, so a torn-down run leaves a permanent gap
  and name continuity is not evidence that nothing ran.
- **Labels are not values.** `PricingTermUnit` value `Annual` is labelled "Years"; every
  one of the nine role values differs from its label. Compare API values.
- **Defaults appear.** `QuantityScaleMethod` defaults to `Proportional`,
  `IsComponentRequired` and friends to `false`.
- **Numbers normalise.** A `double` sent as `5` returns as `5.0`.
- **Datetimes come back in a different notation.** `2027-01-01T00:00:00.000Z` sent returns as
  `2027-01-01T00:00:00.000+0000`: identical instant, different string, and a literal
  comparison reports a difference that is not one. Compare datetimes by value;
  `_orgio.same_instant` is what `verify.py` uses.

Report these as *expected differences*, listed, rather than filtering them out silently. A
verify that prints nothing is indistinguishable from a verify that did not run.
