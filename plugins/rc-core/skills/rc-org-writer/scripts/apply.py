"""Apply phase: create the records a spec declares, in dependency order.

Writes to an org. It refuses to run unless the spec validates, unless a target
org is named, and unless `--confirm` is passed, which stands for the human who
read the preview. Editing the spec voids that confirmation, so run preview again.

Two rules the first real run of this cycle taught, both enforced here rather
than described:

- **It stops at the first error.** A create that fails does not let the next one
  proceed. A half-applied spec whose later records assumed an earlier one is a
  worse state than a spec that stopped.
- **No log line without an Id.** A line recording an empty Id is worse than no
  line at all, because teardown believes the log. If a create returns without an
  Id, nothing is written and the run ends.

Usage:
    python3 apply.py <spec.yaml> --target-org <alias> --log <run.jsonl> --confirm

Exit codes: 0 applied, 1 refused or stopped on an error, 2 bad invocation.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import _orgio as org_io  # noqa: E402
from validate_spec import (  # noqa: E402
    DEFAULT_PACK, SpecError, check, order, parse,
)


def soql_literal(value) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    return "'" + str(value).replace("\\", "\\\\").replace("'", "\\'") + "'"


def resolve_lookups(org: str, lookups: list[dict], log: Path) -> dict[str, str]:
    """Each lookup resolves to exactly one record, or nothing is written."""
    ids: dict[str, str] = {}
    for lk in lookups:
        alias, obj = lk["alias"], lk["object"]
        clause = lk.get("where") or {}
        where = " AND ".join(f"{k} = {soql_literal(v)}" for k, v in clause.items())
        rows = org_io.query(org, f"SELECT Id FROM {obj} WHERE {where} LIMIT 2")
        if len(rows) != 1:
            raise org_io.OrgError(
                f"lookup @{alias} on {obj} matched {len(rows)} records, not 1 "
                f"({where}). Nothing has been written."
            )
        ids[alias] = rows[0]["Id"]
        # Recorded, never deleted: teardown filters on kind.
        org_io.log_append(log, {
            "kind": "lookup", "alias": alias, "object": obj,
            "id": ids[alias], "where": clause,
        })
        print(f"  resolved @{alias:<22s} {obj:<28s} {ids[alias]}")
    return ids


def main() -> int:
    ap = argparse.ArgumentParser(description="Create the records a spec declares.")
    ap.add_argument("spec", type=Path)
    ap.add_argument("--target-org", required=True)
    ap.add_argument("--log", type=Path, required=True)
    ap.add_argument("--confirm", action="store_true",
                    help="stands for the human who read this spec's preview")
    ap.add_argument("--pack", type=Path, default=DEFAULT_PACK)
    args = ap.parse_args()

    if not args.spec.exists():
        org_io.die(f"no such spec: {args.spec}")
    if not args.confirm:
        org_io.die(
            "refusing to write without --confirm. Run validate_spec.py against this "
            "org first and read the plan; --confirm stands for having done so."
        )

    try:
        doc = parse(args.spec.read_text(encoding="utf-8"))
    except SpecError as exc:
        org_io.die(f"parse error: {exc}")

    describe_dir = args.pack / "orgs" / args.target_org / "describe"
    errors, _warnings, records = check(doc, describe_dir if describe_dir.is_dir() else None)
    if errors:
        print("refusing to apply: the spec does not validate.", file=sys.stderr)
        for e in errors:
            print(f"    error: {e}", file=sys.stderr)
        return 1

    try:
        planned = order(records)
    except SpecError as exc:
        org_io.die(str(exc))

    marker = (doc.get("marker") or {}).get("token")
    if args.log.exists() and org_io.created_rows(org_io.log_read(args.log)):
        org_io.die(
            f"{args.log} already records created rows. Apply writes a fresh log per run; "
            "tear the previous run down, or point --log at a new file."
        )

    try:
        version = org_io.api_version(args.target_org)
        print(f"org {args.target_org}, API v{version}, log {args.log}")
        print()
        ids = resolve_lookups(args.target_org, doc.get("lookups") or [], args.log)
        print()
        for n, rec in enumerate(planned, start=1):
            alias, obj = rec["alias"], rec["object"]
            fields = {k: org_io.resolve(v, ids) for k, v in (rec.get("fields") or {}).items()}
            record_id = org_io.create(args.target_org, version, obj, fields)
            if not record_id:
                raise org_io.OrgError(
                    f"{obj} @{alias} returned no Id; nothing logged for it"
                )
            ids[alias] = record_id
            org_io.log_append(args.log, {
                "kind": "created", "alias": alias, "object": obj,
                "id": record_id, "marker": marker,
            })
            print(f"  {n:3d}. created {obj:<28s} @{alias:<22s} {record_id}")
    except org_io.OrgError as exc:
        print(file=sys.stderr)
        print(f"stopped: {exc}", file=sys.stderr)
        print(
            "Nothing further was attempted. Records already created are in the log; "
            "run teardown.py against it to reverse them.", file=sys.stderr,
        )
        return 1

    print()
    print(f"Applied {len(planned)} record(s). Run verify.py next, then teardown.py")
    print("when the run has served its purpose.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
