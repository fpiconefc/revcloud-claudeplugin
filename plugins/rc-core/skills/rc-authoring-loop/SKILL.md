---
name: rc-authoring-loop
version: '0.2.0'
description: "The authoring discipline for this repository. Read this BEFORE writing, editing or reviewing any rc-* skill, and before adding anything to the knowledge pack's notes/. It defines the loop every skill is written through — scope, ground, draft, verify claim by claim against the pack, record the deltas, review — and the provenance rules that keep a skill from asserting Revenue Cloud facts it cannot support. Use for \"write a new skill\", \"add a skill to rc-build / rc-migrate / rc-labs / rc-accelerate\", \"review this SKILL.md\", \"is this skill ready to commit\", \"how do we write skills here\", \"lint the skills\", \"record what I learned in the pack\", and whenever a contributor or another agent is about to author content for this repo. Not for answering Revenue Cloud questions or building the knowledge pack itself (that is rc-context-pack), and not for configuring an org."
---

# Authoring loop — how a skill gets written here

A skill in this repository is not a prompt. It is a claim-bearing artifact that someone
will follow while configuring a customer's revenue system. A wrong sentence in a
`SKILL.md` becomes wrong configuration, and the person following it has no way to tell
which sentences were verified and which were generated.

So the rule is not "write a good skill". The rule is: **every factual claim about
Revenue Cloud is marked with where it came from, and anything that cannot be marked is
either verified or removed.** The loop below exists to make that cheap rather than
virtuous.

This skill governs the repo. Read it before authoring; it is not optional for
contributors, human or agent.

## Prerequisite

The knowledge pack must exist and be fresh. Run `rc-context-pack` first. Authoring
without a pack means drafting from memory, which is exactly the failure this repo is
built to prevent. If the pack is stale, refresh it before writing, not after.

## The loop

### 1. Scope

Write one sentence saying what the skill enables someone to do, and one saying when it
should trigger. If either takes a paragraph, the skill is doing two things; split it.

Decide and record two properties now, because they change everything downstream:

- **Reads or writes.** A skill that writes to an org carries different obligations:
  preview before apply, idempotency, and a stated rollback. State it in the body.
- **Which pack half it depends on.** A skill resting on ORG facts cannot be verified
  without a fingerprint of a comparable org. If you don't have one, say so in the skill
  rather than guessing.

### 2. Ground

Before drafting, collect what the pack already knows about the topic: the relevant
describes under `orgs/<alias>/describe/`, the matching section of the developer guide,
and any existing `notes/`. Read them. The point of the pack is that this step is a file
read and not a search.

If the pack has nothing on the topic, that is the finding. Either extend the pack first,
or write the skill with the gap marked explicitly.

### 3. Draft

Write the `SKILL.md` body. Keep it under roughly 500 lines; push detail into
`references/` and repetitive work into `scripts/`. See `assets/SKILL-template.md` for the
shape and `references/frontmatter.md` for the conventions this repo uses.

Draft freely. Do not stop to verify every sentence while writing — that is the next step,
and interleaving them produces a hedged, unreadable skill.

### 4. Verify, claim by claim

Go back through the draft and mark every factual claim about Revenue Cloud. For each one,
resolve it to **DOCS**, **ORG**, or **neither**.

`references/provenance.md` defines what counts as a claim and how to mark it. The short
version: object names, field names, picklist values, API versions, behaviour, and limits
are claims. Design advice and procedure are not.

A claim that resolves to neither has three honest endings, and only three:

- Verify it, and mark it.
- Rewrite it as advice rather than fact ("I'd model this as..." instead of "RCA stores this in...").
- Delete it.

"Leave it, it's probably right" is not one of them. The probability that a plausible
Revenue Cloud sentence is correct is not high enough to spend a customer's implementation on.

#### Count every quantifier

A claim carrying **all**, **none**, **every**, **each**, **neither**, **no two** or **any
two** is a claim about a set, and it is verified by counting the set — against the table
printed underneath it, or against the describe it came from. Do the count; do not eyeball it.

This is a separate step because the failure has a signature: the generalisation overshoots
by one notch and the evidence sitting directly below it disproves the sentence. "Renamed on
each of the three" above a table where two of the three agree. "Does not mean the same thing
on any two of them" above a table showing two identical rows. "Quantity 10 falls in no tier"
where four quantities do. Each one is a correct observation stated one step too strongly, and
each is caught by reading the writer's own table back to them.

Prefer the counted form. "Two of the three share it and the order is the odd one out" is both
true and more useful to a reader than "all three differ", because it is what they can keep in
their head.

#### No catalog data in a SKILL.md

A skill carries no catalog content from any org: no product names, no SKUs or product
codes, no prices, no attribute names and no attribute values. What you cite from an org is
**structure, counts and field metadata** — which objects exist, how many rows of which
shape, what a describe says about a field. Worked examples use invented, generic names, and
say that they are invented.

The test is simple. If a claim needs a real name to stand up, it is not doctrine: it is an
implementation note about one customer, and it belongs in the pack, not in a skill.

Two reasons, and the second is the one people miss. Skills get published, shared and read
by people with no relationship to the org the examples came from. And an example built on
real catalog data quietly invites the reader to copy the catalog rather than the shape,
which is the opposite of what a skill is for — the shape travels to any org, the catalog
travels nowhere.

Counts are not catalog data and should stay. "272 component rows over 240 distinct child
products" is structure, and it is exactly the kind of evidence a reader needs to judge how
far to trust the example.

### 5. Record the deltas

Verification will turn up disagreements between the guide and the org. Those are the most
valuable output of the whole loop, and they are lost unless written down immediately.

For a customer-facing fact, **ORG wins**. For what the product supports in general,
**DOCS wins**. Never average them, and never quietly pick one.

Write each delta to `~/.claude/knowledge/revenue-cloud/notes/` with: what the guide says,
what the org shows, which org and when, and what a reader should do about it. One file per
topic, appended to over time. `references/notes-protocol.md` has the format and the rules
about what does *not* belong there.

The discipline that matters most: an observation from a development or demo org is **not
doctrine**. Dev orgs carry leftovers from experiments. Mark such observations as
unvalidated until a customer org confirms them. A plausible pattern promoted to doctrine
from one dev org is worse than no note at all, because it reads as verified.

### 6. Review before commit

```bash
python3 scripts/lint_skill.py <path-to-skill-dir>
```

The linter checks the mechanical things: frontmatter present and well-formed, description
long enough to trigger reliably and containing trigger phrases, description short enough
for claude.ai to accept (1024 characters — over that it is rejected at upload while
Claude Code loads it happily, so nothing else catches it), body length, references
actually referenced from the body, scripts compiling, and unmarked claim-shaped language.

It catches shape, not truth. A skill that lints clean can still be wrong, so the human
review below is not optional:

- Does every Revenue Cloud fact carry DOCS or ORG?
- Has every quantifier been counted against the table or describe below it?
- Is the skill free of catalog data — product names, SKUs, prices, attribute names and values?
- Is every unverifiable thing stated as unverifiable, in the body, where a reader will see it?
- Would someone following this skill configure something that works?
- If it writes to an org: is there a preview step, and can it be run twice safely?

Then commit. One skill per commit, with the deltas found in the message body. That history
is how you later reconstruct why a skill says something surprising.

## Anti-patterns

**Drafting from memory because the pack was slow to read.** The resulting skill is
indistinguishable from a verified one by anyone downstream. This is the failure mode the
repo exists to prevent and it is the easiest one to slip into.

**Hedging everything.** "May", "typically" and "in some cases" sprayed over a skill is not
provenance, it is the absence of it. Mark the claim or cut it.

**A description that only says what the skill does.** Triggering happens on the
description alone. It must also carry the phrasings a user would actually type. Skills
under-trigger far more often than they over-trigger, so write the description a little
pushier than feels natural.

**Encoding one org's configuration as the way Revenue Cloud works.** Especially from a
dev org. Say which org, and say when.

**Letting a script overwrite `notes/`.** Notes are the only part of the pack that cannot
be regenerated. Scripts append; they never rewrite.

## For agents other than Claude

Same loop, no exceptions. If your agent cannot read the pack, it cannot author for this
repo — have it draft and hand the draft to something that can verify, rather than
committing an unverified skill. See `AGENTS.md` at the repo root.
