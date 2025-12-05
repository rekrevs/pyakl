"""
Tests for built-in predicates.
"""

import pytest
from io import StringIO
import sys

from pyakl.term import Var, Atom, Integer, Float, Struct, Cons, NIL, make_list
from pyakl.engine import ExState, AndBox
from pyakl.builtin import (
    is_builtin, get_builtin, call_builtin, list_builtins,
    builtin_true, builtin_fail, builtin_unify, builtin_is,
)


@pytest.fixture
def exstate():
    """Create a fresh execution state."""
    return ExState()


@pytest.fixture
def andb():
    """Create a fresh and-box."""
    return AndBox()


class TestBuiltinRegistry:
    """Tests for built-in registration."""

    def test_is_builtin(self):
        assert is_builtin("true", 0)
        assert is_builtin("fail", 0)
        assert is_builtin("=", 2)
        assert not is_builtin("nonexistent", 0)

    def test_get_builtin(self):
        func = get_builtin("true", 0)
        assert func is not None
        assert func is builtin_true

    def test_list_builtins(self):
        builtins = list_builtins()
        assert ("true", 0) in builtins
        assert ("fail", 0) in builtins
        assert ("=", 2) in builtins


class TestControlBuiltins:
    """Tests for control built-ins."""

    def test_true(self, exstate, andb):
        assert call_builtin("true", 0, exstate, andb, ())

    def test_fail(self, exstate, andb):
        assert not call_builtin("fail", 0, exstate, andb, ())

    def test_false(self, exstate, andb):
        assert not call_builtin("false", 0, exstate, andb, ())


class TestUnificationBuiltins:
    """Tests for unification built-ins."""

    def test_unify_atoms(self, exstate, andb):
        assert call_builtin("=", 2, exstate, andb, (Atom("foo"), Atom("foo")))
        assert not call_builtin("=", 2, exstate, andb, (Atom("foo"), Atom("bar")))

    def test_unify_var(self, exstate, andb):
        X = Var("X")
        assert call_builtin("=", 2, exstate, andb, (X, Integer(42)))
        assert X.deref() == Integer(42)

    def test_not_unify(self, exstate, andb):
        assert call_builtin("\\=", 2, exstate, andb, (Atom("foo"), Atom("bar")))
        assert not call_builtin("\\=", 2, exstate, andb, (Atom("foo"), Atom("foo")))

    def test_not_unify_no_binding(self, exstate, andb):
        X = Var("X")
        # X \= 42 fails because X can unify with 42
        assert not call_builtin("\\=", 2, exstate, andb, (X, Integer(42)))
        # But X should still be unbound (no side effects)
        assert X.binding is None

    def test_identical(self, exstate, andb):
        X = Var("X")
        assert call_builtin("==", 2, exstate, andb, (Atom("foo"), Atom("foo")))
        assert call_builtin("==", 2, exstate, andb, (X, X))
        assert not call_builtin("==", 2, exstate, andb, (Var("X"), Var("X")))  # Different vars

    def test_not_identical(self, exstate, andb):
        assert call_builtin("\\==", 2, exstate, andb, (Atom("foo"), Atom("bar")))
        assert call_builtin("\\==", 2, exstate, andb, (Var("X"), Var("X")))


class TestArithmeticBuiltins:
    """Tests for arithmetic built-ins."""

    def test_is_simple(self, exstate, andb):
        X = Var("X")
        assert call_builtin("is", 2, exstate, andb, (X, Integer(42)))
        assert X.deref() == Integer(42)

    def test_is_addition(self, exstate, andb):
        X = Var("X")
        expr = Struct(Atom("+"), (Integer(1), Integer(2)))
        assert call_builtin("is", 2, exstate, andb, (X, expr))
        assert X.deref() == Integer(3)

    def test_is_subtraction(self, exstate, andb):
        X = Var("X")
        expr = Struct(Atom("-"), (Integer(10), Integer(3)))
        assert call_builtin("is", 2, exstate, andb, (X, expr))
        assert X.deref() == Integer(7)

    def test_is_multiplication(self, exstate, andb):
        X = Var("X")
        expr = Struct(Atom("*"), (Integer(6), Integer(7)))
        assert call_builtin("is", 2, exstate, andb, (X, expr))
        assert X.deref() == Integer(42)

    def test_is_division(self, exstate, andb):
        X = Var("X")
        expr = Struct(Atom("/"), (Integer(10), Integer(4)))
        assert call_builtin("is", 2, exstate, andb, (X, expr))
        assert X.deref() == Float(2.5)

    def test_is_integer_division(self, exstate, andb):
        X = Var("X")
        expr = Struct(Atom("//"), (Integer(10), Integer(3)))
        assert call_builtin("is", 2, exstate, andb, (X, expr))
        assert X.deref() == Integer(3)

    def test_is_mod(self, exstate, andb):
        X = Var("X")
        expr = Struct(Atom("mod"), (Integer(10), Integer(3)))
        assert call_builtin("is", 2, exstate, andb, (X, expr))
        assert X.deref() == Integer(1)

    def test_is_nested(self, exstate, andb):
        X = Var("X")
        # (2 + 3) * 4
        expr = Struct(Atom("*"), (
            Struct(Atom("+"), (Integer(2), Integer(3))),
            Integer(4)
        ))
        assert call_builtin("is", 2, exstate, andb, (X, expr))
        assert X.deref() == Integer(20)

    def test_is_unary_minus(self, exstate, andb):
        X = Var("X")
        expr = Struct(Atom("-"), (Integer(42),))
        assert call_builtin("is", 2, exstate, andb, (X, expr))
        assert X.deref() == Integer(-42)

    def test_arith_eq(self, exstate, andb):
        assert call_builtin("=:=", 2, exstate, andb, (Integer(42), Integer(42)))
        assert not call_builtin("=:=", 2, exstate, andb, (Integer(42), Integer(43)))

    def test_arith_neq(self, exstate, andb):
        assert call_builtin("=\\=", 2, exstate, andb, (Integer(42), Integer(43)))
        assert not call_builtin("=\\=", 2, exstate, andb, (Integer(42), Integer(42)))

    def test_less_than(self, exstate, andb):
        assert call_builtin("<", 2, exstate, andb, (Integer(1), Integer(2)))
        assert not call_builtin("<", 2, exstate, andb, (Integer(2), Integer(1)))
        assert not call_builtin("<", 2, exstate, andb, (Integer(2), Integer(2)))

    def test_greater_than(self, exstate, andb):
        assert call_builtin(">", 2, exstate, andb, (Integer(2), Integer(1)))
        assert not call_builtin(">", 2, exstate, andb, (Integer(1), Integer(2)))

    def test_less_equal(self, exstate, andb):
        assert call_builtin("=<", 2, exstate, andb, (Integer(1), Integer(2)))
        assert call_builtin("=<", 2, exstate, andb, (Integer(2), Integer(2)))
        assert not call_builtin("=<", 2, exstate, andb, (Integer(3), Integer(2)))

    def test_greater_equal(self, exstate, andb):
        assert call_builtin(">=", 2, exstate, andb, (Integer(2), Integer(1)))
        assert call_builtin(">=", 2, exstate, andb, (Integer(2), Integer(2)))
        assert not call_builtin(">=", 2, exstate, andb, (Integer(1), Integer(2)))


class TestIOBuiltins:
    """Tests for I/O built-ins."""

    def test_write(self, exstate, andb, capsys):
        assert call_builtin("write", 1, exstate, andb, (Atom("hello"),))
        captured = capsys.readouterr()
        assert captured.out == "hello"

    def test_writeln(self, exstate, andb, capsys):
        assert call_builtin("writeln", 1, exstate, andb, (Atom("hello"),))
        captured = capsys.readouterr()
        assert captured.out == "hello\n"

    def test_nl(self, exstate, andb, capsys):
        assert call_builtin("nl", 0, exstate, andb, ())
        captured = capsys.readouterr()
        assert captured.out == "\n"

    def test_put(self, exstate, andb, capsys):
        assert call_builtin("put", 1, exstate, andb, (Integer(65),))  # 'A'
        captured = capsys.readouterr()
        assert captured.out == "A"


class TestMetaBuiltins:
    """Tests for meta predicates."""

    def test_functor_decompose_atom(self, exstate, andb):
        N = Var("N")
        A = Var("A")
        assert call_builtin("functor", 3, exstate, andb, (Atom("foo"), N, A))
        assert N.deref() == Atom("foo")
        assert A.deref() == Integer(0)

    def test_functor_decompose_struct(self, exstate, andb):
        N = Var("N")
        A = Var("A")
        term = Struct(Atom("foo"), (Integer(1), Integer(2)))
        assert call_builtin("functor", 3, exstate, andb, (term, N, A))
        assert N.deref() == Atom("foo")
        assert A.deref() == Integer(2)

    def test_functor_construct(self, exstate, andb):
        T = Var("T")
        assert call_builtin("functor", 3, exstate, andb, (T, Atom("foo"), Integer(2)))
        result = T.deref()
        assert isinstance(result, Struct)
        assert result.functor == Atom("foo")
        assert result.arity == 2

    def test_arg(self, exstate, andb):
        X = Var("X")
        term = Struct(Atom("foo"), (Integer(1), Integer(2), Integer(3)))
        assert call_builtin("arg", 3, exstate, andb, (Integer(2), term, X))
        assert X.deref() == Integer(2)

    def test_arg_out_of_range(self, exstate, andb):
        X = Var("X")
        term = Struct(Atom("foo"), (Integer(1), Integer(2)))
        assert not call_builtin("arg", 3, exstate, andb, (Integer(0), term, X))
        assert not call_builtin("arg", 3, exstate, andb, (Integer(3), term, X))

    def test_univ_decompose(self, exstate, andb):
        L = Var("L")
        term = Struct(Atom("foo"), (Integer(1), Integer(2)))
        assert call_builtin("=..", 2, exstate, andb, (term, L))
        result = L.deref()
        assert isinstance(result, Cons)

    def test_univ_construct(self, exstate, andb):
        T = Var("T")
        lst = make_list([Atom("foo"), Integer(1), Integer(2)])
        assert call_builtin("=..", 2, exstate, andb, (T, lst))
        result = T.deref()
        assert isinstance(result, Struct)
        assert result.functor == Atom("foo")
        assert result.arity == 2

    def test_copy_term(self, exstate, andb):
        X = Var("X")
        Y = Var("Y")
        original = Struct(Atom("foo"), (X, X))
        copy = Var("Copy")
        assert call_builtin("copy_term", 2, exstate, andb, (original, copy))
        result = copy.deref()
        assert isinstance(result, Struct)
        # The copy should have fresh variables
        assert result.args[0] is result.args[1]  # Same var
        assert result.args[0] is not X  # But different from original


class TestTypeBuiltins:
    """Tests for type checking built-ins."""

    def test_var(self, exstate, andb):
        assert call_builtin("var", 1, exstate, andb, (Var("X"),))
        assert not call_builtin("var", 1, exstate, andb, (Atom("foo"),))

    def test_nonvar(self, exstate, andb):
        assert not call_builtin("nonvar", 1, exstate, andb, (Var("X"),))
        assert call_builtin("nonvar", 1, exstate, andb, (Atom("foo"),))

    def test_atom(self, exstate, andb):
        assert call_builtin("atom", 1, exstate, andb, (Atom("foo"),))
        assert not call_builtin("atom", 1, exstate, andb, (Integer(42),))
        assert not call_builtin("atom", 1, exstate, andb, (Var("X"),))

    def test_number(self, exstate, andb):
        assert call_builtin("number", 1, exstate, andb, (Integer(42),))
        assert call_builtin("number", 1, exstate, andb, (Float(3.14),))
        assert not call_builtin("number", 1, exstate, andb, (Atom("foo"),))

    def test_integer(self, exstate, andb):
        assert call_builtin("integer", 1, exstate, andb, (Integer(42),))
        assert not call_builtin("integer", 1, exstate, andb, (Float(3.14),))

    def test_float(self, exstate, andb):
        assert call_builtin("float", 1, exstate, andb, (Float(3.14),))
        assert not call_builtin("float", 1, exstate, andb, (Integer(42),))

    def test_compound(self, exstate, andb):
        assert call_builtin("compound", 1, exstate, andb, (Struct(Atom("foo"), (Integer(1),)),))
        assert call_builtin("compound", 1, exstate, andb, (Cons(Integer(1), NIL),))
        assert not call_builtin("compound", 1, exstate, andb, (Atom("foo"),))

    def test_is_list(self, exstate, andb):
        assert call_builtin("is_list", 1, exstate, andb, (NIL,))
        assert call_builtin("is_list", 1, exstate, andb, (make_list([Integer(1), Integer(2)]),))
        assert not call_builtin("is_list", 1, exstate, andb, (Cons(Integer(1), Var("X")),))

    def test_atomic(self, exstate, andb):
        assert call_builtin("atomic", 1, exstate, andb, (Atom("foo"),))
        assert call_builtin("atomic", 1, exstate, andb, (Integer(42),))
        assert not call_builtin("atomic", 1, exstate, andb, (Struct(Atom("foo"), ()),))


class TestListBuiltins:
    """Tests for list built-ins."""

    def test_length_get(self, exstate, andb):
        L = Var("L")
        lst = make_list([Integer(1), Integer(2), Integer(3)])
        assert call_builtin("length", 2, exstate, andb, (lst, L))
        assert L.deref() == Integer(3)

    def test_length_empty(self, exstate, andb):
        L = Var("L")
        assert call_builtin("length", 2, exstate, andb, (NIL, L))
        assert L.deref() == Integer(0)

    def test_length_check(self, exstate, andb):
        lst = make_list([Integer(1), Integer(2)])
        assert call_builtin("length", 2, exstate, andb, (lst, Integer(2)))
        assert not call_builtin("length", 2, exstate, andb, (lst, Integer(3)))
