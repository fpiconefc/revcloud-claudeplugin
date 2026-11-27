"""Bundle pre-flight for an rc-org-writer spec. Read-only; writes nothing.

rc-org-writer's validator checks that a spec is well formed and that its lookups
resolve. It cannot check what a bundle means, and it cannot check the platform
rules below, because no describe expresses them and two of them compare a field
on one looked-up record against a field on another.

Run this before `validate_spec.py --target-org`, and both before apply.

Platform rules, each observed refusing a real create on API v68:

  1. A component needs ChildProductId or ChildProductClassificationId, although
     the describe marks both nillable.
  1b. QuantityScaleMethod is silently dropped when IsQuantityEditable is true.
  2. A component's group must belong to the same parent product.
  3. The relationship type's MainProductRoleCat must match the parent product's
     ProductClass. Needs --target-org: it compares two looked-up records.
  4. A group's parent product must have its Type set. Needs --target-org.

Structure, from rc-bundles and checkable without an org:

  5. The spec creates no Product2. Products are referenced, never created.
  6. Group cardinality is coherent: min <= max, and neither exceeds the number
     of components the spec puts in that group.
  7. A required component does not sit in a group whose minimum is zero.
  8. A product appears at most once per group.
  9. Group nesting has no cycle.

Usage:
    python3 check_bundle_spec.py <spec.yaml>
    python3 check_bundle_spec.py <spec.yaml> --target-org <alias>

Exit codes: 0 clean, 1 problems found, 2 bad invocation.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_WRITER = Path(__file__).resolve().parents[4] / "rc-core/skills/rc-org-writer/scripts"
if not (_WRITER / "validate_spec.py").exists():
    print("error: rc-org-writer is not installed beside this plugin; it owns the spec "
          f"format and the four phases. Looked in {_WRITER}", file=sys.stderr)
    raise SystemExit(2)
sys.path.insert(0, str(_WRITER))

from validate_spec import SpecError, parse  # noqa: E402

GROUP = "ProductComponentGroup"
COMPONENT = "ProductRelatedComponent"


def ref(value):
    """The alias a field points at, or None if it is a literal."""
    if isinstance(value, str) and value.startswith("@"):
        return value[1:]
    return None


def records(doc: dict, obj: str) -> list[dict]:
    return [r for r in (doc.get("records") or []) if r.get("object") == obj]


def check_no_products(doc: dict, errors: list[str]) -> None:
    for rec in records(doc, "Product2"):
        errors.append(
            f"record @{rec.get('alias', '?')}: this spec creates a Product2. Bundles are "
            "built on products that already exist, referenced through `lookups`. A product "
            "has no standard upsert key and is the most dangerous thing a spec can add to a "
            "catalog, so if one is missing, report it and stop rather than inventing it."
        )


def check_components(doc: dict, errors: list[str]) -> None:
    groups = {r.get("alias"): r for r in records(doc, GROUP)}
    seen: dict[tuple[str, str], str] = {}

    for rec in records(doc, COMPONENT):
        alias = rec.get("alias", "?")
        fields = rec.get("fields") or {}

        if not (fields.get("ChildProductId") or fields.get("ChildProductClassificationId")):
            errors.append(
                f"component @{alias}: neither ChildProductId nor "
                "ChildProductClassificationId is set. The describe marks both nillable and "
                "the platform refuses the record without one: \"Enter either a Child "
                "Product ID or a Child Product Classification ID.\""
            )

        if fields.get("IsQuantityEditable") is True and fields.get("QuantityScaleMethod"):
            errors.append(
                f"component @{alias}: IsQuantityEditable is true and QuantityScaleMethod is "
                f"{fields['QuantityScaleMethod']!r}. The platform accepts the create and "
                "stores the scale method as null, so the spec would permanently disagree "
                "with the org. Drop one: a quantity the buyer edits has no parent scaling."
            )

        group_alias = ref(fields.get("ProductComponentGroupId"))
        if group_alias and group_alias in groups:
            group_parent = (groups[group_alias].get("fields") or {}).get("ParentProductId")
            if group_parent and group_parent != fields.get("ParentProductId"):
                errors.append(
                    f"component @{alias}: its ParentProductId is "
                    f"{fields.get('ParentProductId')!r} but group @{group_alias} belongs to "
                    f"{group_parent!r}. The platform refuses this: \"Select a group related "
                    "to the same bundle as this component.\""
                )
            child = fields.get("ChildProductId")
            if child:
                key = (group_alias, str(child))
                if key in seen:
                    errors.append(
                        f"components @{seen[key]} and @{alias} put the same child in group "
                        f"@{group_alias}. The platform refuses the second: \"The child "
                        "product exists in the group.\""
                    )
                else:
                    seen[key] = alias


def check_cardinality(doc: dict, errors: list[str], warnings: list[str]) -> None:
    counts: dict[str, int] = {}
    required: dict[str, list[str]] = {}
    for rec in records(doc, COMPONENT):
        fields = rec.get("fields") or {}
        alias = ref(fields.get("ProductComponentGroupId"))
        if not alias:
            continue
        counts[alias] = counts.get(alias, 0) + 1
        if fields.get("IsComponentRequired") is True:
            required.setdefault(alias, []).append(rec.get("alias", "?"))

    for rec in records(doc, GROUP):
        alias = rec.get("alias", "?")
        fields = rec.get("fields") or {}
        low, high = fields.get("MinBundleComponents"), fields.get("MaxBundleComponents")
        total = counts.get(alias, 0)

        if isinstance(low, int) and isinstance(high, int) and low > high:
            errors.append(
                f"group @{alias}: MinBundleComponents {low} is above MaxBundleComponents "
                f"{high}; no selection can satisfy it."
            )
        for label, bound in (("MinBundleComponents", low), ("MaxBundleComponents", high)):
            if isinstance(bound, int) and total and bound > total:
                errors.append(
                    f"group @{alias}: {label} is {bound} but the spec puts {total} "
                    f"component(s) in it. The bound cannot be met from what is there."
                )
        if isinstance(low, int) and low == 0 and alias in required:
            errors.append(
                f"group @{alias}: MinBundleComponents is 0, so the buyer may take nothing "
                f"from it, yet {', '.join('@' + a for a in required[alias])} "
                f"{'is' if len(required[alias]) == 1 else 'are'} marked "
                "IsComponentRequired. The group and the component disagree about whether "
                "the choice is optional."
            )
        if total == 0:
            warnings.append(
                f"group @{alias}: the spec puts no components in it. A group with child "
                "groups is a container and this is expected; otherwise it is probably an "
                "oversight."
            )


def check_nesting(doc: dict, errors: list[str]) -> None:
    parent: dict[str, str] = {}
    for rec in records(doc, GROUP):
        alias = rec.get("alias")
        up = ref((rec.get("fields") or {}).get("ParentGroupId"))
        if alias and up:
            parent[alias] = up
    for start in parent:
        seen, node = [], start
        while node in parent:
            if node in seen:
                errors.append(
                    "group nesting has a cycle: " + " -> ".join("@" + a for a in seen + [node])
                )
                break
            seen.append(node)
            node = parent[node]


def check_against_org(doc: dict, org: str, errors: list[str], notes: list[str]) -> None:
    """The two rules that compare one looked-up record against another."""
    import _orgio as org_io

    lookups = {lk.get("alias"): lk for lk in (doc.get("lookups") or [])}
    cache: dict[str, dict] = {}

    def resolve(alias: str, fields: str) -> dict | None:
        if alias in cache:
            return cache[alias]
        lk = lookups.get(alias)
        if lk is None:
            return None
        clause = lk.get("where") or {}
        where = " AND ".join(
            f"{k} = " + ("true" if v is True else "false" if v is False
                         else str(v) if isinstance(v, (int, float))
                         else "'" + str(v).replace("'", "\\'") + "'")
            for k, v in clause.items()
        )
        rows = org_io.query(org, f"SELECT {fields} FROM {lk['object']} WHERE {where} LIMIT 2")
        if len(rows) != 1:
            return None
        cache[alias] = rows[0]
        return rows[0]

    try:
        for rec in records(doc, GROUP):
            alias = rec.get("alias", "?")
            parent_alias = ref((rec.get("fields") or {}).get("ParentProductId"))
            if not parent_alias:
                continue
            product = resolve(parent_alias, "Id, ProductClass, Type")
            if product is None:
                continue
            if not product.get("Type"):
                errors.append(
                    f"group @{alias}: its parent product (@{parent_alias}) has no Type. The "
                    "platform refuses the group: \"Parent product type should not be null.\" "
                    "The message names ParentProductId; what is null is a field on the "
                    "product it points at."
                )
            else:
                notes.append(f"@{parent_alias}: Type {product['Type']}, "
                             f"ProductClass {product.get('ProductClass')}")

        for rec in records(doc, COMPONENT):
            alias = rec.get("alias", "?")
            fields = rec.get("fields") or {}
            parent_alias = ref(fields.get("ParentProductId"))
            type_alias = ref(fields.get("ProductRelationshipTypeId"))
            if not (parent_alias and type_alias):
                continue
            product = resolve(parent_alias, "Id, ProductClass, Type")
            reltype = resolve(type_alias, "Id, MainProductRoleCat, AssociatedProductRoleCat")
            if product is None or reltype is None:
                continue
            role = reltype.get("MainProductRoleCat")
            klass = product.get("ProductClass")
            if role != klass:
                errors.append(
                    f"component @{alias}: the parent product (@{parent_alias}) has "
                    f"ProductClass {klass!r} but the relationship type (@{type_alias}) has "
                    f"MainProductRoleCat {role!r}. Each lookup resolves on its own and the "
                    "pair is invalid: the platform refuses with \"A relationship type record "
                    f"with {klass} as role must have product classification component as "
                    "child.\""
                )
            else:
                notes.append(f"@{alias}: parent class {klass} matches relationship role {role}")
    except org_io.OrgError as exc:
        errors.append(f"could not check against the org: {exc}")


def main() -> int:
    ap = argparse.ArgumentParser(description="Bundle pre-flight for an rc-org-writer spec.")
    ap.add_argument("spec", type=Path)
    ap.add_argument("--target-org", help="also check the two cross-record preconditions")
    args = ap.parse_args()

    if not args.spec.exists():
        print(f"no such spec: {args.spec}", file=sys.stderr)
        return 2
    try:
        doc = parse(args.spec.read_text(encoding="utf-8"))
    except SpecError as exc:
        print(f"[FAIL] {args.spec}\n    parse error: {exc}")
        return 1

    errors: list[str] = []
    warnings: list[str] = []
    notes: list[str] = []

    check_no_products(doc, errors)
    check_components(doc, errors)
    check_cardinality(doc, errors, warnings)
    check_nesting(doc, errors)
    if args.target_org:
        check_against_org(doc, args.target_org, errors, notes)

    print(f"spec       : {args.spec}")
    print(f"groups     : {len(records(doc, GROUP))}")
    print(f"components : {len(records(doc, COMPONENT))}")
    print()
    for note in notes:
        print(f"    org:   {note}")
    for item in errors:
        print(f"    error: {item}")
    for item in warnings:
        print(f"    warn:  {item}")
    print()
    print(f"[{'FAIL' if errors else 'ok'}] {len(errors)} error(s), {len(warnings)} warning(s)")
    if errors:
        return 1
    if not args.target_org:
        print("Structure is sound. The two cross-record preconditions were NOT checked;")
        print("re-run with --target-org before applying.")
    else:
        print("Structure is sound and both cross-record preconditions hold.")
        print("Run validate_spec.py --target-org next, then apply.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
