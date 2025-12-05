"""
Tests for AKL term parser.
"""

import pytest
from pyakl import (
    parse_term, parse_clause, parse_clauses, ParseError,
    Term, Var, Atom, Integer, Float, Struct, Cons, NIL, make_list
)
from pyakl.parser import Lexer, TokenType


class TestLexer:
    """Tests for the lexer."""

    def test_simple_atom(self):
        lexer = Lexer("foo")
        token = lexer.next_token()
        assert token.type == TokenType.ATOM
        assert token.value == "foo"

    def test_variable(self):
        lexer = Lexer("X")
        token = lexer.next_token()
        assert token.type == TokenType.VARIABLE
        assert token.value == "X"

    def test_underscore_variable(self):
        lexer = Lexer("_Foo")
        token = lexer.next_token()
        assert token.type == TokenType.VARIABLE
        assert token.value == "_Foo"

    def test_anonymous_variable(self):
        lexer = Lexer("_")
        token = lexer.next_token()
        assert token.type == TokenType.VARIABLE
        assert token.value == "_"

    def test_integer(self):
        lexer = Lexer("42")
        token = lexer.next_token()
        assert token.type == TokenType.INTEGER
        assert token.value == "42"

    def test_minus_as_operator(self):
        """Minus is lexed as operator, not part of number."""
        lexer = Lexer("-42")
        token = lexer.next_token()
        assert token.type == TokenType.OPERATOR
        assert token.value == "-"
        token = lexer.next_token()
        assert token.type == TokenType.INTEGER
        assert token.value == "42"

    def test_float(self):
        lexer = Lexer("3.14")
        token = lexer.next_token()
        assert token.type == TokenType.FLOAT
        assert token.value == "3.14"

    def test_float_exponent(self):
        lexer = Lexer("1.5e10")
        token = lexer.next_token()
        assert token.type == TokenType.FLOAT

    def test_base_notation(self):
        lexer = Lexer("2'1010")
        token = lexer.next_token()
        assert token.type == TokenType.INTEGER
        assert token.value == "10"  # binary 1010 = 10

    def test_hex_notation(self):
        lexer = Lexer("16'FF")
        token = lexer.next_token()
        assert token.type == TokenType.INTEGER
        assert token.value == "255"

    def test_char_code(self):
        lexer = Lexer("0'A")
        token = lexer.next_token()
        assert token.type == TokenType.INTEGER
        assert token.value == "65"

    def test_quoted_atom(self):
        lexer = Lexer("'hello world'")
        token = lexer.next_token()
        assert token.type == TokenType.QUOTED_ATOM
        assert token.value == "hello world"

    def test_quoted_atom_escaped(self):
        lexer = Lexer("'can''t'")
        token = lexer.next_token()
        assert token.type == TokenType.QUOTED_ATOM
        assert token.value == "can't"

    def test_operator(self):
        lexer = Lexer(":-")
        token = lexer.next_token()
        assert token.type == TokenType.OPERATOR
        assert token.value == ":-"

    def test_arrow_operator(self):
        lexer = Lexer("->")
        token = lexer.next_token()
        assert token.type == TokenType.OPERATOR
        assert token.value == "->"

    def test_empty_list_atom(self):
        lexer = Lexer("[]")
        token = lexer.next_token()
        assert token.type == TokenType.ATOM
        assert token.value == "[]"

    def test_line_comment(self):
        lexer = Lexer("% this is a comment\nfoo")
        token = lexer.next_token()
        assert token.type == TokenType.ATOM
        assert token.value == "foo"

    def test_block_comment(self):
        lexer = Lexer("/* block\ncomment */foo")
        token = lexer.next_token()
        assert token.type == TokenType.ATOM
        assert token.value == "foo"

    def test_punctuation(self):
        lexer = Lexer("(,)|")
        tokens = lexer.tokenize()
        types = [t.type for t in tokens[:-1]]  # exclude EOF
        assert types == [
            TokenType.LPAREN,
            TokenType.COMMA,
            TokenType.RPAREN,
            TokenType.PIPE,
        ]

    def test_special_atoms(self):
        lexer = Lexer("! ;")
        t1 = lexer.next_token()
        t2 = lexer.next_token()
        assert t1.type == TokenType.ATOM and t1.value == "!"
        assert t2.type == TokenType.ATOM and t2.value == ";"


class TestParseAtoms:
    """Tests for parsing atoms."""

    def test_simple_atom(self):
        t = parse_term("foo")
        assert t == Atom("foo")

    def test_atom_with_digits(self):
        t = parse_term("foo123")
        assert t == Atom("foo123")

    def test_atom_with_underscore(self):
        t = parse_term("foo_bar")
        assert t == Atom("foo_bar")

    def test_quoted_atom(self):
        t = parse_term("'Hello World'")
        assert t == Atom("Hello World")

    def test_empty_list_atom(self):
        t = parse_term("[]")
        assert t == NIL

    def test_operator_atom(self):
        t = parse_term(":-")
        assert t == Atom(":-")

    def test_arrow_atom(self):
        t = parse_term("->")
        assert t == Atom("->")


class TestParseVariables:
    """Tests for parsing variables."""

    def test_simple_variable(self):
        t = parse_term("X")
        assert isinstance(t, Var)
        assert t.name == "X"

    def test_variable_with_digits(self):
        t = parse_term("X123")
        assert isinstance(t, Var)
        assert t.name == "X123"

    def test_anonymous_variable(self):
        t = parse_term("_")
        assert isinstance(t, Var)
        assert t.name == "_"

    def test_named_underscore_variable(self):
        t = parse_term("_Foo")
        assert isinstance(t, Var)
        assert t.name == "_Foo"


class TestParseNumbers:
    """Tests for parsing numbers."""

    def test_integer(self):
        t = parse_term("42")
        assert t == Integer(42)

    def test_zero(self):
        t = parse_term("0")
        assert t == Integer(0)

    def test_negative_integer(self):
        """Negative numbers parse as -(N) since - is prefix operator."""
        t = parse_term("-42")
        assert isinstance(t, Struct)
        assert t.functor == Atom("-")
        assert t.args == (Integer(42),)

    def test_float(self):
        t = parse_term("3.14")
        assert t == Float(3.14)

    def test_float_exponent(self):
        t = parse_term("1.5e10")
        assert isinstance(t, Float)

    def test_binary(self):
        t = parse_term("2'1010")
        assert t == Integer(10)

    def test_octal(self):
        t = parse_term("8'17")
        assert t == Integer(15)

    def test_hex(self):
        t = parse_term("16'FF")
        assert t == Integer(255)

    def test_char_code(self):
        t = parse_term("0'A")
        assert t == Integer(65)


class TestParseStructures:
    """Tests for parsing structures."""

    def test_simple_structure(self):
        t = parse_term("foo(X)")
        assert isinstance(t, Struct)
        assert t.functor == Atom("foo")
        assert t.arity == 1
        assert isinstance(t.args[0], Var)

    def test_structure_multiple_args(self):
        t = parse_term("point(1, 2, 3)")
        assert isinstance(t, Struct)
        assert t.functor == Atom("point")
        assert t.arity == 3

    def test_nested_structure(self):
        t = parse_term("foo(bar(X))")
        assert isinstance(t, Struct)
        assert t.functor == Atom("foo")
        inner = t.args[0]
        assert isinstance(inner, Struct)
        assert inner.functor == Atom("bar")

    def test_empty_structure(self):
        t = parse_term("foo()")
        assert isinstance(t, Struct)
        assert t.functor == Atom("foo")
        assert t.arity == 0

    def test_structure_with_operator_functor(self):
        t = parse_term(":->(X, Y)")
        assert isinstance(t, Struct)
        assert t.functor == Atom(":->")


class TestParseLists:
    """Tests for parsing lists."""

    def test_empty_list(self):
        t = parse_term("[]")
        assert t is NIL

    def test_single_element(self):
        t = parse_term("[1]")
        assert isinstance(t, Cons)
        assert t.head == Integer(1)
        assert t.tail is NIL

    def test_multiple_elements(self):
        t = parse_term("[1, 2, 3]")
        assert isinstance(t, Cons)
        # Check first element
        assert t.head == Integer(1)
        # Check rest
        rest = t.tail
        assert isinstance(rest, Cons)
        assert rest.head == Integer(2)

    def test_list_with_tail(self):
        t = parse_term("[H|T]")
        assert isinstance(t, Cons)
        assert isinstance(t.head, Var)
        assert t.head.name == "H"
        assert isinstance(t.tail, Var)
        assert t.tail.name == "T"

    def test_list_multiple_with_tail(self):
        t = parse_term("[a, b | Rest]")
        assert isinstance(t, Cons)
        assert t.head == Atom("a")
        rest1 = t.tail
        assert isinstance(rest1, Cons)
        assert rest1.head == Atom("b")
        assert isinstance(rest1.tail, Var)
        assert rest1.tail.name == "Rest"

    def test_nested_list(self):
        t = parse_term("[[1, 2], [3, 4]]")
        assert isinstance(t, Cons)
        assert isinstance(t.head, Cons)


class TestParseComments:
    """Tests for handling comments."""

    def test_line_comment_before(self):
        t = parse_term("% comment\nfoo")
        assert t == Atom("foo")

    def test_line_comment_after(self):
        t = parse_term("foo % comment")
        assert t == Atom("foo")

    def test_block_comment(self):
        t = parse_term("/* comment */ foo")
        assert t == Atom("foo")

    def test_multiline_block_comment(self):
        t = parse_term("/* line1\nline2 */ foo")
        assert t == Atom("foo")


class TestParseErrors:
    """Tests for parse errors."""

    def test_unmatched_paren(self):
        with pytest.raises(ParseError):
            parse_term("foo(X")

    def test_unmatched_bracket(self):
        with pytest.raises(ParseError):
            parse_term("[1, 2")

    def test_extra_token(self):
        with pytest.raises(ParseError):
            parse_term("foo bar")


class TestParseClauses:
    """Tests for parsing clauses."""

    def test_fact(self):
        """Test parsing a simple fact."""
        clause = parse_clause("foo(a, b).")
        assert isinstance(clause, Struct)
        assert clause.functor == Atom("foo")
        assert clause.arity == 2

    def test_rule(self):
        """Test parsing a rule with :- operator."""
        clause = parse_clause("head(X) :- body(X).")
        assert isinstance(clause, Struct)
        assert clause.functor == Atom(":-")
        assert clause.arity == 2

    def test_multiple_clauses(self):
        """Test parsing multiple clauses."""
        source = """
        member(X, [X|_]).
        member(X, [_|R]) :- member(X, R).
        """
        clauses = parse_clauses(source)
        assert len(clauses) == 2


class TestParseOperators:
    """Tests for operator precedence parsing."""

    def test_comma_as_conjunction(self):
        """Comma creates right-associative conjunction."""
        term = parse_term("a, b, c")
        assert isinstance(term, Struct)
        assert term.functor == Atom(",")
        # a, (b, c)
        assert term.args[0] == Atom("a")
        assert isinstance(term.args[1], Struct)
        assert term.args[1].functor == Atom(",")

    def test_clause_operator(self):
        """Test :- operator."""
        term = parse_term("head :- body")
        assert isinstance(term, Struct)
        assert term.functor == Atom(":-")
        assert term.args[0] == Atom("head")
        assert term.args[1] == Atom("body")

    def test_guard_operator(self):
        """Test ? guard operator."""
        term = parse_term("guard ? body")
        assert isinstance(term, Struct)
        assert term.functor == Atom("?")

    def test_quiet_guard_operator(self):
        """Test ?? guard operator."""
        term = parse_term("guard ?? body")
        assert isinstance(term, Struct)
        assert term.functor == Atom("??")

    def test_arrow_operator(self):
        """Test -> operator."""
        term = parse_term("cond -> then")
        assert isinstance(term, Struct)
        assert term.functor == Atom("->")

    def test_arithmetic(self):
        """Test arithmetic operators."""
        term = parse_term("X is 1 + 2 * 3")
        # Should be: is(X, +(1, *(2, 3)))
        assert isinstance(term, Struct)
        assert term.functor == Atom("is")

    def test_comparison(self):
        """Test comparison operators."""
        term = parse_term("X > Y")
        assert isinstance(term, Struct)
        assert term.functor == Atom(">")

    def test_precedence_arithmetic(self):
        """Test that * binds tighter than +."""
        term = parse_term("1 + 2 * 3")
        # Should be +(1, *(2, 3))
        assert term.functor == Atom("+")
        assert term.args[0] == Integer(1)
        assert isinstance(term.args[1], Struct)
        assert term.args[1].functor == Atom("*")

    def test_unary_minus(self):
        """Test unary minus as prefix operator."""
        term = parse_term("-X")
        assert isinstance(term, Struct)
        assert term.functor == Atom("-")
        assert term.arity == 1
