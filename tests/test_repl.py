"""
Tests for the PyAKL REPL and query execution.

These tests verify query execution functionality using the interpreter directly.
"""

import pytest
from io import StringIO
import sys

from pyakl.program import Program, load_string
from pyakl.interpreter import Interpreter
from pyakl.parser import parse_term
from pyakl.repl import execute_query


class TestQueryExecution:
    """Tests for query execution."""

    def test_query_success(self):
        prog = load_string("foo(a).")
        interp = Interpreter(prog)
        goal = parse_term("foo(a)")

        solutions = list(interp.solve(goal))
        assert len(solutions) == 1
        assert solutions[0].bindings == {}

    def test_query_failure(self):
        prog = load_string("foo(a).")
        interp = Interpreter(prog)
        goal = parse_term("foo(b)")

        solutions = list(interp.solve(goal))
        assert len(solutions) == 0

    def test_query_with_binding(self):
        prog = load_string("foo(hello).")
        interp = Interpreter(prog)
        goal = parse_term("foo(X)")

        solutions = list(interp.solve(goal))
        assert len(solutions) == 1
        assert "X" in solutions[0].bindings

    def test_query_multiple_solutions(self):
        prog = load_string("""
            foo(a).
            foo(b).
            foo(c).
        """)
        interp = Interpreter(prog)
        goal = parse_term("foo(X)")

        solutions = list(interp.solve(goal))
        assert len(solutions) == 3


class TestExecuteQuery:
    """Tests for the execute_query function."""

    def test_execute_query_success(self, capsys):
        prog = load_string("foo(a).")
        execute_query("foo(a)", prog, show_all=True)

        captured = capsys.readouterr()
        assert "true" in captured.out
        assert "yes" in captured.out

    def test_execute_query_failure(self, capsys):
        prog = load_string("foo(a).")
        execute_query("foo(b)", prog, show_all=True)

        captured = capsys.readouterr()
        assert "no" in captured.out

    def test_execute_query_with_binding(self, capsys):
        prog = load_string("foo(hello).")
        execute_query("foo(X)", prog, show_all=True)

        captured = capsys.readouterr()
        assert "X = hello" in captured.out

    def test_execute_query_multiple_solutions(self, capsys):
        prog = load_string("""
            foo(a).
            foo(b).
            foo(c).
        """)
        execute_query("foo(X)", prog, show_all=True)

        captured = capsys.readouterr()
        assert "X = a" in captured.out
        assert "X = b" in captured.out
        assert "X = c" in captured.out


class TestDirective:
    """Tests for directive-like queries."""

    def test_true_succeeds(self):
        prog = Program()
        interp = Interpreter(prog)
        goal = parse_term("true")

        solutions = list(interp.solve(goal))
        assert len(solutions) == 1

    def test_fail_fails(self):
        prog = Program()
        interp = Interpreter(prog)
        goal = parse_term("fail")

        solutions = list(interp.solve(goal))
        assert len(solutions) == 0


class TestClauseAddition:
    """Tests for adding clauses to program."""

    def test_add_fact(self):
        prog = load_string("foo(a).")
        assert len(prog.get_clauses("foo", 1)) == 1

    def test_add_rule(self):
        prog = load_string("mortal(X) :- human(X).")
        assert len(prog.get_clauses("mortal", 1)) == 1

    def test_add_multiple_clauses(self):
        prog = load_string("""
            foo(a).
            foo(b).
            foo(c).
        """)
        assert len(prog.get_clauses("foo", 1)) == 3


class TestPredicateListing:
    """Tests for listing predicates."""

    def test_empty_program(self):
        prog = Program()
        preds = list(prog.predicates())
        assert len(preds) == 0

    def test_program_with_predicates(self):
        prog = load_string("""
            foo(a).
            foo(b).
            bar(x, y).
        """)
        preds = list(prog.predicates())
        names = {p.name for p in preds}
        assert "foo" in names
        assert "bar" in names


class TestIntegration:
    """Integration tests for query execution."""

    def test_grandparent_query(self, capsys):
        prog = load_string("""
            parent(tom, bob).
            parent(bob, pat).
            grandparent(X, Z) :- parent(X, Y), parent(Y, Z).
        """)
        execute_query("grandparent(tom, pat)", prog, show_all=True)

        captured = capsys.readouterr()
        assert "true" in captured.out
        assert "yes" in captured.out

    def test_member_query(self, capsys):
        prog = load_string("""
            member(X, [X|_]).
            member(X, [_|T]) :- member(X, T).
        """)
        execute_query("member(X, [1,2,3])", prog, show_all=True)

        captured = capsys.readouterr()
        assert "X = 1" in captured.out
        assert "X = 2" in captured.out
        assert "X = 3" in captured.out

    def test_arithmetic(self, capsys):
        prog = Program()
        execute_query("X is 2 + 3 * 4", prog, show_all=True)

        captured = capsys.readouterr()
        assert "X = 14" in captured.out
