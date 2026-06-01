# Document Verification API

An Azure Functions (Python v4 / v2 programming model) backend that classifies and
verifies identity documents uploaded during legal-services intake. Built for an
immigrant legal-aid use case: clients upload identity documents (passport, green
card, EAD, SSN card, driver's licence, USCIS forms), and the API classifies the
document, checks image quality, extracts structured fields, and routes each case
to **Verified**, **ManualReview**, **RetakePhoto**, or **Rejected**.

The AI never makes a final legal ruling. It triages: every failure mode defaults
to human review, and the client-facing responses contain no extracted personal
data.

---

## How it works

The pipeline runs in stages:

1. **Stage 1 — Classify** (GPT-4o via Azure AI Foundry): identifies the
   document type and judges whether the image is acceptable (not blurry, cropped,
   a screenshot, expired, or tampered). No data extraction.
2. **Document Intelligence — Extract** (`prebuilt-idDocument`): for acceptable,
   known ID types, extracts structured fields with per-field confidence and
   applies a confidence gate.
3. **Stage 2 — Fraud check** (GPT-4o, flag-only by default): a tamper
   review. Disabled from auto-verifying by default — it only flags for human
   review.

Each outcome is persisted to two stores: a PII-free status record (for the client
poll endpoint) and a PII-bearing review record (for the admin review screen,
behind an additional admin key).

---

## Azure resources involved

| Resource | Purpose |
| --- | --- |
| **Azure AI Foundry — GPT-4o deployment** | Powers Stage 1 classification (document type + image quality) and the Stage 2 fraud/tamper check. Accessed through a Foundry-managed OpenAI endpoint. |
| **Azure AI Document Intelligence** (`prebuilt-idDocument`) | Reads the document contents — extracts structured fields (name, document number, date of birth, expiry, etc.) with per-field confidence scores. This is the only stage that actually pulls data out of the document. |
| **Azure Function App** (Python, v4 runtime) | Hosts the API. Exposes the `verify`, `status`, and `review` HTTP endpoints, orchestrates the pipeline, and applies the routing logic. Key-based auth. |
| **Azure Storage Account** | Serves three roles on one account: **Blob storage** holds the uploaded document images (and the API generates short-lived read SAS URLs for the calls); **Table storage** holds the PII-free status records and the PII-bearing admin review records; and it backs the **Functions runtime** itself. |
| **Application Insights** | Captures the metadata-only audit logs (stage, document type, verdict, confidences, latency) emitted by the app. No prompts, responses, or field values are logged. |

All AI and data resources should sit in the same region for data residency, and
the storage account holding client documents and extracted data is the most
sensitive resource — configure its encryption, retention, network access, and
access policy deliberately.

---

## Important: documents must already exist in blob storage

**This API does not upload files.** It works from a reference to a document that
is *already present* in your uploads blob container.

Before calling `/verify`, the document image must be uploaded to the blob
container configured in `AZURE_STORAGE_UPLOADS_CONTAINER`. The `blobReference`
field in the request is the path of that file **within the container** (just the
filename if it sits at the container root, or a relative path if it's in a
subfolder).

If the referenced blob does not exist, `/verify` returns `404 Uploaded document
not found`.

---

## Endpoints

All endpoints require a **function key** (`authLevel=FUNCTION`), passed as a
`?code=<function-key>` query parameter or an `x-functions-key` header.

### 1. `POST /api/documents/verify`

Runs the pipeline for one uploaded document. Returns a PII-free result.

```bash
curl -X POST "https://<your-app>.azurewebsites.net/api/documents/verify?code=<FUNCTION_KEY>" \
  -H "Content-Type: application/json" \
  -d '{
    "documentId": "doc_test_001",
    "caseId": "case_test_001",
    "documentSlot": "passport",
    "blobReference": "sample-passport.png"
  }'
```

Response:

```json
{
  "success": true,
  "data": {
    "documentId": "doc_test_001",
    "status": "ManualReview",
    "documentType": "Passport",
    "messageKey": "verify.manual_review",
    "requiresRetake": false
  }
}
```

`status` is one of `Verified`, `ManualReview`, `RetakePhoto`, `Rejected`.
`messageKey` maps to a localized string in the frontend's i18n table.

### 2. `GET /api/documents/{id}/status`

Client-facing poll endpoint. Returns the same PII-free shape as `/verify`.

```bash
curl "https://<your-app>.azurewebsites.net/api/documents/doc_test_001/status?code=<FUNCTION_KEY>"
```

### 3. `GET /api/documents/{id}/review`

**Admin only.** Returns the extracted fields and quality/tamper flags for the
manual-review screen. Requires the function key **and** an admin key header
(`x-admin-key`). This is the only endpoint that returns personal data.

```bash
curl "https://<your-app>.azurewebsites.net/api/documents/doc_test_001/review?code=<FUNCTION_KEY>" \
  -H "x-admin-key: <ADMIN_REVIEW_KEY>"
```

---

## Project structure

```
document-api/
├── function_app.py                 # Route registration (v2 model)
├── host.json
├── requirements.txt
├── modules/
│   └── documents/
│       ├── functions/              # HTTP handlers (verify, status, review)
│       ├── services/               # Pipeline + stage services + stores
│       ├── types/                  # Request/response models, enums
│       └── caller_contract.py      # Outcome -> status routing
└── shared/                         # config, clients, responses, blob, audit
```

---

## Configuration

All settings (credentials, thresholds, timeouts) are read from environment
variables — Function App application settings in Azure, or `local.settings.json`
locally. **No secrets are committed to this repo.** See the table below for the
keys the app reads; supply your own values.

| Setting | Purpose | Example default |
| --- | --- | --- |
| `AZURE_AI_FOUNDRY_ENDPOINT` | GPT-4o (Foundry) endpoint | — |
| `AZURE_AI_FOUNDRY_KEY` | GPT-4o key | — |
| `AZURE_GPT4O_DEPLOYMENT` | Deployment name | `gpt-4o` |
| `AZURE_DOC_INTELLIGENCE_ENDPOINT` | Document Intelligence endpoint | — |
| `AZURE_DOC_INTELLIGENCE_KEY` | Document Intelligence key | — |
| `AZURE_STORAGE_CONNECTION_STRING` | Storage account (blobs + tables) | — |
| `AZURE_STORAGE_UPLOADS_CONTAINER` | Uploads container name | `uploads` |
| `REVIEW_TABLE_NAME` | Admin review table | `documentReviews` |
| `STATUS_TABLE_NAME` | Client status table | `documentStatus` |
| `ADMIN_REVIEW_KEY` | Extra key for the review endpoint | — |
| `EXTRACTION_FIELD_CONFIDENCE_THRESHOLD` | Per-field gate | `0.90` |
| `EXTRACTION_REQUIRED_FIELDS` | Gated fields (comma-separated) | `DocumentNumber,DateOfBirth,LastName` |
| `STAGE2_LEGITIMACY_THRESHOLD` | Fraud-check verify threshold | `0.85` |
| `STAGE2_ALLOW_AUTO_VERIFY` | Allow Stage 2 to auto-verify | `false` |
| `AI_TIMEOUT_SECONDS` | Per-call AI timeout | `4.0` |
| `SAS_URL_TTL_MINUTES` | Blob SAS lifetime | `5` |

`local.settings.json` is gitignored and must never be committed.

---

## Run locally

```bash
pip install -r requirements.txt
func start
```

Add your settings to `local.settings.json` (use the keys in the table above).
Upload a test image to your uploads container first, then call `/verify` with its
filename as `blobReference`.

## Deploy

```bash
func azure functionapp publish <your-app-name>
```

Configure the environment variables as Function App application settings in the
Azure portal (not in the deployment package).

---

## Notes

- **No PII in client responses.** Only the admin `/review` endpoint returns
  extracted field values, and it is gated by an additional admin key.
- **Confidence and correctness are decoupled.** Synthetic / specimen documents
  often extract correctly but with low confidence, so they may route to
  ManualReview under the default `0.90` gate. Tune the gate for your document mix.
- **Stage 2 is flag-only by default.** General-purpose models are not
  reliable forgery detectors; auto-verify is off unless explicitly enabled.
- This project handles sensitive identity documents. Configure encryption,
  retention, network access, and region on the storage account deliberately.