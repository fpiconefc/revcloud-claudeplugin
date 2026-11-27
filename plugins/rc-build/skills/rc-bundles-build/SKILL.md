---
name: rc-bundles-build
version: '0.1.0'
writes: true
description: "Turn a bundle structure that has already been decided into an rc-org-writer spec and load it: the component group, the components under it, the pre-flight checks that catch what a describe cannot, then preview, apply, verify and teardown. Read this when the structure is settled and the work is building it. Use for \"load this bundle\", \"add these options to the bundle\", \"create the component group\", \"build the bundle in the sandbox\", \"undo the components I just loaded\", \"why did my component fail to save\". This skill writes to an org, through the cycle below. It never creates products. **Not for deciding** the structure: what is a component, what is a group, when to nest — that is rc-bundles, and if the structure is not settled yet, go there first."
---

# Building a bundle structure into an org

Two skills touch these objects. **`rc-bundles` is for deciding**: what belongs in a group,
when nesting earns its keep, which flag expresses which intent, why a `Bundle` schedule with
tiers prices nothing. **This skill is for loading** a structure already decided.

If you arrive without the structure settled — unsure whether something is a component or a
group, or whether a group should nest — **read `rc-bundles` first**. Building a spec from an
unfinished decision just records the indecision in an org.

What this skill owns: which objects a bundle load touches, in what order, and **what to check
before the preview**, because five of the rules that stop a bundle apply appear in no
describe and two of them compare a field on one looked-up record against a field on another.

## Prerequisite

`rc-context-pack` must have fingerprinted the target org, and **`rc-org-writer` must be
installed beside this plugin**. It owns the spec format, lookups, marking, the log and all
four phases with their scripts. This skill emits a spec and calls them.

## Scope: groups and components, never products

This skill creates `ProductComponentGroup` and `ProductRelatedComponent` on products that
**already exist**, reached through lookups.

**It never creates a `Product2`, under any circumstances.** A product has no standard upsert
key, which makes it the most dangerous thing a spec can put into a catalog, and
`rc-org-writer` already names it that way. If a product the structure needs is missing, this
skill reports it and stops. Adding it is a catalog decision for whoever owns the catalog.
`check_bundle_spec.py` fails a spec that declares a `Product2` record at all.

## Why this skill always creates the group

This is the part to understand rather than take on faith, because the obvious
"simplification" reopens a hole.

A `ProductRelatedComponent` is **tier 3**: its `Name` is autonumbered, it has no unique key,
and nothing on the record can carry a marker. Attach one directly to a parent product that
somebody else created and it is **orphaned from its own authorship** — ours by creation,
hanging off something that is not ours, with the run log as the only evidence it exists.
`rc-org-writer` names exactly this as the gap its marking scheme leaves open.

Attaching it to a `ProductComponentGroup` that **this same run created** closes the gap. A
group carries `Code`, which is unique and idLookup, so it is tier 1 and marks itself. The
component then inherits authorship through `marked_by`, and that inheritance is sound here
because the component's lookup to the group is **create-only**: once created, the component
cannot be reparented out of the group that vouches for it.

So the default pattern is **always group first, components hanging off it**, even when the
structure did not call for a group on its own merits. Someone who later "simplifies" by
removing the group and pointing components straight at the product would be reopening the
authorship hole without knowing it. If a group looks redundant, that is what it is for.

## The checks that come before the preview

```bash
python3 plugins/rc-build/skills/rc-bundles-build/scripts/check_bundle_spec.py \
    <spec.yaml> --target-org <alias>
```

Read-only. Run it **before** `validate_spec.py`, and both before apply.

### Platform rules, each observed refusing a real create

PLATFORM (v68, observed 2026-11-27). The literal sentences are kept because for several of
these the sentence is the only documentation there is.

| Rule | What the platform says |
|---|---|
| a component needs a child, though both child fields are `nillable: true` | *"Enter either a Child Product ID or a Child Product Classification ID."* |
| a group's parent product must have its `Type` set | *"Parent product type should not be null."* |
| the relationship type's role must match the parent's `ProductClass` | *"A relationship type record with Bundle as role must have product classification component as child."* |
| a component's group must belong to the same parent product | *"Select a group related to the same bundle as this component."* |
| a child may appear only once per group | *"The child product exists in the group."* |

Two of these are the pattern `rc-pricing-build` meets as the product-to-selling-model
assignment: **two lookups that each resolve to a real record and are invalid together.** A
`Bundle`-class parent with a `Set`-role relationship type is refused, and so is a
`Simple`-class parent with a `Bundle`-role one. Neither lookup is wrong on its own. Checking
this needs the org, which is why `--target-org` is not optional before an apply.

The `Type` rule has a trap in its wording: the message names `ParentProductId`, which **is**
populated. What is null is `Type` on the product it points at — a field on an object the spec
never mentions. Read the error as being about the target, not the lookup.

### A write that succeeds and stores nothing

`QuantityScaleMethod` is **silently discarded when `IsQuantityEditable` is true**. The create
returns success, the field comes back null, and a later update does not stick either. On a
component with `IsQuantityEditable: false` the same value persists.

This is worse than a refusal: nothing fails, and a verify pass comparing the spec to the org
reports the difference on every run forever. The check rejects the combination, and the
reason it is coherent to do so is that a quantity the buyer edits has no parent scaling.

It also explains something `rc-bundles` had recorded as unexplained. Across every component
in the org available for checking, `IsQuantityEditable: true` goes with a null scale method
in **87 cases out of 87**, with no exceptions. Those nulls were never a loading accident.

### Structure, from `rc-bundles` and checkable without an org

- **The spec creates no `Product2`.**
- **Group cardinality is coherent**: minimum at or below maximum, and neither above the
  number of components the spec actually puts in that group.
- **A required component is not in a group whose minimum is zero.** The group says the buyer
  may take nothing; the component says it is mandatory. They cannot both be right.
- **A product appears at most once per group.**
- **Group nesting has no cycle.**

## Can a bundle spec be re-applied?

**No. Re-run it and the correction is teardown then re-apply.**

A bundle spec is a keyed group with unkeyed components, which is exactly the shape
`rc-org-writer` covers: the group carries a `Code` and can be recognised, the components
carry nothing to find them by, so applying again would create a second set under a group
that already exists. Preview stops rather than letting that happen.

What that buys is **a readable error naming the situation instead of a `DUPLICATE_VALUE`
from the platform's index** — worth having, and not the same as the spec being re-appliable.
To load a corrected structure: tear the previous run down from its log, edit the spec, apply
again.

## The cycle

`rc-org-writer` owns all four phases. In order, with this skill's check at the front:

```bash
# 0. bundle pre-flight — this skill
python3 plugins/rc-build/skills/rc-bundles-build/scripts/check_bundle_spec.py \
    <spec.yaml> --target-org <alias>

# 1. preview
python3 plugins/rc-core/skills/rc-org-writer/scripts/validate_spec.py \
    <spec.yaml> --target-org <alias>

# 2. apply, after a person has read the preview
python3 plugins/rc-core/skills/rc-org-writer/scripts/apply.py <spec.yaml> \
    --target-org <alias> --log applied/<run>.jsonl --confirm

# 3. verify
python3 plugins/rc-core/skills/rc-org-writer/scripts/verify.py <spec.yaml> \
    --target-org <alias> --log applied/<run>.jsonl

# 4. teardown
python3 plugins/rc-core/skills/rc-org-writer/scripts/teardown.py \
    --target-org <alias> --log applied/<run>.jsonl --confirm
```

Verify reports expected differences on every component: `ParentProductRole` and
`ChildProductRole`, which are read-only projections of the relationship type, and an
autonumbered `Name`. None is a finding.

**In a chat session with no shell**, `rc-org-writer`'s "Without a shell" section has the
connector equivalent of each phase. The checks above become `soqlQuery` calls: the parent
product's `Type` and `ProductClass`, and the relationship type's `MainProductRoleCat`.

## Out of scope: proving what it configures

This skill creates structure. It does **not** run transactions, and nothing here tells you
how the bundle behaves in a cart — whether a group's cardinality is enforced the way you
expect, what a required component does to a configuration, or what the bundle costs.

That belongs to a testing skill that does not exist yet, which will depend on this one for
the structure it exercises. A verified spec means the records are what you asked for, not
that the configurator behaves as you expect.

## Verified anchors

- **PLATFORM (v68 describe)** — `ProductComponentGroup.Code` is createable, unique and
  idLookup, so a group is tier 1 and marks itself; `ProductRelatedComponent.Name` is
  autonumbered and not createable, so a component is tier 3 and cannot;
  `ProductRelatedComponent.ProductComponentGroupId` is createable and not updateable, so a
  component cannot be reparented out of its group.
- **PLATFORM (v68, observed 2026-11-27)** — the five refusal rules tabulated above, each
  established by attempting the create and reading the error, with every probe record deleted
  afterwards and the org's counts unchanged at the end.
- **PLATFORM (v68, observed 2026-11-27)** — `QuantityScaleMethod` is stored as null whenever
  `IsQuantityEditable` is true, on create and on update, with no error. It persists when
  `IsQuantityEditable` is false.
- **PLATFORM (v68, observed 2026-11-27)** — `assets/example-spec.yaml` runs clean through all
  four phases with its placeholders filled in: pre-flight and preview pass, apply creates a
  group and two components, verify reports 26 matches and 6 expected differences with **zero
  unexpected**, and teardown removes all three. Presence before teardown and absence after
  were confirmed **by querying the org**, not by reading the scripts' output. The org returned
  to its exact prior counts and the three referenced products were untouched.

## Not verified

- **How the bundle behaves in a cart.** Nothing here was configured or priced; see **Out of
  scope**.
- **Whether a `Set` or `AddOn` structure loads the same way.** Both the probes and the example
  use `Bundle`. The relationship-type rule implies a Set parent needs a Set-role type, which
  was observed from the refusal side only: a Set-role type on a Bundle parent is refused. No
  Set bundle was built.
- **Nesting was not exercised.** The cycle check for cycles in `ParentGroupId` is static and
  was tested on a spec, not against an org that rejected one.
- **The eight components with a null scale method and `IsQuantityEditable: false`.** The
  editable-true rule explains 87 of the 95 nulls in the org checked; those eight have some
  other cause, which was not pursued.
- **One org, one API version, not replicated.** These are platform behaviours rather than
  configuration, so they should travel; confirm on a second org before treating them as
  settled everywhere.

## Guardrails

- **Never decide the structure here.** If the conversation is still working out groups and
  components, this is the wrong skill. Send it to `rc-bundles`.
- **Never create a `Product2`.** Report the missing product and stop.
- **Never attach a component directly to a product this run did not create.** Create the
  group first and hang components off it, even when the group looks redundant — that is what
  closes the authorship gap.
- **Never send `QuantityScaleMethod` with `IsQuantityEditable: true`.** The write is accepted
  and discarded, and the spec will disagree with the org forever.
- **Never assume two valid lookups are valid together.** The parent's `ProductClass` must
  match the relationship type's role, and only the org can say.
- **Never re-apply a spec to correct it.** Tear down from the log, edit, apply again.
- **Never reimplement the write cycle.** Emit the spec and call `rc-org-writer`'s scripts.
- **Never treat a verified spec as proof of behaviour.** Verify proves the records match the
  spec. How the bundle configures is a transaction away and out of scope.
