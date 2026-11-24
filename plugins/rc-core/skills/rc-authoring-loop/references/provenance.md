# Provenance

## What counts as a claim

A claim is any sentence a reader could act on and be wrong about. In this domain that is:

- An object or field exists, or is named a particular way
- A picklist holds particular values
- A feature arrived in a particular API version, or requires a particular licence
- The platform behaves a particular way (what an amendment produces, what an API accepts,
  what happens on renewal)
- A limit, a default, or a protected object

Not claims, and not to be marked:

- Design advice ("I'd keep the selling-model library small")
- Procedure ("run the sweep before drafting")
- Anything about this repo itself

The distinction is actionability. "`ProductSellingModelOption` has a `Minimum` field" is a
claim; someone builds on it. "Prefer one product with two selling models" is advice; it
survives being wrong about details.

## Marking

Keep it light. Heavy annotation makes a skill unreadable, which defeats the purpose.

In prose, name the source inline where the claim appears:

> Per the developer guide, `PricingTermUnit` accepts Months, Quarterly, Semi-Annual and Annual.

> In arm-picone (swept 2026-11-24) `PricingTermUnit` also offers Weekly.

In tables, a `Source` column with `DOCS` or `ORG <alias>`.

In a block of claims drawn from one source, one lead-in sentence covers the block. Do not
mark every line of a table that is entirely from one describe.

## Precedence

| Question | Wins |
|---|---|
| What does a customer's org have? | ORG |
| What does the product support in general? | DOCS |
| Which API version introduced it? | DOCS |
| What values does this picklist hold here? | ORG |
| Is this field available without an extra licence? | DOCS, then confirm in ORG |

When the two disagree, say both and say which governs. A reader who only sees the winner
cannot tell whether you checked.

## The unverifiable

Some things neither source settles: whether a configuration was intentional, what a
customer's policy should be, how a feature behaves under load. Say so, in the body, in the
place a reader would otherwise assume you knew.

A short, specific statement of ignorance is more useful than a hedge:

> I could not determine whether the Evergreen premium here is deliberate pricing or a
> leftover from testing. Confirm with the customer before copying it.

## Dating

Every ORG claim carries the org and roughly when it was observed. Orgs change. A claim
without a date is a claim that cannot be re-checked, and in six months nobody will know
whether to trust it.
