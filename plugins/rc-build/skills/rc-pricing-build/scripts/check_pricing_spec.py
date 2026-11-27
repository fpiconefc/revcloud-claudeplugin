"""Pricing pre-flight for an rc-org-writer spec. Read-only; writes nothing.

rc-org-writer's own validator checks that a spec is well formed and that its
lookups resolve. It cannot check what pricing means, and it cannot check the
three platform rules below, because no describe expresses them and two of them
involve an object the spec never names.

Run this before `validate_spec.py --target-org`, and both before apply.

Checks, in two groups.

Platform rules, each observed stopping a real apply on API v68:

  1. Tier bounds are INCLUSIVE at both ends. A tier whose LowerBound equals the
     previous tier's UpperBound is refused as an overlap. The next tier starts
     one unit higher. The Salesforce guide documents the opposite and following
     it produces exactly the shape the platform rejects.
  2. Every tier needs EffectiveFrom, although the describe has it nillable.
  3. The product must already be assigned to the selling model, through a
     ProductSellingModelOption the spec does not mention. Needs --target-org.

Doctrine, from rc-pricing-adjustments:

  4. Only a schedule type that reads tiers may have them.
  5. AdjustmentMethod is stated, never left to its default: Range and Slab give
     different prices from identical tiers.
  6. No gaps between consecutive tiers.
  7. All tiers under one schedule share a selling model, unless `purpose` says
     the mix is deliberate.

Usage:
    python3 check_pricing_spec.py <spec.yaml>
    python3 check_pricing_spec.py <spec.yaml> --target-org <alias>

Exit codes: 0 clean, 1 problems found, 2 bad invocation.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# rc-org-writer owns the spec format; this skill does not re-parse it by hand.
_WRITER = Path(__file__).resolve().parents[4] / "rc-core/skills/rc-org-writer/scripts"
if not (_WRITER / "validate_spec.py").exists():
    print("error: rc-org-writer is not installed beside this plugin; it owns the spec "
          f"format and the four phases. Looked in {_WRITER}", file=sys.stderr)
    raise SystemExit(2)
sys.path.insert(0, str(_WRITER))

from validate_spec import SpecError, parse  # noqa: E402

TIERED_SCHEDULE_TYPES = {"Volume", "Term"}
SCHEDULE = "PriceAdjustmentSchedule"
TIER = "PriceAdjustmentTier"


def number(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def check_schedules(doc: dict, errors: list[str], warnings: list[str]) -> None:
    for rec in doc.get("records") or []:
        if rec.get("object") != SCHEDULE:
            continue
        alias = rec.get("alias", "?")
        fields = rec.get("fields") or {}
        kind = fields.get("ScheduleType")

        if "AdjustmentMethod" not in fields:
            errors.append(
                f"schedule @{alias}: AdjustmentMethod is not set. It defaults to Range, and "
                "Range and Slab produce different prices from the same tiers, so it is "
                "stated deliberately or not at all."
            )
        if kind and kind not in TIERED_SCHEDULE_TYPES:
            tiers = [r for r in (doc.get("records") or [])
                     if r.get("object") == TIER
                     and (r.get("fields") or {}).get("PriceAdjustmentScheduleId") == f"@{alias}"]
            if tiers:
                errors.append(
                    f"schedule @{alias}: ScheduleType {kind!r} does not read "
                    f"{TIER} children, but {len(tiers)} are declared under it. A "
                    f"{kind} schedule carries its own child object and this one would "
                    "price nothing."
                )
        if fields.get("IsActive") is True:
            warnings.append(
                f"schedule @{alias}: IsActive is true. A new schedule is created inactive "
                "and switched on by a person after verify, because an org may already have "
                "an active schedule of the same type over the same price book and the "
                "interaction between two is undocumented."
            )


def tiers_by_schedule(doc: dict) -> dict[str, list[dict]]:
    grouped: dict[str, list[dict]] = {}
    for rec in doc.get("records") or []:
        if rec.get("object") != TIER:
            continue
        parent = str((rec.get("fields") or {}).get("PriceAdjustmentScheduleId", "?"))
        grouped.setdefault(parent, []).append(rec)
    return grouped


def check_tiers(doc: dict, errors: list[str], warnings: list[str]) -> None:
    purpose = str(doc.get("purpose") or "").lower()
    for parent, tiers in tiers_by_schedule(doc).items():
        for rec in tiers:
            alias = rec.get("alias", "?")
            fields = rec.get("fields") or {}
            if not fields.get("EffectiveFrom"):
                errors.append(
                    f"tier @{alias}: EffectiveFrom is not set. The describe has it "
                    "nillable and the platform refuses the record without it: "
                    '"Specify the Effective From date to save your price adjustment tier."'
                )
            for required in ("TierType", "TierValue", "LowerBound"):
                if fields.get(required) is None:
                    errors.append(f"tier @{alias}: {required} is not set")

        models = {str((r.get("fields") or {}).get("ProductSellingModelId")) for r in tiers}
        if len(models) > 1 and "selling model" not in purpose:
            warnings.append(
                f"schedule {parent}: its tiers span {len(models)} selling models. That is "
                "legal and rarely intended; if it is deliberate, say so in `purpose`."
            )

        ordered = sorted(
            (r for r in tiers if number((r.get("fields") or {}).get("LowerBound")) is not None),
            key=lambda r: number(r["fields"]["LowerBound"]),
        )
        for previous, current in zip(ordered, ordered[1:]):
            prev_alias = previous.get("alias", "?")
            cur_alias = current.get("alias", "?")
            upper = number((previous.get("fields") or {}).get("UpperBound"))
            lower = number((current.get("fields") or {}).get("LowerBound"))
            if upper is None:
                errors.append(
                    f"tier @{prev_alias}: no UpperBound, but @{cur_alias} continues above "
                    "it. Only the last tier may be open-ended."
                )
                continue
            if lower == upper:
                errors.append(
                    f"tiers @{prev_alias} and @{cur_alias} share the bound {upper:g}. "
                    "Bounds are inclusive at both ends, so this is an overlap and the "
                    "platform refuses it: \"The tiers must have unique effective date "
                    f"ranges and lower and upper bound value ranges.\" Start @{cur_alias} "
                    f"at {upper + 1:g}, not {lower:g}."
                )
            elif lower < upper:
                errors.append(
                    f"tiers @{prev_alias} and @{cur_alias} overlap: {upper:g} and "
                    f"{lower:g}. Bounds are inclusive at both ends."
                )
            elif lower > upper + 1:
                errors.append(
                    f"tiers @{prev_alias} and @{cur_alias} leave a gap between {upper:g} "
                    f"and {lower:g}. Consecutive tiers step by one: @{cur_alias} starts at "
                    f"{upper + 1:g}."
                )


def check_assignment(doc: dict, org: str, errors: list[str], notes: list[str]) -> None:
    """The precondition on an object the spec never names."""
    import _orgio as org_io

    lookups = {lk.get("alias"): lk for lk in (doc.get("lookups") or [])}
    resolved: dict[str, str] = {}

    def resolve(reference) -> str | None:
        if not (isinstance(reference, str) and reference.startswith("@")):
            return reference if isinstance(reference, str) else None
        alias = reference[1:]
        if alias in resolved:
            return resolved[alias]
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
        rows = org_io.query(org, f"SELECT Id FROM {lk['object']} WHERE {where} LIMIT 2")
        if len(rows) != 1:
            return None
        resolved[alias] = rows[0]["Id"]
        return resolved[alias]

    pairs: dict[tuple[str, str], list[str]] = {}
    for rec in doc.get("records") or []:
        if rec.get("object") != TIER:
            continue
        fields = rec.get("fields") or {}
        product = resolve(fields.get("Product2Id"))
        model = resolve(fields.get("ProductSellingModelId"))
        if product and model:
            pairs.setdefault((product, model), []).append(rec.get("alias", "?"))

    try:
        for (product, model), aliases in pairs.items():
            rows = org_io.query(
                org,
                "SELECT Id FROM ProductSellingModelOption "
                f"WHERE Product2Id = '{product}' AND ProductSellingModelId = '{model}' LIMIT 1",
            )
            which = ", ".join(f"@{a}" for a in aliases)
            if rows:
                notes.append(f"{which}: product is assigned to the selling model")
            else:
                errors.append(
                    f"{which}: the product is not assigned to that selling model. No "
                    "ProductSellingModelOption joins them, and a tier naming both is "
                    "refused. This skill does not create the assignment: doing so changes "
                    "what the product can be sold on. Have the catalog owner add it, then "
                    "run this again."
                )
    except org_io.OrgError as exc:
        errors.append(f"could not check the selling-model assignment: {exc}")


def main() -> int:
    ap = argparse.ArgumentParser(description="Pricing pre-flight for an rc-org-writer spec.")
    ap.add_argument("spec", type=Path)
    ap.add_argument("--target-org", help="also check the selling-model assignment")
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

    check_schedules(doc, errors, warnings)
    check_tiers(doc, errors, warnings)
    if args.target_org:
        check_assignment(doc, args.target_org, errors, notes)

    schedules = sum(1 for r in (doc.get("records") or []) if r.get("object") == SCHEDULE)
    tiers = sum(1 for r in (doc.get("records") or []) if r.get("object") == TIER)
    print(f"spec      : {args.spec}")
    print(f"schedules : {schedules}")
    print(f"tiers     : {tiers}")
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
        print("Pricing shape is sound. The selling-model assignment was NOT checked;")
        print("re-run with --target-org before applying.")
    else:
        print("Pricing shape is sound and every product is assigned to its selling model.")
        print("Run validate_spec.py --target-org next, then apply.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
