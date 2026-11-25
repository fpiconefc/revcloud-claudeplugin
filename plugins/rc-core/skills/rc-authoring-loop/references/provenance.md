# Provenance

## What counts as a claim

A claim is any sentence a reader could act on and be wrong about. In this domain that is:

- An object or field exists, or is named a particular way
- A picklist holds particular values, or a label that differs from its value
- A field is required, defaulted, createable, updateable or read-only
- A feature arrived in a particular API version, or requires a particular licence
- The platform behaves a particular way (what an amendment produces, what an API accepts,
  what happens on renewal)
- A limit, a default, or a protected object

Not claims, and not to be marked:

- Design advice ("I'd keep the selling-model library small")
- Procedure ("run the sweep before drafting")
- Arithmetic performed from a definition the guide gives
- Anything about this repo itself

The distinction is actionability. "`ProductSellingModelOption` has a `Minimum` field" is a
claim; someone builds on it. "Prefer one product with two selling models" is advice; it
survives being wrong about details.

## The three sources

A claim resolves to **DOCS**, **PLATFORM**, **ORG**, or none. The split between the last
two is the one that keeps this repo honest, because they do not travel the same distance.

### DOCS — the developer guide

The Revenue Lifecycle Management developer guide, v68. Best practice, intended behaviour,
API version floors, and what the product supports in general. **DOCS is what structures the
body of a skill**: the shape of a workflow, the order of operations, the vocabulary.

> Per the developer guide, `UpperBound` is not inclusive.

### PLATFORM — field metadata verified by describe

Object and field metadata: writability, picklist values, labels, required, defaults,
read-only projections. This comes from the RCA managed package. It is the same in any org
on the same API version, and configuring an org does not change it. Verifying it against a
describe is the method that stops a skill inventing fields.

**A PLATFORM claim carries the API version it was verified at, and never names an org.**

> **PLATFORM (v68 describe)** — on `PriceAdjustmentTier`, `TierType` is required and
> writable while `AdjustmentType` is createable false and updateable false.

The version is not decoration. Metadata moves when the package moves, and it differs when a
feature is unprovisioned, so a PLATFORM claim with no version cannot be rechecked. If you
verified against two versions, say both.

### ORG — how one org happens to be loaded

Counts, distributions, which records exist, what a catalog looks like. **This structures
nothing.** It is not doctrine, it does not travel, and a reader who copies it has copied
someone else's configuration.

An ORG claim has exactly two legitimate uses in a `SKILL.md`:

1. **Showing where the guide and reality disagree.** The `UpperBound` case in
   `rc-pricing-adjustments` is the model: the guide documents the bound as exclusive and the
   only org available for checking is loaded as though it were inclusive. That contradiction
   is a finding a reader must act on.
2. **Declaring what could not be verified.** "No adjustment has ever been applied in the
   only org available, so every claim about what the engine computes is unrun."

Everything else goes to `notes/` in the pack. Counts that structure the body of a skill are
the failure this rule exists to prevent: written as an observation, read as a
recommendation.

## No skill names an org

A `SKILL.md` does not name an org. Not in a table, not in a column header, not in an
anchor, not in an example, not in a footnote. `lint_skill.py` fails the build on it.

The rule is a consequence of the three categories rather than a separate idea. If a claim
is PLATFORM it does not need the org, because the metadata is the same everywhere. If it is
ORG it does not belong in the body. **So a sentence that needs the org's name to stand up
is telling you it is not doctrine.**

Where naming it is right: `notes/` in the pack, where an entry is expected to carry the
alias, the date and the full counts. That is implementation material, and it is useful
precisely because it is specific.

A script that takes an org alias as an argument is not naming one, and a spec that declares
its target org is naming its own parameter. Neither is a claim.

## Marking

Keep it light. Heavy annotation makes a skill unreadable, which defeats the purpose.

In prose, name the source inline where the claim appears:

> Per the developer guide, `PricingTermUnit` accepts Months, Quarterly, Semi-Annual and Annual.

> A v68 describe adds Weekly to that picklist.

In tables, a `Source` column with `DOCS`, `PLATFORM (v68)` or `ORG`.

In a block of claims drawn from one source, one lead-in sentence covers the block. Do not
mark every line of a table that is entirely from one describe.

## Precedence

| Question | Wins |
|---|---|
| What does the product support in general? | DOCS |
| Which API version introduced it? | DOCS |
| Is this field writable, required, or read-only? | PLATFORM |
| What values does this picklist hold, and what are their labels? | PLATFORM |
| Is this field available without an extra licence? | DOCS, then confirm by describe |
| How is a particular customer's catalog loaded? | ORG, and it stays in `notes/` |

When DOCS and PLATFORM disagree, say both and say which governs. That disagreement is the
most valuable thing the loop produces — the guide documenting `TierType` with no values
while the describe shows three is how a reader learns not to trust one source alone.

## The unverifiable

Some things no source settles: whether a configuration was intentional, what a customer's
policy should be, how a feature behaves under load. Say so, in the body, in the place a
reader would otherwise assume you knew.

A short, specific statement of ignorance is more useful than a hedge:

> I could not determine whether the Evergreen premium is deliberate pricing or a leftover
> from testing. Confirm with the customer before copying it.

## Dating

A PLATFORM claim carries its API version. An ORG observation in `notes/` carries the alias
and the date, because orgs change and an undated observation cannot be rechecked. A DOCS
claim carries the guide version, which for this pack is v68 throughout.
