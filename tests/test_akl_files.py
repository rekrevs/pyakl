"""
Tests parsing real AKL source files from akl-agents/demos.

These tests verify that the parser can handle real-world AKL syntax
by parsing full clauses from source files.
"""

import pytest
import os
from pathlib import Path

from pyakl import parse_term, parse_clauses, print_term, ParseError
from pyakl.parser import Lexer, TokenType


# Path to AKL demos
AKL_DEMOS_PATH = Path(__file__).parent.parent.parent / "akl-agents" / "demos"


def get_akl_files():
    """Get list of AKL files to test."""
    if not AKL_DEMOS_PATH.exists():
        pytest.skip(f"AKL demos not found at {AKL_DEMOS_PATH}")
    return list(AKL_DEMOS_PATH.glob("*.akl"))


class TestAKLFiles:
    """Test parsing clauses from real AKL files."""

    @pytest.fixture
    def akl_files(self):
        """Get available AKL files."""
        files = get_akl_files()
        if not files:
            pytest.skip("No AKL files found")
        return files

    def test_can_find_akl_files(self, akl_files):
        """Verify we can find AKL demo files."""
        assert len(akl_files) > 0

    def test_parse_member_akl(self):
        """Test parsing member.akl - simple clauses."""
        filepath = AKL_DEMOS_PATH / "member.akl"
        if not filepath.exists():
            pytest.skip("member.akl not found")

        source = filepath.read_text()
        clauses = parse_clauses(source)

        # Should have multiple clauses
        assert len(clauses) > 0

        # Check we have member clauses
        from pyakl import Struct, Atom
        member_clauses = [c for c in clauses
                         if (isinstance(c, Struct) and
                             c.functor == Atom("member")) or
                            (isinstance(c, Struct) and
                             c.functor == Atom(":-") and
                             isinstance(c.args[0], Struct) and
                             c.args[0].functor == Atom("member"))]
        assert len(member_clauses) >= 2  # At least the two member clauses

    def test_parse_lists_akl(self):
        """Test parsing lists.akl."""
        filepath = AKL_DEMOS_PATH / "lists.akl"
        if not filepath.exists():
            pytest.skip("lists.akl not found")

        source = filepath.read_text()
        clauses = parse_clauses(source)
        assert len(clauses) > 0

    def test_parse_queens_akl(self):
        """Test parsing queens.akl (more complex)."""
        filepath = AKL_DEMOS_PATH / "queens.akl"
        if not filepath.exists():
            pytest.skip("queens.akl not found")

        source = filepath.read_text()
        clauses = parse_clauses(source)
        assert len(clauses) > 10  # Queens has many clauses

    def test_parse_simple_terms(self):
        """Test parsing individual terms."""
        test_terms = [
            "member",
            "X",
            "R",
            "[X|_]",
            "[_|R]",
            "nlist",
            "1",
            "[1,2,3,4,5]",
            "qmember",
            "6",
        ]

        for term_str in test_terms:
            try:
                t = parse_term(term_str)
                # Verify round-trip
                printed = print_term(t)
                t2 = parse_term(printed)
                assert type(t) == type(t2), f"Round-trip failed for {term_str}"
            except ParseError as e:
                pytest.fail(f"Failed to parse term '{term_str}': {e}")

    def test_parse_list_terms(self):
        """Test parsing various list forms from AKL files."""
        list_terms = [
            "[]",
            "[1]",
            "[1, 2, 3]",
            "[H|T]",
            "[X|_]",
            "[_|R]",
            "[1, 2, 3, 4, 5]",
            "[a, b, c]",
            "[[1, 2], [3, 4]]",
        ]

        for term_str in list_terms:
            t = parse_term(term_str)
            printed = print_term(t)
            t2 = parse_term(printed)
            # Both should parse to lists
            from pyakl import Cons, NIL
            if term_str != "[]":
                assert isinstance(t, Cons), f"Expected Cons for {term_str}"

    def test_parse_structure_terms(self):
        """Test parsing structure forms from AKL files."""
        struct_terms = [
            "foo(X)",
            "bar(1, 2)",
            "point(X, Y, Z)",
            "functor(A, c, N)",
            "arg(M, B, A)",
        ]

        for term_str in struct_terms:
            t = parse_term(term_str)
            printed = print_term(t)
            t2 = parse_term(printed)
            from pyakl import Struct
            assert isinstance(t, Struct), f"Expected Struct for {term_str}"

    def test_parse_number_terms(self):
        """Test parsing number forms from AKL files."""
        # Positive numbers parse directly
        positive_terms = ["0", "1", "42", "3.14", "0.0", "1.5"]
        for term_str in positive_terms:
            t = parse_term(term_str)
            from pyakl import Integer, Float
            assert isinstance(t, (Integer, Float)), f"Expected number for {term_str}"

        # Negative numbers parse as -(N) since - is an operator
        from pyakl import Struct, Atom
        for term_str in ["-1", "-42"]:
            t = parse_term(term_str)
            assert isinstance(t, Struct), f"Expected -(N) for {term_str}"
            assert t.functor == Atom("-")
            assert t.arity == 1

    def test_parse_all_demo_files(self):
        """Test that parser can parse all demo files as clauses."""
        akl_files = get_akl_files()
        total_clauses = 0
        failed_files = []

        for filepath in akl_files:
            try:
                source = filepath.read_text()
                clauses = parse_clauses(source)
                total_clauses += len(clauses)
            except ParseError as e:
                failed_files.append((filepath.name, str(e)))

        # Report results
        if failed_files:
            failures = "\n".join(f"  {f}: {e}" for f, e in failed_files[:10])
            pytest.fail(f"Failed to parse {len(failed_files)} files:\n{failures}")

        assert total_clauses > 100, f"Expected to parse >100 clauses, got {total_clauses}"
        print(f"\nParsed {total_clauses} clauses from {len(akl_files)} files")

    def test_comments_properly_ignored(self):
        """Test that comments in AKL files are properly skipped."""
        # From member.akl
        source = """
        % QUIET WAIT

        % Horn clauses

        member(X,[X|_]).
        """

        lexer = Lexer(source)
        tokens = [t for t in lexer.tokenize() if t.type != TokenType.EOF]

        # Comments should be skipped, so we should only see tokens from the clause
        values = [t.value for t in tokens]
        assert "QUIET" not in values
        assert "Horn" not in values
        assert "member" in values

    def test_block_comments_properly_ignored(self):
        """Test that block comments are properly skipped."""
        # From queens.akl
        source = """
        /* to display the board */

        dqueens(R,C,Rws)
        """

        lexer = Lexer(source)
        tokens = [t for t in lexer.tokenize() if t.type != TokenType.EOF]

        values = [t.value for t in tokens]
        assert "display" not in values
        assert "board" not in values
        assert "dqueens" in values
