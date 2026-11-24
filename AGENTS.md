# Using these skills from a non-Claude agent

Every skill here is a folder with a `SKILL.md` (YAML frontmatter plus Markdown
instructions) and optional `scripts/`, `references/` and `assets/`. Nothing in the
instruction text is Claude-specific, and the scripts are plain Python 3 with no
third-party dependencies. Any agent that can read a file and run a shell command can use
them.

## The contract

1. Read every `SKILL.md` frontmatter at startup. The `name` and `description` are the
   routing metadata. Keep them in context; they are short on purpose.
2. When a user request matches a `description`, load that skill's `SKILL.md` body.
3. Load files under `references/` only when the body tells you to. They exist so the body
   stays short.
4. Run `scripts/` rather than reimplementing what they do. They are deterministic and
   their output format is what the rest of the skill expects.

That three-level loading is the whole design: metadata always, body on trigger,
resources on demand. An agent that loads everything up front will work but will waste
most of its context.

## Discovery

```bash
for f in plugins/*/skills/*/SKILL.md; do
  python3 - "$f" <<'PY'
import sys, re
text = open(sys.argv[1], encoding="utf-8").read()
m = re.match(r"^---\n(.*?)\n---", text, re.S)
print(sys.argv[1], "::", (m.group(1) if m else "")[:400].replace("\n", " "))
PY
done
```

A proper loader should parse the frontmatter as YAML. The snippet above is for eyeballing
the index.

## Prerequisite

`rc-core/rc-context-pack` builds the knowledge pack at
`~/.claude/knowledge/revenue-cloud/`. Every other skill reads it and none of them should
make a factual claim about Revenue Cloud that the pack does not support. Run it first.
The path is under `~/.claude/` for consistency with Claude Code, but nothing about it is
Claude-specific; override it with `--out` and point your agent at the same location.

## Exposing the repo as an MCP server

If your agents speak MCP, wrapping this repo gives them the same progressive loading
without a filesystem mount. Three tools are enough:

- `list_skills()` returns name and description for every `SKILL.md`.
- `get_skill(name)` returns the body.
- `get_resource(name, path)` returns a file under that skill's `references/` or `assets/`.

Keep the server read-only. The scripts should run on the machine that holds the org
credentials, not inside the server.

## House rules for any agent using these skills

- Never state a Revenue Cloud fact that the pack does not support. Say what you could not
  verify instead.
- Never write to a Salesforce org from a skill whose `SKILL.md` says it is read-only.
- Treat an absent object as a finding about provisioning, not as an error to retry.
