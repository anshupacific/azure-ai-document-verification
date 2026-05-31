"""
Azure client factories.

Builds the SDK clients used by the services, reading credentials from config
(Function App settings). Key-based authentication only.

Mirrors the way the TS service constructors build their clients from env config,
but centralized here so every service builds clients the same way.
"""

from openai import AzureOpenAI
from azure.core.credentials import AzureKeyCredential
from azure.ai.documentintelligence import DocumentIntelligenceClient

from shared import config


def build_openai_client() -> AzureOpenAI:
    """
    Azure OpenAI (GPT-4o via Foundry) client, key-based.

    The configured endpoint may be a full REST path; AzureOpenAI wants the base
    host plus api-version separately. We pass the base endpoint and let config
    supply the api-version.
    """
    if not config.AZURE_AI_FOUNDRY_ENDPOINT or not config.AZURE_AI_FOUNDRY_KEY:
        raise RuntimeError(
            "Missing Azure AI Foundry credentials "
            "(AZURE_AI_FOUNDRY_ENDPOINT / AZURE_AI_FOUNDRY_KEY)"
        )

    base_endpoint = _base_host(config.AZURE_AI_FOUNDRY_ENDPOINT)

    return AzureOpenAI(
        azure_endpoint=base_endpoint,
        api_key=config.AZURE_AI_FOUNDRY_KEY,
        api_version=config.AZURE_OPENAI_API_VERSION,
        timeout=config.AI_TIMEOUT_SECONDS,
    )


def build_doc_intelligence_client() -> DocumentIntelligenceClient:
    """Azure AI Document Intelligence client, key-based."""
    if not config.AZURE_DOC_INTELLIGENCE_ENDPOINT or not config.AZURE_DOC_INTELLIGENCE_KEY:
        raise RuntimeError(
            "Missing Document Intelligence credentials "
            "(AZURE_DOC_INTELLIGENCE_ENDPOINT / AZURE_DOC_INTELLIGENCE_KEY)"
        )

    return DocumentIntelligenceClient(
        endpoint=config.AZURE_DOC_INTELLIGENCE_ENDPOINT,
        credential=AzureKeyCredential(config.AZURE_DOC_INTELLIGENCE_KEY),
    )


def _base_host(endpoint: str) -> str:
    """
    Reduce a possibly-full endpoint URL to scheme://host.
    e.g. https://res.cognitiveservices.azure.com/openai/deployments/.../chat/...
      -> https://res.cognitiveservices.azure.com
    """
    from urllib.parse import urlparse

    parsed = urlparse(endpoint)
    if parsed.scheme and parsed.netloc:
        return f"{parsed.scheme}://{parsed.netloc}"
    return endpoint.rstrip("/")