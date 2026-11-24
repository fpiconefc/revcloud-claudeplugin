#!/usr/bin/env python3
"""Fetch the official Salesforce Revenue Cloud documentation into the knowledge pack.

Only Salesforce-published sources are fetched. Each is stored with a SHA-256 so
check_staleness.py can tell later whether it moved. Third-party material belongs
in notes/, clearly marked, never here.

Usage:
    python3 sweep_docs.py --out ~/.claude/knowledge/revenue-cloud
    python3 sweep_docs.py --out ... --only pricing billing
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

GUIDE = ("https://developer.salesforce.com/docs/atlas.en-us."
         "revenue_lifecycle_management_dev_guide.meta/revenue_lifecycle_management_dev_guide")

SOURCES: list[dict[str, str]] = [
    {
        "key": "dev_guide_pdf",
        "module": "all",
        "url": ("https://resources.docs.salesforce.com/latest/latest/en-us/sfdc/pdf/"
                "revenue_lifecycle_management_dev_guide.pdf"),
        "authoritative_for": "Complete object and field reference, API versions, deployment sequence.",
    },
    {
        "key": "pricing_std_objects",
        "module": "salesforce_pricing",
        "url": f"{GUIDE}/pricing_std_objects_parent.htm",
        "authoritative_for": "Salesforce Pricing standard objects and the API version each landed in.",
    },
    {
        "key": "associated_objects",
        "module": "all",
        "url": f"{GUIDE}/sforce_api_associated_objects_list.htm",
        "authoritative_for": "Associated objects (feed, history, share) per standard object.",
    },
]

UA = "rc-context-pack/0.1 (+knowledge pack sweep)"


def fetch(url: str, timeout: int = 60) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def main() -> int:
    ap = argparse.ArgumentParser(description="Sweep official Revenue Cloud docs.")
    ap.add_argument("--out", default="~/.claude/knowledge/revenue-cloud")
    ap.add_argument("--only", nargs="*", help="limit to these module names")
    args = ap.parse_args()

    root = Path(os.path.expanduser(args.out))
    (root / "docs").mkdir(parents=True, exist_ok=True)
    (root / "notes").mkdir(parents=True, exist_ok=True)

    manifest_path = root / "MANIFEST.json"
    manifest = {"sources": {}}
    if manifest_path.exists():
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest.setdefault("sources", {})
        except json.JSONDecodeError:
            pass

    selected = [s for s in SOURCES if not args.only or s["module"] in args.only or s["module"] == "all"]
    failures = []

    for src in selected:
        print(f"fetching {src['key']} ...", file=sys.stderr)
        try:
            body = fetch(src["url"])
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as exc:
            print(f"  FAILED: {exc}", file=sys.stderr)
            failures.append(src["key"])
            continue

        digest = hashlib.sha256(body).hexdigest()
        suffix = ".pdf" if src["url"].endswith(".pdf") else ".htm"
        dest_dir = root / "docs" / src["module"]
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / f"{src['key']}{suffix}"
        dest.write_bytes(body)

        previous = manifest["sources"].get(src["key"], {}).get("sha256")
        manifest["sources"][src["key"]] = {
            "url": src["url"],
            "module": src["module"],
            "authoritative_for": src["authoritative_for"],
            "path": str(dest.relative_to(root)),
            "sha256": digest,
            "bytes": len(body),
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "changed_since_last_sweep": previous is not None and previous != digest,
        }
        marker = " (CHANGED)" if previous and previous != digest else ""
        print(f"  {len(body):,} bytes -> {dest.name}{marker}", file=sys.stderr)

    manifest["swept_at"] = datetime.now(timezone.utc).isoformat()
    manifest["failures"] = failures
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    print(f"\nManifest: {manifest_path}", file=sys.stderr)
    if failures:
        print(f"WARNING: {len(failures)} source(s) failed: {', '.join(failures)}", file=sys.stderr)
        print("The pack is incomplete. Do not treat it as authoritative.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
