"""Gemini-backed clause extraction + red-flag analysis.

Works with either a Gemini API key (local dev) or Vertex AI (production on GCP),
selected by config. The same structured-output contract (AnalysisResult) is used
for both so nothing downstream changes.
"""

from google.genai import types

from .config import get_settings
from .domains import get_domain
from .genai_client import get_client
from .schemas import AnalysisResult


def _build_prompt(domain_name: str, document_text: str) -> str:
    pack = get_domain(domain_name)
    watch_for = "\n".join(f"- {w}" for w in pack.get("watch_for", [])) or "- (none specified)"
    typical = "\n".join(f"- {t}" for t in pack.get("typical_terms", [])) or "- (none specified)"

    return f"""You are FinePrint, an assistant that reads policies and contracts on behalf of \
an ordinary person who is about to sign, and points out what they would otherwise overlook.

DOCUMENT TYPE: {pack.get('name', domain_name)} — {pack.get('description', '')}

Things that are commonly TYPICAL/fair for this kind of document (use as a baseline):
{typical}

Things to WATCH FOR (potential red flags) in this kind of document:
{watch_for}

Your tasks:
1. Extract the document's substantive clauses. Restate each in plain language and keep a short verbatim source excerpt.
2. Flag anything that looks off: internal contradictions, one-sided terms, hidden fees, \
auto-renewals, unusual terms vs. what's typical, rights the reader waives, coverage gaps, or ambiguous wording.
   - Address explanations directly to the reader ("you").
   - Be concrete and practical. Do not invent clauses that aren't in the text.
   - If the document looks fair, it is fine to return few or no findings.

Return ONLY the structured JSON matching the provided schema.

--- DOCUMENT START ---
{document_text}
--- DOCUMENT END ---
"""


def analyze_document(domain_name: str, document_text: str) -> tuple[AnalysisResult, str]:
    """Run extraction + red-flag analysis. Returns (result, model_name)."""
    s = get_settings()
    client = get_client()
    prompt = _build_prompt(domain_name, document_text)

    response = client.models.generate_content(
        model=s.gemini_model,
        contents=prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=AnalysisResult,
            temperature=0.2,
        ),
    )
    result: AnalysisResult = response.parsed
    return result, s.gemini_model
