"""
Shared HTTP response helpers.

Mirrors the TypeScript shared/utils createSuccessResponse / createErrorResponse
pattern, adapted for Azure Functions Python v2 (azure.functions.HttpResponse).

Every endpoint returns a consistent envelope:
    success: bool
    data:    payload on success
    error:   message on failure
"""

import json
import azure.functions as func


def create_success_response(data=None, message: str | None = None, status_code: int = 200) -> func.HttpResponse:
    """Build a standard success response."""
    body = {"success": True}
    if data is not None:
        body["data"] = data
    if message is not None:
        body["message"] = message

    return func.HttpResponse(
        body=json.dumps(body),
        status_code=status_code,
        mimetype="application/json",
    )


def create_error_response(error: str, status_code: int = 400) -> func.HttpResponse:
    """Build a standard error response."""
    body = {"success": False, "error": error}
    return func.HttpResponse(
        body=json.dumps(body),
        status_code=status_code,
        mimetype="application/json",
    )


def validate_required(body: dict, required_fields: list[str]) -> str | None:
    """
    Check that all required fields are present and non-empty in the body.
    Returns an error message string if something is missing, else None.
    Mirrors the TS validateRequired helper.
    """
    if not isinstance(body, dict):
        return "Request body must be a JSON object"

    for field in required_fields:
        value = body.get(field)
        if value is None or (isinstance(value, str) and value.strip() == ""):
            return f"Missing required field: {field}"
    return None