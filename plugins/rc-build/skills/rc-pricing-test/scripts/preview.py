"""Preview phase: resolve the spec against the org and read the configuration
back, before anything is written. Read-only.

Three jobs, in order of how much they are worth:

  1. Every lookup resolves to exactly one record, or nothing runs.
  2. The junctions are checked. A product and a selling model can each name a
     real record and still be invalid together: the pair must be joined by a
     ProductSellingModelOption, and priced by a PricebookEntry that names both.
     This is rc-org-writer's shape 2 in its concrete form -- see "The describe
     is not the contract".
  3. The independent reading. The org's own schedule and tier records say what
     the price should be. That reading is printed beside the expectation the
     spec declares, and the two are never reconciled by changing the spec.

Exit codes: 0 the readings agree or there is nothing to contrast, 1 they
disagree or something did not resolve, 2 bad invocation.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import _pricing as P  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description="Preview a pricing test against an org.")
    ap.add_argument("spec", type=Path)
    ap.add_argument("--target-org", required=True)
    args = ap.parse_args()

    if not args.spec.exists():
        P.die(f"no such file: {args.spec}")
    try:
        doc = P.load(args.spec)
    except Exception as exc:
        P.die(str(exc))

    org = args.target_org
    errors: list[str] = []
    notes: list[str] = []
    disagreements: list[str] = []

    print(f"spec {args.spec}")
    print(f"org  {org}")
    print()

    try:
        found, lookup_errors = P.resolve_lookups(org, doc)
    except P.OrgError as exc:
        P.die(str(exc))
    errors.extend(lookup_errors)

    # ---- the account -------------------------------------------------------
    account = doc["account"]
    mode, name = account["mode"], account["name"]
    if mode == "lookup":
        try:
            rows = P.query(org, "SELECT Id, Name FROM Account WHERE Name = "
                                f"{P.soql_literal(name)} LIMIT 2")
        except P.OrgError as exc:
            P.die(str(exc))
        if len(rows) == 1:
            print(f"account   {name!r} found, {rows[0]['Id']} -- a lookup: not marked, "
                  "not modified, not torn down")
            account_id = rows[0]["Id"]
        else:
            account_id = None
            errors.append(f"account {name!r}: {len(rows)} matches, needs exactly one")
    else:
        account_id = None
        print(f"account   {name!r} will be CREATED by this run, and torn down with it")
    print("          a quote takes its account from an opportunity: Quote.AccountId "
          "is createable false, so")
    print("          this run also creates an opportunity on that account, and "
          "deletes it at teardown")
    print()

    # ---- the lines ---------------------------------------------------------
    contrastable = 0
    for line in doc["lines"]:
        alias = line["alias"]
        print(f"line @{alias}")
        prod_alias = P.ref(line["product"])
        psm_alias = P.ref(line["selling_model"])
        book_alias = P.ref(line.get("price_book") or doc.get("price_book") or "")
        product = found.get(prod_alias)
        psm = found.get(psm_alias)
        if product is None or psm is None:
            errors.append(f"line @{alias}: product or selling model did not resolve")
            print("    unresolved; nothing further checked for this line")
            print()
            continue

        book = None
        for lk in doc.get("lookups") or []:
            if lk.get("object") == "Pricebook2" and lk.get("alias") in found:
                book = found[lk["alias"]]
                break
        if book is None:
            errors.append("the spec declares no Pricebook2 lookup; a quote needs one")
            print()
            continue

        try:
            psmo = P.selling_model_option(org, product["id"], psm["id"])
            pbe = P.pricebook_entry(org, book["id"], product["id"], psm["id"])
        except P.OrgError as exc:
            P.die(str(exc))

        if psmo is None:
            errors.append(
                f"line @{alias}: the product is not assigned to that selling model. "
                "The pair is joined by ProductSellingModelOption, an object this spec "
                "never names. This skill reports it and stops; creating the assignment "
                "would change what the catalog can sell.")
            print("    ProductSellingModelOption  MISSING")
        else:
            print(f"    ProductSellingModelOption  {psmo['Id']}"
                  f"{'  (default)' if psmo.get('IsDefault') else ''}")

        if pbe is None:
            errors.append(
                f"line @{alias}: no PricebookEntry for that product, selling model and "
                "price book. The entry is what puts a selling model on a quote line: "
                "QuoteLineItem.ProductSellingModelId is createable false.")
            print("    PricebookEntry             MISSING")
            print()
            continue
        if pbe.get("IsActive") is False:
            errors.append(f"line @{alias}: the PricebookEntry {pbe['Id']} is inactive")
        list_price = pbe.get("UnitPrice")
        print(f"    PricebookEntry             {pbe['Id']}, list {P.money(list_price)}")
        print(f"    quantity                   {line['quantity']}")

        # ---- the independent reading ---------------------------------------
        try:
            tiers = P.applicable_tiers(org, book["id"], product["id"], psm["id"])
        except P.OrgError as exc:
            P.die(str(exc))
        expect = line["expect"]
        want_net = expect.get("net_unit_price")

        if not tiers:
            notes.append(f"line @{alias}: NO CONTRAST -- no active, in-effect volume "
                         "tier covers this product and selling model, so the org "
                         "offers no second reading of the expected price.")
            print("    tiers in effect            none")
            print()
            continue
        tier = P.tier_for_quantity(tiers, float(line["quantity"]))
        bounds = ", ".join(
            f"{t.get('LowerBound')}-{t.get('UpperBound') if t.get('UpperBound') is not None else 'open'}"
            for t in tiers)
        print(f"    tiers in effect            {bounds}  "
              f"(schedule {tiers[0].get('PriceAdjustmentSchedule', {}).get('Name')!r})")
        if tier is None:
            notes.append(f"line @{alias}: NO CONTRAST -- quantity {line['quantity']} "
                         f"falls in no tier ({bounds}).")
            print(f"    quantity {line['quantity']} falls in no tier")
            print()
            continue
        if list_price is None:
            notes.append(f"line @{alias}: NO CONTRAST -- the entry carries no list price.")
            print()
            continue

        computed, why = P.apply_tier(float(list_price), tier)
        contrastable += 1
        print(f"    tier {tier['Id']}         "
              f"{tier.get('LowerBound')}-"
              f"{tier.get('UpperBound') if tier.get('UpperBound') is not None else 'open'}"
              f", {tier.get('TierType')} {tier.get('TierValue')}: {why}")
        print(f"    org says net unit           {P.money(computed)}")
        print(f"    spec expects net unit       {P.money(want_net)}")
        if want_net is None:
            notes.append(f"line @{alias}: the spec declares no net_unit_price, so the "
                         "org's reading stands alone and is not contrasted.")
        elif P.close(computed, want_net):
            print("    the two readings AGREE")
        else:
            disagreements.append(
                f"line @{alias}: the spec expects {P.money(want_net)}; the org's "
                f"configuration reads {P.money(computed)} "
                f"(list {P.money(list_price)}, {why}).")
        print()

    # ---- the verdict -------------------------------------------------------
    for note in notes:
        print(f"note: {note}")
    if notes:
        print()

    if errors:
        for item in errors:
            print(f"error: {item}")
        print()
        print("Nothing was written. Fix the spec or the org and preview again.")
        return 1

    if disagreements:
        for item in disagreements:
            print(f"DISAGREEMENT: {item}")
        print()
        print("STOP. Two independent readings of this price disagree, and that is the")
        print("finding -- do not run. Editing the expected number so that it matches the")
        print("org's reading deletes the test: it would then confirm the configuration")
        print("against itself. Resolve which reading is right first, in the open.")
        return 1

    if contrastable:
        print(f"{contrastable} line(s) contrasted against the org's own configuration, "
              "and the readings agree.")
    else:
        print("NO CONTRAST was available for any line. The run can still go ahead, and "
              "its report will say that nothing checked the expectation in advance.")
    print("Confirm, then run with run.py --confirm.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
