#!/usr/bin/env python3
"""Fingerprint a Salesforce org's Revenue Cloud Advanced configuration.

Read-only. Describes every object in the seed list, records which are present and
which are absent, extracts the picklist values that drive behaviour, and discovers
objects the seed list missed by following child relationships.

Usage:
    python3 sweep_org.py --org myalias --out ~/.claude/knowledge/revenue-cloud

Requires the Salesforce CLI (`sf`) on PATH and an authenticated org alias.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

# Objects grouped by developer-guide module. Expand freely; absence is recorded,
# not treated as an error, so an over-long list is cheap.
SEED: dict[str, list[str]] = {
    "product_catalog_management": [
        "ProductCatalog", "ProductCategory", "ProductCategoryProduct", "Product2",
        "ProductClassification", "ProductClassificationAttr", "AttributeDefinition",
        "AttributeCategory", "AttributePicklist", "AttributePicklistValue",
        "ProductAttributeDefinition", "ProductSellingModel", "ProductSellingModelOption",
        "ProductComponentGroup", "ProductRelatedComponent", "ProductRelationshipType",
        "ProductComponentGrpOverride", "ProductRelComponentOverride", "UnitOfMeasure",
        "UnitOfMeasureClass", "ProductRampSegment", "AttrPicklistExcludedValue",
        "AttributeCategoryAttribute", "ProductQualification", "ProductDisqualification",
        "ProductCategoryQualification", "ProductCategoryDisqual",
    ],
    # The configurator decides what a bundle may contain and which flow builds it.
    # Absent from the seed list until 2026-11-25 although the guide gives it a module
    # of its own; ProductConfigurationRule is where inclusion and exclusion rules live.
    "product_configurator": [
        "ProductConfigurationFlow", "ProductConfigFlowAssignment",
        "ProductConfigurationRule",
    ],
    "salesforce_pricing": [
        "PricebookEntry", "Pricebook2", "PriceAdjustmentSchedule", "PriceAdjustmentTier",
        "AttributeBasedAdjustment", "BundleBasedAdjustment", "PriceBookEntryDerivedPrice",
        "CostBook", "CostBookEntry", "AttributeBasedAdjRule",
        "AttributeAdjustmentCondition", "ProrationPolicy",
    ],
    "rate_management": [
        "RateCard", "RateCardEntry", "RateAdjustmentByTier", "RateAdjustmentByAttribute",
        "RatingRequest", "UsageResource",
    ],
    "transaction_management": [
        "Quote", "QuoteLineItem", "QuoteLineDetail", "QuoteLineGroup", "QuoteLineRelationship",
        "QuoteAction", "Order", "OrderItem", "OrderItemDetail", "OrderItemRelationship",
        "OrderSummary", "OrderItemSummary", "OrderItemAdjustmentLineItem",
        "SalesTransactionType", "Contract", "ContractItemPrice", "Asset",
        "AssetStatePeriod", "AssetContractRelationship", "AssetAction", "AssetActionSource",
        "AssetRelationship", "QuoteLinePriceAdjustment", "AssetActionSrcPriceAdjustment",
        "OrderAdjustmentGroup", "ContractItemPriceAdjTier", "QuoteLineItemAttribute",
        "OrderItemAttribute", "AssetAttribute", "AssetStatePeriodAttribute",
        "QuoteLineRateCardEntry", "OrderItemRateCardEntry",
    ],
    "billing": [
        "BillingSchedule", "BillingScheduleGroup", "BillingPeriodItem", "BillingForecast",
        "BillingMilestonePlan", "BillingTreatment", "BillingTreatmentItem",
        "Invoice", "InvoiceLine", "InvoiceBatchRun", "InvBatchDraftToPostedRun",
        "CreditMemo", "CreditMemoLine", "DebitMemo", "DebitMemoLine",
        "Payment", "PaymentLineInvoice", "TaxTreatment", "BillingArrangement",
        "RevenueTransactionErrorLog",
    ],
    "usage_management": [
        "UsageSummary", "TransactionJournal", "ProductUsageGrant",
        "ProductUsageResourcePolicy", "UsageEntitlementEntry",
    ],
    "dynamic_revenue_orchestrator": [
        "FulfillmentOrder", "FulfillmentOrderLineItem", "OrchestrationItem",
        "OrchestrationPlan", "OrchestrationPlanDefinition",
    ],
    "advanced_approvals": [
        "ApprovalSubmission", "ApprovalWorkItem",
    ],
}

# Fields whose picklist values change how an implementation is designed. The
# fingerprint lifts these to the top level so a reader does not have to open
# the full describe.
BEHAVIOUR_FIELDS: dict[str, list[str]] = {
    "ProductSellingModel": ["SellingModelType", "PricingTermUnit", "Status"],
    "PriceAdjustmentSchedule": ["ScheduleType", "AdjustmentMethod"],
    # TierType is the field a tier is actually set with, and its values are spelled
    # differently from the read-only AdjustmentType beside it. Lifting it makes the
    # difference visible in the fingerprint instead of only in a full describe.
    "PriceAdjustmentTier": ["TierType", "AdjustmentType"],
    "AttributeBasedAdjRule": ["UsageType"],
    "AttributeAdjustmentCondition": ["Operator", "UsageType"],
    "ContractItemPrice": ["AdjustmentMethod"],
    "ProductConfigurationRule": ["ProcessScope", "RuleType", "RuleSubType", "Status"],
    "ProductConfigurationFlow": ["Status", "Type", "SubType"],
    "ProductConfigFlowAssignment": ["AssignmentType"],
    "ProductRelatedComponent": ["ParentProductRole", "ChildProductRole", "QuantityScaleMethod"],
    "ProductCatalog": ["CatalogType"],
    "BillingSchedule": [
        "BillingTermUnit", "BillingType", "BillingMethod", "Status",
        "Category", "SubCategory", "InvoiceGroupType",
    ],
    "Invoice": ["Status"],
    "Order": ["Status"],
    "Quote": ["Status"],
}


def run_sf(args: list[str]) -> dict | None:
    """Run an sf CLI command expecting --json output. Returns None on failure."""
    try:
        proc = subprocess.run(
            args, capture_output=True, text=True, timeout=120, check=False
        )
    except FileNotFoundError:
        sys.exit("error: the Salesforce CLI (`sf`) is not on PATH.")
    except subprocess.TimeoutExpired:
        return None
    if proc.returncode != 0:
        return None
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError:
        return None


def describe(obj: str, org: str) -> dict | None:
    payload = run_sf(["sf", "sobject", "describe", "--sobject", obj, "--target-org", org, "--json"])
    if not payload:
        return None
    return payload.get("result")


def picklists(desc: dict, names: list[str]) -> dict[str, list[str]]:
    wanted = {n.lower() for n in names}
    out: dict[str, list[str]] = {}
    for field in desc.get("fields", []):
        if field.get("name", "").lower() in wanted:
            values = [v["value"] for v in field.get("picklistValues", []) if v.get("active", True)]
            if values:
                out[field["name"]] = values
    return out


# Companion and platform objects that every describe drags in. They are never a finding
# about Revenue Cloud provisioning, so they are counted but kept out of the human report.
NOISE_SUFFIXES = (
    "ChangeEvent", "Feed", "History", "Share", "OwnerSharingRule", "Tag",
)

NOISE_EXACT = {
    "ActivityHistory", "AttachedContentDocument", "Attachment", "CombinedAttachment",
    "ContentDocumentLink", "ContentVersion", "EmailMessage", "EntitySubscription",
    "Event", "EventRelation", "FeedComment", "FeedItem", "ListEmail", "Note",
    "NoteAndAttachment", "OpenActivity", "OutgoingEmail", "Task", "TopicAssignment",
    "CollaborationGroupRecord", "RecordAction", "RecordActionHistory",
    "ProcessException", "ProcessExceptionEvent", "ProcessInstance",
    "FlowExecutionErrorEvent", "FlowOrchestrationWorkItem", "FlowRecordRelation",
    "AIInsightValue", "AIRecordInsight", "AgentWork", "AppUsageAssignment",
    "AsyncOperationLog", "DuplicateRecordItem", "NetworkActivityAudit",
    "NetworkFeedResponseMetric", "NetworkUserHistoryRecent", "ObjectMetadataTag",
    "PendingServiceRouting", "PendingServiceRoutingInteractionInfo",
    "ResourcePreference", "SurveySubject", "ExtlRecShrStagedRecord",
}


def is_noise(name: str) -> bool:
    """True for platform companion objects that say nothing about provisioning."""
    return name in NOISE_EXACT or name.endswith(NOISE_SUFFIXES)


def main() -> int:
    ap = argparse.ArgumentParser(description="Fingerprint an org's Revenue Cloud config.")
    ap.add_argument("--org", required=True, help="sf CLI target-org alias or username")
    ap.add_argument("--out", default="~/.claude/knowledge/revenue-cloud",
                    help="pack root (default: ~/.claude/knowledge/revenue-cloud)")
    ap.add_argument("--no-describe-files", action="store_true",
                    help="skip writing the full per-object describe JSON")
    args = ap.parse_args()

    root = Path(os.path.expanduser(args.out)) / "orgs" / args.org
    (root / "describe").mkdir(parents=True, exist_ok=True)

    present: dict[str, list[str]] = {}
    absent: dict[str, list[str]] = {}
    behaviour: dict[str, dict[str, list[str]]] = {}
    discovered: set[str] = set()
    noise: set[str] = set()
    seeded = {o for objs in SEED.values() for o in objs}

    total = sum(len(v) for v in SEED.values())
    done = 0

    for module, objects in SEED.items():
        present[module], absent[module] = [], []
        for obj in objects:
            done += 1
            print(f"[{done}/{total}] {module}: {obj}", file=sys.stderr)
            desc = describe(obj, args.org)
            if desc is None:
                absent[module].append(obj)
                continue
            present[module].append(obj)
            if not args.no_describe_files:
                (root / "describe" / f"{obj}.json").write_text(
                    json.dumps(desc, indent=2), encoding="utf-8"
                )
            if obj in BEHAVIOUR_FIELDS:
                found = picklists(desc, BEHAVIOUR_FIELDS[obj])
                if found:
                    behaviour[obj] = found
            for child in desc.get("childRelationships", []):
                name = child.get("childSObject") or child.get("childObject")
                if name and name not in seeded:
                    (noise if is_noise(name) else discovered).add(name)

    fingerprint = {
        "org": args.org,
        "swept_at": datetime.now(timezone.utc).isoformat(),
        "modules": {
            m: {
                "present": present[m],
                "absent": absent[m],
                "enabled": bool(present[m]),
            }
            for m in SEED
        },
        "behaviour_picklists": behaviour,
        "discovered_not_in_seed": sorted(discovered),
        "discovered_noise_filtered": sorted(noise),
    }
    (root / "fingerprint.json").write_text(json.dumps(fingerprint, indent=2), encoding="utf-8")

    lines = [
        f"# Revenue Cloud org fingerprint — {args.org}",
        "",
        f"Swept {fingerprint['swept_at']}. Read-only describe sweep.",
        "",
        "## Modules",
        "",
        "| Module | Enabled | Objects present | Objects absent |",
        "|---|---|---|---|",
    ]
    for m in SEED:
        lines.append(
            f"| {m.replace('_', ' ')} | {'yes' if present[m] else 'NO'} "
            f"| {len(present[m])} | {len(absent[m])} |"
        )
    lines += ["", "## Behaviour picklists", ""]
    for obj, fields in sorted(behaviour.items()):
        lines.append(f"### {obj}")
        for fname, values in fields.items():
            lines.append(f"- `{fname}`: {', '.join(values)}")
        lines.append("")
    if discovered:
        lines += [
            "## Related objects not in the seed list",
            "",
            "Discovered via child relationships. Review and promote the relevant ones.",
            "",
            (f"{len(noise)} companion objects (ChangeEvent, Feed, History, Share and the "
             "like) were filtered out; see discovered_noise_filtered in fingerprint.json."
             if noise else ""),
            "",
            ", ".join(f"`{d}`" for d in sorted(discovered)),
            "",
        ]
    for m in SEED:
        if absent[m]:
            lines += [f"## Absent in {m.replace('_', ' ')}", "",
                      "Absence usually means the module is not provisioned, not an error.",
                      "", ", ".join(f"`{o}`" for o in absent[m]), ""]
    (root / "FINGERPRINT.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    enabled = [m for m in SEED if present[m]]
    print(f"\nWrote {root}/fingerprint.json and FINGERPRINT.md", file=sys.stderr)
    print(f"Modules enabled: {', '.join(enabled) if enabled else 'none detected'}", file=sys.stderr)
    if discovered:
        print(f"{len(discovered)} related objects found outside the seed list "
              f"({len(noise)} companion objects filtered out).", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
