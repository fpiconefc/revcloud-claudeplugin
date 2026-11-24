# Fingerprint format

`sweep_org.py` writes two files per org, plus one JSON per described object.

## fingerprint.json

```json
{
  "org": "alias",
  "swept_at": "ISO-8601 UTC",
  "modules": {
    "<module>": { "present": ["Obj"], "absent": ["Obj"], "enabled": true }
  },
  "behaviour_picklists": {
    "<Object>": { "<Field>": ["Value"] }
  },
  "discovered_not_in_seed": ["Obj"]
}
```

`enabled` is inferred: a module with no describable objects is treated as not
provisioned. That inference is good enough to route a conversation and not good enough
to put in a customer deliverable. Confirm provisioning in Setup before writing it down.

`behaviour_picklists` lifts the values that change a design decision to the top level so
a reader does not open a 3,000-line describe to learn that `BillingType` is Advance or
Arrears. Extend `BEHAVIOUR_FIELDS` in the script as the skills grow.

`discovered_not_in_seed` is the sweep teaching itself. Every object reachable by a child
relationship that the seed list did not name lands here. Review it after each sweep and
promote the relevant ones into `SEED`, which is how the pack keeps up with Salesforce
adding objects without anyone editing a list by hand.

## FINGERPRINT.md

The same content as prose and tables, for pasting into a design document or reading in a
chat session. Generated; never hand-edit it, because the next sweep overwrites it. Put
anything hand-written in `notes/`.

## Reading a fingerprint in a chat session with no shell

Use the Salesforce MCP tools: `getObjectSchema` with a comma-separated object list gives
the same describe content, and `soqlQuery` gives record counts. Record counts matter as
much as schema: an object that exists with zero records means the module is provisioned
but unused, which is a different conversation from an object that is absent.
