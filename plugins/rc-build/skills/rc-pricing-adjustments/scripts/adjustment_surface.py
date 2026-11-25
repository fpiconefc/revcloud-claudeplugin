#!/usr/bin/env python3
"""Print the price-adjustment design surface of an org, from the knowledge pack.

Read-only. Reads the describes that rc-context-pack wrote under
~/.claude/knowledge/revenue-cloud/orgs/<alias>/describe/ and prints the facts a
pricing-adjustment design rests on: which of the five schedule types this org can
carry, which child object each one needs, which field actually sets the adjustment
type on each object and in which spelling, which fields are a read-only projection
you must not try to write, and where an applied adjustment lands.

It also flags the traps this skill documents by checking the org against what the
v68 developer guide describes. A flag is a finding about this org, not an error.

Usage:
    python3 adjustment_surface.py <org-alias>
    python3 adjustment_surface.py <org-alias> --pack /path/to/revenue-cloud

Exit codes: 0 printed, 1 the org or its describes are missing, 2 bad invocation.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

DEFAULT_PACK = Path.home() / ".claude" / "knowledge" / "revenue-cloud"

# What the v68 developer guide documents, for the delta checks below.
GUIDE_PRICING_TERM_UNITS = ["Months", "Quarterly", "Semi-Annual", "Annual"]
GUIDE_SCHEDULE_FIELDS = [
    "AdjustmentMethod", "CurrencyIsoCode", "Description", "EffectiveFrom",
    "EffectiveTo", "IsActive", "Name", "OwnerId", "Pricebook2Id", "ScheduleType",
]

# ScheduleType -> the child object the engine reads for that type.
# Volume/Attribute/Bundle are observed in arm-picone; Term and Custom are inferred.
CHILD_FOR_SCHEDULE_TYPE = {
    "Volume": ("PriceAdjustmentTier", "observed"),
    "Term": ("PriceAdjustmentTier", "inferred"),
    "Attribute": ("AttributeBasedAdjustment", "observed"),
    "Bundle": ("BundleBasedAdjustment", "observed"),
    "Custom": ("(none — custom pricing logic)", "inferred"),
}

# Object -> (field that sets the adjustment type, expected value spelling).
TYPE_FIELD_BY_OBJECT = {
    "PriceAdjustmentTier": ("TierType", "prefixed"),
    "AttributeBasedAdjustment": ("AdjustmentType", "bare"),
    "BundleBasedAdjustment": ("AdjustmentType", "bare"),
    "QuoteLinePriceAdjustment": ("AdjustmentType", "prefixed"),
    "OrderItemAdjustmentLineItem": ("AdjustmentType", "prefixed"),
}

PREFIXED = {"AdjustmentPercentage", "AdjustmentAmount", "OverrideAmount"}
BARE = {"Percentage", "Amount", "Override"}

LANDING_OBJECTS = [
    "QuoteLinePriceAdjustment",
    "OrderItemAdjustmentLineItem",
    "AssetActionSrcPriceAdjustment",
]


class Missing(Exception):
    pass


def load(describe_dir: Path, obj: str) -> dict:
    path = describe_dir / f"{obj}.json"
    if not path.exists():
        raise Missing(obj)
    return json.loads(path.read_text(encoding="utf-8"))


def fields(desc: dict) -> dict[str, dict]:
    return {f["name"]: f for f in desc.get("fields", []) if isinstance(f, dict)}


def picklist(field: dict | None) -> list[str]:
    if not field:
        return []
    return [v["value"] for v in field.get("picklistValues", []) if v.get("active", True)]


def labelled(field: dict | None) -> list[tuple[str, str]]:
    if not field:
        return []
    return [
        (v["value"], v.get("label") or v["value"])
        for v in field.get("picklistValues", [])
        if v.get("active", True)
    ]


def writable(field: dict | None) -> bool:
    return bool(field and (field.get("createable") or field.get("updateable")))


def rule(title: str) -> None:
    print()
    print(title)
    print("-" * len(title))


def show(label: str, value: str) -> None:
    print(f"  {label:34s} {value}")


def show_picklist(label: str, values: list[str]) -> None:
    show(label, ", ".join(values) if values else "(none)")


def report_schedule(describe_dir: Path, findings: list[str]) -> list[str]:
    """Print the schedule surface. Returns the ScheduleType values this org offers."""
    rule("PriceAdjustmentSchedule — the container")
    try:
        f = fields(load(describe_dir, "PriceAdjustmentSchedule"))
    except Missing:
        findings.append(
            "PriceAdjustmentSchedule is absent: Salesforce Pricing is not provisioned. "
            "Nothing else in this skill applies."
        )
        print("  absent")
        return []

    types = picklist(f.get("ScheduleType"))
    methods = picklist(f.get("AdjustmentMethod"))
    show_picklist("ScheduleType", types)
    show_picklist("AdjustmentMethod", methods)
    show("scope fields", ", ".join(
        n for n in ("Pricebook2Id", "ContractId") if n in f
    ) or "(none)")

    for name in ("Product2Id", "ProductSellingModelId", "SellingModelType"):
        if name in f:
            findings.append(
                f"PriceAdjustmentSchedule has {name}, which arm-picone does not. "
                "Product scoping may work differently here."
            )
    if "Product2Id" not in f:
        show("product link", "none — scoping lives on the child record")

    if "ContractId" in f:
        findings.append(
            "PriceAdjustmentSchedule.ContractId is present and undocumented in the v68 "
            "guide. It implies a contract-scoped schedule; unexercised in arm-picone."
        )
    for name in sorted(set(f) - set(GUIDE_SCHEDULE_FIELDS)):
        if name == "GlobalKey":
            findings.append(
                "PriceAdjustmentSchedule.GlobalKey is present and absent from the guide."
            )

    if "Slab" not in methods:
        findings.append("AdjustmentMethod offers no Slab value here; the guide documents it.")
    return types


def report_routing(types: list[str], describe_dir: Path, findings: list[str]) -> None:
    rule("Which child object each ScheduleType needs")
    if not types:
        print("  (no schedule object)")
        return
    for t in types:
        child, confidence = CHILD_FOR_SCHEDULE_TYPE.get(t, ("(unknown)", "unknown"))
        present = ""
        if child.startswith("("):
            present = ""
        else:
            try:
                load(describe_dir, child)
                present = "present"
            except Missing:
                present = "ABSENT in this org"
                findings.append(
                    f"ScheduleType {t} needs {child}, which is absent here. "
                    f"A {t} schedule cannot be completed."
                )
        show(f"{t} ->", f"{child}  [{confidence}]{'  ' + present if present else ''}")


def report_type_fields(describe_dir: Path, findings: list[str]) -> None:
    rule("Which field sets the adjustment type, and in which spelling")
    for obj, (expected_field, spelling) in TYPE_FIELD_BY_OBJECT.items():
        try:
            f = fields(load(describe_dir, obj))
        except Missing:
            show(obj, "not in the pack — describe it in the org")
            continue

        tier_type = f.get("TierType")
        adj_type = f.get("AdjustmentType")
        chosen = tier_type if (tier_type and writable(tier_type)) else adj_type

        if chosen is None:
            show(obj, "no TierType or AdjustmentType field")
            continue

        values = set(picklist(chosen))
        actual_spelling = "prefixed" if values & PREFIXED else (
            "bare" if values & BARE else "unknown"
        )
        name = chosen["name"]
        flag = "" if (name == expected_field and actual_spelling == spelling) else "  <-- differs"
        show(obj, f"set {name}  ({actual_spelling}){flag}")

        if flag:
            findings.append(
                f"{obj}: expected to set {expected_field} with {spelling} values; this org "
                f"wants {name} with {actual_spelling} values."
            )

        # The read-only twin is the trap.
        twin = adj_type if name == "TierType" else tier_type
        if twin is not None and not writable(twin):
            show("", f"  {twin['name']} is READ-ONLY here: {', '.join(sorted(picklist(twin)))}")


def report_tier(describe_dir: Path, findings: list[str]) -> None:
    rule("PriceAdjustmentTier — bounds, dates and the read-only projection")
    try:
        f = fields(load(describe_dir, "PriceAdjustmentTier"))
    except Missing:
        print("  absent")
        return

    for name in ("LowerBound", "UpperBound", "TierValue", "EffectiveFrom", "EffectiveTo"):
        fl = f.get(name)
        if fl is None:
            show(name, "ABSENT")
            continue
        show(name, f"{fl['type']}, {'required' if not fl.get('nillable') else 'nillable'}, "
                   f"{'writable' if writable(fl) else 'READ-ONLY'}")

    sched = f.get("PriceAdjustmentScheduleId")
    if sched is not None and sched.get("createable") and not sched.get("updateable"):
        show("PriceAdjustmentScheduleId", "create-only — a tier cannot be reparented")

    projected = [
        n for n in ("ScheduleType", "SellingModelType", "PricingTerm",
                    "PricingTermUnit", "AdjustmentType")
        if n in f and not writable(f[n])
    ]
    show("read-only projection", ", ".join(projected) if projected else "(none)")
    writable_projection = [
        n for n in ("ScheduleType", "SellingModelType", "PricingTerm",
                    "PricingTermUnit", "AdjustmentType")
        if n in f and writable(f[n])
    ]
    if writable_projection:
        findings.append(
            "These are writable here and read-only in arm-picone: "
            + ", ".join(writable_projection)
            + ". They can diverge from the selling model in this org."
        )

    report_term_unit_labels(f, "PriceAdjustmentTier", findings)


def report_term_unit_labels(f: dict[str, dict], obj: str, findings: list[str]) -> None:
    """The value/label mismatch that makes label-based filtering fail."""
    unit = f.get("PricingTermUnit")
    if unit is None:
        return
    pairs = labelled(unit)
    mismatched = [(v, l) for v, l in pairs if v != l]
    show("PricingTermUnit", ", ".join(v for v, _ in pairs) or "(none)")
    if mismatched:
        show("", "  value != label: " + ", ".join(f"{v} is labelled '{l}'" for v, l in mismatched))
        findings.append(
            f"{obj}.PricingTermUnit: "
            + "; ".join(f"value {v} carries the label '{l}'" for v, l in mismatched)
            + ". Filtering by label fails."
        )
    extra = sorted(set(v for v, _ in pairs) - set(GUIDE_PRICING_TERM_UNITS))
    if extra:
        findings.append(
            f"{obj}.PricingTermUnit offers {', '.join(extra)}, which the guide does not "
            "document for this object."
        )


def report_attribute_chain(describe_dir: Path, findings: list[str]) -> None:
    rule("Attribute adjustments — the rule chain")
    for obj in ("AttributeBasedAdjRule", "AttributeAdjustmentCondition",
                "AttributeBasedAdjustment"):
        try:
            f = fields(load(describe_dir, obj))
        except Missing:
            show(obj, "not in the pack's seed list — describe it in the org")
            continue
        show(obj, f"{len(f)} fields")
        if obj == "AttributeAdjustmentCondition":
            typed = [n for n in ("StringValue", "IntegerValue", "DoubleValue",
                                 "BooleanValue", "DateValue", "DateTimeValue") if n in f]
            show("", "  typed value columns: " + ", ".join(typed))
            show_picklist("  Operator", picklist(f.get("Operator")))
        if obj == "AttributeBasedAdjustment":
            report_term_unit_labels(f, obj, findings)
            if "AttributeAdjConditionsHash" in f:
                show("", "  AttributeAdjConditionsHash present (undocumented match key)")


def report_bundle(describe_dir: Path, findings: list[str]) -> None:
    rule("Bundle adjustments — addressed by path, not by product")
    try:
        f = fields(load(describe_dir, "BundleBasedAdjustment"))
    except Missing:
        print("  absent")
        return
    for name in ("ProductId", "ParentProductId", "RootBundleId"):
        fl = f.get(name)
        if fl is None:
            show(name, "ABSENT")
            findings.append(f"BundleBasedAdjustment.{name} is absent; the guide documents it.")
        else:
            show(name, f"{'required' if not fl.get('nillable') else 'nillable'}, "
                       f"{'create-only' if fl.get('createable') and not fl.get('updateable') else 'writable'}")
    report_term_unit_labels(f, "BundleBasedAdjustment", findings)


def report_landing(describe_dir: Path, findings: list[str]) -> None:
    rule("Where an applied adjustment lands")
    for obj in LANDING_OBJECTS:
        try:
            f = fields(load(describe_dir, obj))
        except Missing:
            show(obj, "not in the pack's seed list — describe it in the org")
            continue
        cause = next((n for n in ("PriceAdjustmentCauseId", "AdjustmentCauseId") if n in f), None)
        money = next((n for n in ("TotalAmount", "Amount", "AdjustmentValue") if n in f), None)
        targets = ", ".join(f[cause].get("referenceTo", [])) if cause else "-"
        show(obj, f"cause={cause or '-'} -> {targets}; money={money or '-'}")
        if cause and "PriceAdjustmentTier" not in (f[cause].get("referenceTo") or []):
            findings.append(
                f"{obj}.{cause} does not reference PriceAdjustmentTier, so a tier-caused "
                "price is not traceable on this object."
            )
    print()
    print("  The cause lookup and the money field are named differently on each.")
    print("  Map them explicitly; a by-name quote-to-order mapping breaks silently.")


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Print an org's price-adjustment surface from the knowledge pack."
    )
    ap.add_argument("alias", help="org alias, as fingerprinted by rc-context-pack")
    ap.add_argument("--pack", type=Path, default=DEFAULT_PACK,
                    help=f"pack root (default {DEFAULT_PACK})")
    args = ap.parse_args()

    describe_dir = args.pack / "orgs" / args.alias / "describe"
    if not describe_dir.is_dir():
        print(f"no describes for '{args.alias}' at {describe_dir}", file=sys.stderr)
        print("Run rc-context-pack to fingerprint this org first.", file=sys.stderr)
        return 1

    print(f"Price-adjustment surface — {args.alias}")
    print(f"(from {describe_dir})")

    findings: list[str] = []
    types = report_schedule(describe_dir, findings)
    report_routing(types, describe_dir, findings)
    report_type_fields(describe_dir, findings)
    report_tier(describe_dir, findings)
    report_attribute_chain(describe_dir, findings)
    report_bundle(describe_dir, findings)
    report_landing(describe_dir, findings)

    rule("Findings")
    if findings:
        for item in findings:
            print(f"  - {item}")
    else:
        print("  Nothing unexpected against the v68 guide and arm-picone's shape.")

    print()
    print("Read-only: this script touched no org and wrote nothing.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
