"""Formal representation of a policy's rules.

The LLM extracts a document into a RuleSet (typed variables + rules expressed as
logical constraints). The Z3 verifier then reasons over that structure and emits
a ConsistencyReport. Keeping the LLM's job to "prose -> structure" and the logic
to the solver is the whole point: the solver, not the model, makes logical claims.
"""

from enum import Enum

from pydantic import BaseModel, Field


# ---------- LLM extraction contract ----------

class VarType(str, Enum):
    boolean = "boolean"
    integer = "integer"
    real = "real"
    enum = "enum"


class Variable(BaseModel):
    name: str = Field(description="snake_case identifier, e.g. 'age_years', 'deposit_refundable'")
    type: VarType
    unit: str = Field(description="unit for numeric vars, e.g. 'years', 'days', 'usd'; '' if N/A")
    enum_values: list[str] = Field(description="allowed values when type is enum; [] otherwise")
    description: str = Field(description="what this variable means")


class CmpOp(str, Enum):
    eq = "=="
    ne = "!="
    ge = ">="
    gt = ">"
    le = "<="
    lt = "<"


class Atom(BaseModel):
    """A single comparison, e.g. age_years >= 65."""
    var: str = Field(description="name of a declared variable")
    op: CmpOp
    value: str = Field(description="literal: a number, 'true'/'false' for booleans, or an enum value")


class RuleKind(str, Enum):
    fact = "fact"              # always asserted (antecedent empty)
    implication = "implication"  # antecedent -> consequent


class Rule(BaseModel):
    id: str = Field(description="short id like 'R1'")
    source_clause: str = Field(description="verbatim quote or label of the clause this came from")
    description: str = Field(description="plain-language restatement of the rule")
    kind: RuleKind
    antecedent: list[Atom] = Field(description="conditions (ANDed); [] for facts")
    consequent: list[Atom] = Field(description="constraints asserted (ANDed)")


class RuleSet(BaseModel):
    variables: list[Variable]
    rules: list[Rule]


# ---------- verifier output ----------

class Contradiction(BaseModel):
    rule_ids: list[str]
    clauses: list[str]
    explanation: str


class UnreachableRule(BaseModel):
    rule_id: str
    clause: str
    explanation: str


class ConsistencyReport(BaseModel):
    checked: bool = True
    consistent: bool = True
    variables: int = 0
    rules: int = 0
    contradictions: list[Contradiction] = Field(default_factory=list)
    unreachable: list[UnreachableRule] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
