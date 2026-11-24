#!/usr/bin/env python3
"""Print the selling-model design surface of an org, from the knowledge pack.

Read-only. Reads the describes that rc-context-pack wrote under
~/.claude/knowledge/revenue-cloud/orgs/<alias>/describe/ and prints the facts a
catalog design rests on: how the selling model is shaped here, which fields the
junction actually exposes, where the price attaches, where billing frequency
lives under its three names, and how an asset is tied to a product.

It also flags the deltas this skill documents, by checking the org against what
the developer guide describes. A flag is a finding about this org, not an error.

Usage:
    python3 selling_model_surface.py <org-alias>
    python3 selling_model_surface.py <org-alias> --pack /path/to/revenue-cloud

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
GUIDE_PSMO_EPC_FIELDS = ["Description", "DisplayName", "Increment", "Maximum", "Minimum"]


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


def rule(title: str) -> None:
    print()
    print(title)
    print("-" * len(title))


def show_picklist(label: str, values: list[str]) -> None:
    print(f"  {label:34s} {', '.join(values) if values else '(none)'}")


def report_selling_model(describe_dir: Path, findings: list[str]) -> None:
    rule("ProductSellingModel")
    try:
        f = fields(load(describe_dir, "ProductSellingModel"))
    except Missing:
        findings.append("ProductSellingModel is absent: product catalog management is not provisioned.")
        print("  absent")
        return

    print(f"  {len(f)} fields")
    units = picklist(f.get("PricingTermUnit"))
    show_picklist("SellingModelType", picklist(f.get("SellingModelType")))
    show_picklist("PricingTermUnit", units)
    show_picklist("Status", picklist(f.get("Status")))

    extra = [u for u in units if u not in GUIDE_PRICING_TERM_UNITS]
    if extra:
        findings.append(
            "DELTA PricingTermUnit: this org adds "
            + ", ".join(extra)
            + " to the guide's "
            + ", ".join(GUIDE_PRICING_TERM_UNITS)
            + "."
        )
    if "DoesAutoRenewAssetByDefault" in f:
        findings.append(
            "DELTA DoesAutoRenewAssetByDefault exists on ProductSellingModel here; "
            "the v68 guide PDF does not document it. Set it deliberately."
        )


def report_option(describe_dir: Path, findings: list[str]) -> None:
    rule("ProductSellingModelOption (the Product2 junction)")
    try:
        f = fields(load(describe_dir, "ProductSellingModelOption"))
    except Missing:
        findings.append("ProductSellingModelOption is absent: nothing can be priced per selling model.")
        print("  absent")
        return

    print(f"  {len(f)} fields")
    for name in ("Product2Id", "ProductSellingModelId", "ProrationPolicyId", "IsDefault"):
        print(f"  {name:34s} {'present' if name in f else 'ABSENT'}")

    absent = [n for n in GUIDE_PSMO_EPC_FIELDS if n not in f]
    if absent:
        findings.append(
            "DELTA ProductSellingModelOption is missing "
            + ", ".join(absent)
            + ", which the guide's Salesforce Pricing section documents. "
            "Those are the Industries EPC fields. You cannot bound a subscription "
            "term on the option here; bound it by which selling models you publish."
        )


def report_price(describe_dir: Path, findings: list[str]) -> None:
    rule("Where the price attaches")
    try:
        f = fields(load(describe_dir, "PricebookEntry"))
    except Missing:
        findings.append("PricebookEntry is absent from the pack for this org.")
        print("  absent")
        return

    if "ProductSellingModelId" in f:
        print("  PricebookEntry.ProductSellingModelId    present")
        print("  grain: price book x product x selling model x currency")
    else:
        findings.append(
            "PricebookEntry has no ProductSellingModelId here. Two prices for one "
            "product are not possible; re-check that Salesforce Pricing is provisioned."
        )
        print("  PricebookEntry.ProductSellingModelId    ABSENT")
    show_picklist("CurrencyIsoCode", picklist(f.get("CurrencyIsoCode")))


def report_billing_frequency(describe_dir: Path, findings: list[str]) -> None:
    rule("Billing frequency, under each of its names")
    seen: dict[str, list[str]] = {}
    for obj, name in (
        ("QuoteLineItem", "BillingFrequency"),
        ("OrderItem", "BillingFrequency"),
        ("OrderItem", "BillingFrequency2"),
        ("AssetStatePeriod", "BillingFrequency"),
    ):
        try:
            f = fields(load(describe_dir, obj))
        except Missing:
            print(f"  {obj + '.' + name:40s} object absent")
            continue
        if name in f:
            vals = picklist(f[name])
            seen[f"{obj}.{name}"] = vals
            print(f"  {obj + '.' + name:40s} {', '.join(vals)}")
        else:
            print(f"  {obj + '.' + name:40s} not present")

    if "OrderItem.BillingFrequency2" in seen and "OrderItem.BillingFrequency" not in seen:
        findings.append(
            "DELTA OrderItem carries BillingFrequency2, not BillingFrequency. "
            "QuoteLineItem carries BillingFrequency. Any quote-to-order mapping that "
            "assumes one name drops the value silently. BillingReference renames the "
            "same way."
        )


def report_lineage(describe_dir: Path, findings: list[str]) -> None:
    rule("Asset lineage — what an asset is tied to")
    try:
        asset = fields(load(describe_dir, "Asset"))
    except Missing:
        print("  Asset absent")
        return

    print(f"  Asset.Product2Id                       {'present' if 'Product2Id' in asset else 'ABSENT'}")
    sm_on_asset = [n for n in asset if "SellingModel" in n]
    print(f"  Asset selling-model field              {', '.join(sm_on_asset) if sm_on_asset else 'none'}")

    try:
        src = fields(load(describe_dir, "AssetActionSource"))
        print(
            "  AssetActionSource.ProductSellingModelId "
            f"{'present' if 'ProductSellingModelId' in src else 'ABSENT'}"
        )
    except Missing:
        print("  AssetActionSource                      absent")

    if not sm_on_asset:
        findings.append(
            "The asset is tied to Product2 and carries no selling model; the selling "
            "model is recorded per event on AssetActionSource. Cloning Product2 to get "
            "a second price therefore splits the asset lineage, and no amendment "
            "repairs it."
        )

    try:
        act = fields(load(describe_dir, "AssetAction"))
        show_picklist("AssetAction.CategoryEnum", picklist(act.get("CategoryEnum")))
    except Missing:
        pass


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Print an org's selling-model design surface from the knowledge pack."
    )
    ap.add_argument("alias", help="org alias as it appears under the pack's orgs/ directory")
    ap.add_argument("--pack", type=Path, default=DEFAULT_PACK, help="pack root")
    args = ap.parse_args()

    describe_dir = args.pack / "orgs" / args.alias / "describe"
    if not describe_dir.is_dir():
        print(f"no describes for org '{args.alias}' under {args.pack / 'orgs'}", file=sys.stderr)
        print("run rc-context-pack to fingerprint it first", file=sys.stderr)
        return 1

    print(f"Selling-model surface — org {args.alias}")
    print(f"pack: {args.pack}")
    swept = args.pack / "orgs" / args.alias / "fingerprint.json"
    if swept.exists():
        try:
            print(f"swept: {json.loads(swept.read_text(encoding='utf-8')).get('swept_at', 'unknown')}")
        except (ValueError, OSError):
            pass

    findings: list[str] = []
    report_selling_model(describe_dir, findings)
    report_option(describe_dir, findings)
    report_price(describe_dir, findings)
    report_billing_frequency(describe_dir, findings)
    report_lineage(describe_dir, findings)

    rule("Findings")
    if findings:
        for i, note in enumerate(findings, start=1):
            print(f"  {i}. {note}")
    else:
        print("  none; this org matches the developer guide on every point checked")

    print()
    print("Read-only. Nothing was written to the org or to the pack.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
