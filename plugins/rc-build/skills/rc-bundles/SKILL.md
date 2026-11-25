---
name: rc-bundles
version: '0.1.0'
description: "How a bundle is composed in Revenue Cloud Advanced: ProductComponentGroup and ProductRelatedComponent, what each component flag actually does, how groups nest, group cardinality, and which part of the price is structural. Read this BEFORE building a bundle, adding an option to one, or deciding whether something is a group or a component. Use for \"bundle\", \"product options\", \"comes with X inside\", \"the customer can add X\", \"pick one of these three\", \"required option\", \"default option\", \"should the quantity scale with the parent\", \"is the option price included in the bundle\", \"nested bundle\", \"migrating CPQ features and options\". Read-only: never writes to an org. Not for base price per selling model (rc-catalog-selling-models), not for the bundle discount itself (rc-pricing-adjustments), and not for the knowledge pack (rc-context-pack)."
---

# Bundles in RCA — composing a product from other products

A bundle is not a product with a list of children. It is a product, a set of **groups**, and
a set of **component rows** that each point at a group. The group decides how many things
the buyer takes from it; the component row decides how one of those things behaves. Put a
constraint on the wrong one of the two and the configuration still saves, still renders, and
constrains nothing.

The second thing to know before you start: the field that decides whether a bundle is a
bundle, a set or an add-on is **not on either of those objects** and is not writable where
you will look for it. And the behaviour flags that carry the whole design are documented by
the guide against a third object, the override — not against the object you configure.

This skill is read-and-design work. **Nothing here writes to an org.**

## Prerequisite

The knowledge pack at `~/.claude/knowledge/revenue-cloud/` must exist. Run
`rc-context-pack` first.

This skill leans on **both halves of the pack**, unevenly and in a way worth stating up
front. The structure plane — which objects exist, which fields are writable, how groups nest
— is observable and is observed below. The **constraint and rule plane is close to empty**:
the org in the pack sets no cardinality on 105 of its 120 groups and has zero configuration
rules. Those two planes are written in different voices here, and the difference is
deliberate. Where this skill sounds confident, it is reporting structure. Where it hedges,
it is reporting that nobody has exercised the thing yet.

## Without a shell

Step 1 runs a script and the verification step hands you SOQL. In a chat session with no
shell, do the same work with the Salesforce MCP tools: `getObjectSchema` on
`ProductComponentGroup`, `ProductRelatedComponent` and `ProductRelationshipType` returns the
describes the script reads, and `soqlQuery` runs every query in
`references/component-field-map.md`. What the script adds over a raw describe is the four
trap checks, and those are written out below — read them against the schema the connector
returns. Never invent a field name to fill a gap in a describe.

## Ground in the org's surface

```bash
python3 plugins/rc-build/skills/rc-bundles/scripts/bundle_surface.py <org-alias>
```

It reads the pack's describes and prints the bundle surface for that org: every field on the
group, the component and the relationship type with its writability, which fields are
read-only projections and of what, every picklist whose label differs from its API value, and
which fields the org has that the v68 guide does not document. It prints no catalog content,
writes nothing and touches no org. The four traps below are what it checks for; run it
against the org you are designing for and read its findings against them.

Record counts come from the queries in `references/component-field-map.md`, which you run
yourself.

## A worked shape — one bundle, twelve groups, forty components

This is the largest bundle in arm-picone, read on 2026-11-25. **Every name below is
invented.** What is observed is the structure and the counts: the group tree, how the forty
components distribute across it, the nesting depth, and the flag mix. No product name, code
or price from that org appears here or anywhere else in this skill.

```
Managed Service Bundle                      (the parent Product2)
├── Core Platform              seq 1        container, 0 components
│   ├── Edition                seq 1        min 1 / max 2   ->  7 components
│   └── Deployment Region      seq 2        min 1 / max 2   ->  2 components
├── Onboarding                 seq 2        no min / no max ->  5 components
├── Support                    seq 3        container, 0 components
│   ├── Support Level          seq 1        no min / no max ->  6 components
│   └── Response Options       seq 2        min 0 / max 4   ->  5 components
├── Integrations               seq 4        container, 0 components
│   ├── Data Connectors        seq 1        no min / no max ->  2 components
│   ├── Identity Connectors    seq 2        no min / no max ->  3 components
│   └── Monitoring Connectors  seq 3        no min / no max ->  4 components
└── Training                   seq 5        no min / no max ->  6 components
```

Five things in that shape are worth taking away, and four of them are counts.

**Twelve groups, two levels, seven of them nested.** Five groups sit at the root and seven
carry a `ParentGroupId`. Those seven are **every nested group in the org** — the other 113
groups across every other bundle are flat. Nesting is real, available, and in this org
exercised exactly once.

**A group holds components or child groups, and here never both.** The three containers —
Core Platform, Support, Integrations — hold zero components between them. They are also the
org's only three groups that no component points at. What looks like three orphaned groups
in a sweep is the nesting pattern, not a loading error.

**Cardinality is set on 3 of the 12.** Edition and Deployment Region at 1–2, Response
Options at 0–4. The other nine are unbounded, which means the buyer takes as many or as few
as they like from them.

**The flag mix is uniform and tells you what kind of bundle this is.** Of the 40 components:
zero are required, zero have their price included in the bundle, 3 are default-selected, 6
scale Proportional and 34 leave `QuantityScaleMethod` null. This is an à-la-carte catalog
with a shell around it, not an all-inclusive package — and note it is the *opposite* of the
pattern that dominates the org as a whole, which the observation section below gets to.

**Forty components, nine populated groups, one parent product.** Group count is a modelling
choice, not a consequence of component count.

## Routing — start from the sentence the customer said

Three sentences cover most of it, and they do not resolve to the same object.

| What the customer says | What it is | Where it is expressed |
|---|---|---|
| "it comes with X inside" | a component that is there by default | component flags: default on, and required if they cannot remove it |
| "they can add X" | an optional component | component flags: default off |
| "they pick one of these three" | a constrained choice | **group** cardinality: `MinBundleComponents` / `MaxBundleComponents` |

The first two are settings on `ProductRelatedComponent`. The third is **not expressible on a
component at all** — a component row has no way to say "and only one of my siblings". That
is what the group is for, and it is the single most common modelling error in this area:
reaching for `MinQuantity` on the component when the requirement was "pick one of three".

Two more that come up:

- **"they can take two of them"** is `MinQuantity` / `MaxQuantity` on the component — a
  quantity of one line, not a count of lines.
- **"this whole section is optional"** is a group with `MinBundleComponents` 0 and a max, as
  Response Options does above.

## What each flag does

Five flags carry the design. Work out each one from the requirement, not from a default.

### `IsComponentRequired`

Whether the buyer can remove the component. Required, defaults to false. Per the developer
guide — describing the override object, which is where the guide documents this field — it
indicates whether the component is required in the bundle.

Use it for the thing that makes the bundle what it is. A required component the buyer cannot
remove is also a component they cannot decline, so it is a commercial statement as much as a
structural one.

### `IsDefaultComponent`

Whether the component starts out selected. Required, defaults to false. This is the flag
people conflate with the previous one, and the distinction is the whole point: **default is
about the starting state, required is about whether they may change it.** Default-on and
removable is "comes with it, drop it if you like". Required is "it is not a choice".

### `IsQuantityEditable`

Whether the buyer can change the quantity of this component. Required, defaults to false.
Set `MinQuantity` and `MaxQuantity` only alongside this: bounds on a quantity nobody can edit
constrain nothing a buyer does.

### `QuantityScaleMethod`

Per the developer guide, on the override object: "the scaling method that determines how the
child product quantity changes as the quantity of the parent product changes in the runtime
cart". `Constant` and `Proportional`, defaulting to `Proportional`.

`Proportional` means ten of the parent brings ten times the component. `Constant` means the
component quantity holds regardless of the parent.

**The field is nillable, and null is a third state that the pack cannot explain.** In
arm-picone 93 of 272 component rows have no value, against 178 `Proportional` and 1
`Constant` — so null is the second most common setting in the only org available, not a
stray. What the engine does with null, and whether it falls back to the documented default,
is not something either half of the pack answers. Set it explicitly and the question does not
arise.

### `DoesBundlePriceIncludeChild`

Per the developer guide, on the override object: it "indicates whether the bundle price
includes the associated child component's price". True means the component rolls into the
parent's price and does not price on its own line. False means it prices separately.

This is the one flag with **no default value in the org describe** while the other three
booleans default to false. A required field with nothing to fall back on is a field you have
to decide, which is the right outcome for the most consequential of the five.

### Combinations that disagree with themselves

Advice, not platform behaviour. Each of these saves without complaint.

| Combination | Why it reads wrong |
|---|---|
| required on, default off | required but not selected to begin with: the runtime has to resolve a contradiction you wrote down |
| quantity bounds set, editable off | the bounds describe something nobody can change |
| `Proportional` and editable on | parent scaling and the buyer both claim the same number |
| price included on, and a bundle adjustment on the same component | the component's price is counted inside the parent and discounted again |
| group min above 0, every component default off | the group demands a choice and offers no starting point |

## Group cardinality and nesting

`MinBundleComponents` and `MaxBundleComponents` are counts of **component rows chosen from
the group**, not quantities. The guide documents both on `ProductComponentGrpOverride`: the
minimum that must be added, and the maximum that can be added.

`ParentGroupId` nests one group inside another. Per the developer guide it is "the parent
product component group in a nested group hierarchy **for the same parent product**", so a
group tree belongs to one bundle and is not shared between bundles. It arrived in API
version 62.0.

Both objects also have an **override** sibling — `ProductComponentGrpOverride` and
`ProductRelComponentOverride` — carrying `OverrideContextId`, a lookup to the root bundle
product. The mechanism they describe is that the same group or component behaves differently
depending on which root bundle it is reached through, so a shared sub-bundle can be required
under one parent and optional under another without duplicating rows. Both override objects
are empty in arm-picone, so none of that is observed working. `references/component-field-map.md`
has their full field lists.

## Where bundles end and pricing begins

The boundary runs through one field, and both skills have to say the same thing about it.

**`DoesBundlePriceIncludeChild` is structural and belongs here.** It answers "does this
component appear as its own priced line, or is it inside the parent's price". That is a fact
about the shape of the bundle, decided when the bundle is built, and it changes what a quote
looks like before any discount exists.

**A discount for being inside the bundle is pricing, and belongs to
`rc-pricing-adjustments`.** That is a `PriceAdjustmentSchedule` with `ScheduleType` `Bundle`
and `BundleBasedAdjustment` rows addressing the component by its path — component, immediate
parent, root bundle. Nothing in this skill sets a price or a percentage.

The practical test: if the answer changes the **number of priced lines**, it is this skill.
If it changes **the number on a line**, it is pricing. The failure mode when the boundary is
ignored is the fourth row of the combinations table above — a component folded into the
parent's price and then discounted again on its own account.

## The four traps

Full field inventory, with writability and both sources, in
`references/component-field-map.md`.

### Trap 1 — the bundle pattern is chosen on a third object, and is create-only

`ParentProductRole` and `ChildProductRole` on `ProductRelatedComponent` are the fields that
say whether this is a Bundle, a Set or an AddOn. Both are **read-only** in arm-picone's
describe (2026-11-25): createable false, updateable false. You cannot set either one.

What you set is `ProductRelationshipTypeId`, a **required** lookup. The
`ProductRelationshipType` it points at carries `MainProductRoleCat` and
`AssociatedProductRoleCat`, whose picklists are identical to the two read-only fields, value
for value and label for label. The roles on the component are a projection of the
relationship type.

And on `ProductRelationshipType` both role fields are **create-only**: createable true,
updateable false. A relationship type's pattern is fixed once the record exists.

One asymmetry inside that pair will catch a load. **`MainProductRoleCat` is required and
`AssociatedProductRoleCat` is nillable** (arm-picone describe, 2026-11-25). On an object whose
entire purpose is the role pair, half of it is optional: a relationship type can declare what
the parent is and say nothing about the child. The guide documents the nillable half and not
the required one, which is delta 3 below, so the half you are obliged to populate is the half
with no DOCS description.

**Do:** choose the pattern by choosing or creating a `ProductRelationshipType`, and treat its
role categories as unchangeable afterwards. To move components to another pattern, point them
at a different type. Neither `ParentProductRole` nor `ChildProductRole` appears anywhere in
the v68 guide, so the describe is the only source for either.

### Trap 2 — every role value differs from its label

The role vocabulary is **nine values**, carried on **four fields** — the parent role and the
child role, each appearing once on the component as a read-only projection and once on the
relationship type as the create-only original. Four parent values, five child values, and not
one of the nine equals its label. ORG arm-picone, 2026-11-25:

| Field pair | Value | Label |
|---|---|---|
| `ParentProductRole` / `MainProductRoleCat` | `Bundle` | Bundle **Parent** |
| | `Set` | Set **Parent** |
| | `AddOn` | **Addon** Parent |
| | `ProductRequest` | Product Request |
| `ChildProductRole` / `AssociatedProductRoleCat` | `BundleComponent` | Bundle Component |
| | `SetComponent` | Set Component |
| | `AddOnComponent` | **Addon** Component |
| | `ClassificationComponent` | **Product** Classification Component |
| | `ProductRequestComponent` | Product Request Component |

Three distinct ways to differ, which is why not one of the nine survives a label match: a
space inserted at every word boundary, a capitalisation change inside a word (`AddOn`
becoming "Addon"), and a label that gains a word the value does not have
(`ClassificationComponent`).

`QuoteVisibility` inverts the problem: its values contain spaces — `Transaction Line Editor
Only` and `Quote Document Only` are API values, not labels.

**Do:** match on the API value. A filter, validation rule, flow decision or load file written
against what the UI displays matches nothing, and the role fields are exactly the ones a
person reads off a screen and retypes.

### Trap 3 — four near-homonyms, and one of them changes units

The pairs that get swapped, with what distinguishes them:

| Looks like a pair | Actually |
|---|---|
| `MinQuantity` / `MaxQuantity` vs `MinBundleComponents` / `MaxBundleComponents` | **different units.** The first bound the quantity of one component; the second bound how many components are chosen from a group. "Pick one of three" is the second pair |
| `ParentSellingModelId` vs `ChildSellingModelId` | **different writability.** Parent is create-only, child is createable and updateable. Both absent from the guide |
| `ParentProductId` on the group vs on the component | the group's is which bundle the group belongs to; the component's is the bundle the component hangs off. Create-only on both |
| `Sequence` on the group vs on the component | order of groups within the bundle, against order of components within a group |

`Name` adds a smaller one: writable on `ProductComponentGroup`, read-only on
`ProductRelatedComponent`. A load file that sets component names fails on a field the group
accepts happily.

**Do:** when a requirement says a number, ask whether it counts lines or units before
choosing the field. That one question separates the first row's two pairs, and it is the
error this skill exists to prevent.

### Trap 4 — the guide documents these objects against the override

Neither `ProductComponentGroup` nor `ProductRelatedComponent` has an object-reference section
in the v68 guide. Searching the 2555-page PDF for each field finds the behaviour flags in
exactly one place each, and that place is the override object:
`DoesBundlePriceIncludeChild`, `IsComponentRequired`, `IsDefaultComponent`,
`IsQuantityEditable` and `QuantityScaleMethod` on `ProductRelComponentOverride`;
`MinBundleComponents`, `MaxBundleComponents` and `IsExcluded` on
`ProductComponentGrpOverride`.

What the guide does give for the base objects is a "Fields on Standard Objects" section
covering one field on the group — `ParentGroupId` — and two on the component,
`ChildProductClassificationId` and `QuoteVisibility`. The rest of the base-object prose is in
the Salesforce Object Reference, outside this guide.

**Do:** cite an override field's description as the best DOCS statement of what the matching
base field means, and say that is what you are doing. Every quotation in this skill is marked
that way. Do not assume the override's documented default — `false` for
`DoesBundlePriceIncludeChild` — holds on the base object, where arm-picone's describe reports
no default at all.

## What one org actually has

Everything above is field semantics and travels to any org. This section is one org's data,
and is weaker evidence. Two flag combinations account for 231 of arm-picone's 272 component
rows (2026-11-25):

| | Required | Default | Qty editable | `QuantityScaleMethod` | Price included | Rows |
|---|---|---|---|---|---|---|
| **A** | no | yes | no | `Proportional` | yes | 153 |
| **B** | no | no | yes | null | no | 78 |

A reads as all-inclusive: selected from the start, quantity follows the parent, price folded
into the bundle. B reads as à la carte: off by default, buyer sets the quantity, prices on
its own line. The remaining 41 rows spread across eight further combinations.

**Read this as an observation with a count, not as a norm.** arm-picone is a development org
seeded by a tool in August 2024. A combination appearing 153 times there is either the
natural shape of bundle modelling or a template applied in bulk, and the pack cannot tell
those apart — the more so given that component reuse is almost nil (272 rows over 240
distinct child products) and the distribution is this lopsided. The worked shape above is
from the same org and contains **zero** A-pattern rows, which is the clearest argument
available that A is concentrated rather than universal.

## Configuration rules — named, not described

`ProductConfigurationRule` holds validation, inclusion and exclusion rules. Per the developer
guide it represents those rules "for products in the context of the selling process", where
the selling process is quoting, configuration or ordering, and it arrived in API version
61.0. It carries `ProcessScope` and `RuleSubType`, which scope a rule to a product, a
classification, a bundle or a transaction.

**This is where CPQ's Product Rules land — not on the component objects.** A migration that
tries to express an inclusion rule through `IsComponentRequired` is solving the wrong
problem.

That is the extent of what this skill will say. **arm-picone has zero
`ProductConfigurationRule` records.** The object is seeded in the pack and empty, so there is
no case to read, no worked example, and nothing to verify beyond the field metadata. Naming
the values of `ProcessScope` and `RuleSubType` here would be describing a picklist, not a
practice. This earns its own skill when an org with rules in it is available.

## Deltas — the guide and the org disagree

Recorded in `notes/bundles.md` in the pack. The ones that change a design:

**1. The base objects have no field reference; the overrides do.** Trap 4. Every behaviour
flag is documented against the object that overrides the setting rather than the one that
holds it.

**2. Five fields on the component are absent from the guide.** `ParentProductRole`,
`ChildProductRole`, `ParentSellingModelId`, `ChildSellingModelId` and `UnitOfMeasureId`. The
first two decide the bundle pattern and the next two bind components to selling models, so
this is not a trailing edge of obscure fields.

**3. `ProductRelationshipType.MainProductRoleCat` is absent from the guide** while its
sibling `AssociatedProductRoleCat` is documented. The guide describes how to say what the
child is and not how to say what the parent is.

**4. `DoesBundlePriceIncludeChild` has no default in the org** and a documented default of
false on the override. The three other booleans on the component default to false in both.

**5. `QuantityScaleMethod` is nillable in the org** and "Defaulted on create" with default
`Proportional` on the override, yet 93 of 272 rows carry null. Either the default does not
apply on the path those rows were loaded through, or it was added after they were written.
Unresolved.

Precedence applied throughout: ORG wins for what this org has, DOCS wins for what the product
supports in general.

## Verified anchors

Field-by-field detail is in `references/component-field-map.md`. The load-bearing ones:

- **DOCS** — `ProductComponentGroup.ParentGroupId` is "the parent product component group in
  a nested group hierarchy for the same parent product", API version 62.0 and later. (Product
  Catalog Management Fields on Standard Objects)
- **DOCS** — `MinBundleComponents` is "the minimum number of components that must be added to
  a group" and `MaxBundleComponents` "the maximum number that can be added"; `IsExcluded`
  excludes a group and automatically excludes all of its child components. (Product Catalog
  Management → ProductComponentGrpOverride)
- **DOCS** — `QuantityScaleMethod` is "the scaling method that determines how the child
  product quantity changes as the quantity of the parent product changes in the runtime
  cart", values Constant and Proportional, default Proportional; `DoesBundlePriceIncludeChild`
  "indicates whether the bundle price includes the associated child component's price",
  default false. (Product Catalog Management → ProductRelComponentOverride)
- **DOCS** — `OverrideContextId` on both override objects is the root bundle product in whose
  context the configuration is overridden. (same two sections)
- **DOCS** — `ProductConfigurationRule` represents validation, inclusion and exclusion rules
  for products in the context of quoting, configuration or ordering, API version 61.0 and
  later. (Product Configurator Standard Objects)
- **DOCS** — `ProductRelationshipType.AssociatedProductRoleCat` is "the role that the
  associated component plays in the relationship", with `BundleComponent` and
  `ClassificationComponent` described; the latter arrived in API version 61.0. (Product
  Catalog Management Fields on Standard Objects)
- **ORG arm-picone, 2026-11-25 describe** — on `ProductRelatedComponent`,
  `ParentProductRole`, `ChildProductRole`, `UnitOfMeasureId` and `Name` are createable false
  and updateable false; `ParentProductId`, `ChildProductId`, `ChildProductClassificationId`
  and `ParentSellingModelId` are create-only; `ProductRelationshipTypeId` is required;
  `DoesBundlePriceIncludeChild` is required with no default. On `ProductRelationshipType`
  both role categories are create-only, `MainProductRoleCat` is required with 4 values and
  `AssociatedProductRoleCat` is nillable with 5 — nine role values over four fields in all.
- **ORG arm-picone, 2026-11-25 SOQL** — 272 component rows over 240 distinct child products
  and 120 groups; 272 of 272 are Bundle → BundleComponent; `IsComponentRequired` true on 3;
  `QuantityScaleMethod` Proportional 178, null 93, Constant 1; 7 groups carry a
  `ParentGroupId` and all 7 belong to one bundle; 3 groups have no component pointing at them
  and those 3 are that bundle's containers; 105 of 120 groups set neither minimum nor maximum
  and 10 are at 1–1; 0 component rows have a null group.

## Not verified

- **The constraint plane is barely exercised.** 105 of 120 groups set no cardinality at all
  and 10 sit at 1–1, so "pick exactly one" is the only constrained shape with more than a
  handful of instances. Nothing here about how the runtime enforces a minimum or a maximum
  rests on an observation.
- **Set and AddOn are unexercised.** `ParentProductRole` offers four patterns and all 272
  rows are `Bundle`. How a Set differs from a Bundle at runtime is not observable from this
  pack, and the guide's own description of the roles is the one-line gloss on
  `AssociatedProductRoleCat`.
- **Nesting is exercised once.** 7 of 120 groups nest, all inside a single bundle, two levels
  deep. Whether a third level behaves is untested, and "a group holds components or child
  groups, never both" is a pattern read off one bundle, not a rule the platform states.
- **Null `QuantityScaleMethod` is unexplained.** 93 rows. Delta 5.
- **Both override objects are empty.** Context-dependent cardinality is documented and
  unobserved, so the shared-sub-bundle argument above is read off the object graph and the
  guide's field descriptions.
- **`ProductConfigurationRule` has zero records.** Nothing about rule evaluation, precedence
  or interaction with the component flags is verified at all.
- **Component reuse is almost nil.** 272 rows over 240 distinct children, so claims about
  sharing a sub-bundle between parents are unverified in practice.
- **I did not watch a bundle configure.** Every statement about what the buyer can and cannot
  do rests on field semantics and the guide's prose, not on a cart I drove. Before promising
  a customer that a flag combination behaves a particular way, build it in their sandbox and
  configure it once.
- **arm-picone is one development org**, seeded by a tool in August 2024. The traps are
  structural, from field metadata and the guide, and travel across orgs. Every count here is
  a single observation.

## Guardrails

- **Never express "pick one of these three" on a component.** It is group cardinality.
  `MinQuantity` bounds a quantity, not a count of siblings.
- **Never try to set `ParentProductRole` or `ChildProductRole`.** They are read-only. Choose
  a `ProductRelationshipType`, and expect its roles to be unchangeable afterwards.
- **Never match a role on its label.** Every role value differs from its label, `AddOn` is
  labelled "Addon", and `QuoteVisibility`'s values contain spaces.
- **Never set a quantity bound without `IsQuantityEditable`.** The bound constrains nothing a
  buyer can do.
- **Never leave `DoesBundlePriceIncludeChild` to chance.** It is required, the org describe
  gives it no default, and it decides whether the component is a priced line at all.
- **Never combine price-included with a bundle discount on the same component.** That is the
  boundary with `rc-pricing-adjustments`, and crossing it double-counts.
- **Do not read the override objects' documented defaults as the base objects'.** Trap 4.
- **Do not put catalog content in a design document.** Structure, counts and field metadata
  travel; a customer's product names do not, and a reader copying names instead of shape has
  taken the wrong thing.
- **This skill writes nothing.** No records, no metadata, no org changes. If a task needs a
  write, it belongs in a skill that declares one, with a preview step and a rollback.
