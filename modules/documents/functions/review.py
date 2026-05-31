"""
Review handler — GET /api/documents/{id}/review

Admin / attorney only. This is the ONLY endpoint that exposes extracted PII
(field values, quality/tamper flags) for the manual-review screen. It is
therefore separated from the client-facing endpoints and protected with an
elevated key: the Function App enforces a function key (authLevel="function"),
and this handler additionally requires an admin key header.

Returns the stored review record for a previously-processed document. In a full
implementation the record is read from your datastore (e.g. a table keyed by
documentId) where the pipeline persisted the extraction/flags. Here the
persistence read is isolated behind get_review_record() so the rest of the API
doesn't depend on the storage choice.
"""

import os
import logging

import azure.functions as func

from shared.responses import create_success_response, create_error_response
from modules.documents.services.review_store import get_review_record

logger = logging.getLogger("nijc.review")

# Separate admin key, supplied via Function App settings. The client key cannot
# reach this endpoint's data — the admin key is an additional gate on top of the
# function-level key.
_ADMIN_KEY = os.environ.get("ADMIN_REVIEW_KEY", "")
_ADMIN_KEY_HEADER = "x-admin-key"


def review_handler(req: func.HttpRequest) -> func.HttpResponse:
    """Return the full review record (fields + flags) for an admin reviewer."""
    logger.info("review: request received")

    if req.method != "GET":
        return create_error_response("Method not allowed. Use GET.", status_code=405)

    # Elevated auth: require the admin key header in addition to the function key.
    if not _ADMIN_KEY:
        logger.error("review: ADMIN_REVIEW_KEY not configured")
        return create_error_response("Review endpoint not configured", status_code=500)

    provided = req.headers.get(_ADMIN_KEY_HEADER, "")
    if provided != _ADMIN_KEY:
        logger.warning("review: missing or invalid admin key")
        return create_error_response("Access denied", status_code=403)

    document_id = req.route_params.get("id")
    if not document_id:
        return create_error_response("Document ID is required in the URL")

    try:
        record = get_review_record(document_id)
    except Exception:
        logger.exception("review: failed to read review record")
        return create_error_response("Internal server error", status_code=500)

    if record is None:
        return create_error_response("Review record not found", status_code=404)

    # This response intentionally CONTAINS PII (extracted field values) — it is
    # the admin review screen. Access is logged above; never expose this shape
    # on the client endpoints.
    return create_success_response(data=record)