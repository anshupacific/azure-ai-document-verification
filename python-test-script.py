"""
Test script for the NIJC document API.

Calls the three endpoints in sequence:
    1. POST  /documents/verify
    2. GET   /documents/{id}/status
    3. GET   /documents/{id}/review   (admin)

Upload your test image to the blob container manually first, then set
BLOB_REFERENCE below to its path within the container.

Run:  python test_api.py
"""

import requests

# ---------------------------------------------------------------------------
# CONFIG — edit these
# ---------------------------------------------------------------------------
BASE_URL = "https://func-app-xxxxx.eastus2-01.azurewebsites.net"
FUNCTION_KEY = "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx=="
ADMIN_KEY = "8xxxxx-xxxx-xxxx-xxxx-fxxxxxxxx6"

# The request payload. blob_reference = path of the file inside your
# "enduseruploads" container (e.g. just the filename if at the container root).
DOCUMENT_ID = "doc_test_001"
CASE_ID = "case_test_001"
DOCUMENT_SLOT = "passport"
BLOB_REFERENCE = "sample-passport2.png"

# ---------------------------------------------------------------------------

VERIFY_URL = f"{BASE_URL}/api/documents/verify"
STATUS_URL = f"{BASE_URL}/api/documents/{DOCUMENT_ID}/status"
REVIEW_URL = f"{BASE_URL}/api/documents/{DOCUMENT_ID}/review"


def call_verify():
    print("=== 1. POST /documents/verify ===")
    resp = requests.post(
        VERIFY_URL,
        params={"code": FUNCTION_KEY},
        json={
            "documentId": DOCUMENT_ID,
            "caseId": CASE_ID,
            "documentSlot": DOCUMENT_SLOT,
            "blobReference": BLOB_REFERENCE,
        },
        timeout=60,
    )
    print(f"HTTP {resp.status_code}")
    print(resp.text)
    print()


def call_status():
    print("=== 2. GET /documents/{id}/status ===")
    resp = requests.get(
        STATUS_URL,
        params={"code": FUNCTION_KEY},
        timeout=30,
    )
    print(f"HTTP {resp.status_code}")
    print(resp.text)
    print()


def call_review():
    print("=== 3. GET /documents/{id}/review (admin) ===")
    resp = requests.get(
        REVIEW_URL,
        params={"code": FUNCTION_KEY},
        headers={"x-admin-key": ADMIN_KEY},
        timeout=30,
    )
    print(f"HTTP {resp.status_code}")
    print(resp.text)
    print()


if __name__ == "__main__":
    call_verify()
    call_status()
    call_review()