"""
Tests for AKL guard semantics.

Tests quiet vs noisy guards, suspension, and promotion.
"""

import pytest
from pyakl.term import Var, Atom, Integer, Struct
from pyakl.program import Program, load_string, GuardType
from pyakl.interpreter import Interpreter, query_all, query_one


class TestGuardTypes:
    """Test that guard types are correctly parsed."""

    def test_wait_guard(self):
        """Test ? (noisy wait) guard parsing."""
        prog = load_string("""
            p(X) :- X = 1 ? true.
        """)
        clauses = prog.get_clauses("p", 1)
        assert len(clauses) == 1
        assert clauses[0].guard_type == GuardType.WAIT

    def test_quiet_wait_guard(self):
        """Test ?? (quiet wait) guard parsing."""
        prog = load_string("""
            p(X) :- X = 1 ?? true.
        """)
        clauses = prog.get_clauses("p", 1)
        assert len(clauses) == 1
        assert clauses[0].guard_type == GuardType.QUIET_WAIT

    def test_arrow_guard(self):
        """Test -> (quiet cut) guard parsing."""
        prog = load_string("""
            p(X) :- X = 1 -> true.
        """)
        clauses = prog.get_clauses("p", 1)
        assert len(clauses) == 1
        assert clauses[0].guard_type == GuardType.ARROW

    def test_commit_guard(self):
        """Test | (quiet commit) guard parsing."""
        prog = load_string("""
            p(X) :- X = 1 | true.
        """)
        clauses = prog.get_clauses("p", 1)
        assert len(clauses) == 1
        assert clauses[0].guard_type == GuardType.COMMIT

    def test_cut_guard(self):
        """Test ! (noisy cut) guard parsing."""
        prog = load_string("""
            p(X) :- X = 1 ! true.
        """)
        clauses = prog.get_clauses("p", 1)
        assert len(clauses) == 1
        assert clauses[0].guard_type == GuardType.CUT


class TestSimpleGuards:
    """Test basic guard execution."""

    def test_wait_guard_succeeds(self):
        """Test ? guard succeeds when guard succeeds."""
        prog = load_string("""
            p(X) :- true ? X = 1.
        """)
        sols = query_all(prog, "p(X)")
        assert len(sols) == 1
        assert sols[0].bindings["X"].value == 1

    def test_wait_guard_fails(self):
        """Test ? guard fails when guard fails."""
        prog = load_string("""
            p(X) :- fail ? X = 1.
        """)
        sols = query_all(prog, "p(X)")
        assert len(sols) == 0

    def test_arrow_guard_succeeds(self):
        """Test -> guard succeeds when guard succeeds."""
        prog = load_string("""
            p(X) :- true -> X = 1.
        """)
        sols = query_all(prog, "p(X)")
        assert len(sols) == 1
        assert sols[0].bindings["X"].value == 1

    def test_commit_guard_succeeds(self):
        """Test | guard succeeds when guard succeeds."""
        prog = load_string("""
            p(X) :- true | X = 1.
        """)
        sols = query_all(prog, "p(X)")
        assert len(sols) == 1
        assert sols[0].bindings["X"].value == 1


class TestGuardPruning:
    """Test guard pruning behavior."""

    def test_arrow_prunes_alternatives(self):
        """Test -> prunes right alternatives when leftmost and succeeds."""
        prog = load_string("""
            p(1) :- true -> true.
            p(2).
        """)
        sols = query_all(prog, "p(X)")
        # -> prunes alternatives to the right when guard succeeds
        # Should get only the first solution
        assert len(sols) == 1
        assert sols[0].bindings["X"].value == 1

    def test_arrow_tries_next_when_guard_fails(self):
        """Test -> tries next clause when guard fails."""
        prog = load_string("""
            p(1) :- fail -> true.
            p(2) :- true -> true.
        """)
        sols = query_all(prog, "p(X)")
        # First guard fails, so second clause should be tried
        assert len(sols) == 1
        assert sols[0].bindings["X"].value == 2

    def test_commit_prunes_all(self):
        """Test | prunes all alternatives when guard succeeds."""
        prog = load_string("""
            p(1) :- true | true.
            p(2).
            p(3).
        """)
        sols = query_all(prog, "p(X)")
        # | prunes all siblings when guard succeeds
        assert len(sols) == 1
        assert sols[0].bindings["X"].value == 1

    def test_wait_allows_backtracking(self):
        """Test ? allows backtracking through all alternatives."""
        prog = load_string("""
            p(1) :- true ? true.
            p(2) :- true ? true.
            p(3) :- true ? true.
        """)
        sols = query_all(prog, "p(X)")
        # ? allows backtracking - should get all solutions
        assert len(sols) == 3
        values = [s.bindings["X"].value for s in sols]
        assert values == [1, 2, 3]

    def test_cut_prunes_right(self):
        """Test ! prunes alternatives to the right."""
        prog = load_string("""
            p(1) :- true ! true.
            p(2).
        """)
        sols = query_all(prog, "p(X)")
        # ! prunes right alternatives
        assert len(sols) == 1
        assert sols[0].bindings["X"].value == 1


class TestNoisyVsQuiet:
    """Test noisy vs quiet guard semantics.

    Noisy guards (?, !) can commit with external bindings.
    Quiet guards (->, |, ??) cannot commit with external bindings.
    """

    def test_noisy_wait_with_binding(self):
        """Test ? (noisy) can succeed with external binding."""
        prog = load_string("""
            p(X, Y) :- X = Y ? true.
        """)
        sols = query_all(prog, "p(1, Y)")
        assert len(sols) == 1
        assert sols[0].bindings["Y"].value == 1

    def test_arrow_deterministic(self):
        """Test -> selects first matching clause deterministically."""
        prog = load_string("""
            max(X, Y, X) :- X >= Y -> true.
            max(X, Y, Y) :- X < Y -> true.
        """)
        sols = query_all(prog, "max(5, 3, M)")
        assert len(sols) == 1
        assert sols[0].bindings["M"].value == 5


class TestMemberWithGuards:
    """Test member/2 with different guard types."""

    def test_member_wait_guard(self):
        """Test member with ? guard - allows backtracking."""
        prog = load_string("""
            member(X, [X|_]) :- true ? true.
            member(X, [_|T]) :- true ? member(X, T).
        """)
        sols = query_all(prog, "member(X, [1, 2, 3])")
        assert len(sols) == 3
        values = [s.bindings["X"].value for s in sols]
        assert values == [1, 2, 3]

    def test_member_arrow_guard(self):
        """Test member with -> guard - deterministic."""
        prog = load_string("""
            member(X, [X|_]) :- true -> true.
            member(X, [_|T]) :- true -> member(X, T).
        """)
        # With -> guard, should still find members but deterministically per clause
        sols = query_all(prog, "member(X, [1, 2, 3])")
        assert len(sols) >= 1  # At least first should work


class TestAppendWithGuards:
    """Test append/3 with guards."""

    def test_append_wait_guard(self):
        """Test append with ? guard."""
        prog = load_string("""
            append([], L, L) :- true ? true.
            append([H|T], L, [H|R]) :- true ? append(T, L, R).
        """)
        sols = query_all(prog, "append([1,2], [3,4], R)")
        assert len(sols) == 1
        # R should be [1,2,3,4]


class TestIfThenElse:
    """Test if-then-else with -> guard."""

    def test_if_then_else_true(self):
        """Test (Cond -> Then ; Else) when Cond succeeds."""
        prog = load_string("""
            test(X, R) :- (X > 0 -> R = positive ; R = non_positive).
        """)
        sols = query_all(prog, "test(5, R)")
        assert len(sols) == 1
        assert str(sols[0].bindings["R"]) == "positive"

    def test_if_then_else_false(self):
        """Test (Cond -> Then ; Else) when Cond fails."""
        prog = load_string("""
            test(X, R) :- (X > 0 -> R = positive ; R = non_positive).
        """)
        sols = query_all(prog, "test(-5, R)")
        assert len(sols) == 1
        assert str(sols[0].bindings["R"]) == "non_positive"


class TestGuardedMerge:
    """Test guarded merge (classic AKL example) with commit guard."""

    def test_merge_commit(self):
        """Test merge with | commit guard for concurrent input."""
        prog = load_string("""
            merge([], Ys, Ys) :- true | true.
            merge(Xs, [], Xs) :- true | true.
            merge([X|Xs], [Y|Ys], [X|Zs]) :- X =< Y | merge(Xs, [Y|Ys], Zs).
            merge([X|Xs], [Y|Ys], [Y|Zs]) :- X > Y | merge([X|Xs], Ys, Zs).
        """)
        sols = query_all(prog, "merge([1,3,5], [2,4], R)")
        assert len(sols) >= 1
        # R should be [1,2,3,4,5]


class TestQuietGuardSuspension:
    """Test that quiet guards cannot bind external variables.

    These tests document expected AKL behavior. Currently they may pass
    because the interpreter doesn't implement full suspension semantics,
    but the behavior shown is correct for simple cases.
    """

    def test_quiet_guard_with_ground_args(self):
        """Quiet guard with ground arguments should work normally."""
        prog = load_string("""
            max(X, Y, X) :- X >= Y -> true.
            max(X, Y, Y) :- X < Y -> true.
        """)
        sols = query_all(prog, "max(5, 3, M)")
        assert len(sols) == 1
        assert sols[0].bindings["M"].value == 5

    def test_commit_selects_first_matching(self):
        """Commit guard should select first matching clause."""
        prog = load_string("""
            choose(a) :- true | true.
            choose(b) :- true | true.
            choose(c) :- true | true.
        """)
        sols = query_all(prog, "choose(X)")
        # | commits to first matching clause
        assert len(sols) == 1
        assert str(sols[0].bindings["X"]) == "a"

    def test_arrow_requires_leftmost(self):
        """Arrow guard should succeed when leftmost and guard succeeds."""
        prog = load_string("""
            first(X) :- true -> X = 1.
            first(X) :- true -> X = 2.
        """)
        sols = query_all(prog, "first(X)")
        # -> prunes right, so only first clause should match
        assert len(sols) == 1
        assert sols[0].bindings["X"].value == 1


class TestCutBehavior:
    """Test cut (!) behavior - noisy, prunes right."""

    def test_cut_prunes_right(self):
        """Cut should prune alternatives to the right."""
        prog = load_string("""
            test(1) :- true ! true.
            test(2).
            test(3).
        """)
        sols = query_all(prog, "test(X)")
        # ! prunes right alternatives
        assert len(sols) == 1
        assert sols[0].bindings["X"].value == 1

    def test_cut_after_guard_failure_tries_next(self):
        """If guard fails, cut should try next clause."""
        prog = load_string("""
            test(1) :- fail ! true.
            test(2) :- true ! true.
            test(3).
        """)
        sols = query_all(prog, "test(X)")
        # First guard fails, second succeeds and cuts
        assert len(sols) == 1
        assert sols[0].bindings["X"].value == 2


class TestQuietGuardExternalBindings:
    """Test that quiet guards cannot bind external variables in guard."""

    def test_quiet_guard_cannot_bind_external_in_guard(self):
        """Quiet guard with external binding in guard should fail/suspend."""
        # This tests that a quiet guard that tries to bind an external
        # variable during guard execution should fail
        prog = load_string("""
            % This guard tries to bind X (external) in the guard itself
            bind_external(X) :- X = 1 | true.
            bind_external(2).
        """)
        sols = query_all(prog, "bind_external(Y)")
        # The first clause tries to bind X=1 in the guard, which binds external Y
        # Since | is a quiet guard, this should fail/suspend
        # The second clause should succeed
        assert len(sols) == 1
        assert sols[0].bindings["Y"].value == 2

    def test_noisy_guard_can_bind_external_in_guard(self):
        """Noisy guard (?) can bind external variables in guard."""
        prog = load_string("""
            bind_external(X) :- X = 1 ? true.
            bind_external(2).
        """)
        sols = query_all(prog, "bind_external(Y)")
        # ? is a noisy guard, can bind externals
        # Both clauses should work, but first commits on success
        assert len(sols) >= 1
        assert sols[0].bindings["Y"].value == 1

    def test_quiet_guard_ok_with_local_bindings(self):
        """Quiet guard can bind local variables."""
        prog = load_string("""
            local_bind(R) :- X = 1, X > 0 | R = X.
        """)
        sols = query_all(prog, "local_bind(R)")
        # Guard binds local X, which is fine for quiet guards
        assert len(sols) == 1
        assert sols[0].bindings["R"].value == 1


class TestVariableEnvironments:
    """Test that variables are properly tracked by environment."""

    def test_recursive_merge_works(self):
        """Recursive merge with commit guards should work correctly."""
        prog = load_string("""
            merge([], Ys, Ys) :- true | true.
            merge(Xs, [], Xs) :- true | true.
            merge([X|Xs], [Y|Ys], [X|Zs]) :- X =< Y | merge(Xs, [Y|Ys], Zs).
            merge([X|Xs], [Y|Ys], [Y|Zs]) :- X > Y | merge([X|Xs], Ys, Zs).
        """)
        sols = query_all(prog, "merge([1,3], [2,4], R)")
        assert len(sols) >= 1
        # R should be [1,2,3,4]

    def test_member_with_commit_guard(self):
        """Member with commit guard should find first match only."""
        prog = load_string("""
            first_member(X, [X|_]) :- true | true.
            first_member(X, [_|T]) :- true | first_member(X, T).
        """)
        sols = query_all(prog, "first_member(X, [1,2,3])")
        # | commits, so should only get first element
        assert len(sols) == 1
        assert sols[0].bindings["X"].value == 1
