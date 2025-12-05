"""
Tests for the AKL interpreter.
"""

import pytest
from pathlib import Path

from pyakl.term import Var, Atom, Integer, Float, Struct, Cons, NIL, make_list
from pyakl.parser import parse_term
from pyakl.program import Program, load_string, load_file
from pyakl.interpreter import (
    Interpreter, Solution,
    solve, solve_all, solve_one,
    query, query_all, query_one
)


class TestSolutionRepr:
    """Tests for Solution representation."""

    def test_empty_solution(self):
        sol = Solution({})
        assert str(sol) == "true"

    def test_single_binding(self):
        sol = Solution({"X": Integer(42)})
        assert "X = 42" in str(sol)

    def test_multiple_bindings(self):
        sol = Solution({"X": Integer(1), "Y": Integer(2)})
        s = str(sol)
        assert "X = 1" in s
        assert "Y = 2" in s


class TestBasicFacts:
    """Tests for querying simple facts."""

    def test_single_fact(self):
        prog = load_string("foo.")
        sols = query_all(prog, "foo")
        assert len(sols) == 1

    def test_fact_with_arg(self):
        prog = load_string("foo(a).")
        sols = query_all(prog, "foo(a)")
        assert len(sols) == 1

    def test_fact_mismatch(self):
        prog = load_string("foo(a).")
        sols = query_all(prog, "foo(b)")
        assert len(sols) == 0

    def test_fact_with_var(self):
        prog = load_string("foo(hello).")
        sols = query_all(prog, "foo(X)")
        assert len(sols) == 1
        assert sols[0].bindings.get("X") == Atom("hello")

    def test_multiple_facts(self):
        prog = load_string("""
            foo(a).
            foo(b).
            foo(c).
        """)
        sols = query_all(prog, "foo(X)")
        assert len(sols) == 3
        values = [sol.bindings["X"] for sol in sols]
        assert Atom("a") in values
        assert Atom("b") in values
        assert Atom("c") in values

    def test_two_arg_fact(self):
        prog = load_string("likes(mary, food).")
        sols = query_all(prog, "likes(X, Y)")
        assert len(sols) == 1
        assert sols[0].bindings["X"] == Atom("mary")
        assert sols[0].bindings["Y"] == Atom("food")


class TestSimpleRules:
    """Tests for simple rules (Horn clauses)."""

    def test_simple_rule(self):
        prog = load_string("""
            human(socrates).
            mortal(X) :- human(X).
        """)
        sols = query_all(prog, "mortal(socrates)")
        assert len(sols) == 1

    def test_rule_with_var(self):
        prog = load_string("""
            human(socrates).
            human(plato).
            mortal(X) :- human(X).
        """)
        sols = query_all(prog, "mortal(Who)")
        assert len(sols) == 2

    def test_chain_rule(self):
        prog = load_string("""
            parent(tom, bob).
            parent(bob, pat).
            grandparent(X, Z) :- parent(X, Y), parent(Y, Z).
        """)
        sols = query_all(prog, "grandparent(tom, pat)")
        assert len(sols) == 1

    def test_chain_with_var(self):
        prog = load_string("""
            parent(tom, bob).
            parent(tom, liz).
            parent(bob, pat).
            parent(liz, ann).
            grandparent(X, Z) :- parent(X, Y), parent(Y, Z).
        """)
        sols = query_all(prog, "grandparent(tom, Who)")
        assert len(sols) == 2
        grandchildren = [sol.bindings["Who"] for sol in sols]
        assert Atom("pat") in grandchildren
        assert Atom("ann") in grandchildren


class TestRecursion:
    """Tests for recursive predicates."""

    def test_member(self):
        prog = load_string("""
            member(X, [X|_]).
            member(X, [_|T]) :- member(X, T).
        """)
        sols = query_all(prog, "member(2, [1,2,3])")
        assert len(sols) == 1

    def test_member_not_found(self):
        prog = load_string("""
            member(X, [X|_]).
            member(X, [_|T]) :- member(X, T).
        """)
        sols = query_all(prog, "member(4, [1,2,3])")
        assert len(sols) == 0

    def test_member_enumerate(self):
        prog = load_string("""
            member(X, [X|_]).
            member(X, [_|T]) :- member(X, T).
        """)
        sols = query_all(prog, "member(X, [a,b,c])")
        assert len(sols) == 3
        values = [sol.bindings["X"] for sol in sols]
        assert Atom("a") in values
        assert Atom("b") in values
        assert Atom("c") in values

    def test_append(self):
        prog = load_string("""
            append([], L, L).
            append([H|T], L, [H|R]) :- append(T, L, R).
        """)
        # Test concatenation
        sols = query_all(prog, "append([1,2], [3,4], X)")
        assert len(sols) == 1
        # Check result is [1,2,3,4]
        result = sols[0].bindings["X"]
        assert isinstance(result, Cons)

    def test_append_split(self):
        prog = load_string("""
            append([], L, L).
            append([H|T], L, [H|R]) :- append(T, L, R).
        """)
        # Split [1,2,3] into X and Y
        sols = query_all(prog, "append(X, Y, [1,2,3])")
        # Should give 4 solutions: []/[1,2,3], [1]/[2,3], [1,2]/[3], [1,2,3]/[]
        assert len(sols) == 4

    def test_length(self):
        prog = load_string("""
            len([], 0).
            len([_|T], N) :- len(T, M), N is M + 1.
        """)
        sols = query_all(prog, "len([a,b,c], X)")
        assert len(sols) == 1
        assert sols[0].bindings["X"] == Integer(3)

    def test_reverse(self):
        prog = load_string("""
            reverse(L, R) :- reverse(L, [], R).
            reverse([], Acc, Acc).
            reverse([H|T], Acc, R) :- reverse(T, [H|Acc], R).
        """)
        sols = query_all(prog, "reverse([1,2,3], X)")
        assert len(sols) == 1


class TestBuiltins:
    """Tests for built-in predicates."""

    def test_true(self):
        prog = load_string("")
        sols = query_all(prog, "true")
        assert len(sols) == 1

    def test_fail(self):
        prog = load_string("")
        sols = query_all(prog, "fail")
        assert len(sols) == 0

    def test_unify(self):
        prog = load_string("")
        sols = query_all(prog, "X = 42")
        assert len(sols) == 1
        assert sols[0].bindings["X"] == Integer(42)

    def test_arithmetic(self):
        prog = load_string("")
        sols = query_all(prog, "X is 2 + 3 * 4")
        assert len(sols) == 1
        assert sols[0].bindings["X"] == Integer(14)

    def test_comparison(self):
        prog = load_string("")
        sols = query_all(prog, "3 < 5")
        assert len(sols) == 1
        sols = query_all(prog, "5 < 3")
        assert len(sols) == 0

    def test_var_check(self):
        prog = load_string("")
        sols = query_all(prog, "var(X)")
        assert len(sols) == 1

    def test_atom_check(self):
        prog = load_string("")
        sols = query_all(prog, "atom(foo)")
        assert len(sols) == 1
        sols = query_all(prog, "atom(42)")
        assert len(sols) == 0


class TestConjunctionDisjunction:
    """Tests for conjunction and disjunction."""

    def test_conjunction_success(self):
        prog = load_string("""
            a(1).
            b(2).
        """)
        sols = query_all(prog, "a(X), b(Y)")
        assert len(sols) == 1
        assert sols[0].bindings["X"] == Integer(1)
        assert sols[0].bindings["Y"] == Integer(2)

    def test_conjunction_fail_first(self):
        prog = load_string("""
            b(2).
        """)
        sols = query_all(prog, "a(X), b(Y)")
        assert len(sols) == 0

    def test_conjunction_fail_second(self):
        prog = load_string("""
            a(1).
        """)
        sols = query_all(prog, "a(X), b(Y)")
        assert len(sols) == 0

    def test_disjunction(self):
        prog = load_string("""
            a(1).
            b(2).
        """)
        sols = query_all(prog, "(a(X) ; b(X))")
        assert len(sols) == 2


class TestNegation:
    """Tests for negation as failure."""

    def test_negation_success(self):
        prog = load_string("")
        sols = query_all(prog, "\\+(fail)")
        assert len(sols) == 1

    def test_negation_fail(self):
        prog = load_string("")
        sols = query_all(prog, "\\+(true)")
        assert len(sols) == 0

    def test_negation_not_member(self):
        prog = load_string("""
            member(X, [X|_]).
            member(X, [_|T]) :- member(X, T).
        """)
        sols = query_all(prog, "\\+(member(4, [1,2,3]))")
        assert len(sols) == 1

    def test_negation_no_binding(self):
        prog = load_string("""
            foo(a).
        """)
        # X should remain unbound after negation check
        sols = query_all(prog, "\\+(foo(b))")
        assert len(sols) == 1


class TestLoadFile:
    """Tests for loading programs from files."""

    def test_load_member_akl(self):
        path = Path(__file__).parent.parent.parent / "akl-agents" / "demos" / "member.akl"
        if not path.exists():
            pytest.skip("member.akl not found")

        prog = load_file(path)
        sols = query_all(prog, "member(2, [1,2,3])")
        assert len(sols) >= 1


class TestInterpreterClass:
    """Tests for Interpreter class."""

    def test_solve_generator(self):
        prog = load_string("""
            foo(a).
            foo(b).
        """)
        interp = Interpreter(prog)
        goal = parse_term("foo(X)")
        count = 0
        for sol in interp.solve(goal):
            count += 1
        assert count == 2

    def test_solve_one(self):
        prog = load_string("""
            foo(a).
            foo(b).
        """)
        interp = Interpreter(prog)
        goal = parse_term("foo(X)")
        sol = interp.solve_one(goal)
        assert sol is not None
        assert sol.bindings["X"] == Atom("a")

    def test_solve_all(self):
        prog = load_string("""
            foo(a).
            foo(b).
        """)
        interp = Interpreter(prog)
        goal = parse_term("foo(X)")
        sols = interp.solve_all(goal)
        assert len(sols) == 2

    def test_no_solution(self):
        prog = load_string("foo(a).")
        sol = query_one(prog, "foo(b)")
        assert sol is None


class TestGuardedClauses:
    """Tests for guarded clauses (basic support)."""

    def test_quiet_wait_guard(self):
        # Basic test that guarded clauses can be executed
        prog = load_string("""
            qmember(X, [X|_]) :- ?? true.
            qmember(X, [_|T]) :- ?? qmember(X, T).
        """)
        sols = query_all(prog, "qmember(2, [1,2,3])")
        assert len(sols) == 1

    def test_arrow_guard(self):
        prog = load_string("""
            abs(X, R) :- X >= 0 -> R = X.
            abs(X, R) :- X < 0 -> R is -X.
        """)
        sols = query_all(prog, "abs(5, R)")
        assert len(sols) == 1
        assert sols[0].bindings["R"] == Integer(5)

        sols = query_all(prog, "abs(-3, R)")
        assert len(sols) == 1
        assert sols[0].bindings["R"] == Integer(3)


class TestUnderscoreVars:
    """Tests for anonymous variables."""

    def test_underscore_not_in_solution(self):
        prog = load_string("foo(a, b).")
        sols = query_all(prog, "foo(X, _)")
        assert len(sols) == 1
        assert "X" in sols[0].bindings
        assert "_" not in sols[0].bindings

    def test_multiple_underscores(self):
        prog = load_string("""
            pair(1, a).
            pair(2, b).
        """)
        sols = query_all(prog, "pair(_, _)")
        assert len(sols) == 2


class TestComplexQueries:
    """Tests for more complex queries."""

    def test_fibonacci(self):
        prog = load_string("""
            fib(0, 0).
            fib(1, 1).
            fib(N, F) :-
                N > 1,
                N1 is N - 1,
                N2 is N - 2,
                fib(N1, F1),
                fib(N2, F2),
                F is F1 + F2.
        """)
        sols = query_all(prog, "fib(6, F)")
        assert len(sols) == 1
        assert sols[0].bindings["F"] == Integer(8)

    def test_factorial(self):
        prog = load_string("""
            fact(0, 1).
            fact(N, F) :-
                N > 0,
                N1 is N - 1,
                fact(N1, F1),
                F is N * F1.
        """)
        sols = query_all(prog, "fact(5, F)")
        assert len(sols) == 1
        assert sols[0].bindings["F"] == Integer(120)

    def test_quicksort(self):
        prog = load_string("""
            qsort([], []).
            qsort([H|T], S) :-
                partition(H, T, L, G),
                qsort(L, SL),
                qsort(G, SG),
                append(SL, [H|SG], S).

            partition(_, [], [], []).
            partition(P, [H|T], [H|L], G) :-
                H =< P,
                partition(P, T, L, G).
            partition(P, [H|T], L, [H|G]) :-
                H > P,
                partition(P, T, L, G).

            append([], L, L).
            append([H|T], L, [H|R]) :- append(T, L, R).
        """)
        sols = query_all(prog, "qsort([3,1,4,1,5,9,2,6], S)")
        assert len(sols) == 1
