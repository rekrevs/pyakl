"""
Tests for and-box copying (nondeterministic splitting).

Tests that:
- Local variables are copied to fresh instances
- External variables remain shared
- And-box tree structure is preserved
- Copy is independent of original
"""

import pytest
from pyakl.term import Var, Atom, Integer, Struct, Cons, make_list
from pyakl.engine import (
    AndBox, ChoiceBox, EnvId, ConstrainedVar, ExState, Status
)
from pyakl.copy import (
    copy_andbox_subtree, CopyState, find_candidate,
    _copy_term, _copy_env
)


class TestCopyState:
    """Test CopyState helper methods."""

    def test_is_local_env_mother(self):
        """Mother's env is local."""
        mother = AndBox()
        state = CopyState(mother=mother)
        assert state.is_local_env(mother.env)

    def test_is_local_env_child(self):
        """Child env is local."""
        mother = AndBox()
        child_env = EnvId(parent=mother.env)
        state = CopyState(mother=mother)
        assert state.is_local_env(child_env)

    def test_is_local_env_external(self):
        """External env (parent of mother) is not local."""
        external_env = EnvId()
        mother = AndBox()
        mother.env = EnvId(parent=external_env)
        state = CopyState(mother=mother)
        assert not state.is_local_env(external_env)

    def test_is_local_var(self):
        """Variable with local env is local."""
        mother = AndBox()
        local_var = ConstrainedVar("X", mother.env)
        state = CopyState(mother=mother)
        assert state.is_local_var(local_var)

    def test_is_local_var_external(self):
        """Variable with external env is not local."""
        external_env = EnvId()
        mother = AndBox()
        mother.env = EnvId(parent=external_env)
        external_var = ConstrainedVar("X", external_env)
        state = CopyState(mother=mother)
        assert not state.is_local_var(external_var)


class TestCopyEnv:
    """Test environment copying."""

    def test_copy_local_env(self):
        """Local env is copied to fresh instance."""
        mother = AndBox()
        state = CopyState(mother=mother)
        new_env = _copy_env(mother.env, state)
        assert new_env is not mother.env
        assert id(mother.env) in state.env_map

    def test_copy_external_env(self):
        """External env is shared (not copied)."""
        external_env = EnvId()
        mother = AndBox()
        mother.env = EnvId(parent=external_env)
        state = CopyState(mother=mother)
        # Copy the external env
        result = _copy_env(external_env, state)
        assert result is external_env  # Same object


class TestCopyTerm:
    """Test term copying."""

    def test_copy_atom(self):
        """Atoms are shared (immutable)."""
        mother = AndBox()
        state = CopyState(mother=mother)
        atom = Atom("foo")
        result = _copy_term(atom, state)
        assert result is atom

    def test_copy_integer(self):
        """Integers are shared (immutable)."""
        mother = AndBox()
        state = CopyState(mother=mother)
        num = Integer(42)
        result = _copy_term(num, state)
        assert result is num

    def test_copy_struct(self):
        """Structures are copied with copied args."""
        mother = AndBox()
        state = CopyState(mother=mother)
        s = Struct(Atom("foo"), (Integer(1), Integer(2)))
        result = _copy_term(s, state)
        assert result is not s
        assert result.functor is s.functor
        assert result.args[0] is s.args[0]  # Shared integers
        assert result.args[1] is s.args[1]

    def test_copy_local_var(self):
        """Local variables are copied to fresh instances."""
        mother = AndBox()
        local_var = ConstrainedVar("X", mother.env)
        state = CopyState(mother=mother)
        result = _copy_term(local_var, state)
        assert result is not local_var
        assert isinstance(result, ConstrainedVar)
        assert result.name == local_var.name

    def test_copy_external_var(self):
        """External variables are shared (not copied)."""
        external_env = EnvId()
        mother = AndBox()
        mother.env = EnvId(parent=external_env)
        external_var = ConstrainedVar("Y", external_env)
        state = CopyState(mother=mother)
        result = _copy_term(external_var, state)
        assert result is external_var  # Same object

    def test_copy_struct_with_local_var(self):
        """Struct with local var gets copied var."""
        mother = AndBox()
        local_var = ConstrainedVar("X", mother.env)
        s = Struct(Atom("foo"), (local_var,))
        state = CopyState(mother=mother)
        result = _copy_term(s, state)
        assert result is not s
        assert result.args[0] is not local_var
        assert result.args[0].name == "X"

    def test_copy_struct_with_external_var(self):
        """Struct with external var keeps shared var."""
        external_env = EnvId()
        mother = AndBox()
        mother.env = EnvId(parent=external_env)
        external_var = ConstrainedVar("Y", external_env)
        s = Struct(Atom("foo"), (external_var,))
        state = CopyState(mother=mother)
        result = _copy_term(s, state)
        assert result is not s
        assert result.args[0] is external_var  # Shared

    def test_copy_list(self):
        """Lists are copied with elements."""
        mother = AndBox()
        local_var = ConstrainedVar("X", mother.env)
        lst = make_list([Integer(1), local_var, Integer(3)])
        state = CopyState(mother=mother)
        result = _copy_term(lst, state)
        # Check structure is copied
        assert result is not lst
        assert isinstance(result, Cons)

    def test_copy_bound_var(self):
        """Bound local variable: binding is copied."""
        mother = AndBox()
        local_var = ConstrainedVar("X", mother.env)
        local_var.binding = Integer(42)
        state = CopyState(mother=mother)
        # When copying a bound var, _copy_term derefs first, so we get the value
        result = _copy_term(local_var, state)
        # Result is the Integer(42) - immutable, shared
        assert result.value == 42
        # The var itself should be in var_map though (if we copy it directly)
        # But here the var was already bound, so deref returned the int

    def test_copy_unbound_var(self):
        """Unbound local variable is copied to fresh instance."""
        mother = AndBox()
        local_var = ConstrainedVar("X", mother.env)
        # Don't bind it
        state = CopyState(mother=mother)
        result = _copy_term(local_var, state)
        assert result is not local_var
        assert isinstance(result, ConstrainedVar)
        assert result.name == "X"
        assert result.binding is None


class TestCopyAndBox:
    """Test and-box copying."""

    def test_copy_simple_andbox(self):
        """Copy simple and-box with local var."""
        exstate = ExState()
        mother = AndBox()
        mother.local_vars["X"] = ConstrainedVar("X", mother.env)

        copy = copy_andbox_subtree(mother, exstate)

        assert copy is not mother
        assert "X" in copy.local_vars
        assert copy.local_vars["X"] is not mother.local_vars["X"]

    def test_copy_andbox_with_goals(self):
        """Copy and-box with goals."""
        exstate = ExState()
        mother = AndBox()
        local_var = ConstrainedVar("X", mother.env)
        mother.local_vars["X"] = local_var
        mother.goals = [Struct(Atom("foo"), (local_var,))]

        copy = copy_andbox_subtree(mother, exstate)

        assert len(copy.goals) == 1
        # Goal's variable should be the copy's variable
        assert copy.goals[0].args[0] is copy.local_vars["X"]

    def test_copy_preserves_status(self):
        """Copy preserves status."""
        exstate = ExState()
        mother = AndBox()
        mother.status = Status.UNSTABLE

        copy = copy_andbox_subtree(mother, exstate)

        assert copy.status == Status.UNSTABLE

    def test_copy_with_child_choicebox(self):
        """Copy and-box with child choice-box."""
        exstate = ExState()
        mother = AndBox()

        # Add a child choice-box with an alternative
        chb = ChoiceBox()
        chb.father = mother
        mother.tried = chb

        alt = AndBox()
        alt.env = EnvId(parent=mother.env)
        alt.father = chb
        chb.tried = alt

        copy = copy_andbox_subtree(mother, exstate)

        assert copy.tried is not None
        assert copy.tried is not chb
        assert copy.tried.father is copy
        assert copy.tried.tried is not None
        assert copy.tried.tried is not alt
        assert copy.tried.tried.father is copy.tried


class TestVarIndependence:
    """Test that copied vars are independent of originals."""

    def test_binding_independence(self):
        """Binding copy doesn't affect original."""
        exstate = ExState()
        mother = AndBox()
        var = ConstrainedVar("X", mother.env)
        mother.local_vars["X"] = var

        copy = copy_andbox_subtree(mother, exstate)

        # Bind copy's variable
        copy.local_vars["X"].binding = Integer(42)

        # Original should be unaffected
        assert var.binding is None

    def test_external_var_shared(self):
        """External vars are shared between original and copy."""
        external_env = EnvId()
        exstate = ExState()

        mother = AndBox()
        mother.env = EnvId(parent=external_env)

        # External variable
        ext_var = ConstrainedVar("Y", external_env)

        # Reference to external var in a goal
        mother.goals = [Struct(Atom("use"), (ext_var,))]

        copy = copy_andbox_subtree(mother, exstate)

        # The external var in the copy should be the same object
        assert copy.goals[0].args[0] is ext_var

        # Binding external affects both
        ext_var.binding = Integer(99)
        assert mother.goals[0].args[0].deref().value == 99
        assert copy.goals[0].args[0].deref().value == 99


class TestFindCandidate:
    """Test candidate finding for splitting."""

    def test_no_candidate_empty(self):
        """No candidate in empty and-box."""
        andb = AndBox()
        assert find_candidate(andb) is None

    def test_candidate_simple(self):
        """Find candidate in simple tree."""
        # Root
        root = AndBox()

        # Choice box with one solved alternative
        chb = ChoiceBox()
        chb.father = root
        root.tried = chb

        alt = AndBox()
        alt.env = EnvId(parent=root.env)
        alt.father = chb
        alt.status = Status.STABLE
        # Solved = no child choice-boxes
        chb.tried = alt

        # The alternative should be a candidate
        candidate = find_candidate(root)
        assert candidate is alt

    def test_leftmost_candidate(self):
        """Find leftmost candidate among multiple."""
        root = AndBox()

        chb = ChoiceBox()
        chb.father = root
        root.tried = chb

        # Two alternatives, both solved
        alt1 = AndBox()
        alt1.env = EnvId(parent=root.env)
        alt1.father = chb
        alt1.status = Status.STABLE
        chb.tried = alt1

        alt2 = AndBox()
        alt2.env = EnvId(parent=root.env)
        alt2.father = chb
        alt2.status = Status.STABLE
        alt1.next = alt2
        alt2.prev = alt1

        # Should find leftmost (alt1)
        candidate = find_candidate(root)
        assert candidate is alt1


class TestNondeterminism:
    """Integration tests for nondeterministic programs."""

    def test_permutation_3(self):
        """Permutation of 3 elements."""
        from pyakl.program import load_string
        from pyakl.interpreter import query_all

        prog = load_string("""
            perm([], []).
            perm([H|T], P) :- perm(T, PT), insert(H, PT, P).
            insert(X, L, [X|L]).
            insert(X, [H|T], [H|R]) :- insert(X, T, R).
        """)

        sols = query_all(prog, "perm([1,2,3], P)")
        assert len(sols) == 6  # 3! = 6 permutations

        # Extract the results as Python lists
        def to_py_list(cons):
            result = []
            from pyakl.term import Cons, NIL
            while isinstance(cons, Cons):
                result.append(cons.head.value)
                cons = cons.tail
            return result

        perms = [to_py_list(s.bindings["P"]) for s in sols]
        assert [1, 2, 3] in perms
        assert [1, 3, 2] in perms
        assert [2, 1, 3] in perms
        assert [2, 3, 1] in perms
        assert [3, 1, 2] in perms
        assert [3, 2, 1] in perms

    def test_4_queens(self):
        """4-queens problem."""
        from pyakl.program import load_string
        from pyakl.interpreter import query_all

        prog = load_string("""
            perm([], []).
            perm([H|T], P) :- perm(T, PT), insert(H, PT, P).
            insert(X, L, [X|L]).
            insert(X, [H|T], [H|R]) :- insert(X, T, R).
            safe([]).
            safe([Q|Qs]) :- safe(Qs), noattack(Q, Qs, 1).
            noattack(_, [], _).
            noattack(Q, [Q1|Qs], D) :-
                D1 is Q1 - Q, D1 =\\= D,
                D2 is Q - Q1, D2 =\\= D,
                D3 is D + 1,
                noattack(Q, Qs, D3).
            queens(N, Qs) :- range(1, N, Rs), perm(Rs, Qs), safe(Qs).
            range(From, To, []) :- From > To.
            range(From, To, [From|R]) :- From =< To, From1 is From + 1, range(From1, To, R).
        """)

        sols = query_all(prog, "queens(4, Q)")
        assert len(sols) == 2  # 4-queens has 2 solutions

        def to_py_list(cons):
            result = []
            from pyakl.term import Cons
            while isinstance(cons, Cons):
                result.append(cons.head.value)
                cons = cons.tail
            return result

        solutions = [to_py_list(s.bindings["Q"]) for s in sols]
        assert [2, 4, 1, 3] in solutions
        assert [3, 1, 4, 2] in solutions

    def test_append_nondeterminate(self):
        """Append with nondeterminate second and third args."""
        from pyakl.program import load_string
        from pyakl.interpreter import query_all

        prog = load_string("""
            append([], L, L).
            append([H|T], L, [H|R]) :- append(T, L, R).
        """)

        sols = query_all(prog, "append(X, Y, [1,2,3])")
        assert len(sols) == 4

        def to_py_list(cons):
            result = []
            from pyakl.term import Cons, NIL
            term = cons
            while isinstance(term, Cons):
                result.append(term.head.value)
                term = term.tail
            return result

        # Extract X, Y pairs
        results = []
        for s in sols:
            x = s.bindings.get("X")
            y = s.bindings.get("Y")
            x_list = to_py_list(x) if x else []
            y_list = to_py_list(y) if y else []
            results.append((x_list, y_list))

        assert ([], [1, 2, 3]) in results
        assert ([1], [2, 3]) in results
        assert ([1, 2], [3]) in results
        assert ([1, 2, 3], []) in results

    def test_member_multiple_solutions(self):
        """Member finds all solutions."""
        from pyakl.program import load_string
        from pyakl.interpreter import query_all

        prog = load_string("""
            member(X, [X|_]).
            member(X, [_|T]) :- member(X, T).
        """)

        sols = query_all(prog, "member(X, [a, b, c])")
        assert len(sols) == 3

        values = [str(s.bindings["X"]) for s in sols]
        assert "a" in values
        assert "b" in values
        assert "c" in values
