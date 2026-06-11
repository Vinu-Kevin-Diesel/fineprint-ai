"""Clause extraction + red-flag analysis via a map-reduce pipeline.

A single pass over a long document makes the model skim — it grabs the first few
obvious clauses and stops. So instead we:

  1. EXTRACT every clause exhaustively (map the document to a clause list).
  2. ANALYZE the clauses in small focused batches, so each clause gets real
     attention instead of being skimmed (reduce to findings).
  3. SUMMARIZE the overall read.

Provider-agnostic: every call goes through generate_structured (Gemini or any
OpenAI-compatible backend like NVIDIA NIM / Groq / vLLM).
"""

from .config import get_settings
from .domains import get_domain
from .llm_provider import generate_structured
from .schemas import (
    AnalysisResult,
    Clause,
    ClauseList,
    DocSummary,
    Finding,
    FindingList,
)

# How many clauses to analyze per focused call. Small enough that the model
# actually reasons about each clause; large enough to bound the number of calls.
_BATCH_SIZE = 6


def _domain_context(domain_name: str) -> tuple[str, str, str]:
    pack = get_domain(domain_name)
    name = f"{pack.get('name', domain_name)} — {pack.get('description', '')}"
    watch_for = "\n".join(f"- {w}" for w in pack.get("watch_for", [])) or "- (none specified)"
    typical = "\n".join(f"- {t}" for t in pack.get("typical_terms", [])) or "- (none specified)"
    return name, watch_for, typical


def _extract_clauses(domain_label: str, document_text: str) -> list[Clause]:
    prompt = f"""You are segmenting a {domain_label} into its clauses for review.

Extract EVERY substantive clause/section — do not skip any. A typical multi-page
contract has 15-40 clauses; if you return only a handful you have failed the task.

For each clause:
- id: stable id like "C1", "C2", ...
- heading: the clause's title or topic
- category: short tag (e.g. fees, deposit, termination, liability, entry, insurance)
- text: the clause restated concisely in plain language
- source_excerpt: a short VERBATIM quote (exact words) from this clause

Walk the document top to bottom, in order. Include every numbered/labeled section.
Do NOT invent clauses that aren't present.

Return ONLY the structured JSON.

--- DOCUMENT START ---
{document_text}
--- DOCUMENT END ---
"""
    result: ClauseList = generate_structured(prompt=prompt, schema=ClauseList, temperature=0.0)
    return result.clauses


def _analyze_batch(
    domain_label: str, watch_for: str, typical: str, clauses: list[Clause]
) -> list[Finding]:
    rendered = "\n\n".join(
        f"[{c.id}] {c.heading} (category: {c.category})\n"
        f"  plain: {c.text}\n  verbatim: \"{c.source_excerpt}\""
        for c in clauses
    )
    prompt = f"""You are FinePrint, reviewing clauses of a {domain_label} on behalf of an \
ordinary person about to sign. Examine EACH clause below ON ITS OWN and decide whether it is \
off in a way the reader would regret missing.

For this kind of document, these are commonly TYPICAL/fair (a baseline):
{typical}

And these are things to WATCH FOR (potential red flags):
{watch_for}

For each clause, ask: is it one-sided, a hidden/auto fee, an auto-renewal, an unusual term \
vs. what's typical, a right the reader waives, a coverage gap, ambiguous, or contradictory? \
A clause may yield zero, one, or more findings. A clause that is genuinely standard/fair \
yields none — do not manufacture findings.

EVERY finding MUST be specific and traceable:
- clause_ids: the clause id(s) above it refers to.
- location: the section/clause number (e.g. "§5.1(b)", "Section 7"); use the heading if unnumbered.
- source_quote: a SHORT VERBATIM quote (exact words from the clause), not the blank label of a fill-in field.
- title: name the actual term. GOOD: "Tenant forfeits deposit interest for first 5 years". BAD: "Security Deposit".
- explanation: cite the concrete detail (exact amount, %, days, deadline, who bears the cost). NO "review carefully" filler.
- recommendation: a concrete question or action about THIS clause.

Do NOT invent numbers or quotes. If a fill-in amount is blank, note it's left blank rather than guessing.

Return ONLY the structured JSON.

--- CLAUSES ---
{rendered}
"""
    result: FindingList = generate_structured(prompt=prompt, schema=FindingList, temperature=0.2)
    return result.findings


def _summarize(domain_label: str, findings: list[Finding]) -> str:
    top = "\n".join(f"- [{f.severity.value}] {f.title} ({f.location})" for f in findings[:12])
    prompt = f"""Write a 2-3 sentence plain-English overall read of this {domain_label} for the \
person about to sign, based on these findings. Be specific about the biggest concerns; address \
the reader as "you". If there are no findings, say it looks largely standard.

FINDINGS:
{top or "(none)"}

Return ONLY the structured JSON.
"""
    result: DocSummary = generate_structured(prompt=prompt, schema=DocSummary, temperature=0.3)
    return result.summary


def analyze_document(domain_name: str, document_text: str) -> tuple[AnalysisResult, str]:
    """Map-reduce analysis: extract all clauses, analyze them in focused batches,
    then summarize. Returns (result, model_name)."""
    s = get_settings()
    domain_label, watch_for, typical = _domain_context(domain_name)

    clauses = _extract_clauses(domain_label, document_text)

    findings: list[Finding] = []
    for start in range(0, len(clauses), _BATCH_SIZE):
        batch = clauses[start : start + _BATCH_SIZE]
        findings.extend(_analyze_batch(domain_label, watch_for, typical, batch))

    summary = _summarize(domain_label, findings)

    result = AnalysisResult(summary=summary, clauses=clauses, findings=findings)
    return result, s.active_model()
