"""
Redundancy Check — Manual Test
================================
Sends two test tickets against a running redundancy-check service.

Test Case 1 (expect DISCARD):
  Same question, same answer as existing ticket CASE-01070.
  → Should be detected as redundant and NOT inserted.

Test Case 2 (expect POST):
  Same question, but assistant answer reflects a NEW policy
  → Should be detected as new and inserted into ticket_db.

Usage:
  python test_redundancy_check.py [--url http://localhost:8080]
"""

import requests
import json
import argparse
import os
from dotenv import load_dotenv
load_dotenv()

ASTRA_ENDPOINT = os.getenv("ASTRA_DB_ENDPOINT")
ASTRA_TOKEN    = os.getenv("ASTRA_DB_TOKEN")
COLLECTION     = "ticket_db"

TEST_TITLES = ["CASE-TEST-DUPLICATE", "CASE-TEST-REPHRASED", "CASE-TEST-NEW-POLICY"] 

BASE_URL = "http://localhost:8080"  # override with --url


# ─────────────────────────────────────────
# Existing ticket in DB (CASE-01070) for reference
# ─────────────────────────────────────────
# user_turn_1:      "How can I view the current overtime policy for part-time employees?
#                    I tried accessing it via the intranet but got an error message."
# assistant_turn_1: "Sorry for the confusion. The document is only available to users
#                    with administrator rights. Please contact IT-Support to have your
#                    access permissions reviewed. Alternatively, you can try to locate
#                    a summary of the document on the general HR portal, although the
#                    full version is not displayed there."


# ─────────────────────────────────────────
# Test Case 1: DISCARD expected
# Identical question + identical answer → redundant
# ─────────────────────────────────────────
TICKET_DUPLICATE = {
    "title": "CASE-TEST-DUPLICATE",
    "intent": "troubleshooting",
    "issue_type": "access_denied",
    "severity": "S2",
    "urgency": "low",
    "language": "de-CH",
    "persona_role": "manager",
    "persona_access_tier": "privileged",
    "gold_doc_ids": "DOC-OT-2025-CH-01",
    "user_turn_1": "How can I view the current overtime policy for part-time employees? I tried accessing it via the intranet but got an error message.",
    "assistant_turn_1": "Sorry for the confusion. The document is only available to users with administrator rights. Please contact IT-Support to have your access permissions reviewed. Alternatively, you can try to locate a summary of the document on the general HR portal, although the full version is not displayed there.",
    "vectorize_text": "How can I view the current overtime policy for part-time employees? I tried accessing it via the intranet but got an error message."
}


# ─────────────────────────────────────────
# Test Case 2: DISCARD expected
# Identical question + rephrased assistant answer → redundant
# ─────────────────────────────────────────
TICKET_REPHRASED = {
    "title": "CASE-TEST-REPHRASED",
    "intent": "troubleshooting",
    "issue_type": "access_denied",
    "severity": "S2",
    "urgency": "low",
    "language": "de-CH",
    "persona_role": "manager",
    "persona_access_tier": "privileged",
    "gold_doc_ids": "DOC-OT-2025-CH-01",
    "user_turn_1": "How can I view the current overtime policy for part-time employees? I tried accessing it via the intranet but got an error message.",
    "assistant_turn_1": "The current overtime policy for part-time employees can only be accessed by users with administrator privileges. Since you received an error on the intranet, please reach out to IT Support to check your permissions.",
    "vectorize_text": "How can I view the current overtime policy for part-time employees? I tried accessing it via the intranet but got an error message."
}


# ─────────────────────────────────────────
# Test Case 3: POST expected
# Same question, but new policy update:
# - Document is now accessible to all employees via updated HR portal (no admin rights needed)
# - Old workaround (IT-Support contact) is no longer required
# ─────────────────────────────────────────
TICKET_NEW_POLICY = {
    "title": "CASE-TEST-NEW-POLICY",
    "intent": "troubleshooting",
    "issue_type": "access_denied",
    "severity": "S2",
    "urgency": "low",
    "language": "de-CH",
    "persona_role": "manager",
    "persona_access_tier": "privileged",
    "gold_doc_ids": "DOC-OT-2025-CH-02",   # updated policy document
    "user_turn_1": "How can I view the current overtime policy for part-time employees? I tried accessing it via the intranet but got an error message.",
    "assistant_turn_1": "As of the latest HR portal update (June 2025), the overtime policy document for part-time employees is now accessible to all staff directly via the HR portal under Policies > Working Hours > Overtime. No administrator rights are required. If you still encounter an error, please clear your browser cache and try again.",
    "vectorize_text": "How can I view the current overtime policy for part-time employees? I tried accessing it via the intranet but got an error message."
}


def run_test(label: str, ticket: dict, expected: str) -> bool:
    print(f"\n{'='*60}")
    print(f"Test: {label}")
    print(f"Expected decision: {expected}")
    print(f"{'='*60}")

    try:
        res = requests.post(f"{BASE_URL}/redundancy-check", json=ticket, timeout=30)
        res.raise_for_status()
        result = res.json()
    except Exception as e:
        print(f"[ERROR] Request failed: {e}")
        return False

    decision     = result.get("decision")
    matched_id   = result.get("matched_ticket_id")
    reason       = result.get("reason")
    llm_checked  = result.get("llm_checked")
    scores       = result.get("similarity_scores", [])

    print(f"\nDecision:    {decision}  {'✓' if decision == expected else '✗ UNEXPECTED'}")
    print(f"LLM checked: {llm_checked}")
    print(f"Matched ID:  {matched_id}")
    print(f"Reason:      {reason}")
    print(f"\nSimilarity scores:")
    for s in scores:
        print(f"  [{s.get('similarity', 0):.4f}] {s.get('ticket_id')}  —  {s.get('title')}")

    passed = decision == expected
    print(f"\nResult: {'PASS' if passed else 'FAIL'}")
    return passed


def run_debug(ticket: dict):
    """Quick similarity-only check without LLM or DB insert."""
    print(f"\n{'='*60}")
    print("Debug: similarity-only (no LLM, no DB insert)")
    print(f"{'='*60}")
    try:
        res = requests.post(f"{BASE_URL}/debug-similarity", json=ticket, timeout=15)
        res.raise_for_status()
        print(json.dumps(res.json(), indent=2))
    except Exception as e:
        print(f"[ERROR] {e}")


def cleanup_test_tickets():
    url = f"{ASTRA_ENDPOINT}/api/json/v1/default_keyspace/{COLLECTION}"
    payload = {
        "deleteMany": {
            "filter": {"title": {"$in": TEST_TITLES}}
        }
    }
    res = requests.post(url, json=payload, headers={
        "Token": ASTRA_TOKEN,
        "Content-Type": "application/json"
    })
    deleted = res.json().get("status", {}).get("deletedCount", "?")
    print(f"[Cleanup] Deleted {deleted} test ticket(s) from DB")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default=BASE_URL, help="Base URL of redundancy-check service")
    parser.add_argument("--debug-only", action="store_true", help="Run similarity debug only (no LLM)")
    parser.add_argument("--cleanup-only", action="store_true")  # 수동 청소용
    args = parser.parse_args()
    BASE_URL = args.url

    if args.debug_only:
        run_debug(TICKET_DUPLICATE)
        run_debug(TICKET_REPHRASED)
        run_debug(TICKET_NEW_POLICY)
    else:
        test_cases = [
            ("Duplicate ticket (same Q + same A)",      TICKET_DUPLICATE,  "DISCARD"),
            ("Rephrased ticket (same Q + rephrased A)", TICKET_REPHRASED,  "DISCARD"),
            ("New policy ticket (same Q + updated A)",  TICKET_NEW_POLICY, "POST"),
        ]

        results = []
        for label, ticket, expected in test_cases:
            print("[Setup] Cleaning up before test...")
            cleanup_test_tickets()

            passed = run_test(label, ticket, expected)
            results.append(passed)

            print("[Teardown] Cleaning up after test...")
            cleanup_test_tickets()

        print(f"\n{'='*60}")
        print(f"Summary: {sum(results)}/{len(results)} passed")
        print(f"{'='*60}")