"""
Review store.

Persists and reads the admin review record — the extracted field values and
quality/tamper flags that back the GET /documents/{id}/review screen.

This is the ONLY place extracted PII is stored. It is isolated behind two simple
functions so the storage backend can change without touching the pipeline or
the handlers:

    save_review_record(document_id, record)
    get_review_record(document_id) -> record | None

The reference implementation uses Azure Table Storage (key-based, via the
storage connection string). Records are keyed by documentId. Retention,
encryption-at-rest, and access policy on this table are a compliance decision
(privileged documents) and should be configured on the storage account.
"""

import os
import json
import logging

from azure.data.tables import TableServiceClient
from azure.core.exceptions import ResourceNotFoundError

logger = logging.getLogger("nijc.review_store")

_CONNECTION_STRING = os.environ.get("AZURE_STORAGE_CONNECTION_STRING", "")
_TABLE_NAME = os.environ.get("REVIEW_TABLE_NAME", "documentReviews")

# Single partition keeps lookups simple; documentId is the row key.
_PARTITION = "review"


def _table_client():
    if not _CONNECTION_STRING:
        raise RuntimeError("Missing AZURE_STORAGE_CONNECTION_STRING")
    service = TableServiceClient.from_connection_string(_CONNECTION_STRING)
    # Create on first use; no-op if it already exists.
    service.create_table_if_not_exists(_TABLE_NAME)
    return service.get_table_client(_TABLE_NAME)


def save_review_record(document_id: str, record: dict) -> None:
    """
    Persist the review record for a document. The record (fields + flags) is
    stored as a JSON blob in a single column. Overwrites any existing record
    for the same documentId.
    """
    client = _table_client()
    entity = {
        "PartitionKey": _PARTITION,
        "RowKey": document_id,
        "payload": json.dumps(record),
    }
    client.upsert_entity(entity)


def get_review_record(document_id: str) -> dict | None:
    """Read the review record for a document, or None if not found."""
    client = _table_client()
    try:
        entity = client.get_entity(partition_key=_PARTITION, row_key=document_id)
    except ResourceNotFoundError:
        return None

    payload = entity.get("payload")
    if not payload:
        return None
    return json.loads(payload)