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

## Scope, the target, and the line that matters most

This skill creates **configuration** by DML: schedules, tiers, groups, components,
relationship types, selling models. That is its whole job.

**It does not run transactions.** Place Sales Transaction, placing a quote, reading which
adjustment landed on `QuoteLinePriceAdjustment` — none of that is here. Those are
`rc-pricing-test`, which follows this contract and stops at the quote. Not pedantry:
configuration DML is reversible by deleting records, while a transaction creates assets and
billing schedules whose removal is a different problem this contract does not cover.

The working target is a **demo org** with catalogs, selling models, components and billing
schedules loaded and in use. The risk there is not breaking production; it is **dirtying or
overwriting demo material** — leaving half-built records in a catalog someone is about to
present, or editing a record that was already doing a job. That is why teardown is not an
extra. Teardown is what turns a demo org into a repeatable test bench: a spec that applies
and tears down cleanly can run on a Monday and again on a Friday, and the org is the same
org afterwards.

## The spec

One declarative YAML file describing what must exist. It is the single input to all four
phases — preview, apply and verify read the same file, which is what makes the phases
comparable to each other. `assets/spec-template.yaml` is the shape:

```yaml
spec: rc-org-writer/v1
target:
  org: <target-org-alias>
author: <who is accountable>
created: '2026-11-26'
purpose: >
  Why these records should exist.
marker:
  token: RCW-20261126-A
lookups:
  - alias: platform_bundle
    object: Product2
    where:
      ProductCode: PLAT-BUNDLE
records:
  - alias: support_group
    object: ProductComponentGroup
    key: Code
    fields:
      Name: RCW-20261126-A Support
      Code: RCW-20261126-A-support
      ParentProductId: '@platform_bundle'
      MinBundleComponents: 0
      MaxBundleComponents: 1
```

### Why references are `@alias` and not Ids

A spec is written before anything exists, so it cannot name Ids: the platform assigns them
during apply. Every relationship is declared against an `alias` another entry carries and
written `@alias` wherever an Id would go. A Salesforce Id can never begin with `@`, so a
reference is impossible to confuse with a literal — which is what lets the validator flag a
literal Id as the mistake it usually is. `references/marking-and-idempotency.md` records why
YAML's own anchors are the wrong tool here, and why the spec is a constrained subset rather
than general YAML.

### `lookups` — naming records that already exist

Most specs attach to something already in the org. A bundle spec needs `ParentProductId` and
`ChildProductId` on every component, pointing at products nobody is creating; ten components
is twenty such references.

Writing those as literal Ids breaks two things at once. The spec stops being portable — Ids
differ between sandbox and production, so a spec pinned to them runs in exactly one org,
which defeats half the reason for having a spec at all. And it buries the warning: a check
that fires twenty times on a correct spec teaches people to ignore the validator.

So a pre-existing record is declared under `lookups`, by a stable key rather than an Id, and
referenced with the same `@alias` syntax as anything the spec creates — the `lookups` block
in the template above is one. The rules are short, and two of them are absolute.

- **Preview resolves each lookup by query against the target org.** A lookup that matches
  nothing, or matches more than one record, **fails the preview and nothing is written.**
  There is no "pick the first" and no prompt to choose.
- **A looked-up record is never created, modified or deleted.** It is the "do not touch what
  this run did not create" rule in its purest form, and the shape enforces it: every log row
  carries a `kind`, apply writes lookups as `kind: lookup` and creations as `kind: created`,
  and teardown deletes only `created`. Ignoring a lookup is structural rather than a check
  that could be forgotten.
- **`marked_by` may not name a lookup.** Authorship is inherited only from a record this run
  creates; a pre-existing record carries no marker of ours.

On many objects nothing guarantees the `where` field is unique — `Product2.ProductCode` is
`unique: false, idLookup: false`, PLATFORM (v68 describe). The validator classifies each
lookup as a **stable** key or a **soft** one and allows both, since refusing soft keys would
rule out products entirely. A soft key warns **once per lookup rather than once per
reference**, and **apply pins the resolved Id in the log** so verify and teardown never re-run
the clause. `references/marking-and-idempotency.md` has the reasoning and the 13 objects with
a standard stable key.

With lookups available, a literal Id in a spec is not forbidden but is now genuinely rare,
and the validator still warns on each one — telling you to declare it as a lookup instead.
When that warning appears, it means something.

## The cycle

Four phases, in order, every time.

### 1. preview — never skipped

```bash
python3 plugins/rc-core/skills/rc-org-writer/scripts/validate_spec.py <spec.yaml> \
    --target-org <alias>
```

Reads the spec, validates it, resolves the references, orders the records by dependency, and
prints every record it would create with every value. **It does not touch the org.**

It checks what can be checked offline: the spec version and metadata, that aliases are unique
and every `@alias` resolves, that there is no reference cycle, that each record declares a
marking route its object actually supports, that a declared `key` is genuinely unique and
idLookup on that object, that the marker token is present where it belongs, and that no field
carries a literal Id unflagged.

`--target-org` runs the half that only the org can answer: **every lookup must resolve to
exactly one record**, and **every record the spec would create is classified into one of
three states**, not two.

| State | What preview does |
|---|---|
| does not exist | nothing to say; apply will create it |
| exists and **matches** field for field | reports a **no-op**, exits 0, writes nothing |
| exists and **differs** | **stops**, naming every differing field with both values |

Query-then-compare: it only reads, so it never writes over a record the run does not own, and
the third state is exactly what an upsert would have overwritten silently. The comparison is
`verify.py`'s applied before a create instead of after, imported from `_orgio.py` by both.

#### Can a spec be re-applied?

**For most specs, no, and the correction is still teardown then re-apply.** The reason is the
shape, not an edge case.

A build skill generates **a keyed parent with unkeyed children**: a schedule and its tiers, a
group and its components. The parent can be classified; the children carry nothing to find
them by — tier 3, where the log is the only authority — so they cannot be, and apply
would create them a second time.

Preview therefore stops on that mixture rather than reporting a clean no-op. **What the three
states buy for a mixed spec is a legible error naming the situation, in place of a
`DUPLICATE_VALUE` from the platform's index** — worth having, and a different thing from
being re-appliable.

The no-op is a real answer only for a spec whose records are **all** keyed, in practice a
small spec of parents, and even then it is **not idempotency in the strong sense**: it says
the state matches now, not that this run produced it.
`references/marking-and-idempotency.md` works through both limits.

Without `--target-org` it degrades to the offline checks and says so. That is not academic:
a spec whose lookup names a product the org lacks passes every offline check and fails at
apply. The offline pass says the spec is well formed, nothing more.

Preview is the only phase a reader can review, so its output is what to put in front of
someone.

### 2. apply — only after explicit confirmation

```bash
python3 plugins/rc-core/skills/rc-org-writer/scripts/apply.py <spec.yaml> \
    --target-org <alias> --log applied/<run>.jsonl --confirm
```

Creates the records in the dependency order preview printed. It runs **only** after a human
has seen the preview and said yes to that specific preview; `--confirm` stands for that, and
apply refuses without it. Not "yes to writing in general",
not a confirmation carried over from an earlier run: the preview and the confirmation are a
pair, and changing the spec voids the confirmation.

**The log is written as each record is created, not at the end.** One line per record, flushed
immediately:

```
applied/<spec-name>-<utc-timestamp>.jsonl
{"kind":"lookup","alias":"platform_bundle","object":"Product2","id":"01t...","where":{"ProductCode":"PLAT-BUNDLE"}}
{"kind":"created","alias":"sched","object":"PriceAdjustmentSchedule","id":"84X...","marker":"RCW-20261126-A"}
```

**Both kinds are recorded; only one is ever deleted.** A lookup is logged because verify and
teardown need the Id it resolved to and must never re-run the `where`; it is not deleted
because teardown filters on `kind: created`. Two different statements, which this body used
to blur into "lookups never enter the log".

Per record, because the run that matters is the one that fails halfway. A log written at the
end leaves an interrupted apply with records in the org and no record of them — which is
exactly the state teardown exists to prevent.

**Append-and-flush narrows that window to one record; it does not close it.** Between a
create returning an Id and the log line reaching disk, the record exists and the log does not
know it, so a kill exactly there leaves one orphan. Irreducible without a transaction the
platform does not offer: after an interrupted apply, query the target object for the marker
before re-running. It is one record, and the plan named which object.

**If a create fails, apply stops**, and the first hand-driven run is why that is a rule
rather than an assumption: a failed create did not stop the sequence, the following creates
ran anyway, and two log lines were written with an empty Id. A log that lies is worse than no
log, because teardown believes it. Apply stops at the first error and **writes no log line
for a create that returned no Id**. It does not roll back what it made — the log plus
teardown is the rollback, and that is a separate, confirmed decision.

### 3. verify — read it back and compare

```bash
python3 plugins/rc-core/skills/rc-org-writer/scripts/verify.py <spec.yaml> \
    --target-org <alias> --log applied/<run>.jsonl
```

Re-queries every record in the log and compares it **field by field** against the spec.

A successful API response does not mean the configuration is what you asked for. Read-only
fields fill themselves in, defaults appear, numbers normalise, and a picklist's label is not
its value. So verify reports three categories and hides none of them:

- **matches** — the field is what the spec said.
- **expected differences** — a read-only projection the platform filled in, a default that
  appeared, `5` returned as `5.0`. Listed, not filtered. A verify that prints nothing is
  indistinguishable from one that did not run.

  There are more of these than one would guess: a single `PriceAdjustmentTier` comes back
  with **five** fields nobody wrote, and `EffectiveFrom` sent as `...000Z` returns as
  `...000+0000`, the same instant written differently. **`verify.py` compares datetimes by
  value**, and `references/marking-and-idempotency.md` has the per-object list.
- **unexpected differences** — everything else. These are findings, and they are the reason
  the phase exists.

`references/marking-and-idempotency.md` lists the known expected differences, per object,
from the three build skills written so far.

### 4. teardown — exactly what this run created

```bash
python3 plugins/rc-core/skills/rc-org-writer/scripts/teardown.py \
    --target-org <alias> --log applied/<run>.jsonl --confirm
```

Deletes the log's `kind: created` rows, **in reverse creation order**, and nothing else. Not
everything matching the marker, not everything in the object: the log is the authority,
because the log is the only thing that knows what this run made. `--dry-run` prints the list
and stops.

It is **idempotent over its own log**: a record already gone is reported as such, not as an
error, so an interrupted teardown runs again cleanly and the same log twice deletes nothing
the second time. It deduplicates on Id, because a log can carry one record twice when a
command block is pasted twice — which is how that was found.

Reverse order because the dependencies that forced the apply order still hold: a schedule
cannot go while its tiers point at it.

Teardown is confirmed like apply, and reports what it could not remove —
`AttributeAdjustmentCondition` cannot be deleted at all, and anything whose delete fails stays
listed so a human can finish the job.

### The four scripts

One per phase. No third-party dependencies; `sf` is a subprocess and `--json` is how Ids are
captured. `_orgio.py` holds what apply, verify and teardown share — the `sf` calls, the log,
`@alias` resolution, the datetime comparison — and is not run directly.

| Script | Phase | Touches the org |
|---|---|---|
| `validate_spec.py` | preview | only with `--target-org`, read-only |
| `apply.py` | apply | writes, and only with `--confirm` |
| `verify.py` | verify | read-only |
| `teardown.py` | teardown | deletes, and only with `--confirm` |

## The describe is not the contract

`notes/` records twelve findings about what the platform does with a write. A describe states
three of them. The other nine are the class this section names. The inventory stays in the
pack — `notes/org-writing.md`, `notes/price-adjustments.md`, `notes/bundles.md`; what belongs
here is the shape, because a new skill has to recognise one before it has an instance of its
own.

| Shape | What happens | Found by | Checkable once known |
|---|---|---|---|
| **1 required, undeclared** (2) | the describe says `nillable: true`, the platform refuses the record without the field | a refused create | from the spec alone |
| **2 invalid combination** (4) | two lookups each resolve to a real record and are invalid together | a refused create | by querying the org, unless both records are in the spec |
| **3 accepted and discarded** (1) | the create returns success, the value does not persist, and an update does not fix it | reading the record back | not before the write |

**Shape 1**, one instance: *"Specify the Effective From date to save your price adjustment
tier."* — `PriceAdjustmentTier.EffectiveFrom`, `nillable: true` in a v68 describe. The other
finding of this shape says why metadata will never close the gap: a component needs *either*
a child product *or* a child product classification, both fields nillable. "One of these two"
is not something a field says about itself.

**Shape 2**, one instance: a tier carries `Product2Id` and `ProductSellingModelId`, and the
pair must already be joined by a `ProductSellingModelOption` — **an object the spec never
mentions.** That is the sharpest of the four. In two others the deciding fields sit on the
records the lookups name, each legal alone; in the last a single lookup's target must have a
field set, and the message names the lookup, which is populated.

**Shape 3**, the only instance so far: `QuantityScaleMethod` is discarded whenever
`IsQuantityEditable` is true. Apply saw a success, the log holds a real Id, the spec is well
formed, the describe calls the field writable — and reading the record back is what showed
nothing had been stored.

**A validator that reads field metadata cannot be complete, by design rather than by
omission.** Not one of the nine is derivable from metadata; each entered this repository
because a write was refused or silently lost. So **preview against the org is not an
optimisation** — it is where shape 2 surfaces, and a clean preview still does not promise
apply will succeed — and **verify reads back every field it wrote, not a sample**, because
shape 3 is invisible from the spec, from apply's output and from the log. When the platform
refuses something, put its sentence in `notes/` verbatim: for most of these rules that
sentence is the only documentation there is.

### What a new build skill does before it emits a spec

- **Two lookups to different objects in one record?** Ask which third object relates them and
  query it in the preview. That nothing does is an answer too, and worth writing down.
- **A field the describe calls optional that the domain says cannot be?** Try it missing,
  once, against an org, before trusting the metadata.
- **An unexpected difference in verify that will not go away?** Suspect shape 3 before
  suspecting the spec. An update that also fails to stick confirms it.

Two findings fit none of the three shapes: a tier sharing a bound with another tier, a child
product appearing twice in one group. Both are collisions between records the spec itself
declares, which is the one position a check argues better than the platform from — it names
the two records that collide, where the platform's message names only the condition.
Everything behind this section was observed on one org and has not been replicated.

## Marking — how a record is known to be ours

Every record this skill creates must be identifiable as created by it. Which mechanism is
available is **per object**, and for most objects the answer is "none". Surveyed across the
109 objects the pack seeds and describes — PLATFORM (v68 describe):

| Route | Objects | Mechanism |
|---|---|---|
| **Tier 1** | 17 | a createable, unique, idLookup field: `GlobalKey` on 3, `Code` on 10, an org-specific custom field on 4 |
| **Tier 2** | 22 | no unique field, but `Name` is createable: a reserved prefix |
| **Tier 3** | 70 | `Name` is autonumbered, read-only or absent: nothing fits on the record |

**`GlobalKey` was the obvious candidate and it is not enough**: unique and idLookup, and
present on three objects; `Code` behaves identically on ten more. **Tier 3 is the common
case, and it is the junctions** — tiers, components, selling-model options, price book
entries, the adjustment children — so the records a build skill creates most of are the
ones that can carry no mark. Each declares **`marked_by`**, naming a record in the same spec
that can carry one and that its required lookup points at.

That inheritance is sound when the lookup is **create-only**. It **fails where the required
parent is pre-existing** — a `ProductRelatedComponent` needs a `ParentProductId` that in a
demo org is usually not ours — and there **the log is the only evidence**. Prefer attaching
to a parent this run also created. `Product2` has no standard upsert key at all, which makes
products the most dangerous thing a spec can create in a loaded catalog.

`references/marking-and-idempotency.md` works all of this through per object.

## Guardrails

Half the value of this skill, and each a rule the cycle enforces rather than advice.

- **Preview before apply, always.** No path writes without a preview a human has read, and
  **confirmation is per preview** — editing the spec voids it.
- **Never modify or delete a record this run did not create.** Preview reports and stops; it
  never assumes it may overwrite. This protects demo material and has no exceptions. A record
  reached through `lookups` is the same rule from the other side: referenced, never written,
  logged only as `kind: lookup`, which teardown skips.
- **A lookup resolves to exactly one record or preview fails**; zero and two are both errors.
- **Applying twice cannot duplicate, and a mixed spec cannot be re-applied at all.** Preview
  classifies a keyed record as a no-op or a conflict; unkeyed children cannot be classified,
  so a spec holding both is stopped and the correction stays teardown then re-apply. Skip
  preview and the unique index refuses the insert with `DUPLICATE_VALUE`, writing no
  `created` row.
- **A true upsert is deliberately absent**, because its update branch would modify a record
  a different run created, which the ownership rule forbids. See
  `references/marking-and-idempotency.md`.
- **Some objects are stronger than their tier suggests, in a narrow scope.**
  `PriceAdjustmentTier` has no marker, yet the platform refuses a tier overlapping another
  under the same schedule, so an identical tier spec cannot duplicate — guaranteed by the
  platform, not the cycle. Tiers with different ranges coexist, so this is not general
  idempotency and must not be quoted as such.
- **Nothing is ever updated, including a record this run created.** There is no update phase;
  see above for the inactive-then-activate case and how it is handled outside the cycle.
- **Correction is delete-and-recreate, as the normal case.** Create-only fields are
  everywhere here — a tier's schedule lookup, every product lookup on a component or bundle
  adjustment, both role categories on a relationship type. A correction path that assumes
  `update` works is wrong about the platform, not unlucky.
- **Never set a read-only field**, such as a tier's selling-model projection or a
  component's roles. Verify expects the platform to fill them.
- **Teardown deletes from the log, never from a query.** "Everything matching the marker"
  would catch a record someone else made with the same prefix.
- **No catalog content invented into a demo org without saying so**, and **no transactions**
  — see **Scope** above.

## Without a shell

claude.ai has no shell, and the connector has `createSobjectRecord`, `updateSobjectRecord`
and `deleteSobjectRecord`, so the whole cycle is executable from a chat session by hand.
That makes the guardrails matter more, not less: there is no script in that branch, and the
log is a transcript rather than a file. `references/without-a-shell.md` has the four phases
written out for it, and the one weakness that branch has.

`updateSobjectRecord` is available here and is **not** part of this cycle; see below.

## There is no update path, and that is deliberate

Apply creates; correction deletes and recreates. **No phase modifies a record, including one
this run created**, and the rule is absolute rather than a default with exceptions, because
"update is fine when I am sure" is how a cycle stops being reversible. The one case that
argues against it — create a schedule inactive, load its tiers, then activate so the
configuration is never live half-built — is out of scope: build it inactive, preview, apply,
verify, and have a person flip the field having read the output.
`references/marking-and-idempotency.md` has the reasoning.

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
- **PLATFORM (v68, observed)** — `GlobalKey` is writable and genuinely unique: a duplicate
  insert is refused by the platform's own index, naming the colliding record, not by an RCA
  validation rule.
- **PLATFORM (v68, observed)** — `PriceAdjustmentTier` is tier 3 as its metadata says: its
  `Name` is `autoNumber: true, createable: false`, and a created record came back numbered.
- **PLATFORM (v68, observed)** — teardown in reverse order succeeds, leaving the org as it
  was with referenced records untouched.
- **PLATFORM (v68, observed)** — `PriceAdjustmentTier.EffectiveFrom` is `nillable: true` and
  rejected when absent; a tier whose bounds overlap another under the same schedule is
  refused. The platform's sentences, and the rest of the inventory, are in `notes/`.

## Not verified

- **The cycle has been run on one org only.** Everything marked *observed* above comes from
  those runs and has **not been replicated on a second org**, so it is unvalidated under the
  pack's notes protocol.
- **Upsert-on-key is still unproven.** A *duplicate insert* on `GlobalKey` is refused by the
  platform's index, naming the colliding record; re-running the same spec stopped with
  `DUPLICATE_VALUE` and created nothing — no duplicate, and no no-op either.
- **Autonumbered names do not reset when records are deleted.** A failed or torn-down apply
  leaves gaps in sequences like `PAT-00000000nn`. Harmless, but the org is not byte-identical
  after a teardown — do not read name continuity as evidence that nothing ran.
- **Whether deleting `AttributeBasedAdjRule` cascades to its conditions.** The conditions
  cannot be deleted directly and nothing says what happens to them, so a spec creating them
  is not known to be cleanly reversible.
- **Whether tier-2 query-then-skip is adequate in practice.** The race is real in principle;
  how likely it is with one operator is a guess.
- **Whether the no-op was tested against a record another run created.** It was exercised
  against one the *same* spec had just applied — the easy case, since the values came from
  one file. A record built by a different run, or edited by a person into a matching state,
  was not tried. The conflict state was reached by editing the spec rather than the org:
  the same comparison, different provenance.
- **What the platform normalises, beyond what these runs showed.** The datetime rewriting
  and the five tier projections were observed; the rest of the expected-difference list is
  assembled from field metadata. Treat it as a starting point and add to it.
- **The 17/22/70 split counts the objects this pack seeds**, four on org-local custom fields.
  Another org splits differently, which is why the validator reads the target org's describes.

## For a build skill that uses this one

Declare `writes: true`, say in your description that you write to an org, and name your
preview, confirmation and teardown in your body. Do not re-implement the cycle: emit a spec
and run it through these scripts. A build skill's job is knowing *what* should exist, which
is domain doctrine; knowing how to put it there safely is this skill's job, and there should
be one answer to that in the repository.
