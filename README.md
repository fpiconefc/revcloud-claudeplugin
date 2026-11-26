# revenue-cloud-skills

Skills for building on Salesforce Revenue Cloud Advanced and migrating to it from
Salesforce CPQ. Usable as a Claude Code plugin marketplace and, through `AGENTS.md`, by
any other agent.

## Layout

```
.claude-plugin/marketplace.json   # lists every plugin
plugins/<plugin>/
  .claude-plugin/plugin.json      # plugin manifest
  skills/<skill>/
    SKILL.md                      # required: frontmatter + instructions
    references/                   # loaded on demand
    scripts/                      # deterministic work
    assets/                       # templates and files used in output
```

## Plugins

| Plugin | Status | Scope |
|---|---|---|
| `rc-core` | in progress | Grounding. Builds the verified knowledge pack. Prerequisite for the rest. |
| `rc-migrate` | planned | CPQ to Revenue Cloud: extraction, discovery, requirements, solution design, migration plan. |
| `rc-build` | planned | Catalog, selling models, pricing, bundles, billing, invoicing. |
| `rc-labs` | planned | Tactical skills and troubleshooting. |
| `rc-accelerate` | planned | Tracker, test plan, quote-to-cash harness. |

## Install (Claude Code)

```
/plugin marketplace add <this repo>
/plugin install rc-core@revenue-cloud-skills
```

Then build the pack before anything else:

```bash
python3 plugins/rc-core/skills/rc-context-pack/scripts/sweep_docs.py
python3 plugins/rc-core/skills/rc-context-pack/scripts/sweep_org.py --org <alias>
```

## Design rules

**Ground before claiming.** Revenue Cloud's object model is large and version-gated.
Every factual claim traces to the developer guide or to a live `describe`. `rc-core`
exists to make that cheap; the rest of the repo depends on it.

**Docs tell you what the product does; notes tell you what broke.** The `notes/` folder
in the pack is the accumulated doctrine from real implementations. It is the part that
cannot be regenerated, so it is never overwritten by a script.

**A plugin cannot reach outside its own directory.** Claude Code copies each plugin to a
cache on install, so relative paths like `../shared` do not resolve. Shared state lives
in the knowledge pack under the user's home directory; shared files inside the repo need
symlinks.

**Read-only means read-only.** Skills that fingerprint, discover or audit never write to
an org. Writing belongs to skills that say so in their frontmatter.

## Validate locally

```bash
python3 -c "import json;json.load(open('.claude-plugin/marketplace.json'))"
for f in plugins/*/.claude-plugin/plugin.json; do python3 -c "import json,sys;json.load(open(sys.argv[1]))" "$f"; done
for f in plugins/*/skills/*/scripts/*.py; do python3 -m py_compile "$f"; done
python3 plugins/rc-core/skills/rc-authoring-loop/scripts/lint_skill.py plugins/*/skills/*
```

The last line is the skill linter, and CI runs the same invocation. Errors fail the
build, warnings do not. Add `--strict` to fail on warnings too.

### Pre-commit hook

Git does not version `.git/hooks`, so the hook lives at `scripts/hooks/pre-commit` and
has to be activated once per clone:

```bash
git config core.hooksPath scripts/hooks
```

It runs the linter above and blocks a commit on any error; `git commit --no-verify`
bypasses it. The error worth having it for is a `SKILL.md` description over 1024
characters: claude.ai rejects such a skill at upload while Claude Code loads it without
complaint, so nothing on the authoring machine reports it.
