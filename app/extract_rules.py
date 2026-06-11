"""Extract a formal RuleSet from policy prose using the LLM.

The model's only job is translation: turn natural-language clauses into typed
variables and logical rules. It must NOT decide whether the rules conflict —
that's Z3's job. Consistency across clauses (same concept -> same variable,
same unit) is what makes the downstream solving meaningful, so the prompt
pushes hard on that.
"""

from google.genai import types

from .config import get_settings
from .genai_client import generate_with_retry
from .formal_schemas import RuleSet

_EXTRACTION_PROMPT = """You translate policy/contract text into a FORMAL rule set for a logic solver.
Do NOT judge whether rules conflict — only faithfully encode what the text says.

Output a JSON object with two lists: `variables` and `rules`.

VARIABLES — the measurable quantities and yes/no facts the rules talk about:
- name: snake_case (e.g. age_years, tenure_months, deposit_refundable, plan_tier)
- type: boolean | integer | real | enum (use enum for categorical values; give enum_values)
- unit: for numeric vars give a single canonical unit (e.g. days, months, years, usd)

RULES — encode each substantive clause as either:
- a "fact": something always asserted (antecedent empty), e.g. deposit_refundable == false
- an "implication": antecedent (conditions, ANDed) -> consequent (asserted constraints, ANDed)
Each atom is one comparison: {var, op (== != >= > <= <), value}.

CRITICAL RULES FOR A USABLE ENCODING:
1. SAME CONCEPT -> SAME VARIABLE. If two clauses both talk about tenure, age, a
   deposit being refundable, eligibility, etc., they MUST use the exact same variable
   name. This is essential — the solver can only find a conflict if both clauses
   reference one shared variable.
2. NORMALIZE UNITS. Convert everything about one concept to one unit before writing
   atoms. "less than 1 year" and "at least 24 months" about the same variable must be
   written in the same unit (e.g. tenure_months < 12 and tenure_months >= 24).
3. Booleans use value "true"/"false". Enums use one of the declared enum_values.
4. Only encode clauses that express a checkable condition or constraint. Skip pure prose.
5. Keep source_clause to a short verbatim quote so a human can trace the rule.
6. REQUIREMENT direction matters. A clause like "to qualify for BENEFIT a member MUST
   have CONDITION" or "BENEFIT is available ONLY IF CONDITION" means the benefit IMPLIES
   the requirement: antecedent [benefit == true] -> consequent [CONDITION]. (So two
   clauses stating different required values for the same benefit will conflict when the
   benefit is granted.) In contrast, "if CONDITION then BENEFIT" is the opposite
   direction: antecedent [CONDITION] -> consequent [benefit == true]. Encode faithfully.

Return ONLY the structured JSON.

--- DOCUMENT START ---
{document_text}
--- DOCUMENT END ---
"""


def extract_ruleset(document_text: str) -> RuleSet:
    s = get_settings()
    response = generate_with_retry(
        model=s.gemini_model,
        contents=_EXTRACTION_PROMPT.replace("{document_text}", document_text),
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=RuleSet,
            temperature=0.0,
        ),
    )
    return response.parsed
