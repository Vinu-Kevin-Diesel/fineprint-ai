"""FinePrint API — upload a policy/contract, get back the clauses that look off."""

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import HTMLResponse

from . import __version__
from .config import get_settings
from .domains import list_domains
from .extract_text import UnsupportedFileType, extract_text
from .llm import analyze_document
from .schemas import AnalysisResponse

app = FastAPI(
    title="FinePrint",
    version=__version__,
    description="Reads the fine print so you don't have to — flags contradictions, "
    "hidden fees, and one-sided terms in policies and contracts.",
)


@app.get("/health")
def health() -> dict:
    s = get_settings()
    return {
        "status": "ok",
        "version": __version__,
        "llm_configured": s.is_llm_configured,
        "provider": "vertex" if s.use_vertex else "gemini-api",
        "model": s.gemini_model,
        "domains": list_domains(),
    }


@app.post("/analyze", response_model=AnalysisResponse)
async def analyze(
    file: UploadFile = File(...),
    domain: str = Form("generic"),
) -> AnalysisResponse:
    s = get_settings()
    if not s.is_llm_configured:
        raise HTTPException(
            status_code=503,
            detail="LLM is not configured. Set GEMINI_API_KEY (or USE_VERTEX=true) in your .env.",
        )

    data = await file.read()
    if len(data) > s.max_upload_mb * 1024 * 1024:
        raise HTTPException(status_code=413, detail=f"File exceeds {s.max_upload_mb} MB limit.")

    try:
        text = extract_text(file.filename or "upload", data)
    except UnsupportedFileType as e:
        raise HTTPException(status_code=415, detail=str(e))

    if not text.strip():
        raise HTTPException(status_code=422, detail="Could not extract any text from the document.")

    try:
        result, model = analyze_document(domain, text)
    except Exception as e:  # surface provider errors cleanly to the client
        raise HTTPException(status_code=502, detail=f"Analysis failed: {e}")

    return AnalysisResponse(
        document_name=file.filename or "upload",
        domain=domain,
        model=model,
        result=result,
    )


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    domains = list_domains()
    options = "".join(f'<option value="{d}">{d}</option>' for d in domains)
    return f"""<!doctype html>
<html><head><meta charset="utf-8"><title>FinePrint</title>
<style>
  body {{ font-family: system-ui, sans-serif; max-width: 760px; margin: 40px auto; padding: 0 16px; color: #1a1a1a; }}
  h1 {{ margin-bottom: 4px; }} .sub {{ color: #666; margin-top: 0; }}
  form {{ background: #f6f7f9; padding: 20px; border-radius: 12px; }}
  label {{ display: block; margin: 12px 0 4px; font-weight: 600; }}
  select, input[type=file] {{ width: 100%; padding: 8px; }}
  button {{ margin-top: 16px; padding: 10px 18px; border: 0; border-radius: 8px; background: #1a73e8; color: #fff; font-size: 15px; cursor: pointer; }}
  #out {{ white-space: pre-wrap; margin-top: 24px; }}
  .finding {{ border-left: 4px solid #e8a01a; background: #fff8ec; padding: 10px 14px; margin: 10px 0; border-radius: 6px; }}
  .high {{ border-color: #d93025; background: #fce8e6; }}
  .badge {{ font-size: 12px; text-transform: uppercase; color: #666; }}
</style></head>
<body>
  <h1>FinePrint</h1>
  <p class="sub">Upload a lease, insurance policy, or contract. We'll point out what looks off.</p>
  <form id="f">
    <label>Document type</label>
    <select name="domain">{options}</select>
    <label>File (PDF, DOCX, or TXT)</label>
    <input type="file" name="file" accept=".pdf,.docx,.txt,.md" required>
    <button type="submit">Analyze</button>
  </form>
  <div id="out"></div>
<script>
const f = document.getElementById('f'), out = document.getElementById('out');
f.addEventListener('submit', async (e) => {{
  e.preventDefault();
  out.textContent = 'Analyzing…';
  const res = await fetch('/analyze', {{ method: 'POST', body: new FormData(f) }});
  if (!res.ok) {{ out.textContent = 'Error: ' + (await res.text()); return; }}
  const data = await res.json();
  const r = data.result;
  let html = '<h2>Summary</h2><p>' + r.summary + '</p><h2>Findings (' + r.findings.length + ')</h2>';
  for (const fd of r.findings) {{
    html += '<div class="finding ' + fd.severity + '">' +
      '<span class="badge">' + fd.severity + ' · ' + fd.type + '</span>' +
      '<strong> ' + fd.title + '</strong><br>' + fd.explanation +
      '<br><em>What to do:</em> ' + fd.recommendation + '</div>';
  }}
  html += '<h2>Clauses extracted (' + r.clauses.length + ')</h2>';
  out.innerHTML = html;
}});
</script>
</body></html>"""
