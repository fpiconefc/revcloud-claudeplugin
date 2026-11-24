# Frontmatter conventions

Every `SKILL.md` opens with YAML between `---` fences. Two keys are required by the
platform; this repo adds a third by convention.

```yaml
---
name: rc-catalog-selling-models
version: '0.1.0'
description: "..."
---
```

## name

Lowercase, hyphenated, matching the directory name. Prefix is not needed: the plugin
already namespaces it (`rc-build:rc-catalog-selling-models`).

## version

Quoted, semantic. Bump the patch for wording, the minor for new behaviour, the major when
a reader following the old version would now do the wrong thing. The version in
`marketplace.json` is the plugin's, not the skill's; they move independently.

## description

This is the whole triggering mechanism, so it carries more weight than its length
suggests. It must say what the skill does, when it applies, and — this is the part people
skip — the phrasings a user would actually type.

Shape that works:

> "[What it does]. Read this BEFORE [the moment it must not be skipped]. Covers [scope].
> Use for \"[phrase]\", \"[phrase]\", \"[phrase]\". Not for [the neighbouring skill's job]."

Three rules learned the hard way:

**Be pushy.** Skills under-trigger far more than they over-trigger. A description that
reads slightly too insistent performs better than a balanced one.

**Include the clumsy phrasings.** Users do not type the skill's vocabulary. They type "the
monthly and annual thing" and "why isn't the invoice splitting". Put those in.

**State what it is not for.** With several neighbouring skills, the boundary is what stops
the wrong one loading. Name the neighbour.

Do not put "when to use" guidance in the body. The body is only read after the skill has
already triggered, so it is too late to matter there.

## Optional keys

`compatibility` names required tooling when it is not obvious — `sf` CLI, a connector, a
Python package. Use it sparingly; most skills here need the pack and nothing else.
