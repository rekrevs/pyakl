"""
Tests for term representation.

Tests the fundamental properties required by the AKL semantics:
- Variable identity (same name != same variable)
- Atom interning (same name == same object)
- Variable binding and dereferencing
- List construction and deconstruction
"""

import pytest
from pyakl.term import (
    Term,
    Var,
    Atom,
    Integer,
    Float,
    Struct,
    Cons,
    NIL,
    make_list,
    list_to_python,
)


class TestVar:
    """Tests for logic variables."""

    def test_var_identity_different_objects(self):
        """Two variables with same name are different objects."""
        x1 = Var("X")
        x2 = Var("X")
        assert x1 is not x2
        assert id(x1) != id(x2)

    def test_var_identity_same_object(self):
        """Same variable object is identical to itself."""
        x = Var("X")
        y = x
        assert x is y

    def test_var_initially_unbound(self):
        """New variables are unbound."""
        x = Var("X")
        assert not x.is_bound()
        assert x.binding is None

    def test_var_deref_unbound(self):
        """Dereferencing unbound variable returns itself."""
        x = Var("X")
        assert x.deref() is x

    def test_var_bind(self):
        """Variables can be bound to terms."""
        x = Var("X")
        val = Integer(42)
        x.bind(val)
        assert x.is_bound()
        assert x.binding is val

    def test_var_deref_bound(self):
        """Dereferencing bound variable returns the value."""
        x = Var("X")
        val = Integer(42)
        x.bind(val)
        assert x.deref() is val

    def test_var_deref_chain(self):
        """Dereferencing follows binding chains."""
        x = Var("X")
        y = Var("Y")
        val = Integer(42)

        x.bind(y)
        y.bind(val)

        assert x.deref() is val
        assert y.deref() is val

    def test_var_cannot_rebind(self):
        """Binding an already-bound variable raises error."""
        x = Var("X")
        x.bind(Integer(1))

        with pytest.raises(AssertionError):
            x.bind(Integer(2))

    def test_var_unbind(self):
        """Variables can be unbound (for backtracking)."""
        x = Var("X")
        x.bind(Integer(42))
        x.unbind()
        assert not x.is_bound()
        assert x.deref() is x

    def test_var_auto_name(self):
        """Variables get automatic names if none provided."""
        x = Var()
        assert x.name.startswith("_G")

    def test_var_repr_unbound(self):
        """Unbound variable repr shows name."""
        x = Var("X")
        assert repr(x) == "X"

    def test_var_repr_bound(self):
        """Bound variable repr shows name=value."""
        x = Var("X")
        x.bind(Integer(42))
        assert repr(x) == "X=42"


class TestAtom:
    """Tests for atoms (named constants)."""

    def test_atom_interning(self):
        """Atoms with same name are the same object."""
        a1 = Atom("foo")
        a2 = Atom("foo")
        assert a1 is a2

    def test_atom_different_names(self):
        """Atoms with different names are different objects."""
        a1 = Atom("foo")
        a2 = Atom("bar")
        assert a1 is not a2

    def test_atom_deref(self):
        """Atoms dereference to themselves."""
        a = Atom("foo")
        assert a.deref() is a

    def test_atom_equality(self):
        """Atom equality works correctly."""
        a1 = Atom("foo")
        a2 = Atom("foo")
        a3 = Atom("bar")

        assert a1 == a2
        assert a1 != a3

    def test_atom_hash(self):
        """Atoms are hashable."""
        a = Atom("foo")
        d = {a: "value"}
        assert d[Atom("foo")] == "value"

    def test_atom_repr_simple(self):
        """Simple atom repr is just the name."""
        a = Atom("foo")
        assert repr(a) == "foo"

    def test_atom_repr_quoted(self):
        """Atoms needing quotes are quoted in repr."""
        a = Atom("Hello World")
        assert repr(a) == "'Hello World'"

    def test_nil_is_atom(self):
        """NIL is an atom."""
        assert isinstance(NIL, Atom)
        assert NIL.name == "[]"


class TestInteger:
    """Tests for integer constants."""

    def test_integer_value(self):
        """Integer stores its value."""
        i = Integer(42)
        assert i.value == 42

    def test_integer_deref(self):
        """Integer dereferences to itself."""
        i = Integer(42)
        assert i.deref() is i

    def test_integer_equality(self):
        """Integer equality based on value."""
        i1 = Integer(42)
        i2 = Integer(42)
        i3 = Integer(43)

        assert i1 == i2
        assert i1 != i3

    def test_integer_hash(self):
        """Integers are hashable."""
        i = Integer(42)
        d = {i: "value"}
        assert d[Integer(42)] == "value"

    def test_integer_repr(self):
        """Integer repr is the number."""
        assert repr(Integer(42)) == "42"
        assert repr(Integer(-5)) == "-5"


class TestFloat:
    """Tests for float constants."""

    def test_float_value(self):
        """Float stores its value."""
        f = Float(3.14)
        assert f.value == 3.14

    def test_float_deref(self):
        """Float dereferences to itself."""
        f = Float(3.14)
        assert f.deref() is f

    def test_float_equality(self):
        """Float equality based on value."""
        f1 = Float(3.14)
        f2 = Float(3.14)
        f3 = Float(2.71)

        assert f1 == f2
        assert f1 != f3

    def test_float_repr(self):
        """Float repr is the number."""
        assert repr(Float(3.14)) == "3.14"


class TestStruct:
    """Tests for compound terms (structures)."""

    def test_struct_creation(self):
        """Struct stores functor and args."""
        f = Atom("foo")
        s = Struct(f, (Integer(1), Integer(2)))

        assert s.functor is f
        assert s.arity == 2
        assert s.args == (Integer(1), Integer(2))

    def test_struct_deref(self):
        """Struct dereferences to itself."""
        s = Struct(Atom("foo"), (Integer(1),))
        assert s.deref() is s

    def test_struct_with_variables(self):
        """Struct can contain variables."""
        x = Var("X")
        s = Struct(Atom("foo"), (x, Integer(2)))

        assert s.args[0] is x

        # After binding, deref shows bound value
        x.bind(Integer(1))
        assert s.args[0].deref() == Integer(1)

    def test_struct_equality(self):
        """Struct equality checks functor and args."""
        s1 = Struct(Atom("foo"), (Integer(1), Integer(2)))
        s2 = Struct(Atom("foo"), (Integer(1), Integer(2)))
        s3 = Struct(Atom("foo"), (Integer(1), Integer(3)))
        s4 = Struct(Atom("bar"), (Integer(1), Integer(2)))

        assert s1 == s2
        assert s1 != s3  # Different arg
        assert s1 != s4  # Different functor

    def test_struct_equality_with_vars(self):
        """Struct equality dereferences variables."""
        x = Var("X")
        x.bind(Integer(1))

        s1 = Struct(Atom("foo"), (x,))
        s2 = Struct(Atom("foo"), (Integer(1),))

        assert s1 == s2

    def test_struct_repr(self):
        """Struct repr shows functor(args)."""
        s = Struct(Atom("foo"), (Integer(1), Integer(2)))
        assert repr(s) == "foo(1, 2)"

    def test_struct_empty_args(self):
        """Struct with no args."""
        s = Struct(Atom("foo"), ())
        assert s.arity == 0
        assert repr(s) == "foo()"


class TestList:
    """Tests for list structures (Cons/NIL)."""

    def test_nil_is_empty_list(self):
        """NIL represents empty list."""
        assert NIL.name == "[]"

    def test_cons_creation(self):
        """Cons creates list cell."""
        c = Cons(Integer(1), NIL)
        assert c.head == Integer(1)
        assert c.tail is NIL

    def test_cons_deref(self):
        """Cons dereferences to itself."""
        c = Cons(Integer(1), NIL)
        assert c.deref() is c

    def test_make_list_empty(self):
        """make_list with empty list returns NIL."""
        lst = make_list([])
        assert lst is NIL

    def test_make_list_single(self):
        """make_list with one element."""
        lst = make_list([Integer(1)])
        assert isinstance(lst, Cons)
        assert lst.head == Integer(1)
        assert lst.tail is NIL

    def test_make_list_multiple(self):
        """make_list with multiple elements."""
        lst = make_list([Integer(1), Integer(2), Integer(3)])

        assert isinstance(lst, Cons)
        assert lst.head == Integer(1)

        tail1 = lst.tail
        assert isinstance(tail1, Cons)
        assert tail1.head == Integer(2)

        tail2 = tail1.tail
        assert isinstance(tail2, Cons)
        assert tail2.head == Integer(3)
        assert tail2.tail is NIL

    def test_make_list_with_tail(self):
        """make_list with custom tail (improper list)."""
        t = Var("T")
        lst = make_list([Integer(1), Integer(2)], t)

        assert isinstance(lst, Cons)
        tail = lst.tail
        assert isinstance(tail, Cons)
        assert tail.tail is t

    def test_list_repr_proper(self):
        """Proper list repr shows [a, b, c]."""
        lst = make_list([Integer(1), Integer(2), Integer(3)])
        assert repr(lst) == "[1, 2, 3]"

    def test_list_repr_improper(self):
        """Improper list repr shows [a, b | T]."""
        t = Var("T")
        lst = make_list([Integer(1), Integer(2)], t)
        assert repr(lst) == "[1, 2 | T]"

    def test_list_repr_empty(self):
        """Empty list repr is []."""
        assert repr(NIL) == "[]"

    def test_list_equality(self):
        """List equality compares elements."""
        l1 = make_list([Integer(1), Integer(2)])
        l2 = make_list([Integer(1), Integer(2)])
        l3 = make_list([Integer(1), Integer(3)])

        assert l1 == l2
        assert l1 != l3

    def test_list_to_python(self):
        """Convert proper list to Python list."""
        lst = make_list([Integer(1), Integer(2), Integer(3)])
        py_list = list_to_python(lst)

        assert py_list == [Integer(1), Integer(2), Integer(3)]

    def test_list_to_python_empty(self):
        """Convert empty list to Python list."""
        py_list = list_to_python(NIL)
        assert py_list == []

    def test_list_to_python_improper_fails(self):
        """Converting improper list raises error."""
        t = Var("T")
        lst = make_list([Integer(1)], t)

        with pytest.raises(ValueError):
            list_to_python(lst)


class TestDeref:
    """Tests for dereferencing in complex structures."""

    def test_deref_nested_vars(self):
        """Dereference through multiple variable bindings."""
        x = Var("X")
        y = Var("Y")
        z = Var("Z")

        x.bind(y)
        y.bind(z)
        z.bind(Integer(42))

        assert x.deref() == Integer(42)

    def test_deref_in_struct(self):
        """Variables in structs are dereferenced for equality."""
        x = Var("X")
        y = Var("Y")

        s1 = Struct(Atom("foo"), (x, y))
        s2 = Struct(Atom("foo"), (Integer(1), Integer(2)))

        # Before binding, not equal
        assert s1 != s2

        # After binding, equal
        x.bind(Integer(1))
        y.bind(Integer(2))
        assert s1 == s2

    def test_deref_in_list(self):
        """Variables in lists are dereferenced."""
        x = Var("X")
        lst = make_list([x, Integer(2)])

        x.bind(Integer(1))

        expected = make_list([Integer(1), Integer(2)])
        assert lst == expected


class TestTermIsInstance:
    """Test that all term types are instances of Term."""

    def test_var_is_term(self):
        assert isinstance(Var("X"), Term)

    def test_atom_is_term(self):
        assert isinstance(Atom("foo"), Term)

    def test_integer_is_term(self):
        assert isinstance(Integer(42), Term)

    def test_float_is_term(self):
        assert isinstance(Float(3.14), Term)

    def test_struct_is_term(self):
        assert isinstance(Struct(Atom("foo"), ()), Term)

    def test_cons_is_term(self):
        assert isinstance(Cons(Integer(1), NIL), Term)

    def test_nil_is_term(self):
        assert isinstance(NIL, Term)
