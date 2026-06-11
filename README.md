# FinePrint

**Reads the fine print so you don't have to.** Upload a lease, insurance policy, loan
agreement, or terms-of-service document and FinePrint pinpoints the clauses that look
off — contradictions, hidden fees, auto-renewals, one-sided terms, waived rights, and
coverage gaps — in plain English.

It's the validation layer humans skip: the boring document nobody reads, read carefully
every time.

## How it works

```
Upload (PDF/DOCX/TXT/image)
   │
   ▼  FastAPI (Cloud Run)
ingest ── native text layer? ──► use it
   │  └─ scanned / image ──► OCR (Gemini multimodal, or Tesseract)
   ▼
   ├─► Mode B: Gemini red-flag analysis (guided by a domain pack)
   └─► Mode A: Gemini rule extraction ──► Z3 SMT solver (prove contradictions)
   ▼
structured findings + consistency report  ──►  JSON API  +  simple web UI
```

### Pluggable reasoning provider

The clause analysis and rule extraction go through a provider-agnostic layer
([app/llm_provider.py](app/llm_provider.py)), selected by `LLM_PROVIDER`:

- **`gemini`** (default) — Google Gemini / Vertex, using native structured output.
- **`openai_compatible`** — any OpenAI-compatible endpoint via one client + `LLM_BASE_URL`:
  **NVIDIA NIM** (`https://integrate.api.nvidia.com/v1`), **Groq**, **self-hosted vLLM**
  (`http://localhost:8000/v1`), or OpenAI. Structured output is done with JSON mode + the
  schema in the prompt + **Pydantic validation, re-asking the model on invalid JSON**, plus
  transient-error retry and (for Gemini) model failover.

Swapping providers is config-only — no code changes. OCR is intentionally separate (it needs
a vision-capable model), so you can run reasoning on a text LLM (NIM/vLLM) while OCR stays on
Gemini or Tesseract.

### Text extraction & OCR

Ingestion tries the **native text layer first** (fast, free) and falls back to **OCR**
for scanned PDFs and image uploads (`.png/.jpg/.tiff/...`). The response reports which
path was used via `extraction_method` (`native` | `ocr` | `native+ocr`). OCR backends:

- **`gemini`** (default) — multimodal OCR through the same Gemini/Vertex model. No extra
  dependencies; works locally and on GCP unchanged.
- **`tesseract`** (optional, offline) — `pip install -r requirements-ocr-tesseract.txt`
  plus the system Tesseract binary, then set `OCR_BACKEND=tesseract`.

- **Domain-agnostic engine, swappable domain packs.** The analysis engine never changes;
  each document type (`domains/lease.yaml`, `domains/insurance.yaml`, …) supplies the
  baseline of *what's typical* and *what to watch for*. Add a new document type by dropping
  in a YAML file.
- **Two detection modes:**
  - **Mode B — Red-flag detection** (LLM): one-sided terms, hidden fees, auto-renewals,
    unusual terms vs. the norm, waived rights, gaps.
  - **Mode A — Formal consistency checking** (LLM + Z3 SMT solver): the LLM translates
    prose into typed variables and logical rules; **Z3 then *proves*** contradictions and
    unreachable clauses. The model never decides what conflicts — the solver does.

### Formal verification (Mode A)

The split is the whole point: the LLM does prose→structure (which it's good at); the SMT
solver does the logic (which the LLM is bad at), so every consistency claim is a theorem,
not a guess.

- **Rule extraction** ([app/extract_rules.py](app/extract_rules.py)) → a `RuleSet` of typed
  variables (`age_years: int`, `deposit_refundable: bool`, `plan: enum`) and rules as
  facts or `condition → consequence` implications.
- **Z3 verifier** ([app/verify.py](app/verify.py)) proves:
  - **Contradictions** (pairwise): two clauses whose conditions can co-occur but whose
    consequences are then jointly unsatisfiable — e.g. "65+ is eligible" vs. "65+ is not
    eligible", or a deposit that's both refundable and non-refundable.
  - **Unreachable clauses**: a condition that's impossible given the policy's fixed terms —
    dead logic that can never apply.
- **Tested** independently of the LLM: [tests/test_verify.py](tests/test_verify.py) pins the
  solver's verdicts on hand-built rule sets (`pytest`).
- *Documented limitation:* contradiction detection is pairwise, so a conflict that only
  emerges from 3+ clauses jointly is not reported.

Try it: `python scripts/run_local.py samples/sample-insurance-policy.txt insurance` — the
sample has four planted contradictions (senior eligibility, loyalty discount, premium tier,
waiting period) that Z3 proves.

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
- **OCR (done):** native-first ingestion with OCR fallback for scanned PDFs/images.
- **M4 — formal verification (done):** Z3 SMT consistency engine — *proves* contradictions
  and unreachable clauses, with a unit-tested solver.
- **Next:** eval harness (precision/recall on labeled contracts); grounding/source-span
  verification; async job model + persistence; Cloud Run + Vertex AI deploy.
