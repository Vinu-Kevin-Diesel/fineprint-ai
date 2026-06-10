# FinePrint

**Reads the fine print so you don't have to.** Upload a lease, insurance policy, loan
agreement, or terms-of-service document and FinePrint pinpoints the clauses that look
off — contradictions, hidden fees, auto-renewals, one-sided terms, waived rights, and
coverage gaps — in plain English.

It's the validation layer humans skip: the boring document nobody reads, read carefully
every time.

## How it works

```
Upload (PDF/DOCX/TXT)
   │
   ▼  FastAPI (Cloud Run)
text extraction ──► Gemini (clause extraction + red-flag analysis)
   │                        guided by a swappable per-document "domain pack"
   ▼
structured findings  ──►  JSON API  +  simple web UI
```

- **Domain-agnostic engine, swappable domain packs.** The analysis engine never changes;
  each document type (`domains/lease.yaml`, `domains/insurance.yaml`, …) supplies the
  baseline of *what's typical* and *what to watch for*. Add a new document type by dropping
  in a YAML file.
- **Two detection modes:**
  - *Red-flag detection* (live now): one-sided terms, hidden fees, auto-renewals, unusual
    terms vs. the norm, waived rights, gaps.
  - *Formal consistency checking* (planned, M4): compile extracted rules to logic and use an
    SMT solver to **prove** contradictions / unreachable clauses.

## Run locally (no GCP needed)

1. Get a free Gemini API key: https://aistudio.google.com/apikey
2. Configure:
   ```powershell
   Copy-Item .env.example .env
   # edit .env and set GEMINI_API_KEY=...
   ```
3. Install and run:
   ```powershell
   python -m venv .venv
   .venv\Scripts\Activate.ps1
   pip install -r requirements.txt
   uvicorn app.main:app --reload
   ```
4. Open http://127.0.0.1:8000 — upload a document, pick its type, hit **Analyze**.

API: `GET /health`, `POST /analyze` (multipart: `file`, `domain`). Docs at `/docs`.

## Deploy to GCP (Cloud Run + Vertex AI)

> Requires the `gcloud` CLI and a GCP project with billing (the free trial credit is plenty).

```powershell
gcloud run deploy fineprint `
  --source . `
  --region us-central1 `
  --allow-unauthenticated `
  --set-env-vars USE_VERTEX=true,GCP_PROJECT=YOUR_PROJECT,GEMINI_MODEL=gemini-2.5-flash
```

With `USE_VERTEX=true` the app uses the Cloud Run service account's credentials via
Vertex AI — no API key in the environment.

## Roadmap

- **M1 (done):** upload → extract → Gemini red-flag analysis + web UI.
- **M2:** LangGraph multi-agent pipeline; persist clauses + source spans in pgvector.
- **M3:** Pub/Sub → BigQuery findings stream; Looker/React dashboard.
- **M4:** Z3 SMT consistency engine — *prove* contradictions and unreachable clauses.
