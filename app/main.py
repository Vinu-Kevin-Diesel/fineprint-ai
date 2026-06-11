"""FinePrint API — upload a policy/contract, get back the clauses that look off."""

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import HTMLResponse

from . import __version__
import logging

from .config import get_settings
from .domains import list_domains
from .extract_rules import extract_ruleset
from .extract_text import UnsupportedFileType
from .ingest import ingest
from .llm import analyze_document
from .ocr import OcrUnavailable
from .schemas import AnalysisResponse
from .verify import check_consistency

logger = logging.getLogger(__name__)

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
        "provider": s.llm_provider,
        "model": s.active_model(),
        "ocr_backend": s.ocr_backend,
        "domains": list_domains(),
    }


@app.post("/analyze", response_model=AnalysisResponse)
async def analyze(
    file: UploadFile = File(...),
    domain: str = Form("generic"),
    verify_consistency: bool = Form(True),
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
        ingested = ingest(file.filename or "upload", data)
    except UnsupportedFileType as e:
        raise HTTPException(status_code=415, detail=str(e))
    except OcrUnavailable as e:
        raise HTTPException(status_code=501, detail=str(e))
    except Exception as e:  # OCR/provider failure during extraction
        raise HTTPException(status_code=502, detail=f"Text extraction failed: {e}")

    if not ingested.text.strip():
        raise HTTPException(
            status_code=422,
            detail="Could not extract any text from the document (even with OCR).",
        )

    try:
        result, model = analyze_document(domain, ingested.text)
    except Exception as e:  # surface provider errors cleanly to the client
        raise HTTPException(status_code=502, detail=f"Analysis failed: {e}")

    # Mode A: formal consistency check (extract rules -> prove with Z3).
    # Best-effort: a verification failure shouldn't sink the whole analysis.
    consistency = None
    if verify_consistency:
        try:
            consistency = check_consistency(extract_ruleset(ingested.text))
        except Exception as e:
            logger.warning("Consistency check failed: %s", e)

    return AnalysisResponse(
        document_name=file.filename or "upload",
        domain=domain,
        model=model,
        extraction_method=ingested.method,
        result=result,
        consistency=consistency,
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
  .quote {{ font-style: italic; color: #444; border-left: 2px solid #ccc; padding-left: 8px; display: inline-block; margin: 4px 0; }}
</style></head>
<body>
  <h1>FinePrint</h1>
  <p class="sub">Upload a lease, insurance policy, or contract. We'll point out what looks off.</p>
  <form id="f">
    <label>Document type</label>
    <select name="domain">{options}</select>
    <label>File (PDF, DOCX, TXT, or a scanned image)</label>
    <input type="file" name="file" accept=".pdf,.docx,.txt,.md,.png,.jpg,.jpeg,.tif,.tiff,.bmp,.webp" required>
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
  let html = '<p class="badge">read via: ' + data.extraction_method + ' · ' + data.model + '</p>';
  html += '<h2>Summary</h2><p>' + r.summary + '</p>';
  html += '<h2>Flagged by AI review (' + r.findings.length + ')</h2>';
  for (const fd of r.findings) {{
    const loc = fd.location ? ('<span class="badge"> · ' + fd.location + '</span>') : '';
    const quote = fd.source_quote ? ('<br><span class="quote">“' + fd.source_quote + '”</span>') : '';
    html += '<div class="finding ' + fd.severity + '">' +
      '<span class="badge">' + fd.severity + ' · ' + fd.type + '</span>' + loc +
      '<strong> ' + fd.title + '</strong>' + quote + '<br>' + fd.explanation +
      '<br><em>What to do:</em> ' + fd.recommendation + '</div>';
  }}
  const cons = data.consistency;
  if (cons && cons.checked) {{
    html += '<h2>Proven by SMT solver (Z3)</h2>';
    html += '<p class="badge">' + cons.variables + ' variables · ' + cons.rules + ' rules · '
      + (cons.consistent ? 'no contradictions proven' : (cons.contradictions.length + ' contradiction(s) proven')) + '</p>';
    for (const c of cons.contradictions) {{
      html += '<div class="finding high"><span class="badge">contradiction · ' + c.rule_ids.join(', ')
        + '</span><br>' + c.explanation + '</div>';
    }}
    for (const u of cons.unreachable) {{
      html += '<div class="finding"><span class="badge">unreachable · ' + u.rule_id
        + '</span><br>' + u.explanation + '</div>';
    }}
  }}
  html += '<h2>Clauses extracted (' + r.clauses.length + ')</h2>';
  out.innerHTML = html;
}});
</script>
</body></html>"""
