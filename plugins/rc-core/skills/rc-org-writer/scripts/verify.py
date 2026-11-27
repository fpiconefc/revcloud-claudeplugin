"""Verify phase: read back what apply created and compare it to the spec.

Read-only. A successful create does not mean the configuration is what was asked
for, so every created record is re-queried and compared field by field. Three
outcomes are reported and none is hidden:

    match                 the field is what the spec said
    expected difference   a read-only projection the platform filled in, a
                          default that appeared, or a value it normalised
    unexpected difference everything else -- these are the findings

Comparisons are by value, not by text. The platform returns
`2027-01-01T00:00:00.000+0000` for what was sent as `...000Z`: the same instant
written differently, which a literal comparison reports as a difference that is
not one.

Usage:
    python3 verify.py <spec.yaml> --target-org <alias> --log <run.jsonl>

Exit codes: 0 no unexpected differences, 1 unexpected differences or an error.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import _orgio as org_io  # noqa: E402
from validate_spec import DEFAULT_PACK, SpecError, parse  # noqa: E402

# The comparison lives in _orgio so preview and verify cannot drift apart.
PROJECTED = org_io.PROJECTED
AUTONUMBERED = org_io.AUTONUMBERED
equivalent = org_io.equivalent

def main() -> int:
    ap = argparse.ArgumentParser(description="Compare created records against the spec.")
    ap.add_argument("spec", type=Path)
    ap.add_argument("--target-org", required=True)
    ap.add_argument("--log", type=Path, required=True)
    ap.add_argument("--pack", type=Path, default=DEFAULT_PACK)
    args = ap.parse_args()

    for path in (args.spec, args.log):
        if not path.exists():
            org_io.die(f"no such file: {path}")

    try:
        doc = parse(args.spec.read_text(encoding="utf-8"))
        rows = org_io.log_read(args.log)
    except (SpecError, org_io.OrgError) as exc:
        org_io.die(str(exc))

    by_alias = {r["alias"]: r for r in (doc.get("records") or []) if r.get("alias")}
    created = org_io.created_rows(rows)
    looked_up = org_io.lookup_rows(rows)
    ids = {r["alias"]: r["id"] for r in looked_up + created}

    if not created:
        print("the log records no created rows; nothing to verify")
        return 0

    print(f"org {args.target_org}, log {args.log}")
    print(f"{len(created)} created record(s), {len(looked_up)} lookup(s) pinned")
    print()

    matches = expected = 0
    unexpected: list[str] = []

    try:
        for row in created:
            alias, obj, record_id = row["alias"], row["object"], row["id"]
            spec_rec = by_alias.get(alias)
            if spec_rec is None:
                unexpected.append(f"@{alias}: in the log, absent from the spec")
                continue
            fields = spec_rec.get("fields") or {}
            names = sorted(fields)
            projected = sorted(PROJECTED.get(obj, set()) | AUTONUMBERED)
            select = ", ".join(dict.fromkeys(["Id"] + names + projected))
            found = org_io.query(
                args.target_org, f"SELECT {select} FROM {obj} WHERE Id = '{record_id}'"
            )
            if not found:
                unexpected.append(f"@{alias} ({obj} {record_id}): not found in the org")
                continue
            got = found[0]
            print(f"  {obj} @{alias} {record_id}")
            for name in names:
                want = org_io.resolve(fields[name], ids)
                have = got.get(name)
                equal, why = equivalent(want, have)
                if equal and not why:
                    matches += 1
                elif equal:
                    expected += 1
                    print(f"      ~ {name:28s} {want!r} -> {have!r}  ({why})")
                else:
                    unexpected.append(
                        f"@{alias} {name}: spec {want!r}, org {have!r}"
                    )
                    print(f"      ! {name:28s} spec {want!r}, org {have!r}")
            for name in projected:
                if name in names or got.get(name) in (None, ""):
                    continue
                expected += 1
                print(f"      + {name:28s} {got[name]!r}  (platform populated this)")
    except org_io.OrgError as exc:
        org_io.die(str(exc))

    print()
    print(f"matches: {matches}   expected differences: {expected}   "
          f"unexpected: {len(unexpected)}")
    if unexpected:
        print()
        for item in unexpected:
            print(f"    unexpected: {item}")
        print()
        print("An unexpected difference is a finding. Report it before changing anything:")
        print("there is no update path in this cycle, so the fix is a teardown and a")
        print("corrected spec.")
        return 1
    print("Every field the spec set came back as the spec set it.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
