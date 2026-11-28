"""Run phase: create the account if the spec says to, the opportunity, the quote
and its lines, and price them. Writes to the org, and only with --confirm.

Everything it creates goes in the log, one line per record, written immediately
after the record exists and never for a create that returned no Id. Teardown
believes the log, so a log that lies is worse than no log at all.

One thing here is particular to this API and worth knowing before reading the
code. The Place Sales Transaction call can come back with isSuccess false AND a
salesTransactionId -- the quote was saved and then the pricing step refused it.
A failed run can therefore leave a quote behind, so the transaction is logged
whenever an Id came back, success or not.

Usage:
    python3 run.py <spec.yaml> --target-org <alias> --log <run.jsonl> --confirm

Exit codes: 0 priced, 1 refused or failed, 2 bad invocation.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import _pricing as P  # noqa: E402

POLL_SECONDS = 3
POLL_LIMIT = 40


def main() -> int:
    ap = argparse.ArgumentParser(description="Run a pricing transaction.")
    ap.add_argument("spec", type=Path)
    ap.add_argument("--target-org", required=True)
    ap.add_argument("--log", type=Path, required=True)
    ap.add_argument("--confirm", action="store_true",
                    help="required; without it nothing is written")
    args = ap.parse_args()

    if not args.spec.exists():
        P.die(f"no such file: {args.spec}")
    if not args.confirm:
        P.die("refusing to write without --confirm. Run preview.py first and put its "
              "output in front of a person.")
    if args.log.exists() and args.log.stat().st_size:
        P.die(f"{args.log} already holds a run. Use a new log file, or tear the old "
              "run down first: one log, one run.")

    try:
        doc = P.load(args.spec)
    except Exception as exc:
        P.die(str(exc))

    org = args.target_org
    log = args.log
    try:
        version = P.org_io.api_version(org)
        found, errors = P.resolve_lookups(org, doc)
    except P.OrgError as exc:
        P.die(str(exc))
    if errors:
        for item in errors:
            print(f"error: {item}", file=sys.stderr)
        P.die("lookups did not resolve; nothing written")

    for alias, row in found.items():
        P.log_append(log, {"kind": "lookup", "alias": alias, "object": row["object"],
                           "id": row["id"], "where": row["where"]})

    print(f"org {org}, API v{version}")

    # ---- account -----------------------------------------------------------
    account = doc["account"]
    name = account["name"]
    try:
        if account["mode"] == "lookup":
            rows = P.query(org, "SELECT Id FROM Account WHERE Name = "
                                f"{P.soql_literal(name)} LIMIT 2")
            if len(rows) != 1:
                P.die(f"account {name!r}: {len(rows)} matches, needs exactly one")
            account_id = rows[0]["Id"]
            P.log_append(log, {"kind": "lookup", "alias": "account",
                               "object": "Account", "id": account_id,
                               "where": {"Name": name}})
            print(f"account      {account_id}  (pre-existing, will not be torn down)")
        else:
            account_id = P.org_io.create(org, version, "Account", {"Name": name})
            P.log_append(log, {"kind": "created", "alias": "account",
                               "object": "Account", "id": account_id})
            print(f"account      {account_id}  created")

        opp_name = f"{doc['marker']['token']} pricing test"
        opp_id = P.org_io.create(org, version, "Opportunity", {
            "Name": opp_name,
            "StageName": doc.get("opportunity_stage") or "Prospecting",
            "CloseDate": doc.get("opportunity_close_date") or "2099-12-31",
            "AccountId": account_id,
        })
        P.log_append(log, {"kind": "created", "alias": "opportunity",
                           "object": "Opportunity", "id": opp_id})
        print(f"opportunity  {opp_id}  created")
    except P.OrgError as exc:
        print(f"error: {P.unescape(str(exc))}", file=sys.stderr)
        print("Stopped at the first failure. Tear down what the log holds.", file=sys.stderr)
        return 1

    # ---- the graph ---------------------------------------------------------
    book = next((found[lk["alias"]] for lk in doc.get("lookups") or []
                 if lk.get("object") == "Pricebook2" and lk.get("alias") in found), None)
    if book is None:
        P.die("the spec declares no Pricebook2 lookup")

    records = [{"referenceId": "refQuote", "record": {
        "attributes": {"type": "Quote", "method": "POST"},
        "Name": f"{doc['marker']['token']} pricing test",
        "OpportunityId": opp_id,
        "Pricebook2Id": book["id"]}}]

    for i, line in enumerate(doc["lines"]):
        product = found[P.ref(line["product"])]
        psm = found[P.ref(line["selling_model"])]
        try:
            pbe = P.pricebook_entry(org, book["id"], product["id"], psm["id"])
        except P.OrgError as exc:
            P.die(str(exc))
        if pbe is None:
            P.die(f"line @{line['alias']}: no PricebookEntry; preview would have "
                  "caught this. Tear down what the log holds.")
        record = {
            "attributes": {"type": "QuoteLineItem", "method": "POST"},
            "QuoteId": "@{refQuote.id}",
            "Product2Id": product["id"],
            "PricebookEntryId": pbe["Id"],
            "Quantity": float(line["quantity"]),
        }
        # PLATFORM (v68, observed): pricing refuses a line with neither an end date
        # nor a subscription term, and refuses a dated line with no period boundary,
        # although a describe marks all three nillable. A term-defined or evergreen
        # selling model also refuses a line with no billing frequency.
        for spec_key, field in (("start_date", "StartDate"), ("end_date", "EndDate"),
                                ("period_boundary", "PeriodBoundary"),
                                ("billing_frequency", "BillingFrequency")):
            if line.get(spec_key) not in (None, ""):
                record[field] = line[spec_key]
        records.append({"referenceId": f"refLine{i}", "record": record})

    body = {"pricingPref": "Force", "graph": {"graphId": "rcPricingTest",
                                              "records": records}}

    print(f"placing a sales transaction with {len(doc['lines'])} line(s)")
    try:
        reply = P.place(org, version, body)
    except P.OrgError as exc:
        print(f"error: {P.unescape(str(exc))}", file=sys.stderr)
        return 1

    quote_id = reply.get("salesTransactionId") or ""
    if quote_id:
        P.log_append(log, {"kind": "created", "alias": "quote", "object": "Quote",
                           "id": quote_id})
        print(f"quote        {quote_id}  created")

    if not reply.get("isSuccess"):
        print()
        for err in reply.get("errorResponse") or []:
            code = err.get("errorCode", "")
            print(f"REFUSED {code}: {P.unescape(err.get('message', ''))}"
                  f"  (reference {err.get('referenceId')})", file=sys.stderr)
        print()
        if quote_id:
            print("A quote was saved before the refusal and is in the log. Tear it "
                  "down.", file=sys.stderr)
        else:
            print("No quote was saved.", file=sys.stderr)
        print("The platform's sentence above is the documentation for a rule that "
              "may have none. Record it in notes/.", file=sys.stderr)
        return 1

    # ---- wait for pricing to finish ---------------------------------------
    status = None
    for _ in range(POLL_LIMIT):
        try:
            rows = P.query(org, "SELECT CalculationStatus FROM Quote "
                                f"WHERE Id = '{quote_id}'")
        except P.OrgError as exc:
            P.die(str(exc))
        status = rows[0]["CalculationStatus"] if rows else None
        if status and (status in P.TERMINAL
                       or status.startswith(P.TERMINAL_PREFIXES)):
            break
        time.sleep(POLL_SECONDS)
    print(f"CalculationStatus {status!r}")
    P.log_append(log, {"kind": "transaction", "alias": "quote", "object": "Quote",
                       "id": quote_id, "calculation_status": status})

    if status and "Failed" in status:
        print("The quote exists and its pricing failed. compare.py will still read "
              "it back; what it reports is a finding, not an error to retry.",
              file=sys.stderr)
        return 1
    print("Priced. Run compare.py next, then teardown.py --confirm.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
