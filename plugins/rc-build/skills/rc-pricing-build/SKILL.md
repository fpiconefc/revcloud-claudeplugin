---
name: rc-pricing-build
version: '0.1.0'
writes: true
description: "Turn a discount policy that has already been decided into an rc-org-writer spec and load it: volume and term tiers, the price adjustment schedule they hang off, the pre-flight checks that catch what a describe cannot, then preview, apply, verify and teardown. Read this when the pricing decision is made and the work is building it. Use for \"load this volume discount\", \"create the price adjustment schedule\", \"build these tiers in the sandbox\", \"apply the discount policy\", \"undo the tiers I just loaded\", \"why did my tier fail to save\". This skill writes to an org, through the cycle below. **Not for deciding** what the pricing should be: Volume against Term, Range against Slab, which object a schedule type reads — that is rc-pricing-adjustments, and if the decision is not made yet, go there first."
---

# Building a pricing decision into an org

Two skills touch these objects and they do different jobs. **`rc-pricing-adjustments` is for
deciding**: what varies, which `ScheduleType` reads which child object, why Range and Slab
price differently from identical tiers, where the adjustment lands. **This skill is for
loading** a decision that has already been made.

If you arrive here without the decision — unsure whether this is Volume or Term, or whether
the method should be Range or Slab — **stop and read `rc-pricing-adjustments` first**. A spec
is a precise statement of an imprecise decision, and building one is how an unexamined
default becomes a price.

What this skill owns is narrow: which objects and fields a pricing load touches, in what
order, and **what to check before the preview** — because three of the rules that stop a
pricing apply appear in no describe, and one of them concerns an object the spec never names.

## Prerequisite

Two, and neither is optional.

`rc-context-pack` must have fingerprinted the target org. `rc-org-writer` must be installed
beside this plugin: it owns the spec format, the `@alias` references, lookups, marking, the
log, and all four phases, **including their scripts**. This skill emits a spec and calls
them. It does not reimplement any of it, and a build skill that reimplements a write cycle is
how the loosest standard in the repository becomes the standard.

## What gets built

A volume or term discount is two objects:

| Object | One per | Carries |
|---|---|---|
| `PriceAdjustmentSchedule` | policy | `ScheduleType`, `AdjustmentMethod`, `Pricebook2Id`, effective dates |
| `PriceAdjustmentTier` | band | bounds, `TierType`, `TierValue`, the product and selling model it applies to |

The schedule is created first and the tiers reference it by `@alias`. The product, the
selling model and the price book are **lookups**: they exist already, the spec names them by
a stable key rather than an Id, and nothing in this cycle modifies them.

`assets/example-spec.yaml` is a complete one — one schedule, three tiers, meant to be
applied and torn down as a unit. Its shape is finished; three placeholder values are replaced
with the target org's own identifiers before it runs.

## The checks that come before the preview

```bash
python3 plugins/rc-build/skills/rc-pricing-build/scripts/check_pricing_spec.py \
    <spec.yaml> --target-org <alias>
```

Read-only. Run it **before** `validate_spec.py`, and both before apply. Seven checks in two
groups, and the first three are platform rules that no describe expresses — each one observed
stopping a real apply on API v68.

### 1. Tier bounds are inclusive at both ends

A tier whose `LowerBound` equals the previous tier's `UpperBound` is refused:

> The tiers must have unique effective date ranges and lower and upper bound value ranges.

A shared boundary is an overlap, so each tier starts **one unit above** the previous upper
bound: 251, not 250. The Salesforce guide documents the opposite — *"set this value one digit
higher than the quantity you want the tier to include"* — and following it produces bands
written 1–100, 100–200, 200–300, each sharing a bound with the next, which is exactly the
shape the platform rejects. `rc-pricing-adjustments` Trap 1 has the evidence.

**This skill generates correct bounds rather than leaving the trap for the reader.** When a
policy says "5% from 100, 10% from 251, 15% from 501", the bands are derived from the
thresholds: each tier's `UpperBound` is the next threshold minus one, and the last is left
open. The check exists for a spec written by hand, and it fails with both numbers:

```
error: tiers @tier_100 and @tier_251 share the bound 250. Bounds are inclusive at both
ends, so this is an overlap and the platform refuses it. Start @tier_251 at 251, not 250.
```

### 2. Every tier needs `EffectiveFrom`

PLATFORM (v68 describe) reports it `nillable: true`. The platform refuses the record without
it:

> Specify the Effective From date to save your price adjustment tier.

Set it on every tier. The schedule's own dates do not substitute.

### 3. The product must already be assigned to the selling model

A tier carries `Product2Id` and `ProductSellingModelId`. Both can name real records and the
tier still fails, because the pair must be joined by a `ProductSellingModelOption` — **an
object the spec never mentions.** Two individually valid lookups, jointly invalid.

`validate_spec.py --target-org` cannot see this: it checks that each lookup resolves, and
each one does. So this skill queries the junction directly, for every distinct
product-and-selling-model pair its tiers use.

**If the assignment is missing, this skill reports it and stops.** It does not create the
junction. Adding a `ProductSellingModelOption` changes what a product in the customer's
catalog can be sold on, which is a catalog decision belonging to whoever owns the catalog,
not a side effect of loading a discount.

### 4–7. Doctrine, carried over from `rc-pricing-adjustments`

- **The schedule type must read tiers.** `Volume` and `Term` do. An `Attribute` or `Bundle`
  schedule carries a different child object, so tiers under it price nothing and raise no
  error — the failure `rc-pricing-adjustments` opens with.
- **`AdjustmentMethod` is stated, never defaulted.** It defaults to `Range`, and Range and
  Slab produce different prices from identical tiers. A method nobody chose is the most
  expensive unexamined field in this graph.
- **No gaps between consecutive tiers.** A quantity that falls in no band gets no adjustment
  and a plausible invoice.
- **All tiers under one schedule share a selling model**, unless the mix is deliberate, in
  which case `purpose` says so. This one warns rather than fails.

## The spec is the control point

The spec is written by this skill from the conversation, and **read by a person before
anything is written**. That review is the only place a wrong policy is caught cheaply, so the
spec is written to be reviewable rather than merely valid.

Five things must be legible at a glance, per tier or per schedule:

| What | Why it is on the page |
|---|---|
| the bounds of every tier | the off-by-one is the likeliest error and the hardest to see later |
| the selling model | a tier priced against the wrong term is not visibly wrong afterwards |
| the effective dates | a schedule live from the wrong date misprices silently |
| the price book | scope: which catalog this policy reaches |
| `AdjustmentMethod` | Range or Slab changes every number below it |

If a reviewer has to resolve an `@alias`, open another file or run a query to check any of
those, the spec is not reviewable and should be rewritten until it is.

## The cycle

`rc-org-writer` owns all four phases and their scripts. In order, with this skill's check
added at the front:

```bash
# 0. pricing pre-flight — this skill
python3 plugins/rc-build/skills/rc-pricing-build/scripts/check_pricing_spec.py \
    <spec.yaml> --target-org <alias>

# 1. preview — rc-org-writer
python3 plugins/rc-core/skills/rc-org-writer/scripts/validate_spec.py \
    <spec.yaml> --target-org <alias>

# 2. apply, after a person has read the preview
python3 plugins/rc-core/skills/rc-org-writer/scripts/apply.py <spec.yaml> \
    --target-org <alias> --log applied/<run>.jsonl --confirm

# 3. verify
python3 plugins/rc-core/skills/rc-org-writer/scripts/verify.py <spec.yaml> \
    --target-org <alias> --log applied/<run>.jsonl

# 4. teardown, when the run has served its purpose
python3 plugins/rc-core/skills/rc-org-writer/scripts/teardown.py \
    --target-org <alias> --log applied/<run>.jsonl --confirm
```

The confirmation before apply is per preview: editing the spec voids it. Verify will report
expected differences on every tier — five fields the platform projects from the schedule and
the selling model, an autonumbered `Name`, and `EffectiveFrom` returned in a different offset
notation. Those are documented in `rc-org-writer`; none of them is a finding.

**In a chat session with no shell**, `rc-org-writer`'s "Without a shell" section has the
connector equivalent of each phase. The pricing checks above are queries you run by hand
there: the tier bounds and `EffectiveFrom` are read off the spec, and the selling-model
assignment is one `soqlQuery` against `ProductSellingModelOption`.

## A new schedule is created inactive

Every schedule this skill writes carries `IsActive: false`, and switching it on is a human
step outside the cycle.

The reason is specific rather than general caution. **An org can already have an active
schedule of the same type over the same price book**, and what happens when two of them
cover the same product is neither documented in the guide nor visible in any describe.
Establishing it would mean running a transaction and reading which adjustment landed — which
is out of scope here, below. So the cycle refuses to be the thing that makes a second
schedule live: it builds the configuration, verify proves it is what the spec said, and a
person with the org in front of them decides whether to turn it on.

Note that in the spec's own terms this is the inactive-then-activate case `rc-org-writer`
declares out of scope: there is no update phase, so the activation is not a step this cycle
performs.

## Out of scope: proving what it prices

This skill creates configuration. It does **not** run transactions, and nothing here tells
you what a quote actually prices.

Placing a quote and reading which adjustment landed on `QuoteLinePriceAdjustment` or
`OrderItemAdjustmentLineItem` belongs to a testing skill that does not exist yet, and which
will depend on this one for the configuration it exercises. Until it does, a verified spec
means the records are what you asked for — not that the engine prices the way you expect.
Those are different claims and the gap between them is where a pricing bug lives.

## Verified anchors

- **PLATFORM (v68, observed)** — a tier whose `LowerBound` equals the previous tier's
  `UpperBound` is refused as an overlap: *"The tiers must have unique effective date ranges
  and lower and upper bound value ranges."* Bounds are inclusive at both ends; the next tier
  starts one unit higher.
- **PLATFORM (v68, observed)** — a tier without `EffectiveFrom` is refused, *"Specify the
  Effective From date to save your price adjustment tier"*, although the describe reports the
  field `nillable: true`.
- **PLATFORM (v68, observed)** — a tier naming a product and a selling model not joined by a
  `ProductSellingModelOption` is refused. The precondition is on an object the spec does not
  reference.
- **PLATFORM (v68 describe)** — `PriceAdjustmentSchedule.ScheduleType` offers Volume, Term,
  Attribute, Bundle and Custom; `AdjustmentMethod` offers Range and Slab and defaults to
  Range; `PriceAdjustmentTier.PriceAdjustmentScheduleId` is createable and not updateable, so
  a tier cannot be moved between schedules.
- **PLATFORM (v68, observed)** — a created tier returns `AdjustmentType`, `ScheduleType`,
  `SellingModelType`, `PricingTerm` and `PricingTermUnit` unasked, plus an autonumbered
  `Name`, and `EffectiveFrom` in a different offset notation than it was sent.
- **DOCS** — the guide documents `UpperBound` as not inclusive and instructs setting it one
  higher than the intended quantity. The platform contradicts this; see
  `rc-pricing-adjustments` Trap 1.
- **PLATFORM (v68, observed 2026-11-27)** — `assets/example-spec.yaml` runs clean through
  all four phases with its placeholders filled in: pre-flight and preview pass, apply creates
  the schedule and three tiers, verify reports 27 matches and 22 expected differences with
  **zero unexpected**, and teardown removes all four. The tiers persist with their stepped
  bounds intact — 100–250, 251–500, 501 open — and the schedule persists inactive.
  Existence before teardown and absence after were both confirmed **by querying the org**,
  not by reading the scripts' output: that distinction is what caught a teardown reporting
  deletions it had not performed. The org returned to its exact prior counts, and the
  referenced product's selling-model options were untouched throughout.

## Not verified

- **What the engine does with a fractional quantity between tiers.** Because bounds are
  inclusive and a shared bound is refused, consecutive tiers must step by one. For whole
  quantities that is gapless. For a product quantified in fractions, a quantity of 250.5
  falls between a 100–250 tier and a 251–500 tier, and **the gap cannot be closed**, because
  the configuration that would cover it is the one the platform rejects. If a product is
  fractionally quantified, settle this before designing tiers on it.
- **Re-applying the same spec fails rather than being a no-op.** The second run stops with
  `DUPLICATE_VALUE` on the schedule's `GlobalKey` and creates nothing, which is correct and
  safe. But a skill that generates re-appliable specs will meet this constantly, and the
  answer within the contract is teardown then re-apply, not upsert —
  `rc-org-writer` explains why upsert would break its ownership rule.
- **How two active schedules of the same type over one price book interact.** The reason
  schedules are created inactive, and not something this pack can settle without a
  transaction.
- **These rules were observed on one org, on one API version**, and are not replicated. They
  are platform behaviour rather than configuration, so they should travel; confirm on a
  second org before treating them as settled everywhere.
- **The example spec is not unverified** — it was taken through all four phases on API
  v68, and what remains unverified about it is only what a second org would settle. See
  **Verified anchors**.

## Guardrails

- **Never decide the pricing here.** If the conversation is still choosing between Volume and
  Term, or Range and Slab, this skill is the wrong one. Send it to
  `rc-pricing-adjustments`.
- **Never let consecutive tiers share a bound.** Step by one. The guide's instruction tells
  you to do the opposite and the platform refuses it.
- **Never omit `EffectiveFrom` on a tier**, whatever the describe says about nillability.
- **Never create a `ProductSellingModelOption` to make a tier save.** That changes what the
  product can be sold on. Report the missing assignment and stop.
- **Never leave `AdjustmentMethod` to its default.** State Range or Slab deliberately.
- **Never activate a schedule as part of the run.** Verify first, then a person decides.
- **Never reimplement the write cycle.** Emit the spec and call `rc-org-writer`'s scripts.
- **Never treat a verified spec as proof of a price.** Verify proves the records match the
  spec. What they price is a transaction away and out of scope here.
