"""
Status handler — GET /api/documents/{id}/status

Client-facing poll endpoint, used when verification runs asynchronously. Returns
the SAME PII-free shape as the verify response: status, documentType, message
key, retake flag. No field values, no reasons[].

Key-based auth enforced by the Function App (authLevel="function"). Unlike the
review endpoint, this requires NO admin key — but it also returns no PII.

Reads a small client-status record persisted by the pipeline (separate from the
PII-bearing review record). Isolated behind get_status_record() so storage can
change without touching the handler.
"""

import logging

import azure.functions as func

from shared.responses import create_success_response, create_error_response
from modules.documents.services.status_store import get_status_record

logger = logging.getLogger("nijc.status")


def status_handler(req: func.HttpRequest) -> func.HttpResponse:
    """Return the PII-free verification status for a document."""
    logger.info("status: request received")

    if req.method != "GET":
        return create_error_response("Method not allowed. Use GET.", status_code=405)

    document_id = req.route_params.get("id")
    if not document_id:
        return create_error_response("Document ID is required in the URL")

    try:
        record = get_status_record(document_id)
    except Exception:
        logger.exception("status: failed to read status record")
        return create_error_response("Internal server error", status_code=500)

    if record is None:
        return create_error_response("Status not found", status_code=404)

    # record is already the PII-free client shape (the VerifyResponse dict)
    return create_success_response(data=record)