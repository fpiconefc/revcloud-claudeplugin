"""Compare phase: read back what the engine did and set it beside what the spec
declared. Read-only.

It reports and does not judge. Every number it prints is followed by the record
it came from and that record's Id, so a disagreement can be checked by hand
without rerunning anything. It never proposes a cause: a FAIL has at least
three readings and this script cannot tell them apart.

Two sources are read for each line, and they are different claims:

  QuoteLineItem      what the line is priced at now -- ListPrice against
                     NetUnitPrice is where an adjustment shows up as money
  QuoteLinePriceAdjustment
                     the itemised record of why. PLATFORM (v68, observed): an
                     org priced a line 10% below list and wrote no adjustment
                     row at all, so an empty result here does not mean no
                     adjustment was applied. It is reported as its own line.

Usage:
    python3 compare.py <spec.yaml> --target-org <alias> --log <run.jsonl>

Exit codes: 0 every declared expectation was met, 1 at least one was not,
2 bad invocation.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import _pricing as P  # noqa: E402

FIELD = {"net_unit_price": "NetUnitPrice", "total_price": "TotalPrice",
         "list_price": "ListPrice", "quantity": "Quantity"}


def main() -> int:
    ap = argparse.ArgumentParser(description="Compare a priced quote to the spec.")
    ap.add_argument("spec", type=Path)
    ap.add_argument("--target-org", required=True)
    ap.add_argument("--log", type=Path, required=True)
    args = ap.parse_args()

    for path in (args.spec, args.log):
        if not path.exists():
            P.die(f"no such file: {path}")
    try:
        doc = P.load(args.spec)
        rows = P.log_read(args.log)
    except Exception as exc:
        P.die(str(exc))

    org = args.target_org
    quote = next((r for r in rows if r.get("object") == "Quote" and r.get("id")), None)
    if quote is None:
        P.die("the log holds no quote; there is nothing to compare")
    quote_id = quote["id"]
    status = next((r.get("calculation_status") for r in rows
                   if r.get("kind") == "transaction"), None)
    ids = {r["alias"]: r["id"] for r in rows if r.get("alias") and r.get("id")}

    try:
        lines = P.query(org,
            "SELECT Id, Product2Id, ProductSellingModelId, Quantity, ListPrice, "
            "UnitPrice, NetUnitPrice, TotalPrice, TotalLineAmount, StartDate, EndDate "
            f"FROM QuoteLineItem WHERE QuoteId = '{quote_id}' ORDER BY Id")
        adjustments = P.query(org,
            "SELECT Id, QuoteLineItemId, AdjustmentSource, AdjustmentType, "
            "AdjustmentValue, TotalAmount, AppliedAdjustmentAmount, Priority, "
            "PriceAdjustmentCauseId FROM QuoteLinePriceAdjustment "
            f"WHERE QuoteLineItem.QuoteId = '{quote_id}'")
    except P.OrgError as exc:
        P.die(str(exc))

    print(f"org   {org}")
    print(f"quote {quote_id}   CalculationStatus {status!r}")
    print(f"      {len(lines)} line(s) read back, {len(adjustments)} "
          "QuoteLinePriceAdjustment row(s)")
    print()

    by_product: dict[str, list[dict]] = {}
    for row in lines:
        by_product.setdefault(row["Product2Id"], []).append(row)

    failures: list[str] = []
    unmatched = 0

    for spec_line in doc["lines"]:
        alias = spec_line["alias"]
        product_id = ids.get(P.ref(spec_line["product"]))
        candidates = by_product.get(product_id or "", [])
        row = next((r for r in candidates
                    if P.close(r.get("Quantity"), spec_line["quantity"], 0.0001)), None)
        print(f"line @{alias}")
        if row is None:
            unmatched += 1
            failures.append(f"@{alias}: no quote line came back for that product and "
                            "quantity")
            print("    no line in the org matches this spec line")
            print()
            continue

        print(f"    QuoteLineItem           {row['Id']}")
        print(f"    quantity                {row.get('Quantity')}")
        print(f"    ListPrice               {P.money(row.get('ListPrice'))}")
        print(f"    NetUnitPrice            {P.money(row.get('NetUnitPrice'))}")
        print(f"    TotalPrice              {P.money(row.get('TotalPrice'))}")

        mine = [a for a in adjustments if a.get("QuoteLineItemId") == row["Id"]]
        if mine:
            for a in mine:
                print(f"    QuoteLinePriceAdjustment {a['Id']}  "
                      f"{a.get('AdjustmentType')} {a.get('AdjustmentValue')}, "
                      f"total {P.money(a.get('TotalAmount'))}, "
                      f"cause {a.get('PriceAdjustmentCauseId')}")
        else:
            moved = (row.get("ListPrice") is not None
                     and row.get("NetUnitPrice") is not None
                     and not P.close(row["ListPrice"], row["NetUnitPrice"]))
            print("    QuoteLinePriceAdjustment none" + (
                "  -- and the net price differs from list, so an adjustment was "
                "applied without an itemised record" if moved else
                "  -- and the net price equals list"))

        for key, want in (spec_line["expect"] or {}).items():
            field = FIELD.get(key)
            if field is None:
                print(f"    ? expect.{key} is not a field this skill reads back")
                continue
            have = row.get(field)
            if P.close(have, want):
                print(f"    MET      {key}: expected {P.money(want)}, "
                      f"{field} is {P.money(have)}")
            else:
                failures.append(f"@{alias} {key}: expected {P.money(want)}, "
                                f"{field} came back {P.money(have)} "
                                f"(QuoteLineItem {row['Id']})")
                print(f"    NOT MET  {key}: expected {P.money(want)}, "
                      f"{field} is {P.money(have)}")
        print()

    if not failures:
        print("PASS. Every expectation the spec declared was met by the records read "
              "back above.")
        print("That is a statement about this org on this day, not about the product.")
        return 0

    print("FAIL")
    for item in failures:
        print(f"    {item}")
    print()
    print("A FAIL has at least three readings and nothing here can tell them apart:")
    print()
    print("  1. the expectation was wrong -- the policy says something other than")
    print("     what the person believed it said")
    print("  2. the configuration is wrong -- the records exist but do not express")
    print("     the policy, which is rc-pricing-adjustments' territory")
    print("  3. the configuration is right and the engine did something else, for a")
    print("     reason nobody here knows yet")
    print()
    print("The third is the valuable one and it is a new entry for notes/, with the")
    print("quote Id above so somebody can look at it. Do not edit the expectation to")
    print("make this pass: that converts a finding into a green light.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
