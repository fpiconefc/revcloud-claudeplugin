# Official documentation sources

Only Salesforce-published sources belong in the docs sweep. Anything else goes in
`notes/` with its origin stated. The sweep records a SHA-256 per source so a later
check can tell whether it moved.

| Key | What it is authoritative for |
|---|---|
| `dev_guide_pdf` | The complete Revenue Lifecycle Management Developer Guide. Object and field reference, the API version each object landed in, the deployment sequence and data-translation tables per module, and which objects are protected and non-extensible. The single most useful artifact in the pack. |
| `pricing_std_objects` | Salesforce Pricing standard objects, with the API version each became available in. Useful because pricing objects arrived across many releases (60.0 through 67.0 and later), so "does this org have it" depends on the org's API version, not just on the module. |
| `associated_objects` | Which standard objects carry Feed, History and Share companions. Needed before promising field history tracking or sharing rules. |

## Modules in the guide

The developer guide organises Revenue Cloud Advanced into nine modules. The seed
object list in `sweep_org.py` follows the same split so a fingerprint maps onto the
guide without translation.

1. Product Catalog Management
2. Salesforce Pricing
3. Rate Management
4. Product Configurator
5. Transaction Management
6. Advanced Approvals
7. Dynamic Revenue Orchestrator
8. Usage Management
9. Billing

## Naming

The product has been renamed repeatedly: Revenue Cloud, Revenue Lifecycle Management
(RLM), and more recently Agentforce Revenue Management appear in Salesforce material
and partner material respectively. The developer guide URL still uses
`revenue_lifecycle_management_dev_guide`. None of these is legacy Salesforce CPQ,
which is a separate managed package with a separate object model. Confirm which one
the user means before answering.

## Adding a source

Append to `SOURCES` in `sweep_docs.py` with a `key`, the `module` it belongs to, the
`url`, and one sentence saying what it is authoritative for. That sentence is not
decoration: it is what tells a later reader which source settles a disagreement.
