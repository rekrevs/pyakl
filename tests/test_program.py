"""
Tests for program storage and clause compilation.
"""

import pytest
from pathlib import Path

from pyakl.term import Atom, Integer, Struct, Var
from pyakl.parser import parse_term, parse_clause
from pyakl.program import (
    GuardType, Clause, Predicate, Program,
    compile_clause, load_string, load_file
)


class TestCompileClause:
    """Tests for clause compilation."""

    def test_compile_fact_atom(self):
        term = parse_clause("foo.")
        clause = compile_clause(term)
        assert clause.head == Atom("foo")
        assert clause.is_fact
        assert clause.guard is None
        assert clause.guard_type == GuardType.NONE
        assert clause.body == []

    def test_compile_fact_struct(self):
        term = parse_clause("likes(mary, food).")
        clause = compile_clause(term)
        assert isinstance(clause.head, Struct)
        assert clause.head.functor == Atom("likes")
        assert clause.head.arity == 2
        assert clause.is_fact

    def test_compile_simple_rule(self):
        term = parse_clause("mortal(X) :- human(X).")
        clause = compile_clause(term)
        assert isinstance(clause.head, Struct)
        assert clause.head.functor == Atom("mortal")
        assert clause.guard is None
        assert clause.guard_type == GuardType.NONE
        assert len(clause.body) == 1
        assert clause.body[0].functor == Atom("human")

    def test_compile_rule_with_conjunction(self):
        term = parse_clause("grandparent(X, Z) :- parent(X, Y), parent(Y, Z).")
        clause = compile_clause(term)
        assert len(clause.body) == 2
        assert clause.body[0].functor == Atom("parent")
        assert clause.body[1].functor == Atom("parent")

    def test_compile_guard_wait(self):
        term = parse_clause("foo(X) :- bar(X) ? baz(X).")
        clause = compile_clause(term)
        assert clause.guard is not None
        assert clause.guard.functor == Atom("bar")
        assert clause.guard_type == GuardType.WAIT
        assert len(clause.body) == 1
        assert clause.body[0].functor == Atom("baz")

    def test_compile_guard_quiet_wait(self):
        term = parse_clause("member(X, [X|_]) :- ?? true.")
        clause = compile_clause(term)
        assert clause.guard is not None
        assert clause.guard == Atom("true")
        assert clause.guard_type == GuardType.QUIET_WAIT
        assert clause.body == []

    def test_compile_guard_arrow(self):
        term = parse_clause("foo(X) :- test(X) -> action(X).")
        clause = compile_clause(term)
        assert clause.guard is not None
        assert clause.guard_type == GuardType.ARROW
        assert len(clause.body) == 1

    def test_compile_guard_commit(self):
        term = parse_clause("foo(X) :- check(X) | do(X).")
        clause = compile_clause(term)
        assert clause.guard is not None
        assert clause.guard_type == GuardType.COMMIT

    def test_compile_guard_cut(self):
        term = parse_clause("foo(X) :- once(X) ! rest(X).")
        clause = compile_clause(term)
        assert clause.guard is not None
        assert clause.guard_type == GuardType.CUT

    def test_compile_complex_body(self):
        term = parse_clause("foo(X, Y) :- a(X), b(Y), c(X, Y).")
        clause = compile_clause(term)
        assert len(clause.body) == 3

    def test_compile_guard_with_complex_body(self):
        term = parse_clause("foo(X) :- guard(X) ? a(X), b(X), c(X).")
        clause = compile_clause(term)
        assert clause.guard is not None
        assert len(clause.body) == 3

    def test_head_vars(self):
        term = parse_clause("foo(X, Y, X) :- bar(X, Y, Z).")
        clause = compile_clause(term)
        assert clause.head_vars == {"X", "Y"}

    def test_all_vars(self):
        term = parse_clause("foo(X, Y) :- bar(Y, Z).")
        clause = compile_clause(term)
        assert clause.all_vars == {"X", "Y", "Z"}

    def test_functor_and_arity(self):
        term = parse_clause("append([], L, L).")
        clause = compile_clause(term)
        assert clause.functor == Atom("append")
        assert clause.arity == 3


class TestPredicate:
    """Tests for Predicate class."""

    def test_create_predicate(self):
        pred = Predicate("foo", 2)
        assert pred.name == "foo"
        assert pred.arity == 2
        assert len(pred.clauses) == 0

    def test_add_clause(self):
        pred = Predicate("foo", 1)
        clause = compile_clause(parse_clause("foo(a)."))
        pred.add_clause(clause)
        assert len(pred.clauses) == 1

    def test_functor_key(self):
        pred = Predicate("member", 2)
        assert pred.functor_key == ("member", 2)


class TestProgram:
    """Tests for Program class."""

    def test_empty_program(self):
        prog = Program()
        assert len(prog) == 0
        assert prog.lookup("foo", 1) is None

    def test_add_single_clause(self):
        prog = Program()
        clause = compile_clause(parse_clause("foo(a)."))
        prog.add_clause(clause)
        assert len(prog) == 1
        assert ("foo", 1) in prog

    def test_add_multiple_clauses_same_predicate(self):
        prog = Program()
        prog.add_clause(compile_clause(parse_clause("foo(a).")))
        prog.add_clause(compile_clause(parse_clause("foo(b).")))
        prog.add_clause(compile_clause(parse_clause("foo(c).")))
        assert len(prog) == 1  # One predicate
        assert len(prog.get_clauses("foo", 1)) == 3

    def test_add_different_predicates(self):
        prog = Program()
        prog.add_clause(compile_clause(parse_clause("foo(a).")))
        prog.add_clause(compile_clause(parse_clause("bar(b).")))
        assert len(prog) == 2
        assert ("foo", 1) in prog
        assert ("bar", 1) in prog

    def test_different_arities(self):
        prog = Program()
        prog.add_clause(compile_clause(parse_clause("foo(a).")))
        prog.add_clause(compile_clause(parse_clause("foo(a, b).")))
        assert len(prog) == 2  # Different predicates
        assert prog.lookup("foo", 1) is not None
        assert prog.lookup("foo", 2) is not None

    def test_lookup(self):
        prog = Program()
        prog.add_clause(compile_clause(parse_clause("member(X, [X|_]).")))
        prog.add_clause(compile_clause(parse_clause("member(X, [_|T]) :- member(X, T).")))

        pred = prog.lookup("member", 2)
        assert pred is not None
        assert pred.name == "member"
        assert pred.arity == 2
        assert len(pred.clauses) == 2

    def test_get_clauses_not_found(self):
        prog = Program()
        assert prog.get_clauses("nonexistent", 1) == []

    def test_predicates_list(self):
        prog = Program()
        prog.add_clause(compile_clause(parse_clause("foo(a).")))
        prog.add_clause(compile_clause(parse_clause("bar(b).")))
        preds = prog.predicates()
        assert len(preds) == 2


class TestLoadString:
    """Tests for loading programs from strings."""

    def test_load_empty(self):
        prog = load_string("")
        assert len(prog) == 0

    def test_load_facts(self):
        source = """
        likes(mary, food).
        likes(mary, wine).
        likes(john, wine).
        likes(john, mary).
        """
        prog = load_string(source)
        assert len(prog) == 1
        assert len(prog.get_clauses("likes", 2)) == 4

    def test_load_rules(self):
        source = """
        mortal(X) :- human(X).
        human(socrates).
        """
        prog = load_string(source)
        assert len(prog) == 2
        assert len(prog.get_clauses("mortal", 1)) == 1
        assert len(prog.get_clauses("human", 1)) == 1

    def test_load_member(self):
        source = """
        member(X, [X|_]).
        member(X, [_|T]) :- member(X, T).
        """
        prog = load_string(source)
        assert len(prog.get_clauses("member", 2)) == 2

    def test_load_with_guards(self):
        source = """
        qmember(X, [X|_]) :- ?? true.
        qmember(X, [_|T]) :- ?? qmember(X, T).
        """
        prog = load_string(source)
        clauses = prog.get_clauses("qmember", 2)
        assert len(clauses) == 2
        assert clauses[0].guard_type == GuardType.QUIET_WAIT
        assert clauses[1].guard_type == GuardType.QUIET_WAIT

    def test_load_with_comments(self):
        source = """
        % This is a comment
        foo(a).
        /* Block comment */
        foo(b).
        """
        prog = load_string(source)
        assert len(prog.get_clauses("foo", 1)) == 2

    def test_load_append(self):
        source = """
        append([], L, L).
        append([H|T], L, [H|R]) :- append(T, L, R).
        """
        prog = load_string(source)
        clauses = prog.get_clauses("append", 3)
        assert len(clauses) == 2
        assert clauses[0].is_fact
        assert not clauses[1].is_fact

    def test_load_into_existing(self):
        prog = Program()
        prog.add_clause(compile_clause(parse_clause("existing(fact).")))

        load_string("new(fact).", prog)
        assert len(prog) == 2


class TestLoadFile:
    """Tests for loading programs from files."""

    def test_load_member_akl(self):
        path = Path(__file__).parent.parent.parent / "akl-agents" / "demos" / "member.akl"
        if not path.exists():
            pytest.skip("member.akl not found")

        prog = load_file(path)
        assert len(prog) > 0

        # Should have member predicate
        member_clauses = prog.get_clauses("member", 2)
        assert len(member_clauses) >= 2

    def test_load_lists_akl(self):
        path = Path(__file__).parent.parent.parent / "akl-agents" / "demos" / "lists.akl"
        if not path.exists():
            pytest.skip("lists.akl not found")

        prog = load_file(path)
        assert len(prog) > 0

        # Should have reverse predicate
        reverse_clauses = prog.get_clauses("reverse", 3)
        assert len(reverse_clauses) >= 2


class TestGuardExtraction:
    """Tests for guard type extraction."""

    def test_no_guard_fact(self):
        clause = compile_clause(parse_clause("fact."))
        assert clause.guard_type == GuardType.NONE
        assert clause.guard is None

    def test_no_guard_rule(self):
        clause = compile_clause(parse_clause("a :- b."))
        assert clause.guard_type == GuardType.NONE
        assert clause.guard is None

    def test_wait_guard(self):
        clause = compile_clause(parse_clause("a :- g ? b."))
        assert clause.guard_type == GuardType.WAIT

    def test_quiet_wait_guard(self):
        clause = compile_clause(parse_clause("a :- g ?? b."))
        assert clause.guard_type == GuardType.QUIET_WAIT

    def test_arrow_guard(self):
        clause = compile_clause(parse_clause("a :- g -> b."))
        assert clause.guard_type == GuardType.ARROW

    def test_commit_guard(self):
        clause = compile_clause(parse_clause("a :- g | b."))
        assert clause.guard_type == GuardType.COMMIT

    def test_cut_guard(self):
        clause = compile_clause(parse_clause("a :- g ! b."))
        assert clause.guard_type == GuardType.CUT

    def test_guard_is_conjunction(self):
        clause = compile_clause(parse_clause("a :- g1, g2 ? b."))
        assert clause.guard_type == GuardType.WAIT
        # Guard should be the whole conjunction
        assert isinstance(clause.guard, Struct)
        assert clause.guard.functor == Atom(",")
