"""Shared plumbing for rc-pricing-test. Not run directly.

Holds three things the four phases must agree on, so they cannot drift:

  * the spec shape, parsed by rc-org-writer's parser rather than a second one
  * the org lookups a pricing transaction needs, including the two junction
    objects that join a product to a selling model and to a price
  * the independent reading: what the org's own configuration says the price
    should be, computed from the schedule and tier records rather than from
    what the person expects

The independent reading is the point of the skill. It is a second source, not
a substitute for the expectation in the spec, and nothing here ever rewrites
an expectation to match it.
"""

from __future__ import annotations

import datetime as _dt
import json
import re
import sys
from pathlib import Path

_WRITER = Path(__file__).resolve().parents[4] / "rc-core/skills/rc-org-writer/scripts"
if not (_WRITER / "_orgio.py").exists():
    print("error: rc-org-writer is not installed beside this plugin; it owns the sf "
          f"plumbing, the run log and the YAML parser. Looked in {_WRITER}",
          file=sys.stderr)
    raise SystemExit(2)
sys.path.insert(0, str(_WRITER))

import _orgio as org_io          # noqa: E402
from validate_spec import SpecError, parse as _parse  # noqa: E402

OrgError = org_io.OrgError
query = org_io.query
die = org_io.die

SPEC_VERSION = "rc-pricing-test/v1"
LIST_SECTIONS = ("lookups", "lines")
SECTION_KEYS = {
    "lookups": {"alias", "object", "where"},
    "lines": {"alias", "product", "selling_model", "quantity", "start_date",
              "end_date", "period_boundary", "billing_frequency", "expect"},
}
REQUIRED_META = ("target", "author", "created", "purpose", "marker", "account")
REFERENCE = re.compile(r"^@([A-Za-z_][A-Za-z0-9_]*)$")

# Terminal values of Quote.CalculationStatus. PLATFORM (v68, observed): an org
# returned CompletedWithTax, which its own describe does not list, so the set is
# matched by prefix as well as by membership.
TERMINAL = {"CompletedWithPricing", "CompletedWithoutPricing", "CompletedWithTax",
            "PriceCalculationFailed", "SaveFailedOrIncomplete", "TaxCalculationFailed"}
TERMINAL_PREFIXES = ("Completed", "Failed")


# ------------------------------------------------------------------ spec ---

def load(path: Path) -> dict:
    doc = _parse(path.read_text(encoding="utf-8"), LIST_SECTIONS, SECTION_KEYS)
    if doc.get("spec") != SPEC_VERSION:
        raise SpecError(f"spec must be {SPEC_VERSION!r}, got {doc.get('spec')!r}")
    for key in REQUIRED_META:
        if not doc.get(key):
            raise SpecError(f"the spec has no {key!r} section")
    account = doc["account"]
    mode = account.get("mode")
    if mode not in ("lookup", "create"):
        raise SpecError("account.mode must be 'lookup' or 'create'")
    if not account.get("name"):
        raise SpecError("account.name is required")
    token = (doc.get("marker") or {}).get("token")
    if not token:
        raise SpecError("marker.token is required; a created account carries it")
    if mode == "create" and token not in str(account["name"]):
        raise SpecError(
            f"account.name must contain the marker token {token!r} when mode is "
            "'create', so a leftover account is identifiable as this run's")
    placeholders = sorted(_placeholders(doc))
    if placeholders:
        raise SpecError(
            "the spec still carries values from the example that have to be replaced: "
            + ", ".join(placeholders)
            + ". They belong to an org you do not have.")
    if not doc.get("lines"):
        raise SpecError("the spec creates no lines; there is nothing to price")
    for line in doc["lines"]:
        for key in ("alias", "product", "selling_model", "quantity"):
            if line.get(key) in (None, ""):
                raise SpecError(f"line @{line.get('alias', '?')}: {key} is required")
        if not isinstance(line.get("expect"), dict) or not line["expect"]:
            raise SpecError(
                f"line @{line['alias']}: no `expect` block. A run with nothing "
                "declared in advance is not a test.")
    return doc


PLACEHOLDER = re.compile(r"^<[^<>]+>$")


def _placeholders(node) -> set:
    """Values still in the example's <ANGLE-BRACKET> form. Catching them here
    turns a confusing disagreement at preview into a sentence that says what to
    replace."""
    found = set()
    if isinstance(node, dict):
        for value in node.values():
            found |= _placeholders(value)
    elif isinstance(node, list):
        for item in node:
            found |= _placeholders(item)
    elif isinstance(node, str) and PLACEHOLDER.match(node.strip()):
        found.add(node.strip())
    return found


def ref(value):
    """The alias a spec value points at, or None if it is a literal."""
    if isinstance(value, str):
        m = REFERENCE.match(value)
        if m:
            return m.group(1)
    return None


# ---------------------------------------------------------------- org io ---

def soql_literal(value) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    return "'" + str(value).replace("\\", "\\\\").replace("'", "\\'") + "'"


def resolve_lookups(org: str, doc: dict) -> tuple[dict, list[str]]:
    """Every lookup must resolve to exactly one record. Nothing is created here."""
    found: dict[str, dict] = {}
    errors: list[str] = []
    for lk in doc.get("lookups") or []:
        alias, obj = lk.get("alias"), lk.get("object")
        where = lk.get("where") or {}
        if not (alias and obj and where):
            errors.append(f"lookup @{alias}: needs object and a where clause")
            continue
        clause = " AND ".join(f"{k} = {soql_literal(v)}" for k, v in where.items())
        rows = query(org, f"SELECT Id FROM {obj} WHERE {clause} LIMIT 2")
        if len(rows) == 1:
            found[alias] = {"id": rows[0]["Id"], "object": obj, "where": where}
        elif not rows:
            errors.append(f"lookup @{alias}: no {obj} matches {clause}")
        else:
            errors.append(f"lookup @{alias}: more than one {obj} matches {clause}; "
                          "there is no 'pick the first' here")
    return found, errors


def selling_model_option(org: str, product_id: str, psm_id: str):
    """ProductSellingModelOption joins the two. Neither lookup is wrong without it."""
    rows = query(org, "SELECT Id, IsDefault FROM ProductSellingModelOption "
                      f"WHERE Product2Id = '{product_id}' "
                      f"AND ProductSellingModelId = '{psm_id}' LIMIT 2")
    return rows[0] if rows else None


def pricebook_entry(org: str, book_id: str, product_id: str, psm_id: str):
    """The entry carries the list price AND the selling model: QuoteLineItem's own
    ProductSellingModelId is createable false, so choosing the entry is how a line
    gets a selling model at all."""
    rows = query(org, "SELECT Id, UnitPrice, IsActive FROM PricebookEntry "
                      f"WHERE Pricebook2Id = '{book_id}' "
                      f"AND Product2Id = '{product_id}' "
                      f"AND ProductSellingModelId = '{psm_id}' LIMIT 2")
    return rows[0] if rows else None


def applicable_tiers(org: str, book_id: str, product_id: str, psm_id: str) -> list[dict]:
    """Volume tiers the org's own configuration says apply to this pair today."""
    rows = query(org,
        "SELECT Id, LowerBound, UpperBound, TierType, TierValue, EffectiveFrom, "
        "EffectiveTo, PriceAdjustmentScheduleId, PriceAdjustmentSchedule.Name, "
        "PriceAdjustmentSchedule.ScheduleType, PriceAdjustmentSchedule.IsActive "
        "FROM PriceAdjustmentTier "
        f"WHERE Product2Id = '{product_id}' "
        f"AND ProductSellingModelId = '{psm_id}' "
        f"AND PriceAdjustmentSchedule.Pricebook2Id = '{book_id}' "
        "ORDER BY LowerBound")
    now = _dt.datetime.now(_dt.timezone.utc)
    live = []
    for r in rows:
        schedule = r.get("PriceAdjustmentSchedule") or {}
        if schedule.get("IsActive") is False:
            continue
        if _after(now, r.get("EffectiveFrom")) and _before(now, r.get("EffectiveTo")):
            live.append(r)
    return live


def _after(now, value) -> bool:
    dt = org_io._parse_dt(value) if value else None
    return dt is None or now >= dt


def _before(now, value) -> bool:
    dt = org_io._parse_dt(value) if value else None
    return dt is None or now < dt


def tier_for_quantity(tiers: list[dict], quantity) -> dict | None:
    """Bounds are inclusive at BOTH ends -- PLATFORM (v68, observed): the platform
    refuses two tiers that share a bound, so a shared value belongs to the lower
    tier. rc-pricing-adjustments Trap 1 has the evidence."""
    for t in tiers:
        low, high = t.get("LowerBound"), t.get("UpperBound")
        if low is not None and quantity < low:
            continue
        if high is not None and quantity > high:
            continue
        return t
    return None


def apply_tier(list_price: float, tier: dict) -> tuple[float, str]:
    """What the tier does to the list price, and the sentence that says why."""
    kind, value = tier.get("TierType"), tier.get("TierValue")
    if kind == "AdjustmentPercentage":
        return list_price * (1 - float(value) / 100), f"{value}% off list"
    if kind == "AdjustmentAmount":
        return list_price - float(value), f"{value} off list"
    if kind == "OverrideAmount":
        return float(value), f"list replaced by {value}"
    return list_price, f"TierType {kind!r} is not one this skill computes"


def close(a, b, tolerance=0.005) -> bool:
    try:
        return abs(float(a) - float(b)) <= tolerance
    except (TypeError, ValueError):
        return False


def money(value) -> str:
    return "none" if value is None else f"{float(value):,.2f}"


# ------------------------------------------------------------------- log ---

def log_append(path: Path, entry: dict) -> None:
    org_io.log_append(path, entry)


def log_read(path: Path) -> list[dict]:
    return org_io.log_read(path)


def unescape(text: str) -> str:
    """The platform HTML-escapes apostrophes in some refusals; the sentence is
    the documentation, so it is reported as written rather than as encoded."""
    import html
    return html.unescape(text or "")


def place(org: str, version: str, body: dict) -> dict:
    """Place Sales Transaction. Returns the parsed reply; the caller decides what
    a reply with isSuccess false means, because such a reply can still have
    created a quote."""
    import subprocess
    import tempfile
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as fh:
        json.dump(body, fh)
        tmp = fh.name
    try:
        proc = subprocess.run(
            ["sf", "api", "request", "rest",
             f"/services/data/v{version}/connect/rev/sales-transaction/actions/place",
             "--method", "POST", "--body", "@" + tmp, "--target-org", org],
            capture_output=True, text=True, timeout=300)
    finally:
        Path(tmp).unlink(missing_ok=True)
    out = (proc.stdout or "").strip()
    if not out:
        raise OrgError(proc.stderr.strip() or "no reply from the place API")
    try:
        return json.loads(out)
    except json.JSONDecodeError:
        raise OrgError(f"non-JSON reply from the place API: {out[:300]}")
