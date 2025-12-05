"""
PyAKL - Python implementation of the Andorra Kernel Language.

A high-level implementation of AKL semantics using Python's
garbage collection and dynamic features.
"""

from .term import (
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

from .parser import parse_term, parse_clause, parse_clauses, ParseError
from .printer import print_term
from .program import Program, Clause, load_string, load_file
from .interpreter import (
    Interpreter,
    Solution,
    solve,
    solve_all,
    solve_one,
    query,
    query_all,
    query_one,
)
# REPL imported lazily to avoid circular import when running python -m pyakl.repl
def __getattr__(name: str):
    if name == "REPL":
        from .repl import REPL
        return REPL
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
from .builtin import akl_context

__version__ = "0.1.0"

__all__ = [
    # Terms
    "Term",
    "Var",
    "Atom",
    "Integer",
    "Float",
    "Struct",
    "Cons",
    "NIL",
    "make_list",
    "list_to_python",
    # Parser
    "parse_term",
    "parse_clause",
    "parse_clauses",
    "ParseError",
    # Printer
    "print_term",
    # Program
    "Program",
    "Clause",
    "load_string",
    "load_file",
    # Interpreter
    "Interpreter",
    "Solution",
    "solve",
    "solve_all",
    "solve_one",
    "query",
    "query_all",
    "query_one",
    # REPL
    "REPL",
    # Context
    "akl_context",
]
