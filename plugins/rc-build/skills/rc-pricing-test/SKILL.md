---
name: rc-pricing-test
version: '0.1.0'
writes: true
description: "Run a real pricing transaction against an org and report what the engine actually charged, beside what the person said they expected. Read this when the configuration is loaded and the question is whether it prices. Use for \"test that this discount applies\", \"does the volume tier actually work\", \"price 150 units of this and show me\", \"prove the bundle prices right\", \"why is my quote at list price\", \"check the tier before the demo\", \"undo the test quote\". It creates a quote and its lines, prices them, reads the result back and tears the quote down; it writes to an org, under the cycle below. **Not for deciding** what the price should be (rc-pricing-adjustments) or for loading the configuration (rc-pricing-build, rc-bundles-build). It stops at the quote: orders, assets, billing and amendments are out of scope."
---

# Proving what a quote actually prices

Every configuration skill in this repository ends at the same wall. A verified spec means
the records are what you asked for. It does not mean the engine prices by them, and the gap
between those two claims is where a pricing bug lives. This skill crosses that gap, and it
is the one the others point at.

It is worth saying what it is not. **A pricing test is not a green light.** It is the
instrument that finds the next platform rule, and a failure is usually worth more than a
pass — the first two runs written against a real org produced four refusals no describe
expresses and one case where correct configuration priced at list anyway.

## Prerequisite

`rc-context-pack` must have fingerprinted the target org, and **`rc-org-writer` must be
installed beside this plugin**. It owns the `sf` plumbing, the run log, the YAML parser and
the doctrine this cycle follows — in particular *The describe is not the contract*, which
this skill is a long worked example of.

## Scope: up to the reversibility frontier, and not one step past it

In scope: an account, an opportunity, a quote and its lines; running the pricing; reading
back `QuoteLineItem` and `QuoteLinePriceAdjustment`; deleting all of it.

**Out of scope: converting to an order, activating, assets, billing schedules, amendments
and renewals.** The line is reversibility, not difficulty. A quote deletes. An order that
has been activated has produced assets and billing schedules whose removal is a different
problem, and an org you can safely do that in is a disposable org, not a demo org somebody
presents from on Monday. That belongs to a second skill which does not exist yet and which
should not be written against a shared org.

---

# Half A — how the conversation goes

Nobody writes YAML. The person says what they want proved, in their own words — *"check
that 150 units of the licence price at the discounted rate on the annual model, for the
test account"* — and this skill turns that into a spec and puts it up for confirmation
before anything runs.

## What the confirmation says back

Short prose, not a dump of the file. Four things:

- **the account**, and whether it is being looked up or created. These are different risks
  and the person has to see which one they are agreeing to.
- **each line**: product, quantity, selling model.
- **what they said they expected.**
- **anything that was inferred, and why it was inferred.** "The annual selling model,
  because it is the only one the product is assigned to" is an inference. Say so. An
  inference the person does not see is a decision somebody else made for them.

## The independent check, which is the heart of this skill

Before running anything, read the org's own configuration — the schedule, the tiers in
effect, the list price on the entry — and work out what *should* happen.

**That reading does not replace the person's number. It contrasts with it.** Two sources
that were arrived at separately, agreeing, is evidence. One source checked against itself
is not evidence of anything.

- **If the two agree**, say so, say why — which tier, which bound, what it does to list —
  and ask for confirmation to run.
- **If they disagree, stop.** Do not run, and do not adjust the expected number. Show both
  readings with their grounds and ask the person to resolve it.

> **Correcting the expected number so that it matches what you read in the org deletes the
> test.** The run would then confirm the configuration against itself and pass by
> construction. This is a rule of this repository, not a preference. If the person decides
> their number was wrong, that is a decision they make in the open, and it is a new run.

**The expected number is fixed once the spec is confirmed, and is never edited after the
run.** A different number is a different test.

## When there is nothing to contrast

Sometimes the org offers no second reading: no schedule covers the product and selling
model, the quantity falls in no tier, or the entry carries no list price. Say which of
those it is, and offer to run anyway. The report is then **marked as having had no prior
contrast**, and that mark matters — a pass with nothing checking it in advance is a weaker
claim than a pass with two sources behind it.

---

# Half B — the scripts

They know nothing about natural language. They take a spec, a target org and a log. One per
phase, plus `_pricing.py`, which holds what they share — the spec shape, the junction
lookups and the independent reading — and is not run directly.

No third-party dependencies; `sf` is a subprocess and `--json` is how Ids come back. JSON
is never piped through a shell with stderr merged into it: stderr stays separate, the
envelope's status is checked before any record is read, and an empty result and a broken
command are never reported the same way.

## The spec

```yaml
spec: rc-pricing-test/v1
target:
  org: <target-org-alias>
author: <who is accountable>
created: '2026-11-27'
purpose: >
  Why this run should happen.
marker:
  token: RCT-20261127-A
account:
  mode: create          # or: lookup
  name: RCT-20261127-A Test Account
lookups:
  - alias: book
    object: Pricebook2
    where: {Name: <PRICE-BOOK-NAME>}
  - alias: product
    object: Product2
    where: {ProductCode: <PRODUCT-CODE>}
  - alias: model
    object: ProductSellingModel
    where: {Name: <SELLING-MODEL-NAME>}
lines:
  - alias: line_a
    product: '@product'
    selling_model: '@model'
    quantity: 7
    start_date: '2027-01-01'
    end_date: '2027-12-31'
    period_boundary: Anniversary
    billing_frequency: Annual
    expect:
      net_unit_price: <EXPECTED-NET-UNIT>
```

`assets/example-spec.yaml` is this file complete, with every replaceable value marked. The
`@alias` convention and the parser are `rc-org-writer`'s; this skill passes its own section
names to the same parser rather than growing a second one.

**A line with no `expect` block is rejected.** A run with nothing declared in advance is
not a test.

## The cycle

### 1. preview — never skipped

```bash
python3 plugins/rc-build/skills/rc-pricing-test/scripts/preview.py <spec.yaml> \
    --target-org <alias>
```

Read-only. Three jobs, in ascending order of worth.

**Every lookup resolves to exactly one record,** or nothing runs. No "pick the first".

**The junctions are checked, and this is where `--target-org` earns its place.** A product
and a selling model can each name a real record and be invalid together. Two objects decide
it, and the spec declares no lookup to either one:

| Junction | What it decides | If it is missing |
|---|---|---|
| `ProductSellingModelOption` | whether the product may be sold on that model at all | report and stop |
| `PricebookEntry` | the list price, **and the selling model on the line** | report and stop |

The second is the one that surprises people. `QuoteLineItem.ProductSellingModelId` is
`createable: false` — PLATFORM (v68 describe) — so you cannot put a selling model on a line
directly. Choosing the entry is how a line gets one, and a product with three entries in
one book is three different prices wearing one product code.

**Neither junction is ever created by this skill.** Adding a `ProductSellingModelOption`
changes what the customer's catalog can sell; adding a `PricebookEntry` invents a price.
Both are catalog decisions belonging to whoever owns the catalog.

**Then the independent reading**, printed beside the expectation: which tiers are in
effect, which one covers the quantity, what it does to list price, and whether the two
agree. Bounds are inclusive at both ends — see `rc-pricing-adjustments` Trap 1. On
disagreement preview exits 1 and says, in the output, that editing the expectation would
delete the test.

### 2. run — only after explicit confirmation

```bash
python3 .../run.py <spec.yaml> --target-org <alias> --log <run.jsonl> --confirm
```

Refuses without `--confirm`, and refuses a log file that already holds a run: one log, one
run. It creates the account if the spec says to, then the opportunity, then places a sales
transaction carrying the quote and its lines, then waits for `Quote.CalculationStatus` to
reach a terminal value.

**Why an opportunity appears in a pricing test.** `Quote.AccountId` is `createable: false`
— PLATFORM (v68 describe). A quote takes its account from an opportunity, so naming an
account means creating one. It is created by the run, logged, and deleted at teardown.

**It stops at the first failure and writes no log line for anything that returned no Id.**

One behaviour of this API is worth knowing before you read the code. **A refusal can still
have created a quote.** PLATFORM (v68, observed): the place call returned `isSuccess: false`
together with a `salesTransactionId`, and that quote was in the org with no lines under it —
the quote saved, then pricing refused the line and rolled the line back. Other refusals
came back with an empty `salesTransactionId` and left nothing. So the transaction is logged
whenever an Id came back, success or not, and a failed run still has something to tear down.

### 3. compare — report, do not judge

```bash
python3 .../compare.py <spec.yaml> --target-org <alias> --log <run.jsonl>
```

Read-only. It prints what was expected, what came back, and **which record it read to know
that, with the Id**, so a disagreement can be checked by hand without rerunning anything.
It does not say what is wrong and it does not propose a cause.

Two sources are read per line and they are different claims:

- **`QuoteLineItem`** — `ListPrice` against `NetUnitPrice` is where an adjustment shows up
  as money.
- **`QuoteLinePriceAdjustment`** — the itemised record of why.

**An empty adjustment table does not mean no adjustment was applied.** PLATFORM (v68,
observed): a line priced ten percent below its list price and no adjustment row was written
at all. The report states the two separately — whether the price moved, and whether
anything recorded why — because conflating them turns a configuration question into a
mystery.

### 4. teardown — exactly what this run created

```bash
python3 .../teardown.py --target-org <alias> --log <run.jsonl> --confirm
```

Reverse creation order, `kind: created` rows only, deduplicated on Id so a command pasted
twice cannot report two successes for one record. Deleting the quote takes its lines with
it.

**Absence is then established by query, one record at a time.** Not by the delete reply: a
delete that returns a well-formed refusal looks exactly like a delete that worked, which is
how a teardown in this repository once reported four deletions that never happened.

## Accounts, and the limit worth stating in advance

| `account.mode` | Marked | Modified | Torn down |
|---|---|---|---|
| `lookup` | no | no | **no** |
| `create` | the name carries the marker token | no | yes |

A looked-up account is somebody else's record. The spec validator refuses `mode: create`
unless the name contains the marker token, so a leftover is identifiable as this run's.

**The real limit: an account with records hanging off it does not delete.** If teardown
fails part way — the quote goes, the opportunity does not — the account stays. The report
says it stayed, naming it, and exits non-zero. It never reports a deletion it did not
perform.

## What a FAIL means, which is the part worth reading

A FAIL admits at least three readings and no script can tell them apart:

1. **the expectation was wrong** — the policy says something other than what the person
   believed it said;
2. **the configuration is wrong** — the records exist but do not express the policy, which
   is `rc-pricing-adjustments`' territory;
3. **the configuration is right and the engine did something else**, for a reason nobody
   knows yet.

The third is the valuable one, and it is a new entry in `notes/` rather than a bug to
retry. It happened on the second run written against a real org: preview agreed with the
expectation, both readings derived from an active schedule whose tier covered the quantity,
and the line priced at list. A different product under **the same schedule, same book, same
selling model** took its tier correctly. Nothing visible in either tier record distinguishes
them. That is recorded as an open question, not as an answer.

## Platform rules this skill found, each by being refused

PLATFORM (v68, observed 2026-11-27). The sentences are kept verbatim because for these the
sentence is the only documentation there is. Each is shape 1 in `rc-org-writer`'s *The
describe is not the contract*: required, and undeclared.

| Rule | What the platform says |
|---|---|
| a line needs an end date or a subscription term | *"Specify either the end date or add the Subscription Term and subscription term unit parameters to execute your Pricing Procedure."* |
| a dated line needs a period boundary | *"Enter a start proration period with one of these values: AlignToCalendar, Anniversary, DayOfPeriod, or LastDayOfPeriod."* |
| a term or evergreen line needs a billing frequency | *"When the SellingModelType is Evergreen or Term-Defined, BillingFrequency can't be null"* |

A v68 describe marks `EndDate`, `PeriodBoundary` and `BillingFrequency` all `nillable: true`
on `QuoteLineItem`, and marks `SubscriptionTermUnit` `createable: false` — so the first
message names a parameter you cannot supply. Give the dates and the boundary.

## Verified anchors

- **PLATFORM (v68 describe)** — `Quote.AccountId` and
  `QuoteLineItem.ProductSellingModelId` are both `createable: false`;
  `PricebookEntry.ProductSellingModelId` is createable and not updateable.
- **PLATFORM (v68, observed)** — the place call returned `isSuccess: false` with a
  populated `salesTransactionId` on one refusal and an empty one on another, so a failed
  run may or may not leave a quote.
- **PLATFORM (v68, observed)** — a quote reached `CalculationStatus` `CompletedWithTax`, a
  value the same org's describe does not list among that field's picklist values.
- **PLATFORM (v68, observed)** — a line priced below its list price with zero
  `QuoteLinePriceAdjustment` rows written.
- **PLATFORM (v68, observed)** — deleting a quote removed its lines; deleting an account
  succeeded once the opportunity above it was gone.

## Not verified

- **Everything observed here comes from one org and one day**, and none of it has been
  replicated on a second org. Under the pack's notes protocol it is unvalidated.
- **Why a correctly configured tier did not apply to one product** while another product on
  the same schedule priced correctly. The leading guess — that pricing reads a decision
  table which has to be refreshed from Setup after tiers change — is a guess; nothing here
  tested it, and testing it means a Setup action this skill does not perform.
- **Whether `QuoteLinePriceAdjustment` rows ever appear** in an org where price waterfall
  persistence is switched on. The absence observed here may be that setting rather than a
  property of the engine.
- **Only `Volume` schedules are contrasted.** The independent reading reads
  `PriceAdjustmentTier`. Attribute and bundle adjustments are not computed, so a spec that
  depends on them runs with no prior contrast and the report says so.
- **One line at a time is all that has been exercised.** The spec takes several and the
  scripts handle several; a multi-line quote has not been run.
- **Bundles have not been priced through this.** A bundle parent with components reaching
  the quote as `QuoteLineRelationship` rows is a shape this skill does not build yet.
