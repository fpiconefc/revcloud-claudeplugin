"""Validate an rc-org-writer spec and print the apply plan. Writes nothing, touches no org.

This is the offline half of the preview phase: it parses the spec, checks every
rule the contract imposes, resolves the symbolic references, orders the records by
dependency, and prints exactly what apply would create. It never contacts an org,
so a clean run here means the spec is well-formed -- not that the org will accept it.

The spec is a constrained YAML subset, parsed by this file rather than by PyYAML,
because skills in this repo run with no third-party dependencies. Anything outside
the subset is an error with a line number, never a guess. See
assets/spec-template.yaml for the shape and SKILL.md for the contract.

Usage:
    python3 validate_spec.py <spec.yaml>
    python3 validate_spec.py <spec.yaml> --pack /path/to/revenue-cloud

Exit codes: 0 the spec is valid, 1 errors found, 2 bad invocation.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

DEFAULT_PACK = Path.home() / ".claude" / "knowledge" / "revenue-cloud"
SPEC_VERSION = "rc-org-writer/v1"

REFERENCE = re.compile(r"^@([A-Za-z_][A-Za-z0-9_]*)$")
SALESFORCE_ID = re.compile(r"^[a-zA-Z0-9]{15}([a-zA-Z0-9]{3})?$")
ALIAS = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
RECORD_KEYS = {"alias", "object", "key", "marked_by", "fields"}
REQUIRED_META = ("target", "author", "created", "purpose", "marker")


class SpecError(Exception):
    pass


# ---------------------------------------------------------------- parsing ---

def _scalar(raw: str, line: int):
    """Convert a scalar the subset allows. Quoted stays a string."""
    s = raw.strip()
    if not s:
        return ""
    if s[0] in "\"'" and s[-1] == s[0] and len(s) >= 2:
        return s[1:-1]
    if s in ("true", "false"):
        return s == "true"
    if s in ("null", "~"):
        return None
    if s in ("[]", "{}"):
        raise SpecError(f"line {line}: flow style is outside the spec subset")
    if s.startswith("&") or s.startswith("*"):
        raise SpecError(
            f"line {line}: YAML anchors and aliases are outside the spec subset; "
            "use an @alias reference instead"
        )
    try:
        return int(s)
    except ValueError:
        pass
    try:
        return float(s)
    except ValueError:
        pass
    return s


def parse(text: str) -> dict:
    """Parse the constrained subset: top-level mappings, one nested mapping level,
    a list of mappings under `records`, and a list of scalars elsewhere."""
    doc: dict = {}
    records: list[dict] = []
    current: dict | None = None      # record being built
    section: str | None = None       # top-level key currently open
    nested: dict | None = None       # a one-level nested mapping (target, marker, fields)
    rec_indent = 0                   # indent of the open record's own keys
    block_key: tuple | None = None   # (container, key, indent) collecting a `>` block

    for n, raw in enumerate(text.splitlines(), start=1):
        if block_key is not None:
            container, key, base = block_key
            if not raw.strip():
                continue
            if len(raw) - len(raw.lstrip()) > base:
                container[key] = (container[key] + " " + raw.strip()).strip()
                continue
            block_key = None

        line = raw.rstrip()
        if not line.strip() or line.lstrip().startswith("#"):
            continue

        indent = len(line) - len(line.lstrip())
        body = line.strip()

        # a list item
        if body.startswith("- "):
            item = body[2:].strip()
            if section == "records":
                if ":" not in item:
                    raise SpecError(f"line {n}: a record must start with `alias: <name>`")
                current = {}
                records.append(current)
                nested = None
                rec_indent = indent + 2
                k, _, v = item.partition(":")
                current[k.strip()] = _scalar(v, n)
            elif nested is not None and isinstance(nested, dict):
                raise SpecError(f"line {n}: a list cannot sit inside a nested mapping here")
            elif section:
                doc.setdefault(section, [])
                if not isinstance(doc[section], list):
                    doc[section] = []
                doc[section].append(_scalar(item, n))
            else:
                raise SpecError(f"line {n}: list item outside any key")
            continue

        if ":" not in body:
            raise SpecError(f"line {n}: expected `key: value`, got {body!r}")

        key, _, value = body.partition(":")
        key = key.strip()
        value = value.strip()

        # deeper than the record's own keys: a nested mapping such as `fields`
        if current is not None and indent > rec_indent:
            if nested is None:
                raise SpecError(f"line {n}: {key!r} is indented under no mapping")
            if value == ">":
                nested[key] = ""
                block_key = (nested, key, indent)
            else:
                nested[key] = _scalar(value, n)
            continue

        if current is not None and indent >= rec_indent:
            if not value:
                nested = {}
                current[key] = nested
            else:
                if key not in RECORD_KEYS:
                    raise SpecError(
                        f"line {n}: {key!r} is not a record key; allowed: "
                        + ", ".join(sorted(RECORD_KEYS))
                    )
                current[key] = _scalar(value, n)
                nested = None
            continue

        if indent >= 2 and section and isinstance(doc.get(section), dict):
            if value == ">":
                doc[section][key] = ""
                block_key = (doc[section], key, indent)
            else:
                doc[section][key] = _scalar(value, n)
            continue

        # top level
        current = None
        nested = None
        if not value:
            section = key
            doc[key] = {} if key != "records" else records
        elif value == ">":
            section = key
            doc[key] = ""
            block_key = (doc, key, indent)
        else:
            section = key
            doc[key] = _scalar(value, n)

    doc["records"] = records
    return doc


# ------------------------------------------------------------- pack lookup ---

def marking_tier(describe_dir: Path | None, obj: str) -> tuple[str, list[str]]:
    """Classify how a record of this object can be marked as ours.

    Returns (tier, keys): tier 1 has a unique idLookup field usable as an upsert
    key, tier 2 has a writable Name and nothing unique, tier 3 has neither.
    """
    if describe_dir is None:
        return ("unknown", [])
    path = describe_dir / f"{obj}.json"
    if not path.exists():
        return ("unknown", [])
    import json
    fields = json.loads(path.read_text(encoding="utf-8")).get("fields", [])
    keys = [
        f["name"] for f in fields
        if f.get("createable") and f.get("unique") and f.get("idLookup")
        and f["name"] != "Id"
    ]
    if keys:
        return ("1", keys)
    name = next((f for f in fields if f["name"] == "Name"), None)
    if name is not None and name.get("createable"):
        return ("2", ["Name"])
    return ("3", [])


# --------------------------------------------------------------- checking ---

def check(doc: dict, describe_dir: Path | None) -> tuple[list[str], list[str], list[dict]]:
    errors: list[str] = []
    warnings: list[str] = []

    if doc.get("spec") != SPEC_VERSION:
        errors.append(f"spec must be {SPEC_VERSION!r}, got {doc.get('spec')!r}")
    for field in REQUIRED_META:
        if not doc.get(field):
            errors.append(f"metadata is missing {field!r}")

    target = doc.get("target") or {}
    if isinstance(target, dict) and not target.get("org"):
        errors.append("target.org is missing; a spec names the org it is for")

    marker = doc.get("marker") or {}
    token = marker.get("token") if isinstance(marker, dict) else None
    if not token:
        errors.append("marker.token is missing; nothing would identify what this run created")

    records = doc.get("records") or []
    if not records:
        errors.append("the spec creates no records")

    seen: dict[str, dict] = {}
    for i, rec in enumerate(records, start=1):
        where = f"record {i}"
        alias = rec.get("alias")
        if not alias:
            errors.append(f"{where}: no alias")
            continue
        where = f"record {i} ({alias})"
        if not ALIAS.match(str(alias)):
            errors.append(f"{where}: alias must match {ALIAS.pattern}")
        if alias in seen:
            errors.append(f"{where}: alias is already used")
        seen[alias] = rec
        if not rec.get("object"):
            errors.append(f"{where}: no object")
        extra = set(rec) - RECORD_KEYS
        if extra:
            errors.append(f"{where}: unknown key(s) {', '.join(sorted(extra))}")
        if not isinstance(rec.get("fields"), dict) or not rec.get("fields"):
            errors.append(f"{where}: no fields")

    # references, marking and literal ids
    for alias, rec in seen.items():
        obj = rec.get("object") or "?"
        where = f"record {alias}"
        for fname, value in (rec.get("fields") or {}).items():
            if not isinstance(value, str):
                continue
            m = REFERENCE.match(value)
            if m:
                if m.group(1) not in seen:
                    errors.append(
                        f"{where}: field {fname} references @{m.group(1)}, "
                        "which no record declares"
                    )
                continue
            if value.startswith("@"):
                errors.append(f"{where}: field {fname} has a malformed reference {value!r}")
            elif fname.endswith("Id") and SALESFORCE_ID.match(value):
                warnings.append(
                    f"{where}: field {fname} looks like a literal Salesforce Id. A spec "
                    "addresses records it creates by @alias; a literal Id is a record "
                    "this run does not own."
                )

        tier, keys = marking_tier(describe_dir, obj)
        fields = rec.get("fields") or {}
        declared_key = rec.get("key")
        marked_by = rec.get("marked_by")

        if marked_by and marked_by not in seen:
            errors.append(f"{where}: marked_by names @{marked_by}, which no record declares")

        if tier == "1":
            if not declared_key:
                errors.append(
                    f"{where}: {obj} has a unique key ({', '.join(keys)}); "
                    "declare it with `key:` so apply can be idempotent"
                )
            elif declared_key not in keys:
                errors.append(
                    f"{where}: key {declared_key!r} is not unique+idLookup on {obj}; "
                    f"usable: {', '.join(keys)}"
                )
            elif declared_key not in fields:
                errors.append(f"{where}: key {declared_key!r} is declared but not set in fields")
            elif token and token not in str(fields.get(declared_key, "")):
                errors.append(
                    f"{where}: {declared_key} must contain the marker token {token!r}"
                )
        elif tier == "2":
            if declared_key:
                errors.append(f"{where}: {obj} has no unique key; remove `key:`")
            name = str(fields.get("Name", ""))
            if not name:
                errors.append(f"{where}: {obj} has a writable Name; set it and carry the marker")
            elif token and not name.startswith(token):
                errors.append(f"{where}: Name must start with the marker token {token!r}")
        elif tier == "3":
            if declared_key:
                errors.append(f"{where}: {obj} has no unique key; remove `key:`")
            if not marked_by:
                errors.append(
                    f"{where}: {obj} cannot carry a marker on the record, so it must "
                    "declare `marked_by:` naming a record in this spec that can. "
                    "Without it, only the run log would prove authorship."
                )
        else:
            warnings.append(
                f"{where}: {obj} is not in the pack's describes, so its marking route "
                "could not be checked. Describe it before applying."
            )

    return errors, warnings, records


def order(records: list[dict]) -> list[dict]:
    """Topological order by @alias references. Raises on a cycle."""
    by_alias = {r["alias"]: r for r in records if r.get("alias")}
    deps: dict[str, set[str]] = {}
    for alias, rec in by_alias.items():
        d = set()
        for value in (rec.get("fields") or {}).values():
            if isinstance(value, str):
                m = REFERENCE.match(value)
                if m and m.group(1) in by_alias:
                    d.add(m.group(1))
        if rec.get("marked_by") in by_alias:
            d.add(rec["marked_by"])
        deps[alias] = d

    out: list[dict] = []
    done: set[str] = set()
    while len(done) < len(by_alias):
        ready = sorted(a for a in by_alias if a not in done and deps[a] <= done)
        if not ready:
            stuck = sorted(set(by_alias) - done)
            raise SpecError("reference cycle among: " + ", ".join(stuck))
        for a in ready:
            out.append(by_alias[a])
            done.add(a)
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="Validate an rc-org-writer spec.")
    ap.add_argument("spec", type=Path)
    ap.add_argument("--pack", type=Path, default=DEFAULT_PACK)
    args = ap.parse_args()

    if not args.spec.exists():
        print(f"no such spec: {args.spec}", file=sys.stderr)
        return 2

    try:
        doc = parse(args.spec.read_text(encoding="utf-8"))
    except SpecError as exc:
        print(f"[FAIL] {args.spec}")
        print(f"    parse error: {exc}")
        return 1

    target = doc.get("target") or {}
    alias = target.get("org") if isinstance(target, dict) else None
    describe_dir = args.pack / "orgs" / str(alias) / "describe" if alias else None
    if describe_dir is not None and not describe_dir.is_dir():
        print(f"note: no describes for org {alias!r} in the pack; "
              "marking routes cannot be checked.")
        describe_dir = None

    errors, warnings, records = check(doc, describe_dir)

    try:
        planned = order(records) if records else []
    except SpecError as exc:
        errors.append(str(exc))
        planned = []

    marker = doc.get("marker") or {}
    print(f"spec    : {args.spec}")
    print(f"org     : {alias}")
    print(f"marker  : {marker.get('token') if isinstance(marker, dict) else None}")
    print(f"records : {len(records)}")

    if planned and not errors:
        print()
        print("Apply order (dependencies first):")
        for i, rec in enumerate(planned, start=1):
            tier, _ = marking_tier(describe_dir, rec.get("object", ""))
            route = {"1": "key", "2": "Name", "3": "marked_by"}.get(tier, "?")
            print(f"  {i:3d}. {rec['object']:<30s} @{rec['alias']:<22s} marked by {route}")
            for fname, value in (rec.get("fields") or {}).items():
                shown = f"-> @{REFERENCE.match(value).group(1)}" if (
                    isinstance(value, str) and REFERENCE.match(value)
                ) else repr(value)
                print(f"       {fname:28s} {shown}")

    print()
    for e in errors:
        print(f"    error: {e}")
    for w in warnings:
        print(f"    warn:  {w}")
    print()
    print(f"[{'FAIL' if errors else 'ok'}] {len(errors)} error(s), {len(warnings)} warning(s)")
    if not errors:
        print("Valid. This checked the spec, not the org: preview against the org before apply.")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
