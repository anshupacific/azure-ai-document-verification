"""
Status store.

Persists and reads the PII-free client status record — the VerifyResponse shape
(status, documentType, messageKey, requiresRetake) that backs the
GET /documents/{id}/status poll endpoint.

This store holds NO PII. It is deliberately separate from review_store (which
holds the extracted field values for admins), so the client poll path never
touches the PII table.

    save_status_record(document_id, record)
    get_status_record(document_id) -> record | None

Reference implementation uses Azure Table Storage (key-based).
"""

import os
import json
import logging

from azure.data.tables import TableServiceClient
from azure.core.exceptions import ResourceNotFoundError

logger = logging.getLogger("nijc.status_store")

_CONNECTION_STRING = os.environ.get("AZURE_STORAGE_CONNECTION_STRING", "")
_TABLE_NAME = os.environ.get("STATUS_TABLE_NAME", "documentStatus")

_PARTITION = "status"


def _table_client():
    if not _CONNECTION_STRING:
        raise RuntimeError("Missing AZURE_STORAGE_CONNECTION_STRING")
    service = TableServiceClient.from_connection_string(_CONNECTION_STRING)
    service.create_table_if_not_exists(_TABLE_NAME)
    return service.get_table_client(_TABLE_NAME)


def save_status_record(document_id: str, record: dict) -> None:
    """
    Persist the PII-free client status record (the VerifyResponse dict).
    Overwrites any existing record for the same documentId.
    """
    client = _table_client()
    entity = {
        "PartitionKey": _PARTITION,
        "RowKey": document_id,
        "payload": json.dumps(record),
    }
    client.upsert_entity(entity)


def get_status_record(document_id: str) -> dict | None:
    """Read the client status record for a document, or None if not found."""
    client = _table_client()
    try:
        entity = client.get_entity(partition_key=_PARTITION, row_key=document_id)
    except ResourceNotFoundError:
        return None

    payload = entity.get("payload")
    if not payload:
        return None
    return json.loads(payload)