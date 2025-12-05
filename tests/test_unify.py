"""
Tests for unification algorithm.
"""

import pytest
from pyakl.term import Var, Atom, Integer, Float, Struct, Cons, NIL, make_list
from pyakl.engine import ExState, ConstrainedVar, EnvId
from pyakl.unify import (
    unify, unify_with_occurs_check, can_unify,
    copy_term, variant, collect_vars
)


class TestUnifyBasic:
    """Basic unification tests."""

    def test_unify_identical_atoms(self):
        assert unify(Atom("foo"), Atom("foo"))

    def test_unify_different_atoms(self):
        assert not unify(Atom("foo"), Atom("bar"))

    def test_unify_identical_integers(self):
        assert unify(Integer(42), Integer(42))

    def test_unify_different_integers(self):
        assert not unify(Integer(42), Integer(43))

    def test_unify_identical_floats(self):
        assert unify(Float(3.14), Float(3.14))

    def test_unify_different_floats(self):
        assert not unify(Float(3.14), Float(2.71))

    def test_unify_atom_integer(self):
        assert not unify(Atom("foo"), Integer(42))

    def test_unify_nil(self):
        assert unify(NIL, NIL)
        assert unify(NIL, Atom("[]"))


class TestUnifyVariables:
    """Unification with variables."""

    def test_unify_var_atom(self):
        X = Var("X")
        result = unify(X, Atom("foo"))
        assert result
        assert X.deref() == Atom("foo")

    def test_unify_atom_var(self):
        X = Var("X")
        result = unify(Atom("foo"), X)
        assert result
        assert X.deref() == Atom("foo")

    def test_unify_var_var(self):
        X = Var("X")
        Y = Var("Y")
        result = unify(X, Y)
        assert result
        # One should be bound to the other
        assert X.deref() is Y or Y.deref() is X

    def test_unify_var_integer(self):
        X = Var("X")
        result = unify(X, Integer(42))
        assert result
        assert X.deref() == Integer(42)

    def test_unify_var_list(self):
        X = Var("X")
        lst = make_list([Integer(1), Integer(2)])
        result = unify(X, lst)
        assert result
        assert X.deref() == lst

    def test_unify_same_var(self):
        X = Var("X")
        assert unify(X, X)

    def test_unify_bound_var(self):
        X = Var("X")
        X.binding = Integer(42)
        assert unify(X, Integer(42))
        assert not unify(X, Integer(43))


class TestUnifyStructures:
    """Unification of compound terms."""

    def test_unify_same_structure(self):
        t1 = Struct(Atom("foo"), (Integer(1), Integer(2)))
        t2 = Struct(Atom("foo"), (Integer(1), Integer(2)))
        assert unify(t1, t2)

    def test_unify_different_functor(self):
        t1 = Struct(Atom("foo"), (Integer(1),))
        t2 = Struct(Atom("bar"), (Integer(1),))
        assert not unify(t1, t2)

    def test_unify_different_arity(self):
        t1 = Struct(Atom("foo"), (Integer(1),))
        t2 = Struct(Atom("foo"), (Integer(1), Integer(2)))
        assert not unify(t1, t2)

    def test_unify_structure_with_var(self):
        X = Var("X")
        Y = Var("Y")
        t1 = Struct(Atom("foo"), (X, Integer(2)))
        t2 = Struct(Atom("foo"), (Integer(1), Y))
        result = unify(t1, t2)
        assert result
        assert X.deref() == Integer(1)
        assert Y.deref() == Integer(2)

    def test_unify_nested_structure(self):
        X = Var("X")
        t1 = Struct(Atom("f"), (Struct(Atom("g"), (X,)),))
        t2 = Struct(Atom("f"), (Struct(Atom("g"), (Integer(42),)),))
        result = unify(t1, t2)
        assert result
        assert X.deref() == Integer(42)

    def test_unify_empty_structure(self):
        t1 = Struct(Atom("foo"), ())
        t2 = Struct(Atom("foo"), ())
        assert unify(t1, t2)


class TestUnifyLists:
    """Unification of lists."""

    def test_unify_empty_lists(self):
        assert unify(NIL, NIL)

    def test_unify_single_element(self):
        l1 = make_list([Integer(1)])
        l2 = make_list([Integer(1)])
        assert unify(l1, l2)

    def test_unify_multiple_elements(self):
        l1 = make_list([Integer(1), Integer(2), Integer(3)])
        l2 = make_list([Integer(1), Integer(2), Integer(3)])
        assert unify(l1, l2)

    def test_unify_different_lists(self):
        l1 = make_list([Integer(1), Integer(2)])
        l2 = make_list([Integer(1), Integer(3)])
        assert not unify(l1, l2)

    def test_unify_different_lengths(self):
        l1 = make_list([Integer(1), Integer(2)])
        l2 = make_list([Integer(1)])
        assert not unify(l1, l2)

    def test_unify_list_with_var_head(self):
        H = Var("H")
        T = Var("T")
        l1 = Cons(H, T)
        l2 = make_list([Integer(1), Integer(2), Integer(3)])
        result = unify(l1, l2)
        assert result
        assert H.deref() == Integer(1)
        # T should be [2, 3]
        t_deref = T.deref()
        assert isinstance(t_deref, Cons)
        assert t_deref.head.deref() == Integer(2)

    def test_unify_list_pattern(self):
        # [X|_] with [1,2,3]
        X = Var("X")
        pattern = Cons(X, Var("_"))
        lst = make_list([Integer(1), Integer(2), Integer(3)])
        result = unify(pattern, lst)
        assert result
        assert X.deref() == Integer(1)


class TestOccursCheck:
    """Tests for occurs check."""

    def test_no_occurs_check_circular(self):
        # Without occurs check, this creates a circular structure
        X = Var("X")
        t = Struct(Atom("f"), (X,))
        # This should succeed without occurs check (creates cycle)
        result = unify(X, t)
        assert result

    def test_occurs_check_fails(self):
        X = Var("X")
        t = Struct(Atom("f"), (X,))
        result = unify_with_occurs_check(X, t)
        assert not result

    def test_occurs_check_nested(self):
        X = Var("X")
        t = Struct(Atom("f"), (Struct(Atom("g"), (X,)),))
        result = unify_with_occurs_check(X, t)
        assert not result

    def test_occurs_check_in_list(self):
        X = Var("X")
        t = Cons(Integer(1), X)
        result = unify_with_occurs_check(X, t)
        assert not result


class TestUnifyWithTrail:
    """Tests for unification with trailing."""

    def test_trail_binding(self):
        exstate = ExState()
        X = Var("X")
        unify(X, Integer(42), exstate)
        assert X.deref() == Integer(42)
        assert len(exstate.trail) == 1

    def test_undo_binding(self):
        exstate = ExState()
        X = Var("X")
        unify(X, Integer(42), exstate)
        assert X.deref() == Integer(42)

        exstate.undo_trail()
        assert X.binding is None

    def test_multiple_bindings_undo(self):
        exstate = ExState()
        X = Var("X")
        Y = Var("Y")
        Z = Var("Z")

        t1 = Struct(Atom("f"), (X, Y, Z))
        t2 = Struct(Atom("f"), (Integer(1), Integer(2), Integer(3)))

        unify(t1, t2, exstate)
        assert X.deref() == Integer(1)
        assert Y.deref() == Integer(2)
        assert Z.deref() == Integer(3)
        assert len(exstate.trail) == 3

        exstate.undo_trail()
        assert X.binding is None
        assert Y.binding is None
        assert Z.binding is None

    def test_partial_undo(self):
        exstate = ExState()
        X = Var("X")
        Y = Var("Y")

        unify(X, Integer(1), exstate)
        pos = exstate.trail_position()
        unify(Y, Integer(2), exstate)

        assert X.deref() == Integer(1)
        assert Y.deref() == Integer(2)

        exstate.undo_trail(pos)
        assert X.deref() == Integer(1)
        assert Y.binding is None


class TestCanUnify:
    """Tests for can_unify (non-destructive check)."""

    def test_can_unify_succeeds(self):
        X = Var("X")
        assert can_unify(X, Integer(42))
        # X should not be bound
        assert X.binding is None

    def test_can_unify_fails(self):
        assert not can_unify(Atom("foo"), Atom("bar"))

    def test_can_unify_structure(self):
        X = Var("X")
        t1 = Struct(Atom("f"), (X,))
        t2 = Struct(Atom("f"), (Integer(42),))
        assert can_unify(t1, t2)
        assert X.binding is None


class TestCopyTerm:
    """Tests for copy_term."""

    def test_copy_atom(self):
        t = Atom("foo")
        c = copy_term(t)
        assert c is t  # Atoms are immutable

    def test_copy_integer(self):
        t = Integer(42)
        c = copy_term(t)
        assert c is t  # Integers are immutable

    def test_copy_var(self):
        X = Var("X")
        c = copy_term(X)
        assert isinstance(c, Var)
        assert c is not X

    def test_copy_structure(self):
        X = Var("X")
        t = Struct(Atom("f"), (X, Integer(1)))
        c = copy_term(t)

        assert isinstance(c, Struct)
        assert c.functor == t.functor
        # X in copy should be different variable
        assert isinstance(c.args[0], Var)
        assert c.args[0] is not X
        # Integer should be same
        assert c.args[1] is t.args[1]

    def test_copy_preserves_sharing(self):
        X = Var("X")
        t = Struct(Atom("f"), (X, X))
        c = copy_term(t)

        # Both args should be same new variable
        assert c.args[0] is c.args[1]
        assert c.args[0] is not X

    def test_copy_list(self):
        X = Var("X")
        t = make_list([X, Integer(1), X])
        c = copy_term(t)

        # Should be a list
        assert isinstance(c, Cons)
        # First element should be new var
        assert isinstance(c.head, Var)
        assert c.head is not X

    def test_copy_bound_var(self):
        X = Var("X")
        X.binding = Integer(42)
        c = copy_term(X)
        # Should copy the value, not create new var
        assert c == Integer(42)


class TestVariant:
    """Tests for variant check."""

    def test_variant_atoms(self):
        assert variant(Atom("foo"), Atom("foo"))
        assert not variant(Atom("foo"), Atom("bar"))

    def test_variant_vars(self):
        X = Var("X")
        Y = Var("Y")
        assert variant(X, Y)

    def test_variant_structures(self):
        X1 = Var("X")
        X2 = Var("X")
        t1 = Struct(Atom("f"), (X1, Integer(1)))
        t2 = Struct(Atom("f"), (X2, Integer(1)))
        assert variant(t1, t2)

    def test_variant_different_structure(self):
        X = Var("X")
        Y = Var("Y")
        t1 = Struct(Atom("f"), (X, X))
        t2 = Struct(Atom("f"), (Y, Integer(1)))
        assert not variant(t1, t2)

    def test_variant_same_var_twice(self):
        X = Var("X")
        Y = Var("Y")
        Z = Var("Z")
        t1 = Struct(Atom("f"), (X, X))
        t2 = Struct(Atom("f"), (Y, Y))
        t3 = Struct(Atom("f"), (Y, Z))
        assert variant(t1, t2)
        assert not variant(t1, t3)

    def test_variant_lists(self):
        X1 = Var("X")
        X2 = Var("X")
        l1 = make_list([X1, Integer(1)])
        l2 = make_list([X2, Integer(1)])
        assert variant(l1, l2)


class TestCollectVars:
    """Tests for collect_vars."""

    def test_collect_no_vars(self):
        t = Struct(Atom("f"), (Integer(1), Integer(2)))
        assert collect_vars(t) == []

    def test_collect_single_var(self):
        X = Var("X")
        assert collect_vars(X) == [X]

    def test_collect_multiple_vars(self):
        X = Var("X")
        Y = Var("Y")
        t = Struct(Atom("f"), (X, Y))
        vars = collect_vars(t)
        assert len(vars) == 2
        assert X in vars
        assert Y in vars

    def test_collect_repeated_var(self):
        X = Var("X")
        t = Struct(Atom("f"), (X, X, X))
        vars = collect_vars(t)
        assert len(vars) == 1
        assert vars[0] is X

    def test_collect_vars_in_list(self):
        X = Var("X")
        Y = Var("Y")
        t = make_list([X, Integer(1), Y])
        vars = collect_vars(t)
        assert len(vars) == 2

    def test_collect_vars_order(self):
        X = Var("X")
        Y = Var("Y")
        Z = Var("Z")
        t = Struct(Atom("f"), (X, Y, Z))
        vars = collect_vars(t)
        assert vars == [X, Y, Z]


class TestUnifyWakesSuspended:
    """Tests that unification wakes suspended goals."""

    def test_wake_on_bind(self):
        exstate = ExState()
        env = EnvId()
        var = ConstrainedVar("X", env)

        # Create a suspended and-box
        from pyakl.engine import AndBox, Suspension
        waiting = AndBox()
        susp = Suspension.for_andbox(waiting)
        var.add_suspension(susp)

        # Unify should wake the suspended goal
        unify(var, Integer(42), exstate)

        assert len(exstate.wake) == 1
        assert exstate.wake[0] is waiting
        assert var.suspensions is None
