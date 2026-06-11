"""Deterministic tests for the Z3 consistency engine — no LLM/API involved.

These pin the solver's behavior independent of extraction quality: hand-built
rule sets with known logical structure must produce known verdicts.
"""

from app.formal_schemas import Atom, Rule, RuleSet, Variable
from app.verify import check_consistency


def _atom(var, op, value):
    return Atom(var=var, op=op, value=value)


def _var(name, type_, unit="", enum_values=None):
    return Variable(name=name, type=type_, unit=unit, enum_values=enum_values or [], description="")


def _fact(rid, cons, clause="c"):
    return Rule(id=rid, source_clause=clause, description="", kind="fact", antecedent=[], consequent=cons)


def _impl(rid, ant, cons, clause="c"):
    return Rule(id=rid, source_clause=clause, description="", kind="implication", antecedent=ant, consequent=cons)


def test_direct_fact_contradiction():
    rs = RuleSet(
        variables=[_var("deposit_refundable", "boolean")],
        rules=[
            _fact("R1", [_atom("deposit_refundable", "==", "true")]),
            _fact("R2", [_atom("deposit_refundable", "==", "false")]),
        ],
    )
    rep = check_consistency(rs)
    assert rep.consistent is False
    assert len(rep.contradictions) == 1
    assert set(rep.contradictions[0].rule_ids) == {"R1", "R2"}


def test_conditional_contradiction():
    # Same trigger (age>=65), opposite consequences -> conflict.
    rs = RuleSet(
        variables=[_var("age_years", "integer", "years"), _var("eligible", "boolean")],
        rules=[
            _impl("R1", [_atom("age_years", ">=", "65")], [_atom("eligible", "==", "true")]),
            _impl("R2", [_atom("age_years", ">=", "65")], [_atom("eligible", "==", "false")]),
        ],
    )
    rep = check_consistency(rs)
    assert rep.consistent is False
    assert {tuple(sorted(c.rule_ids)) for c in rep.contradictions} == {("R1", "R2")}


def test_non_overlapping_conditions_do_not_conflict():
    # Opposite consequences but mutually-exclusive triggers -> NO conflict.
    rs = RuleSet(
        variables=[_var("age_years", "integer", "years"), _var("eligible", "boolean")],
        rules=[
            _impl("R1", [_atom("age_years", ">=", "65")], [_atom("eligible", "==", "true")]),
            _impl("R2", [_atom("age_years", "<", "65")], [_atom("eligible", "==", "false")]),
        ],
    )
    rep = check_consistency(rs)
    assert rep.consistent is True
    assert rep.contradictions == []


def test_unreachable_clause():
    # Fact fixes plan to premium; a clause conditioned on plan==basic can never apply.
    rs = RuleSet(
        variables=[_var("plan", "enum", enum_values=["basic", "premium"]), _var("rebate", "boolean")],
        rules=[
            _fact("F1", [_atom("plan", "==", "premium")]),
            _impl("R1", [_atom("plan", "==", "basic")], [_atom("rebate", "==", "true")]),
        ],
    )
    rep = check_consistency(rs)
    assert rep.consistent is True  # no contradiction (R1 just never fires)
    assert [u.rule_id for u in rep.unreachable] == ["R1"]


def test_clean_policy_is_consistent():
    rs = RuleSet(
        variables=[_var("age_years", "integer", "years"), _var("can_apply", "boolean")],
        rules=[
            _impl("R1", [_atom("age_years", ">=", "18")], [_atom("can_apply", "==", "true")]),
            _fact("R2", [_atom("age_years", ">=", "0")]),
        ],
    )
    rep = check_consistency(rs)
    assert rep.consistent is True
    assert rep.contradictions == []
    assert rep.unreachable == []
