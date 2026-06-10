"""Pydantic schemas — also used as the LLM structured-output contract."""

from enum import Enum

from pydantic import BaseModel, Field


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
    type: FindingType
    severity: Severity
    title: str = Field(description="One-line summary of what's off.")
    explanation: str = Field(description="Plain-English why-this-matters, addressed to the person signing.")
    recommendation: str = Field(description="What the reader should do or ask about.")


class AnalysisResult(BaseModel):
    summary: str = Field(description="2-3 sentence overall read on the document.")
    clauses: list[Clause]
    findings: list[Finding]


class AnalysisResponse(BaseModel):
    """What the API returns to the client."""
    document_name: str
    domain: str
    model: str
    extraction_method: str  # "native" | "ocr" | "native+ocr"
    result: AnalysisResult
