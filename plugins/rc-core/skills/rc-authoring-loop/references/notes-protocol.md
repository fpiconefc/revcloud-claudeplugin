# Notes protocol

`~/.claude/knowledge/revenue-cloud/notes/` is the part of the pack that cannot be
regenerated. Docs can be re-swept and orgs re-fingerprinted; notes are the accumulated
experience of people who hit something and worked it out. Treat the folder accordingly.

## What belongs

- **Deltas.** The guide says one thing, an org shows another.
- **Traps.** Something that looks like it should work and does not. The `BillingFrequency`
  / `BillingFrequency2` rename between quote and order is the archetype: no document warns
  you, and the failure is silent.
- **Verified patterns.** A configuration seen working, with the org and date.
- **Dead ends.** An approach tried that did not work, and why. Saves the next person the
  same afternoon.

## What does not

- Anything a re-sweep would produce. Describes belong in `describe/`, not here.
- Customer-identifying data. Notes get shared; keep them about the platform.
- Doctrine from a single dev org, unmarked. See below.

## Format

One Markdown file per topic, named for the topic, appended to over time. Each entry:

```markdown
## <short title>

**Observed:** <org alias>, <date>. <Or: developer guide vN, section>.
**Status:** verified | unvalidated | contradicted

<What was seen, in two or three sentences.>

**Do:** <what a reader should do about it.>
```

`Status` is the field that does the work:

- **verified** — seen in a customer org, or in more than one org.
- **unvalidated** — seen once, in a dev or demo org. Could be a leftover from an
  experiment. This is the default for a single observation.
- **contradicted** — a later observation disagrees. Keep the entry; add the contradiction
  under it. Deleting it loses the fact that the question is unsettled.

## Why unvalidated is the default

Development orgs accumulate residue. Someone tested a pricing idea in 2024 and left it.
Writing that up as "the pattern" and sending it into a customer design is how an
implementation acquires a decision nobody made.

The cost of marking something unvalidated is one word. The cost of promoting a dev-org
artifact to doctrine is discovered months later, by someone who trusted you.

## Promotion

An unvalidated note becomes verified when a second, independent org shows the same thing.
Update the status, add the second org and date. Do not promote on the strength of it
making sense; plenty of wrong things make sense.
