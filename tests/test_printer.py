"""
Tests for AKL term printer.
"""

import pytest
from pyakl import (
    parse_term, print_term,
    Var, Atom, Integer, Float, Struct, Cons, NIL, make_list
)


class TestPrintAtoms:
    """Tests for printing atoms."""

    def test_simple_atom(self):
        assert print_term(Atom("foo")) == "foo"

    def test_atom_with_underscore(self):
        assert print_term(Atom("foo_bar")) == "foo_bar"

    def test_atom_needs_quoting_uppercase(self):
        assert print_term(Atom("Foo")) == "'Foo'"

    def test_atom_needs_quoting_space(self):
        assert print_term(Atom("hello world")) == "'hello world'"

    def test_atom_needs_quoting_digit_start(self):
        assert print_term(Atom("123abc")) == "'123abc'"

    def test_empty_list_atom(self):
        assert print_term(NIL) == "[]"

    def test_operator_atom(self):
        assert print_term(Atom(":-")) == ":-"

    def test_atom_with_quote(self):
        assert print_term(Atom("can't")) == "'can''t'"


class TestPrintVariables:
    """Tests for printing variables."""

    def test_simple_variable(self):
        v = Var("X")
        assert print_term(v) == "X"

    def test_bound_variable(self):
        v = Var("X")
        v.bind(Integer(42))
        assert print_term(v) == "42"

    def test_bound_variable_no_deref(self):
        v = Var("X")
        v.bind(Integer(42))
        assert print_term(v, deref=False) == "X"


class TestPrintNumbers:
    """Tests for printing numbers."""

    def test_integer(self):
        assert print_term(Integer(42)) == "42"

    def test_negative_integer(self):
        assert print_term(Integer(-42)) == "-42"

    def test_float(self):
        result = print_term(Float(3.14))
        assert "3.14" in result

    def test_float_whole(self):
        # Ensure whole numbers get decimal point
        result = print_term(Float(3.0))
        assert "." in result


class TestPrintStructures:
    """Tests for printing structures."""

    def test_simple_structure(self):
        s = Struct(Atom("foo"), (Integer(1), Integer(2)))
        assert print_term(s) == "foo(1, 2)"

    def test_empty_structure(self):
        s = Struct(Atom("foo"), ())
        assert print_term(s) == "foo()"

    def test_nested_structure(self):
        inner = Struct(Atom("bar"), (Integer(1),))
        outer = Struct(Atom("foo"), (inner,))
        assert print_term(outer) == "foo(bar(1))"

    def test_structure_with_var(self):
        v = Var("X")
        s = Struct(Atom("foo"), (v,))
        assert print_term(s) == "foo(X)"


class TestPrintLists:
    """Tests for printing lists."""

    def test_empty_list(self):
        assert print_term(NIL) == "[]"

    def test_single_element(self):
        lst = make_list([Integer(1)])
        assert print_term(lst) == "[1]"

    def test_multiple_elements(self):
        lst = make_list([Integer(1), Integer(2), Integer(3)])
        assert print_term(lst) == "[1, 2, 3]"

    def test_improper_list(self):
        t = Var("T")
        lst = make_list([Integer(1), Integer(2)], t)
        assert print_term(lst) == "[1, 2 | T]"

    def test_nested_list(self):
        inner = make_list([Integer(1), Integer(2)])
        outer = make_list([inner, Integer(3)])
        assert print_term(outer) == "[[1, 2], 3]"


class TestRoundTrip:
    """Tests for parse -> print -> parse round-trip."""

    def assert_roundtrip(self, source: str):
        """Assert that parsing and printing gives equivalent result."""
        t1 = parse_term(source)
        printed = print_term(t1)
        t2 = parse_term(printed)

        # Compare structurally
        assert self.terms_equal(t1, t2), f"Round-trip failed: {source!r} -> {printed!r}"

    def terms_equal(self, t1, t2) -> bool:
        """Check structural equality of two terms (ignoring variable names)."""
        t1 = t1.deref()
        t2 = t2.deref()

        if type(t1) != type(t2):
            return False

        if isinstance(t1, Var):
            # Variables are equal if both unbound (names may differ)
            return not t1.is_bound() and not t2.is_bound()

        if isinstance(t1, Atom):
            return t1.name == t2.name

        if isinstance(t1, Integer):
            return t1.value == t2.value

        if isinstance(t1, Float):
            return t1.value == t2.value

        if isinstance(t1, Struct):
            if t1.functor != t2.functor or t1.arity != t2.arity:
                return False
            return all(self.terms_equal(a, b) for a, b in zip(t1.args, t2.args))

        if isinstance(t1, Cons):
            return (self.terms_equal(t1.head, t2.head) and
                    self.terms_equal(t1.tail, t2.tail))

        return False

    def test_atom(self):
        self.assert_roundtrip("foo")

    def test_quoted_atom(self):
        self.assert_roundtrip("'Hello World'")

    def test_integer(self):
        self.assert_roundtrip("42")

    def test_negative_integer(self):
        self.assert_roundtrip("-42")

    def test_float(self):
        self.assert_roundtrip("3.14")

    def test_variable(self):
        self.assert_roundtrip("X")

    def test_structure(self):
        self.assert_roundtrip("foo(1, 2, 3)")

    def test_nested_structure(self):
        self.assert_roundtrip("foo(bar(X), baz(Y))")

    def test_empty_list(self):
        self.assert_roundtrip("[]")

    def test_list(self):
        self.assert_roundtrip("[1, 2, 3]")

    def test_list_with_tail(self):
        self.assert_roundtrip("[a, b | T]")

    def test_nested_list(self):
        self.assert_roundtrip("[[1, 2], [3, 4]]")

    def test_complex(self):
        self.assert_roundtrip("foo([1, bar(X, Y)], Z)")
