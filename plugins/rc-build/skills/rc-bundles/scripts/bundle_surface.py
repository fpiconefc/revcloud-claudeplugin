"""Print the bundle-composition design surface of an org, from the knowledge pack.

Read-only. Reads the describes that rc-context-pack wrote under
~/.claude/knowledge/revenue-cloud/orgs/<alias>/describe/ and prints the facts a
bundle design rests on: which fields the group and the component objects expose,
which of them you can actually write, which are read-only projections of something
else, where a picklist's label differs from its API value, and which fields this
org has that the v68 guide does not document.

It prints no catalog content. Field and picklist metadata only; it does not query
records and does not touch an org.

Usage:
    python3 bundle_surface.py <org-alias>
    python3 bundle_surface.py <org-alias> --pack /path/to/revenue-cloud

Exit codes: 0 printed, 1 the org or its describes are missing, 2 bad invocation.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

DEFAULT_PACK = Path.home() / ".claude" / "knowledge" / "revenue-cloud"

AUDIT = {
    "Id", "IsDeleted", "CreatedById", "CreatedDate", "LastModifiedById",
    "LastModifiedDate", "SystemModstamp", "LastViewedDate", "LastReferencedDate",
    "OwnerId",
}

# Fields the v68 guide documents for these objects, anywhere: the two base-object
# fields it covers under "Fields on Standard Objects", plus every field it covers
# on the override objects. Anything outside this set is undocumented there.
GUIDE_DOCUMENTED = {
    "ProductComponentGroup": {
        "ParentGroupId", "MinBundleComponents", "MaxBundleComponents", "Name",
        "Description", "Sequence", "CurrencyIsoCode",
    },
    "ProductRelatedComponent": {
        "ChildProductClassificationId", "QuoteVisibility", "Quantity", "MinQuantity",
        "MaxQuantity", "IsComponentRequired", "IsDefaultComponent",
        "IsQuantityEditable", "DoesBundlePriceIncludeChild", "QuantityScaleMethod",
        "Name", "Sequence", "CurrencyIsoCode", "ParentProductId", "ChildProductId",
        "ProductComponentGroupId", "ProductRelationshipTypeId",
    },
    "ProductRelationshipType": {"Name", "AssociatedProductRoleCat"},
}

# Base-object field -> the object it is projected from, for the read-only pairs.
PROJECTED_FROM = {
    "ParentProductRole": "ProductRelationshipType.MainProductRoleCat",
    "ChildProductRole": "ProductRelationshipType.AssociatedProductRoleCat",
    "UnitOfMeasureId": "the child product",
}

OBJECTS = ["ProductComponentGroup", "ProductRelatedComponent", "ProductRelationshipType"]
OVERRIDES = ["ProductComponentGrpOverride", "ProductRelComponentOverride"]


class Missing(Exception):
    pass


def load(describe_dir: Path, obj: str) -> dict:
    path = describe_dir / f"{obj}.json"
    if not path.exists():
        raise Missing(obj)
    return json.loads(path.read_text(encoding="utf-8"))


def fields(desc: dict) -> dict[str, dict]:
    return {f["name"]: f for f in desc.get("fields", []) if isinstance(f, dict)}


def pairs(field: dict | None) -> list[tuple[str, str]]:
    if not field:
        return []
    return [
        (v["value"], v.get("label") or v["value"])
        for v in field.get("picklistValues", [])
        if v.get("active", True)
    ]


def writability(f: dict) -> str:
    c, u = f.get("createable"), f.get("updateable")
    if c and u:
        return "write"
    if c and not u:
        return "CREATE-ONLY"
    if not c and not u:
        return "READ-ONLY"
    return "update-only"


def rule(title: str) -> None:
    print()
    print(title)
    print("-" * len(title))


def report_object(describe_dir: Path, obj: str, findings: list[str]) -> None:
    rule(obj)
    try:
        f = fields(load(describe_dir, obj))
    except Missing:
        print("  absent from the pack — describe it in the org")
        findings.append(f"{obj} is absent from the pack's describes.")
        return

    substantive = {n: fl for n, fl in f.items() if n not in AUDIT}
    print(f"  {len(f)} fields, {len(substantive)} substantive")
    for name in sorted(substantive):
        fl = substantive[name]
        w = writability(fl)
        req = "required" if not fl.get("nillable") else "nillable"
        note = ""
        if w == "READ-ONLY" and name in PROJECTED_FROM:
            note = f"  <- projected from {PROJECTED_FROM[name]}"
            findings.append(
                f"{obj}.{name} is read-only here; it follows "
                f"{PROJECTED_FROM[name]}. Setting the source is how you choose it."
            )
        print(f"    {name:32s} {fl['type']:10s} {w:12s} {req}{note}")

    report_labels(substantive, obj, findings)
    report_undocumented(set(substantive), obj, findings)


def report_labels(substantive: dict[str, dict], obj: str, findings: list[str]) -> None:
    """A picklist whose label differs from its API value breaks label-based filters."""
    mismatched: list[str] = []
    for name, fl in sorted(substantive.items()):
        bad = [(v, l) for v, l in pairs(fl) if v != l]
        if not bad or name == "CurrencyIsoCode":
            continue
        mismatched.append(name)
        print(f"    {name}: value != label")
        for v, l in bad:
            print(f"        {v:28s} is labelled '{l}'")
    if mismatched:
        findings.append(
            f"{obj}: value and label differ on {', '.join(mismatched)}. "
            "Match on the API value; a filter written against the label fails."
        )


def report_undocumented(present: set[str], obj: str, findings: list[str]) -> None:
    documented = GUIDE_DOCUMENTED.get(obj)
    if documented is None:
        return
    extra = sorted(present - documented)
    if extra:
        print(f"    not documented in the v68 guide: {', '.join(extra)}")
        findings.append(
            f"{obj} has {len(extra)} field(s) the v68 guide does not document: "
            + ", ".join(extra)
        )


def report_overrides(describe_dir: Path, findings: list[str]) -> None:
    rule("Override objects")
    for obj in OVERRIDES:
        try:
            f = fields(load(describe_dir, obj))
        except Missing:
            print(f"  {obj:30s} absent from the pack")
            continue
        print(f"  {obj:30s} present, {len(f)} fields")
    print()
    print("  These are the only objects the v68 guide gives a full field section to.")
    print("  Treat an override field's description as the best DOCS statement of what")
    print("  the matching base field means, and say so when citing it.")


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Print an org's bundle-composition surface from the knowledge pack."
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

    print(f"Bundle-composition surface — {args.alias}")
    print(f"(from {describe_dir})")

    findings: list[str] = []
    for obj in OBJECTS:
        report_object(describe_dir, obj, findings)
    report_overrides(describe_dir, findings)

    rule("Findings")
    if findings:
        for item in findings:
            print(f"  - {item}")
    else:
        print("  Nothing unexpected against the v68 guide and the reference shape.")

    print()
    print("Read-only: this script touched no org, wrote nothing, and printed no")
    print("catalog content.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
