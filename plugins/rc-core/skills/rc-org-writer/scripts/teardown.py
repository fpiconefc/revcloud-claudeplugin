"""Teardown phase: delete exactly what this run created, and nothing else.

Writes to an org. The log is the authority: teardown deletes the rows whose
`kind` is `created`, in reverse creation order, and never queries for the marker
to find more. "Everything matching the marker" would catch a record somebody
else made with the same prefix.

A looked-up record is out of reach by construction. Its log row carries
`kind: lookup`, this phase filters on `created`, and so a pre-existing record can
never be deleted here however the spec referenced it.

Idempotent over its own log. A record already gone is reported as such and is not
an error, so a teardown interrupted halfway can be run again. Running the same log
twice deletes nothing the second time.

Usage:
    python3 teardown.py --target-org <alias> --log <run.jsonl> --confirm

Exit codes: 0 everything is gone, 1 something could not be deleted, 2 bad invocation.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import _orgio as org_io  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description="Delete what a run created.")
    ap.add_argument("--target-org", required=True)
    ap.add_argument("--log", type=Path, required=True)
    ap.add_argument("--confirm", action="store_true",
                    help="stands for the human who read the list below")
    ap.add_argument("--dry-run", action="store_true",
                    help="print what would be deleted and stop")
    args = ap.parse_args()

    if not args.log.exists():
        org_io.die(f"no such log: {args.log}")

    try:
        rows = org_io.log_read(args.log)
    except org_io.OrgError as exc:
        org_io.die(str(exc))

    created = org_io.created_rows(rows)
    skipped = len(org_io.lookup_rows(rows))

    # Deduplicate on Id: a log can carry the same record twice if a command block
    # was pasted twice, and deleting the same Id twice is noise, not an error.
    seen: set[str] = set()
    targets = []
    for row in reversed(created):
        if row["id"] in seen:
            continue
        seen.add(row["id"])
        targets.append(row)

    print(f"log {args.log}")
    print(f"{len(targets)} record(s) to delete, in reverse creation order")
    if skipped:
        print(f"{skipped} looked-up record(s) in the log will not be touched")
    print()
    for n, row in enumerate(targets, start=1):
        print(f"  {n:3d}. {row['object']:<30s} @{row.get('alias', '?'):<22s} {row['id']}")

    if args.dry_run:
        print()
        print("Dry run: nothing was deleted.")
        return 0
    if not args.confirm:
        print()
        org_io.die("refusing to delete without --confirm. The list above is what would go.")

    print()
    failures: list[str] = []
    try:
        version = org_io.api_version(args.target_org)
    except org_io.OrgError as exc:
        org_io.die(str(exc))

    for n, row in enumerate(targets, start=1):
        try:
            outcome = org_io.delete(args.target_org, version, row["object"], row["id"])
            print(f"  {n:3d}. {outcome:<12s} {row['object']:<30s} {row['id']}")
        except org_io.OrgError as exc:
            failures.append(f"{row['object']} {row['id']}: {exc}")
            print(f"  {n:3d}. FAILED       {row['object']:<30s} {row['id']}")

    print()
    if failures:
        for item in failures:
            print(f"    could not delete: {item}")
        print()
        print("These are still in the org. The log is unchanged, so this teardown can be")
        print("run again once the cause is cleared.")
        return 1
    print("Everything this run created is gone. The log is kept as the record that it was.")
    print("Note that autonumbered names do not reset: a later run starts from a higher")
    print("number, and the gap this run left stays a gap.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
