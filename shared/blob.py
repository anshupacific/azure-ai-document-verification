"""
Blob storage helper.

Resolves an uploaded blob reference into the two forms the pipeline needs:
  - a short-lived (read-only) SAS URL for the GPT-4o vision calls
  - the raw bytes for the Document Intelligence call

The SAS TTL comes from config (SAS_URL_TTL_MINUTES) so it is tunable from the
Function App settings. Key-based auth via the storage account connection string.

NOTE: This requires AZURE_STORAGE_CONNECTION_STRING and a container name in the
Function App settings. If storage isn't wired up yet, the functions raise a
clear error; swap in your own storage wiring without touching the pipeline.
"""

import os
from datetime import datetime, timedelta, timezone

from azure.storage.blob import (
    BlobServiceClient,
    generate_blob_sas,
    BlobSasPermissions,
)

from shared import config

_CONNECTION_STRING = os.environ.get("AZURE_STORAGE_CONNECTION_STRING", "")
_CONTAINER = os.environ.get("AZURE_STORAGE_UPLOADS_CONTAINER", "uploads")


def _service_client() -> BlobServiceClient:
    if not _CONNECTION_STRING:
        raise RuntimeError("Missing AZURE_STORAGE_CONNECTION_STRING")
    return BlobServiceClient.from_connection_string(_CONNECTION_STRING)


def get_image_url_and_bytes(blob_reference: str) -> tuple[str, bytes]:
    """
    Given a blob reference (path within the uploads container), return:
      (sas_url, image_bytes)

    The SAS URL is read-only and expires after SAS_URL_TTL_MINUTES.
    Raises FileNotFoundError if the blob does not exist.
    """
    service = _service_client()
    blob_client = service.get_blob_client(container=_CONTAINER, blob=blob_reference)

    if not blob_client.exists():
        raise FileNotFoundError(f"Blob not found: {blob_reference}")

    # Raw bytes for Document Intelligence
    image_bytes = blob_client.download_blob().readall()

    # Short-lived read SAS for the vision calls
    sas_token = generate_blob_sas(
        account_name=blob_client.account_name,
        container_name=_CONTAINER,
        blob_name=blob_reference,
        account_key=service.credential.account_key,
        permission=BlobSasPermissions(read=True),
        expiry=datetime.now(timezone.utc) + timedelta(minutes=config.SAS_URL_TTL_MINUTES),
    )
    sas_url = f"{blob_client.url}?{sas_token}"

    return sas_url, image_bytes