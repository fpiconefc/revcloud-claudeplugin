"""Teardown phase: delete exactly what this run created, in reverse order, and
then ask the org whether it is actually gone.

Three rules, each of them a bug this repository has already had:

  * only `kind: created` rows are deleted. A looked-up account is somebody
    else's record and is never touched.
  * the list is deduplicated on Id, because a command run twice must not try
    to delete the same record twice and report two successes.
  * absence is established by query, not by the delete reply. A delete that
    returns a well-formed refusal looks exactly like a delete that worked.

What this cannot do: an account with other records hanging off it does not
delete. When that happens the account stays in the org and this says so, in
those words. It does not report a deletion it did not perform.

Usage:
    python3 teardown.py --target-org <alias> --log <run.jsonl> --confirm

Exit codes: 0 everything the log listed is gone, 1 something is left, 2 bad
invocation.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import _pricing as P  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description="Delete what a pricing test created.")
    ap.add_argument("--target-org", required=True)
    ap.add_argument("--log", type=Path, required=True)
    ap.add_argument("--confirm", action="store_true",
                    help="required; without it nothing is deleted")
    args = ap.parse_args()

    if not args.log.exists():
        P.die(f"no such file: {args.log}")
    if not args.confirm:
        P.die("refusing to delete without --confirm")

    try:
        rows = P.log_read(args.log)
        version = P.org_io.api_version(args.target_org)
    except Exception as exc:
        P.die(str(exc))

    created, seen = [], set()
    for row in rows:
        if row.get("kind") != "created" or not row.get("id"):
            continue
        if row["id"] in seen:
            continue
        seen.add(row["id"])
        created.append(row)

    if not created:
        print("the log records nothing created; nothing to tear down")
        return 0

    print(f"org {args.target_org}, {len(created)} record(s) to delete, "
          "in reverse creation order")
    left: list[str] = []
    for row in reversed(created):
        obj, rid = row["object"], row["id"]
        try:
            outcome = P.org_io.delete(args.target_org, version, obj, rid)
            print(f"  {obj:12s} {rid}  {outcome}")
        except P.OrgError as exc:
            message = P.unescape(str(exc))
            print(f"  {obj:12s} {rid}  REFUSED: {message}")
            left.append(f"{obj} {rid} was NOT deleted: {message}")

    print()
    print("confirming by query, because a delete reply is not evidence")
    for row in created:
        obj, rid = row["object"], row["id"]
        try:
            found = P.query(args.target_org, f"SELECT Id FROM {obj} WHERE Id = '{rid}'")
        except P.OrgError as exc:
            print(f"  {obj:12s} {rid}  could not be checked: {P.unescape(str(exc))}")
            left.append(f"{obj} {rid} could not be checked")
            continue
        if found:
            print(f"  {obj:12s} {rid}  STILL IN THE ORG")
            if not any(rid in item for item in left):
                left.append(f"{obj} {rid} is still in the org although its delete "
                            "reported success")
        else:
            print(f"  {obj:12s} {rid}  gone")

    print()
    if left:
        for item in left:
            print(f"LEFT BEHIND: {item}")
        print()
        print("The org is not back where it started. An account usually stays because")
        print("something else now points at it; whatever the reason, it is still there")
        print("and somebody has to deal with it.")
        return 1
    print("Every record this run created is gone, confirmed by query. Records the "
          "spec looked up were never touched.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
