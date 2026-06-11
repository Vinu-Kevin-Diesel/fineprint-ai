"""Pydantic schemas — also used as the LLM structured-output contract."""

from enum import Enum

from pydantic import BaseModel, Field

from .formal_schemas import ConsistencyReport


class Severity(str, Enum):
    low = "low"
    medium = "medium"
    high = "high"


class FindingType(str, Enum):
    contradiction = "contradiction"        # two clauses conflict (Mode A territory)
    one_sided = "one_sided"                # heavily favors the other party
    hidden_fee = "hidden_fee"              # cost that's easy to miss
    auto_renewal = "auto_renewal"          # renews/charges unless you act
    unusual_term = "unusual_term"          # deviates from what's typical
    waived_right = "waived_right"          # you give up a normal protection
    coverage_gap = "coverage_gap"          # something important left unaddressed
    ambiguous = "ambiguous"                # vague wording that could be exploited


class Clause(BaseModel):
    id: str = Field(description="Stable id, e.g. 'C1', 'C2'.")
    heading: str = Field(description="Short label for the clause, e.g. 'Security Deposit'.")
    text: str = Field(description="The clause restated concisely in plain language.")
    category: str = Field(description="Domain category, e.g. 'fees', 'termination', 'liability'.")
    source_excerpt: str = Field(description="A short verbatim quote from the document this came from.")


class Finding(BaseModel):
    clause_ids: list[str] = Field(description="Clause id(s) this finding refers to.")
    location: str = Field(
        description="Where in the document this is, e.g. a section/clause number like '§5.1(b)' or 'Section 7'. Use '' only if truly unlabeled."
    )
    source_quote: str = Field(
        description="A short VERBATIM quote (max ~25 words) from the document that supports this finding. Must be copied exactly, not paraphrased."
    )
    type: FindingType
    severity: Severity
    title: str = Field(description="Specific one-line summary naming the actual term (e.g. 'Deposit interest forfeited for first 5 years'), not a generic label.")
    explanation: str = Field(
        description="Why this matters to the person signing, citing the concrete detail (exact amount, deadline, %, who bears it). No generic 'review carefully' filler."
    )
    recommendation: str = Field(description="A specific action or question to raise about THIS clause.")


class AnalysisResult(BaseModel):
    summary: str = Field(description="2-3 sentence overall read on the document.")
    clauses: list[Clause]
    findings: list[Finding]


# --- intermediate structured-output contracts for the map-reduce pipeline ---

class ClauseList(BaseModel):
    clauses: list[Clause]


class FindingList(BaseModel):
    findings: list[Finding]


class DocSummary(BaseModel):
    summary: str = Field(description="2-3 sentence plain-English read on the document overall.")


class AnalysisResponse(BaseModel):
    """What the API returns to the client."""
    document_name: str
    domain: str
    model: str
    extraction_method: str  # "native" | "ocr" | "native+ocr"
    result: AnalysisResult
    consistency: ConsistencyReport | None = None  # Z3 formal verification (Mode A)
