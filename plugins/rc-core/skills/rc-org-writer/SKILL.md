---
name: rc-org-writer
version: '0.1.0'
writes: true
description: "The contract every skill that writes to a Revenue Cloud org must follow: the YAML spec format, the preview / apply / verify / teardown cycle, how a created record is marked so it can be found again, idempotency, and why create-only fields make correction a delete-and-recreate. Read this BEFORE any skill creates, updates or deletes a record in an org, and before writing a build skill that will. Use for \"create these records in the org\", \"apply this configuration\", \"load a price adjustment schedule\", \"build it in the sandbox\", \"undo what you just created\", \"clean up the demo org\", \"is this safe to run twice\", \"how do we write to an org here\". This skill writes to an org, under the cycle below. Not for running transactions or reading what a quote priced, and not for domain doctrine (rc-catalog-selling-models, rc-pricing-adjustments, rc-bundles)."
---

# Writing to an org — the contract

Every other skill in this repository ends with the same line: it writes nothing. This one
inverts that, and the inversion needs justifying rather than assuming.

Reading an org answers questions. Building in one is how you find out whether a design
actually works — whether the tier boundary prices the way the guide says, whether the flag
combination configures. That evidence cannot be got by reading, and the pack is full of
claims marked unvalidated precisely because nobody has run them. So writing is permitted
here, and permitted **only** through the cycle below, because a build skill that invents its
own level of care sets the standard for every skill after it, and the loosest one is the one
that eventually bites.

What makes this safe is not caution. It is that **everything this skill creates can be
found again and removed.** A write you cannot reverse is not a test, it is a change.

## Prerequisite

The knowledge pack at `~/.claude/knowledge/revenue-cloud/` must exist, with a fingerprint of
the **target** org. Run `rc-context-pack` first.

This is not a formality here. The spec validator reads the target org's describes to work
out how each record can be marked and whether a field is writable at all. Against an org
with no fingerprint it degrades to checking syntax, and says so.

## Scope, and the line that matters most

This skill creates **configuration** by DML: schedules, tiers, groups, components,
relationship types, selling models. That is its whole job.

**It does not run transactions.** Place Sales Transaction, placing a quote, reading which
adjustment landed on `QuoteLinePriceAdjustment` or `OrderItemAdjustmentLineItem` — none of
that is here. Those belong to a testing skill that does not exist yet, and when it does it
will depend on this one for the configuration it exercises. Until then, a spec builds the
setup side and a human drives the transaction.

The distinction is not pedantry. Configuration DML is reversible by deleting records.
A transaction creates assets, billing schedules and order items whose removal is a different
problem entirely, and nothing in this contract covers it.

## The target, and what the real risk is

The working target is a **demo org** with catalogs, selling models, components and billing
schedules loaded and in use. The risk there is not breaking production. It is
**dirtying or overwriting demo material** — leaving half-built records in a catalog someone
is about to present, or editing a record that was already doing a job.

That is why teardown is not an extra. Teardown is what turns a demo org into a repeatable
test bench: a spec that applies and tears down cleanly can be run on a Monday and again on a
Friday, and the org is the same org afterwards.

## The spec

One declarative YAML file describing what must exist. It is the single input to all four
phases — preview, apply and verify read the same file, which is what makes the phases
comparable to each other. `assets/spec-template.yaml` is the shape:

```yaml
spec: rc-org-writer/v1
target:
  org: <target-org-alias>
author: <who is accountable>
created: '2026-11-25'
purpose: >
  Why these records should exist.
marker:
  token: RCW-20261125-A
records:
  - alias: sched
    object: PriceAdjustmentSchedule
    key: GlobalKey
    fields:
      Name: RCW-20261125-A volume policy
      GlobalKey: RCW-20261125-A-sched
      ScheduleType: Volume
      AdjustmentMethod: Range
      IsActive: true
  - alias: tier_low
    object: PriceAdjustmentTier
    marked_by: sched
    fields:
      PriceAdjustmentScheduleId: '@sched'
      LowerBound: 100
      UpperBound: 250
      TierType: AdjustmentPercentage
      TierValue: 5
```

### Why references are `@alias` and not Ids

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

A literal Id in a spec is not forbidden — sometimes a new tier genuinely belongs under an
existing schedule — but the validator warns on every one, because an Id is a record **this
run does not own** and therefore must not modify or delete.

### The subset, and why it is constrained

Scripts here run with no third-party dependencies, and PyYAML is not available. The spec is
therefore a deliberately small YAML subset: mappings, one nested level, a list of mappings
under `records`, scalars, and `>` for the purpose block. No anchors, no flow style, no
multi-line scalars elsewhere. `validate_spec.py` errors with a line number on anything
outside it rather than guessing — a spec is a contract document, and a parser that guesses at
a contract is worse than one that refuses.

## The cycle

Four phases, in order, every time.

### 1. preview — never skipped

```bash
python3 plugins/rc-core/skills/rc-org-writer/scripts/validate_spec.py <spec.yaml>
```

Reads the spec, validates it, resolves the references, orders the records by dependency, and
prints every record it would create with every value. **It does not touch the org.**

It checks what can be checked offline: the spec version and metadata, that aliases are unique
and every `@alias` resolves, that there is no reference cycle, that each record declares a
marking route its object actually supports, that a declared `key` is genuinely unique and
idLookup on that object, that the marker token is present where it belongs, and that no field
carries a literal Id unflagged.

Then preview against the org: for each record, query whether something matching its key or
its marked name already exists. A hit is reported and **stops the run**. Preview is also the
only phase a reader can review, so its output is the artifact to put in front of someone.

### 2. apply — only after explicit confirmation

Creates the records in the dependency order preview printed. It runs **only** after a human
has seen the preview and said yes to that specific preview. Not "yes to writing in general",
not a confirmation carried over from an earlier run: the preview and the confirmation are a
pair, and changing the spec voids the confirmation.

**The log is written as each record is created, not at the end.** One line per record, flushed
immediately:

```
applied/<spec-name>-<utc-timestamp>.jsonl
{"alias":"sched","object":"PriceAdjustmentSchedule","id":"84X...","marker":"RCW-20261125-A","at":"2026-11-25T18:04:11Z"}
```

Per record, because the run that matters is the one that fails halfway. A log written at the
end leaves an interrupted apply with records in the org and no record of them — which is
exactly the state teardown exists to prevent. Append-and-flush means an interrupted run is
still fully reversible.

If a create fails, apply stops. It does not continue past an error and it does not roll back
what it already made: the log plus teardown is the rollback, and it is a separate, confirmed
decision.

### 3. verify — read it back and compare

Re-queries every record in the log and compares it **field by field** against the spec.

A successful API response does not mean the configuration is what you asked for. Read-only
fields fill themselves in, defaults appear, numbers normalise, and a picklist's label is not
its value. So verify reports three categories and hides none of them:

- **matches** — the field is what the spec said.
- **expected differences** — a read-only projection the platform filled in, a default that
  appeared, `5` returned as `5.0`. Listed, not filtered. A verify that prints nothing is
  indistinguishable from one that did not run.
- **unexpected differences** — everything else. These are findings, and they are the reason
  the phase exists.

`references/marking-and-idempotency.md` lists the known expected differences, per object,
from the three build skills written so far.

### 4. teardown — exactly what this run created

Deletes the records in the log, **in reverse creation order**, and nothing else. Not
everything matching the marker, not everything in the object: the log is the authority,
because the log is the only thing that knows what this run made.

Reverse order because the dependencies that forced the apply order still hold: a schedule
cannot go while its tiers point at it.

Teardown is confirmed like apply, and reports what it could not remove —
`AttributeAdjustmentCondition` cannot be deleted at all, and anything whose delete fails stays
listed so a human can finish the job.

## Marking — how a record is known to be ours

Every record this skill creates must be identifiable as created by it. Which mechanism is
available is **per object**, and for most objects the answer is "none". Surveyed across the
109 objects the pack seeds and describes — PLATFORM (v68 describe):

| Route | Objects | Mechanism |
|---|---|---|
| **Tier 1** | 17 | a createable, unique, idLookup field: `GlobalKey` on 3, `Code` on 10, an org-specific custom field on 4 |
| **Tier 2** | 22 | no unique field, but `Name` is createable: a reserved prefix |
| **Tier 3** | 70 | `Name` is autonumbered, read-only or absent: nothing fits on the record |

**`GlobalKey` was the obvious candidate and it is not enough.** PLATFORM (v68 describe) has
it createable, updateable, unique and idLookup — so where it exists it solves authorship and
idempotency in one field, and an upsert on it is exactly once. It exists on three objects:
`PriceAdjustmentSchedule`, `Pricebook2` and `ProductRelationshipType`. `Code` behaves
identically on ten more. That is 13 objects with a standard key out of 109.

**Tier 3 is the common case, and it is the junctions.** `PriceAdjustmentTier`,
`ProductRelatedComponent`, `ProductSellingModelOption`, `PricebookEntry`,
`AttributeBasedAdjustment`, `BundleBasedAdjustment`, `ProductCategoryProduct` — the records a
build skill creates most of are precisely the ones that can carry no mark. So:

- A tier-3 record declares **`marked_by`**, naming a record in the same spec that can carry a
  marker and that this record's required lookup points at. Authorship is inherited.
- That inheritance is sound when the lookup is **create-only**, because the child then cannot
  be moved off its parent. `PriceAdjustmentTier.PriceAdjustmentScheduleId` is exactly this.
- It fails where the required parent is pre-existing. A `ProductRelatedComponent` needs a
  `ParentProductId`, and in a demo org that product is usually not ours. Such a record is ours
  by creation and hangs off something that is not, so **the log is the only evidence**. Prefer
  attaching to a group this run also created, and treat the rest as the named gap it is.

**`Product2` has no standard upsert key.** `ExternalId`, `ProductCode` and
`StockKeepingUnit` are all `unique: false, idLookup: false` — plain text despite the names.
That makes products the most dangerous thing a spec can create in a demo catalog, and a spec
that creates them says so in `purpose`.

## Guardrails

These are half the value of this skill. Each one is a rule the cycle enforces, not advice.

- **Preview before apply, always.** There is no path that writes without a preview a human
  has read.
- **Confirmation is per preview.** Editing the spec voids it. Approval to write once is not
  approval to write again.
- **Never modify or delete a record this run did not create.** If the spec asks for something
  that already exists, preview reports it and stops. It does not assume it may overwrite. This
  is the rule that protects demo material, and it has no exceptions.
- **Applying twice must not duplicate.** Tier 1 upserts on its key and is exactly once. Tier 2
  is query-then-skip, which is adequate for one operator and **is not safe against two
  concurrent runs** — say so rather than implying stronger.
- **Correction is delete-and-recreate, as the normal case.** Create-only fields are everywhere
  in this model: `PriceAdjustmentTier.PriceAdjustmentScheduleId`, every product lookup on
  `ProductRelatedComponent` and `BundleBasedAdjustment`, both role categories on
  `ProductRelationshipType`. A spec whose correction path assumes `update` works is wrong
  about the platform, not unlucky.
- **Never set a read-only field.** The selling-model projection on `PriceAdjustmentTier`,
  `ParentProductRole` and `ChildProductRole` on `ProductRelatedComponent`. Verify must expect
  the platform to fill them.
- **Teardown deletes from the log, never from a query.** "Everything matching the marker"
  would catch a record someone else created with the same prefix.
- **No catalog content invented into a demo org without saying so.** A spec that adds products
  to a live demo catalog is a change to someone's demo, whatever the marker says.
- **This skill does not run transactions.** See **Scope** above.

## Without a shell

claude.ai has no shell, and the Salesforce connector has `createSobjectRecord`,
`updateSobjectRecord` and `deleteSobjectRecord`. So the whole cycle is executable from a chat
session, which makes it **more** important that the guardrails live in this body and not only
in a script: in that branch there is no script, and this text is the entire contract.

Run the four phases the same way, by hand:

- **preview.** Parse the spec yourself and print the plan: every record, every field, the
  dependency order, and the marking route per object. Use `getObjectSchema` on each object to
  confirm the marking tier and that every field in the spec is createable — the validator's
  offline checks are what you are reproducing, and `references/marking-and-idempotency.md`
  has the per-object answers already worked out. Then `soqlQuery` for each record's key or
  marked name to prove it does not exist yet. Show all of it before asking.
- **apply.** `createSobjectRecord` in dependency order, after an explicit yes to that
  preview. **Write the log into the conversation as you go** — object, alias, returned Id,
  one line per record, immediately after each create. That transcript is the log, and it is
  the only thing a teardown will have. Do not batch the ids up and print them at the end: if
  the session is interrupted, what has been printed is what is recoverable.
- **verify.** `soqlQuery` each created Id back and compare field by field against the spec,
  reporting matches, expected differences and unexpected differences separately.
- **teardown.** `deleteSobjectRecord` in reverse order, from the ids in the transcript, and
  nothing else.

`updateSobjectRecord` is available in that branch and is **not** part of this cycle. Apply
creates; correction deletes and recreates. The one legitimate use is reversing a field the
platform normalised on a record this run created, and that is a finding to report before it
is a change to make.

## Verified anchors

Per-object detail, with the counts behind the tier table, in
`references/marking-and-idempotency.md`.

- **PLATFORM (v68 describe)** — of the 109 objects the pack seeds, 17 have a createable, unique,
  idLookup field; 22 have no such field but a createable `Name`; 70 have neither. `GlobalKey`
  is createable, updateable, unique, idLookup and 80 characters on `PriceAdjustmentSchedule`,
  `Pricebook2` and `ProductRelationshipType`, and appears on no other object in the pack.
  `Code` has the same properties on 10 objects.
- **PLATFORM (v68 describe)** — `Product2.ExternalId`, `.ProductCode` and
  `.StockKeepingUnit` are createable and updateable with `unique: false` and
  `idLookup: false`; `Product2.Name` is idLookup and not unique.
- **PLATFORM (v68 describe)** — `PriceAdjustmentTier.PriceAdjustmentScheduleId`
  is createable and not updateable, so a tier cannot be reparented.
- **PLATFORM (v68 describe)** — `ProductRelatedComponent.Name` is not createable;
  `ParentProductId`, `ChildProductId`, `ChildProductClassificationId` and
  `ParentSellingModelId` are createable and not updateable.
- **DOCS** — `AttributeAdjustmentCondition`'s supported calls omit `delete()` and
  `undelete()`, while `AttributeBasedAdjRule` has both. (Salesforce Pricing)

## Not verified

- **No spec has been applied to an org yet.** This contract is written from the describes and
  from what the three read-only build skills found. The cycle is unexercised end to end, and
  the first real apply should be a spec small enough to read in full.
- **Upsert-on-key has not been executed.** That `GlobalKey` and `Code` being unique and
  idLookup makes an upsert exactly once is read off the describe, not observed. Prove it with
  a two-record spec applied twice before relying on it.
- **Whether deleting `AttributeBasedAdjRule` cascades to its conditions.** The conditions
  cannot be deleted directly and nothing in the pack says what happens to them when the rule
  goes. A spec that creates attribute conditions is not known to be cleanly reversible.
- **Whether tier-2 query-then-skip is adequate in practice.** `Name` is idLookup and not
  unique, so the race is real in principle. How likely it is with one operator is a guess.
- **What the platform normalises.** The expected-difference list in the reference is
  assembled from field metadata and the other skills' findings, not from a verify run that
  produced them.
- **The 17/22/70 split counts the objects this pack seeds**, and four of the 17 rest on
  custom fields that exist in one org rather than in Revenue Cloud. An org with different
  custom fields splits differently, which is why the validator reads the target org's own
  describes rather than trusting this table.

## For a build skill that uses this one

Declare `writes: true` in your frontmatter, say in your description that you write to an org,
and name your preview, your confirmation and your teardown in your body. Do not re-implement
the cycle: emit a spec and run it through these phases. A build skill's job is knowing *what*
should exist in the org — that is domain doctrine, and it lives in `rc-catalog-selling-models`,
`rc-pricing-adjustments` and `rc-bundles`. Knowing how to put it there safely is this skill's
job, and there should be exactly one answer to it in the repository.
