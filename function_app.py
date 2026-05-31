"""
function_app.py — Azure Functions v4 runtime, Python v2 programming model.

This is the registration layer only. Each route is a thin wrapper that delegates
to its handler in modules/documents/functions/. All endpoints use key-based auth
(authLevel=FUNCTION), so callers must present a function key. The review endpoint
additionally checks an admin key inside its handler.

Routes:
    POST  /api/documents/verify          -> verify_handler
    GET   /api/documents/{id}/status     -> status_handler   (PII-free)
    GET   /api/documents/{id}/review     -> review_handler   (admin, PII)
"""

import azure.functions as func

from modules.documents.functions.verify import verify_handler
from modules.documents.functions.status import status_handler
from modules.documents.functions.review import review_handler

app = func.FunctionApp()


@app.route(
    route="documents/verify",
    methods=["POST"],
    auth_level=func.AuthLevel.FUNCTION,
)
def verify(req: func.HttpRequest) -> func.HttpResponse:
    return verify_handler(req)


@app.route(
    route="documents/{id}/status",
    methods=["GET"],
    auth_level=func.AuthLevel.FUNCTION,
)
def status(req: func.HttpRequest) -> func.HttpResponse:
    return status_handler(req)


@app.route(
    route="documents/{id}/review",
    methods=["GET"],
    auth_level=func.AuthLevel.FUNCTION,
)
def review(req: func.HttpRequest) -> func.HttpResponse:
    return review_handler(req)