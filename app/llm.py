"""Gemini-backed clause extraction + red-flag analysis.

Works with either a Gemini API key (local dev) or Vertex AI (production on GCP),
selected by config. The same structured-output contract (AnalysisResult) is used
for both so nothing downstream changes.
"""

from .config import get_settings
from .domains import get_domain
from .llm_provider import generate_structured
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

EVERY finding MUST be SPECIFIC and TRACEABLE — generic findings are useless:
- location: cite the exact section/clause number it comes from (e.g. "§5.1(b)", "Section 7"). If the document is unlabeled, give the heading.
- source_quote: copy a SHORT VERBATIM phrase from the document (exact words, not paraphrased) that proves the finding.
- title: name the actual term. GOOD: "Tenant forfeits deposit interest for first 5 years". BAD: "Security Deposit Deductions".
- explanation: cite the concrete detail — the exact dollar amount, %, number of days, deadline, or who bears the cost. NEVER write filler like "review carefully" or "be aware".
- recommendation: a concrete question or action about THIS specific clause.

Rules:
- Address explanations directly to the reader ("you").
- Do NOT invent clauses, numbers, or quotes that aren't in the text. If a detail (like a dollar amount) is blank in the document, say so rather than guessing.
- Prefer fewer, sharper findings over many vague ones. If the document genuinely looks fair, return few or no findings.

Return ONLY the structured JSON matching the provided schema.

--- DOCUMENT START ---
{document_text}
--- DOCUMENT END ---
"""


def analyze_document(domain_name: str, document_text: str) -> tuple[AnalysisResult, str]:
    """Run extraction + red-flag analysis. Returns (result, model_name)."""
    s = get_settings()
    prompt = _build_prompt(domain_name, document_text)
    result: AnalysisResult = generate_structured(prompt=prompt, schema=AnalysisResult, temperature=0.2)
    return result, s.active_model()
