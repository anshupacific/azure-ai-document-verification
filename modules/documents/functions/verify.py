"""
Verify handler — POST /api/documents/verify

Mirrors the TS createFacility/index.ts handler shape: validate method, parse and
validate the body, call the service, return a standard response. Key-based auth
is enforced by the Function App (authLevel="function") — no JWT claims.

The handler is thin: it resolves the uploaded blob (URL for vision calls, bytes
for Document Intelligence), delegates to DocumentService, and returns the
PII-free VerifyResponse.
"""

import json
import logging

import azure.functions as func

from shared.responses import create_success_response, create_error_response, validate_required
from shared.blob import get_image_url_and_bytes
from modules.documents.services.document_service import DocumentService

logger = logging.getLogger("nijc.verify")

REQUIRED_FIELDS = ["documentId", "caseId", "documentSlot", "blobReference"]


def verify_handler(req: func.HttpRequest) -> func.HttpResponse:
    """Run the verification pipeline for one uploaded document."""
    logger.info("verify: request received")

    # Method guard (route also restricts, this is a belt-and-braces check)
    if req.method != "POST":
        return create_error_response("Method not allowed. Use POST.", status_code=405)

    # Parse body
    try:
        body = req.get_json()
    except ValueError:
        return create_error_response("Invalid JSON in request body")

    if not body:
        return create_error_response("Request body is required")

    # Validate required fields
    validation_error = validate_required(body, REQUIRED_FIELDS)
    if validation_error:
        return create_error_response(validation_error)

    document_id = body["documentId"]
    blob_reference = body["blobReference"]

    # Resolve the uploaded blob: short-lived SAS URL for the vision calls,
    # raw bytes for the Document Intelligence call.
    try:
        image_url, image_bytes = get_image_url_and_bytes(blob_reference)
    except FileNotFoundError:
        return create_error_response("Uploaded document not found", status_code=404)
    except Exception:
        logger.exception("verify: failed to resolve blob")
        return create_error_response("Could not access the uploaded document", status_code=502)

    # Run the pipeline
    try:
        service = DocumentService()
        result = service.verify(
            document_id=document_id,
            image_url=image_url,
            image_bytes=image_bytes,
        )
    except Exception:
        logger.exception("verify: pipeline error")
        return create_error_response("Internal server error", status_code=500)

    # PII-free response
    return create_success_response(data=result.to_dict())