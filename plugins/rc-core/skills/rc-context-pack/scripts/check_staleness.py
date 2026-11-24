#!/usr/bin/env python3
"""Report whether the Revenue Cloud knowledge pack is fresh enough to rely on.

Cheap by design: reads the local manifest and fingerprints, and makes at most one
network call (a HEAD against the developer guide PDF) unless --offline is passed.

Exit codes: 0 fresh, 1 stale, 2 missing.

Usage:
    python3 check_staleness.py
    python3 check_staleness.py --offline --max-age-days 120
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

UA = "rc-context-pack/0.1 (+staleness check)"


def age_days(iso: str) -> float | None:
    try:
        then = datetime.fromisoformat(iso)
    except (ValueError, TypeError):
        return None
    if then.tzinfo is None:
        then = then.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - then).total_seconds() / 86400


def main() -> int:
    ap = argparse.ArgumentParser(description="Check knowledge-pack freshness.")
    ap.add_argument("--out", default="~/.claude/knowledge/revenue-cloud")
    ap.add_argument("--max-age-days", type=float, default=120.0,
                    help="roughly one Salesforce release (default 120)")
    ap.add_argument("--offline", action="store_true", help="skip the network probe")
    args = ap.parse_args()

    root = Path(os.path.expanduser(args.out))
    manifest_path = root / "MANIFEST.json"

    if not manifest_path.exists():
        print(f"MISSING: no pack at {root}")
        print("Build it: sweep_docs.py then sweep_org.py --org <alias>")
        return 2

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    stale = False

    docs_age = age_days(manifest.get("swept_at", ""))
    if docs_age is None:
        print("docs: manifest has no usable timestamp -> treat as stale")
        stale = True
    else:
        verdict = "STALE" if docs_age > args.max_age_days else "fresh"
        print(f"docs: swept {docs_age:.0f} days ago -> {verdict}")
        stale = stale or docs_age > args.max_age_days

    if manifest.get("failures"):
        print(f"docs: INCOMPLETE, {len(manifest['failures'])} source(s) failed last sweep: "
              f"{', '.join(manifest['failures'])}")
        stale = True

    orgs_dir = root / "orgs"
    org_dirs = sorted(p for p in orgs_dir.iterdir() if p.is_dir()) if orgs_dir.exists() else []
    if not org_dirs:
        print("orgs: none fingerprinted -> the pack can answer product questions "
              "but nothing about a customer's org")
        stale = True
    for org_dir in org_dirs:
        fp_path = org_dir / "fingerprint.json"
        if not fp_path.exists():
            print(f"orgs: {org_dir.name} has no fingerprint.json -> stale")
            stale = True
            continue
        fp = json.loads(fp_path.read_text(encoding="utf-8"))
        org_age = age_days(fp.get("swept_at", ""))
        enabled = [m for m, v in fp.get("modules", {}).items() if v.get("enabled")]
        verdict = "STALE" if (org_age or 999) > args.max_age_days else "fresh"
        print(f"orgs: {org_dir.name} swept {org_age:.0f} days ago -> {verdict} "
              f"({len(enabled)} module(s) enabled)")
        stale = stale or (org_age or 999) > args.max_age_days

    if not args.offline:
        pdf = manifest.get("sources", {}).get("dev_guide_pdf", {})
        url = pdf.get("url")
        if url:
            try:
                req = urllib.request.Request(url, method="HEAD", headers={"User-Agent": UA})
                with urllib.request.urlopen(req, timeout=20) as resp:
                    remote_len = resp.headers.get("Content-Length")
                if remote_len and pdf.get("bytes") and int(remote_len) != int(pdf["bytes"]):
                    print(f"docs: developer guide PDF changed size "
                          f"({pdf['bytes']:,} -> {int(remote_len):,} bytes) -> re-sweep")
                    stale = True
                else:
                    print("docs: developer guide PDF unchanged since last sweep")
            except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, ValueError) as exc:
                print(f"docs: could not probe the guide ({exc}); skipping that check")

    print()
    if stale:
        print("VERDICT: stale. Re-sweep before relying on the pack, or say plainly "
              "which parts you could not verify.")
        return 1
    print("VERDICT: fresh.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
