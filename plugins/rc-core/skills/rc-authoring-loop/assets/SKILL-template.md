---
name: <skill-name-matching-directory>
version: '0.1.0'
description: "<What it does>. Read this BEFORE <the moment it must not be skipped>. Covers <scope>. Use for \"<phrase a user would type>\", \"<a clumsier phrase>\", \"<a symptom, not a feature name>\". Not for <neighbouring skill's job>."
---

# <Title — what this does, in plain words>

<Two or three sentences on why this skill exists. Name the failure it prevents.
Avoid restating the description; by the time anyone reads this, the skill has
already triggered.>

## Prerequisite

<State the pack dependency, and which half. If the skill writes to an org, say so
here, in the first screen, not buried below.>

## Routing

<When several paths exist, a small table that picks one. Delete if there is one path.>

| Situation | Do |
|---|---|
|  |  |

## Workflow

### 1. <First step, imperative>

<What to do. Commands in fenced blocks. One idea per step.>

### 2. <Second step>

### 3. <Verify>

<Every skill that changes something ends with how to tell whether it worked.
A skill that writes without a verification step is incomplete.>

## Verified anchors

<Facts this skill rests on, each marked. Keep short; depth goes in references/.>

- **DOCS** — <claim>. (developer guide, <section>)
- **ORG <alias>, <date>** — <claim>.

## Not verified

<What you could not settle, stated plainly, where a reader will see it before
acting. If this section is empty, say why rather than deleting it: an empty
section means you checked, a missing one means nobody knows.>

## Guardrails

- <The mistake a reader is most likely to make.>
- <What this skill must never do — write to an org, assume a module is provisioned,
  encode a dev-org artifact as doctrine.>
