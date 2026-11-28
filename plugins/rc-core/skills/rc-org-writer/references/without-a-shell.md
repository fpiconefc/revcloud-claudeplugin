# Running the cycle without a shell

Read this only when there is no terminal: a claude.ai session, or any host where the four
scripts cannot run. The contract is identical; what changes is that nothing enforces it for
you, so this text is the whole of it.

The connector has `createSobjectRecord`, `updateSobjectRecord` and `deleteSobjectRecord`, so
the whole cycle is executable from a chat session. Run the four phases by hand, in order:

- **preview.** Reproduce the offline checks with `getObjectSchema` per object
  (`marking-and-idempotency.md`, beside this file, has the per-object answers), then `soqlQuery` each
  lookup to prove it resolves to exactly one, and each `key` to classify the record into the
  three states `SKILL.md` sets out under preview — absent, matching, or differing. Show all of it before asking.
- **apply.** `createSobjectRecord` in dependency order, after an explicit yes to that
  preview. **Write the log into the conversation as you go**, one line per record with the
  returned Id, immediately after each create. Stop at the first failure, and write no line
  for a create that returned no Id.
- **verify.** `soqlQuery` each created Id back, comparing by value and reporting matches,
  expected differences and unexpected differences separately.
- **teardown.** `deleteSobjectRecord` in reverse order, from the logged ids, and nothing else.

**The weak point of this branch is the log, and it is worth saying plainly.** The transcript
is the log, and a conversation is not durable storage: if the session is lost or compacted,
the ids go with it and teardown has no source — the records stay in the org with nothing but
the marker to find them by, and on the 70 objects that carry no marker, not even that. For
anything past a handful of records **use the terminal branch**, where the log is a file.
Otherwise keep the spec small enough that the whole transcript fits on one screen, and copy
the ids somewhere durable before moving on.

`updateSobjectRecord` is available here and is **not** part of this cycle. `SKILL.md`'s *There is no update path, and that is deliberate* says why.
