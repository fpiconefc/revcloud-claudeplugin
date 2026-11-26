"""Shared plumbing for the apply, verify and teardown phases.

Not a phase itself and not run directly. It holds the three things all of them
need: talking to an org through the `sf` CLI, reading and writing the run log,
and resolving `@alias` references to Ids. No third-party dependencies; `sf` is
invoked as a subprocess with `--json` so Ids can be captured.

The log is JSONL, one line per record, appended and flushed as it happens. Each
line carries a `kind`:

    {"kind": "lookup",  "alias": ..., "object": ..., "id": ..., "where": {...}}
    {"kind": "created", "alias": ..., "object": ..., "id": ..., "marker": ...}

Both kinds are recorded, because verify and teardown need to know which Id a
lookup resolved to and must never re-resolve the key. Only `created` rows are
ever deleted: teardown filters on the kind, which is what keeps a looked-up
record out of reach.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

TIMEOUT = 120


class OrgError(Exception):
    pass


# --------------------------------------------------------------- sf calls ---

def _run(args: list[str]) -> dict:
    try:
        proc = subprocess.run(args, capture_output=True, text=True, timeout=TIMEOUT)
    except FileNotFoundError:
        raise OrgError("the Salesforce CLI (`sf`) is not on PATH")
    except subprocess.TimeoutExpired:
        raise OrgError(f"timed out after {TIMEOUT}s: {' '.join(args[:4])}")
    out = proc.stdout.strip()
    if not out:
        raise OrgError(proc.stderr.strip() or f"no output from {' '.join(args[:4])}")
    try:
        payload = json.loads(out)
    except json.JSONDecodeError:
        raise OrgError(f"non-JSON reply: {out[:300]}")
    # A failure from the CLI is still valid JSON. Treating "it parsed" as "it
    # worked" is how a teardown reports deletions that never happened.
    if isinstance(payload, dict):
        status = payload.get("status")
        if (status not in (0, None)) or payload.get("name") == "SfError":
            raise OrgError(_message(payload))
    return payload


def _errors(node) -> list[str]:
    """Pull Salesforce's own error sentences out of whatever shape they arrived in.

    These sentences are the documentation for rules no describe expresses, so they
    are worth surfacing verbatim rather than burying in an HTTP envelope.
    """
    found: list[str] = []
    if isinstance(node, list):
        for item in node:
            found.extend(_errors(item))
    elif isinstance(node, dict):
        message = node.get("message")
        if isinstance(message, str):
            code = node.get("errorCode")
            fields = node.get("fields")
            text = message
            if code and code not in message:
                text = f"{code}: {message}"
            if fields:
                text += f" (fields: {', '.join(fields)})"
            found.append(text)
        for key in ("body", "result", "data", "errors"):
            if key in node:
                found.extend(_errors(node[key]))
    return found


def _message(payload: dict) -> str:
    """The most useful error string the CLI gave us."""
    found = _errors(payload)
    if found:
        return " | ".join(dict.fromkeys(found))
    if isinstance(payload.get("name"), str):
        return payload["name"]
    return json.dumps(payload)[:300]


def api_version(org: str) -> str:
    payload = _run(["sf", "org", "display", "--target-org", org, "--json"])
    version = (payload.get("result") or {}).get("apiVersion")
    if not version:
        raise OrgError("could not read the org's API version")
    return str(version)


def query(org: str, soql: str) -> list[dict]:
    payload = _run(["sf", "data", "query", "--query", soql,
                    "--target-org", org, "--json"])
    if payload.get("status") not in (0, None):
        raise OrgError(_message(payload))
    return (payload.get("result") or {}).get("records") or []


def create(org: str, version: str, obj: str, fields: dict) -> str:
    """Create one record and return its Id. Raises OrgError with the platform's
    own message, which is where the validation rules no describe expresses show up."""
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as fh:
        json.dump(fields, fh)
        body = fh.name
    try:
        payload = _run([
            "sf", "api", "request", "rest",
            f"/services/data/v{version}/sobjects/{obj}",
            "--method", "POST", "--body", "@" + body,
            "--target-org", org, "--json",
        ])
    finally:
        Path(body).unlink(missing_ok=True)

    for node in (payload.get("result"), payload.get("body"), payload):
        candidate = node
        if isinstance(candidate, dict) and "body" in candidate:
            candidate = candidate["body"]
        if isinstance(candidate, list) and candidate:
            candidate = candidate[0]
        if (isinstance(candidate, dict) and candidate.get("id")
                and candidate.get("success") is not False):
            return str(candidate["id"])
    raise OrgError(_message(payload))


def delete(org: str, version: str, obj: str, record_id: str) -> str:
    """Delete one record. Returns 'deleted' or 'already gone'.

    Uses `sf data delete record` rather than a REST DELETE: the REST subcommand
    refuses a request with no body mode, and its refusal is valid JSON, so an
    earlier version reported deletions that never reached the org.

    Success is confirmed from the reply, never assumed.
    """
    try:
        payload = _run([
            "sf", "data", "delete", "record",
            "--sobject", obj, "--record-id", record_id,
            "--target-org", org, "--json",
        ])
    except OrgError as exc:
        # Normalise so "ENTITY_IS_DELETED" and "entity is deleted" both match:
        # the platform uses both spellings for the same condition.
        text = str(exc).upper().replace("_", " ")
        if any(token in text for token in
               ("NOT FOUND", "ENTITY IS DELETED", "INVALID CROSS REFERENCE KEY",
                "ALREADY BEEN DELETED", "404")):
            return "already gone"
        raise
    result = payload.get("result")
    if isinstance(result, list) and result:
        result = result[0]
    if isinstance(result, dict) and result.get("success") is True:
        return "deleted"
    raise OrgError(f"delete of {obj} {record_id} was not confirmed: {_message(payload)}")


# ------------------------------------------------------------------- log ---

def log_append(path: Path, entry: dict) -> None:
    """One line, flushed before returning. The window this leaves is one record
    wide and is documented in SKILL.md; it is not closed here."""
    entry.setdefault("at", datetime.now(timezone.utc).isoformat())
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, sort_keys=True) + "\n")
        fh.flush()


def log_read(path: Path) -> list[dict]:
    if not path.exists():
        return []
    rows = []
    for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            raise OrgError(f"{path}: line {n} is not JSON")
    return rows


def created_rows(rows: list[dict]) -> list[dict]:
    return [r for r in rows if r.get("kind") == "created" and r.get("id")]


def lookup_rows(rows: list[dict]) -> list[dict]:
    return [r for r in rows if r.get("kind") == "lookup" and r.get("id")]


# ------------------------------------------------------------ references ---

def resolve(value, ids: dict[str, str]):
    """Replace an `@alias` with the Id it resolved to. Other values pass through."""
    if isinstance(value, str) and value.startswith("@"):
        alias = value[1:]
        if alias not in ids:
            raise OrgError(f"@{alias} has no resolved Id yet")
        return ids[alias]
    return value


# ------------------------------------------------------------- datetimes ---

def same_instant(a, b) -> bool:
    """Compare two datetime strings by value, not by text.

    The platform returns `2027-01-01T00:00:00.000+0000` for what was sent as
    `2027-01-01T00:00:00.000Z`. Same instant, different string; a literal
    comparison reports a difference that is not one.
    """
    pa, pb = _parse_dt(a), _parse_dt(b)
    if pa is None or pb is None:
        return False
    return pa == pb


def _parse_dt(value):
    if not isinstance(value, str):
        return None
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    elif len(text) > 5 and (text[-5] in "+-") and ":" not in text[-5:]:
        text = text[:-2] + ":" + text[-2:]
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def die(message: str) -> None:
    print(f"error: {message}", file=sys.stderr)
    raise SystemExit(1)
