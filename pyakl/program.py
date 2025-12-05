"""
Program storage and clause compilation for AKL.

This module provides:
- Clause: Preprocessed clause structure
- Predicate: Collection of clauses for a functor/arity
- Program: Database of predicates
- compile_clause: Convert parsed term to Clause
- load_file: Load AKL source file into Program
"""

from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum, auto
from pathlib import Path
from typing import Any

from .term import Term, Var, Atom, Integer, Float, Struct, Cons, NIL
from .parser import parse_clauses
from .unify import collect_vars


class GuardType(Enum):
    """Types of guards in AKL clauses."""
    NONE = auto()        # No guard (fact or simple rule)
    WAIT = auto()        # ? - nondeterminate wait
    QUIET_WAIT = auto()  # ?? - quiet/ordered wait
    ARROW = auto()       # -> - conditional (if-then)
    COMMIT = auto()      # | - commit (local cut)
    CUT = auto()         # ! - hard cut


@dataclass
class Clause:
    """
    A preprocessed AKL clause.

    Attributes:
        head: The clause head (for matching)
        guard: Guard expression (before guard operator), or None
        guard_type: Type of guard operator
        body: Body goals (after guard operator)
        source: Original source term
        head_vars: Variables appearing in head
        all_vars: All variables in clause
    """
    head: Term
    guard: Term | None = None
    guard_type: GuardType = GuardType.NONE
    body: list[Term] = field(default_factory=list)
    source: Term | None = None
    head_vars: set[str] = field(default_factory=set)
    all_vars: set[str] = field(default_factory=set)

    @property
    def is_fact(self) -> bool:
        """Check if this is a simple fact (no body)."""
        return self.guard is None and len(self.body) == 0

    @property
    def functor(self) -> Atom:
        """Get the head functor."""
        head = self.head
        if isinstance(head, Atom):
            return head
        if isinstance(head, Struct):
            return head.functor
        raise ValueError(f"Invalid head: {head}")

    @property
    def arity(self) -> int:
        """Get the head arity."""
        head = self.head
        if isinstance(head, Atom):
            return 0
        if isinstance(head, Struct):
            return head.arity
        raise ValueError(f"Invalid head: {head}")


@dataclass
class Predicate:
    """
    A predicate definition: all clauses for a functor/arity.

    Attributes:
        name: Predicate name
        arity: Number of arguments
        clauses: List of clauses defining this predicate
    """
    name: str
    arity: int
    clauses: list[Clause] = field(default_factory=list)

    def add_clause(self, clause: Clause) -> None:
        """Add a clause to this predicate."""
        self.clauses.append(clause)

    @property
    def functor_key(self) -> tuple[str, int]:
        """Get the (name, arity) key."""
        return (self.name, self.arity)


class Program:
    """
    A collection of predicate definitions.

    Provides lookup by functor/arity and clause management.
    """

    def __init__(self) -> None:
        self._predicates: dict[tuple[str, int], Predicate] = {}

    def add_clause(self, clause: Clause) -> None:
        """Add a clause to the appropriate predicate."""
        key = (clause.functor.name, clause.arity)
        if key not in self._predicates:
            self._predicates[key] = Predicate(clause.functor.name, clause.arity)
        self._predicates[key].add_clause(clause)

    def lookup(self, name: str, arity: int) -> Predicate | None:
        """Look up a predicate by name and arity."""
        return self._predicates.get((name, arity))

    def get_clauses(self, name: str, arity: int) -> list[Clause]:
        """Get clauses for a predicate, or empty list if not found."""
        pred = self.lookup(name, arity)
        return pred.clauses if pred else []

    def predicates(self) -> list[Predicate]:
        """Get all predicates."""
        return list(self._predicates.values())

    def __contains__(self, key: tuple[str, int]) -> bool:
        """Check if predicate exists."""
        return key in self._predicates

    def __len__(self) -> int:
        """Number of predicates."""
        return len(self._predicates)


# =============================================================================
# Clause Compilation
# =============================================================================

def compile_clause(term: Term) -> Clause:
    """
    Compile a parsed clause term into a Clause structure.

    Recognizes these forms:
    - head.                           -> fact
    - head :- body.                   -> rule
    - head :- guard ? body.           -> guarded rule (wait)
    - head :- guard ?? body.          -> guarded rule (quiet wait)
    - head :- guard -> body.          -> conditional
    - head :- guard | body.           -> commit
    - head :- guard ! body.           -> cut

    Args:
        term: The parsed clause term

    Returns:
        Compiled Clause structure
    """
    # Simple fact (atom or structure without :-)
    if isinstance(term, (Atom, Struct)) and not _is_clause_op(term):
        return _make_clause(head=term, source=term)

    # Rule: head :- body
    if isinstance(term, Struct) and term.functor == Atom(":-") and term.arity == 2:
        head = term.args[0]
        body_term = term.args[1]

        # Check for guard operators in body
        guard, guard_type, body = _extract_guard(body_term)

        return _make_clause(
            head=head,
            guard=guard,
            guard_type=guard_type,
            body=body,
            source=term
        )

    # Directive (no head): :- goal
    if isinstance(term, Struct) and term.functor == Atom(":-") and term.arity == 1:
        # Treat as a query/directive - not a clause
        raise ValueError(f"Directives not supported as clauses: {term}")

    raise ValueError(f"Cannot compile term as clause: {term}")


def _is_clause_op(term: Term) -> bool:
    """Check if term is a clause operator structure."""
    if isinstance(term, Struct):
        return term.functor == Atom(":-")
    return False


def _extract_guard(body_term: Term) -> tuple[Term | None, GuardType, list[Term]]:
    """
    Extract guard and body from a body term.

    Returns (guard, guard_type, body_goals).

    Handles both:
    - Binary form: guard ?? body  (guard_type is binary operator)
    - Unary form: ?? guard_only   (guard_type is prefix operator, no body)
    """
    if not isinstance(body_term, Struct):
        # Simple atom body
        body = _flatten_conjunction(body_term)
        return (None, GuardType.NONE, body)

    op = body_term.functor.name if isinstance(body_term.functor, Atom) else None

    # Binary guard operators: guard OP body
    if body_term.arity == 2:
        if op == "?":
            guard = body_term.args[0]
            body = _flatten_conjunction(body_term.args[1])
            return (guard, GuardType.WAIT, body)

        if op == "??":
            guard = body_term.args[0]
            body = _flatten_conjunction(body_term.args[1])
            return (guard, GuardType.QUIET_WAIT, body)

        if op == "->":
            guard = body_term.args[0]
            body = _flatten_conjunction(body_term.args[1])
            return (guard, GuardType.ARROW, body)

        if op == "|":
            guard = body_term.args[0]
            body = _flatten_conjunction(body_term.args[1])
            return (guard, GuardType.COMMIT, body)

        if op == "!":
            guard = body_term.args[0]
            body = _flatten_conjunction(body_term.args[1])
            return (guard, GuardType.CUT, body)

    # Unary/prefix guard operators: OP guard_only (no body)
    # This handles cases like `:- ?? true` where there's just a guard
    if body_term.arity == 1:
        if op == "?":
            guard = body_term.args[0]
            return (guard, GuardType.WAIT, [])

        if op == "??":
            guard = body_term.args[0]
            return (guard, GuardType.QUIET_WAIT, [])

        if op == "->":
            guard = body_term.args[0]
            return (guard, GuardType.ARROW, [])

        if op == "|":
            guard = body_term.args[0]
            return (guard, GuardType.COMMIT, [])

        if op == "!":
            guard = body_term.args[0]
            return (guard, GuardType.CUT, [])

    # No guard - just body
    body = _flatten_conjunction(body_term)
    return (None, GuardType.NONE, body)


def _flatten_conjunction(term: Term) -> list[Term]:
    """
    Flatten a conjunction (a, b, c) into a list [a, b, c].
    """
    result: list[Term] = []
    _flatten_conj_impl(term, result)
    return result


def _flatten_conj_impl(term: Term, result: list[Term]) -> None:
    """Implementation of conjunction flattening."""
    if isinstance(term, Struct) and term.functor == Atom(",") and term.arity == 2:
        _flatten_conj_impl(term.args[0], result)
        _flatten_conj_impl(term.args[1], result)
    else:
        result.append(term)


def _make_clause(head: Term, guard: Term | None = None,
                 guard_type: GuardType = GuardType.NONE,
                 body: list[Term] | None = None,
                 source: Term | None = None) -> Clause:
    """Create a Clause with computed variable sets."""
    if body is None:
        body = []

    # Collect variables
    head_vars = {v.name for v in collect_vars(head)}
    all_vars = set(head_vars)

    if guard is not None:
        all_vars.update(v.name for v in collect_vars(guard))

    for goal in body:
        all_vars.update(v.name for v in collect_vars(goal))

    return Clause(
        head=head,
        guard=guard,
        guard_type=guard_type,
        body=body,
        source=source,
        head_vars=head_vars,
        all_vars=all_vars,
    )


# =============================================================================
# File Loading
# =============================================================================

def load_file(path: str | Path, program: Program | None = None) -> Program:
    """
    Load an AKL source file into a program.

    Args:
        path: Path to .akl file
        program: Existing program to add to, or None to create new

    Returns:
        Program with loaded clauses
    """
    if program is None:
        program = Program()

    path = Path(path)
    source = path.read_text()

    clauses = parse_clauses(source)
    for clause_term in clauses:
        try:
            clause = compile_clause(clause_term)
            program.add_clause(clause)
        except ValueError as e:
            # Skip directives and invalid clauses
            pass

    return program


def load_string(source: str, program: Program | None = None) -> Program:
    """
    Load AKL source from a string into a program.

    Args:
        source: AKL source code
        program: Existing program to add to, or None to create new

    Returns:
        Program with loaded clauses
    """
    if program is None:
        program = Program()

    clauses = parse_clauses(source)
    for clause_term in clauses:
        try:
            clause = compile_clause(clause_term)
            program.add_clause(clause)
        except ValueError as e:
            # Skip directives and invalid clauses
            pass

    return program
