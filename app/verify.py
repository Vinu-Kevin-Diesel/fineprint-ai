"""Z3-backed consistency checking over an extracted RuleSet.

What the solver proves:
  - CONTRADICTIONS (pairwise): two clauses whose conditions CAN hold together
    (A_i ∧ A_j is satisfiable) but whose consequences are then incompatible
    (A_i ∧ A_j ∧ C_i ∧ C_j is unsatisfiable). This is the right test for policy
    conflicts — a plain "is everything satisfiable?" check misses them, because
    implications are vacuously satisfiable by never triggering their condition.
  - UNREACHABLE RULES: an implication whose condition is impossible on its own or
    given the always-true facts — a clause that can never apply (dead logic).

The LLM never decides any of this; it only produced the typed rules. Every claim
below is a theorem proved by Z3.

Limitation (documented on purpose): contradiction detection is pairwise, so a
conflict that only emerges from 3+ clauses jointly is not reported.
"""

from dataclasses import dataclass

import z3

from .formal_schemas import (
    Atom,
    ConsistencyReport,
    Contradiction,
    Rule,
    RuleSet,
    UnreachableRule,
)


class _SkipAtom(Exception):
    """An atom that can't be compiled (unknown var / bad value / type mismatch)."""


@dataclass
class _CompiledRule:
    rule: Rule
    consequent: z3.BoolRef          # the asserted constraint (ANDed atoms)
    antecedent: z3.BoolRef | None   # the condition; None for facts (always apply)


def _atom_str(a: Atom) -> str:
    return f"{a.var} {a.op.value} {a.value}"


def _rule_str(rule: Rule) -> str:
    cons = " AND ".join(_atom_str(a) for a in rule.consequent) or "true"
    if rule.kind.value == "implication" and rule.antecedent:
        ant = " AND ".join(_atom_str(a) for a in rule.antecedent)
        return f"IF ({ant}) THEN ({cons})"
    return cons


def _build_variables(rs: RuleSet, notes: list[str]):
    z3vars: dict[str, z3.ExprRef] = {}
    vartype: dict[str, str] = {}
    enum_consts: dict[str, dict[str, z3.ExprRef]] = {}
    for v in rs.variables:
        t = v.type.value
        vartype[v.name] = t
        if t == "boolean":
            z3vars[v.name] = z3.Bool(v.name)
        elif t == "integer":
            z3vars[v.name] = z3.Int(v.name)
        elif t == "real":
            z3vars[v.name] = z3.Real(v.name)
        elif t == "enum":
            if not v.enum_values:
                notes.append(f"enum variable '{v.name}' has no values; skipped")
                continue
            sort, consts = z3.EnumSort(f"{v.name}_sort", list(v.enum_values))
            z3vars[v.name] = z3.Const(v.name, sort)
            enum_consts[v.name] = dict(zip(v.enum_values, consts))
    return z3vars, vartype, enum_consts


def _atom_to_z3(a: Atom, z3vars, vartype, enum_consts) -> z3.BoolRef:
    if a.var not in z3vars:
        raise _SkipAtom(f"unknown variable '{a.var}'")
    var = z3vars[a.var]
    t = vartype[a.var]
    op = a.op.value

    if t == "boolean":
        truthy = a.value.strip().lower() in ("true", "1", "yes")
        rhs = z3.BoolVal(truthy)
        if op == "==":
            return var == rhs
        if op == "!=":
            return var != rhs
        raise _SkipAtom(f"operator {op} not valid on boolean '{a.var}'")

    if t in ("integer", "real"):
        try:
            num = float(a.value)
        except ValueError:
            raise _SkipAtom(f"non-numeric value '{a.value}' for '{a.var}'")
        rhs = z3.IntVal(int(num)) if t == "integer" else z3.RealVal(num)
        return {
            "==": var == rhs, "!=": var != rhs,
            ">=": var >= rhs, ">": var > rhs,
            "<=": var <= rhs, "<": var < rhs,
        }[op]

    if t == "enum":
        consts = enum_consts.get(a.var, {})
        if a.value not in consts:
            raise _SkipAtom(f"value '{a.value}' not in enum '{a.var}'")
        rhs = consts[a.value]
        if op == "==":
            return var == rhs
        if op == "!=":
            return var != rhs
        raise _SkipAtom(f"operator {op} not valid on enum '{a.var}'")

    raise _SkipAtom(f"unknown type for '{a.var}'")


def _compile_atoms(atoms, z3vars, vartype, enum_consts, notes, rule_id):
    out = []
    for a in atoms:
        try:
            out.append(_atom_to_z3(a, z3vars, vartype, enum_consts))
        except _SkipAtom as e:
            notes.append(f"rule {rule_id}: dropped atom ({e})")
    return out


def _conj(exprs):
    if not exprs:
        return None
    return exprs[0] if len(exprs) == 1 else z3.And(*exprs)


def _compile_rules(rs: RuleSet, z3vars, vartype, enum_consts, notes) -> list[_CompiledRule]:
    compiled: list[_CompiledRule] = []
    for rule in rs.rules:
        cons = _compile_atoms(rule.consequent, z3vars, vartype, enum_consts, notes, rule.id)
        cons_expr = _conj(cons)
        if cons_expr is None:
            notes.append(f"rule {rule.id}: no usable consequent; skipped")
            continue

        antecedent = None
        if rule.kind.value == "implication" and rule.antecedent:
            ant = _compile_atoms(rule.antecedent, z3vars, vartype, enum_consts, notes, rule.id)
            antecedent = _conj(ant)
        compiled.append(_CompiledRule(rule, cons_expr, antecedent))
    return compiled


def _unsat(*constraints) -> bool:
    s = z3.Solver()
    s.add(*constraints)
    return s.check() == z3.unsat


def _sat(*constraints) -> bool:
    s = z3.Solver()
    s.add(*constraints)
    return s.check() == z3.sat


def _fact_conflicts(facts: list[_CompiledRule]):
    """Facts always hold, so two facts conflict iff their consequents are jointly unsat."""
    found: list[Contradiction] = []
    conflicting_ids: set[str] = set()
    for i in range(len(facts)):
        for j in range(i + 1, len(facts)):
            a, b = facts[i], facts[j]
            if _unsat(a.consequent, b.consequent):
                found.append(Contradiction(
                    rule_ids=[a.rule.id, b.rule.id],
                    clauses=[a.rule.source_clause, b.rule.source_clause],
                    explanation=(
                        "These fixed terms conflict — they can never both hold. "
                        f"[{a.rule.id}] {_rule_str(a.rule)}  vs.  [{b.rule.id}] {_rule_str(b.rule)}."
                    ),
                ))
                conflicting_ids |= {a.rule.id, b.rule.id}
    return found, conflicting_ids


def _safe_background(facts: list[_CompiledRule], conflicting_ids: set[str]) -> z3.BoolRef:
    """A satisfiable conjunction of the non-conflicting facts — the constraints that
    genuinely always hold, used to gate which rule conditions are reachable."""
    exprs = [c.consequent for c in facts if c.rule.id not in conflicting_ids]
    bg = _conj(exprs)
    if bg is None or not _sat(bg):
        return z3.BoolVal(True)
    return bg


def _impl_conflicts(impls: list[_CompiledRule], bg: z3.BoolRef) -> list[Contradiction]:
    found: list[Contradiction] = []

    # A single rule that contradicts the fixed terms whenever its condition is met.
    for c in impls:
        if not _sat(bg, c.antecedent):
            continue  # condition unreachable given fixed terms -> dead, not contradictory
        if _unsat(bg, c.antecedent, c.consequent):
            found.append(Contradiction(
                rule_ids=[c.rule.id],
                clauses=[c.rule.source_clause],
                explanation=(
                    f"This clause contradicts the policy's fixed terms whenever it applies: "
                    f"[{c.rule.id}] {_rule_str(c.rule)}."
                ),
            ))

    # Two rules whose conditions can co-occur (respecting fixed terms) but whose
    # consequences are then jointly impossible.
    for i in range(len(impls)):
        for j in range(i + 1, len(impls)):
            a, b = impls[i], impls[j]
            trigger = z3.And(bg, a.antecedent, b.antecedent)
            if not _sat(trigger):
                continue  # conditions can't both occur -> no conflict
            if _unsat(trigger, a.consequent, b.consequent):
                found.append(Contradiction(
                    rule_ids=[a.rule.id, b.rule.id],
                    clauses=[a.rule.source_clause, b.rule.source_clause],
                    explanation=(
                        "These two clauses conflict — when both apply, their requirements "
                        f"can't both be met. [{a.rule.id}] {_rule_str(a.rule)}  vs.  "
                        f"[{b.rule.id}] {_rule_str(b.rule)}."
                    ),
                ))
    return found


def _find_contradictions(compiled: list[_CompiledRule]) -> list[Contradiction]:
    facts = [c for c in compiled if c.antecedent is None]
    impls = [c for c in compiled if c.antecedent is not None]
    fact_found, conflicting_ids = _fact_conflicts(facts)
    bg = _safe_background(facts, conflicting_ids)
    return fact_found + _impl_conflicts(impls, bg)


def _find_unreachable(compiled: list[_CompiledRule]) -> list[UnreachableRule]:
    """A conditional rule is unreachable if its condition is impossible on its own
    or given the always-true facts of the policy."""
    facts = [c.consequent for c in compiled if c.antecedent is None]
    background = _conj(facts)
    if background is None:
        background = z3.BoolVal(True)

    out: list[UnreachableRule] = []
    for c in compiled:
        if c.antecedent is None:
            continue
        s = z3.Solver()
        s.add(background, c.antecedent)
        if s.check() == z3.unsat:
            out.append(UnreachableRule(
                rule_id=c.rule.id,
                clause=c.rule.source_clause,
                explanation=(
                    f"This clause can never apply: its condition "
                    f"({_rule_str(c.rule)}) is impossible given the policy's fixed terms."
                ),
            ))
    return out


def check_consistency(rs: RuleSet) -> ConsistencyReport:
    notes: list[str] = []
    z3vars, vartype, enum_consts = _build_variables(rs, notes)
    compiled = _compile_rules(rs, z3vars, vartype, enum_consts, notes)

    report = ConsistencyReport(
        checked=True,
        variables=len(rs.variables),
        rules=len(rs.rules),
        notes=notes,
    )
    if not compiled:
        report.notes.append("No formalizable rules were extracted; nothing to verify.")
        return report

    report.contradictions = _find_contradictions(compiled)
    report.consistent = not report.contradictions

    # Reachability is only meaningful on an otherwise-consistent policy: if the
    # fixed terms already conflict, every conditional clause looks "unreachable".
    if report.consistent:
        report.unreachable = _find_unreachable(compiled)
    else:
        report.notes.append(
            "Skipped unreachable-clause analysis because the policy has contradictions."
        )
    return report
