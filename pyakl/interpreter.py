"""
Simple AKL Interpreter.

This module implements a basic interpreter for AKL programs.
For now, focuses on deterministic Horn clauses with backtracking.

Key components:
- solve(): Main entry point for queries
- execute_goal(): Execute a single goal
- try_clause(): Try matching a clause
- Backtracking via generator-based choice points
"""

from __future__ import annotations
from typing import Iterator, Generator, Any
from dataclasses import dataclass

from .term import Term, Var, Atom, Integer, Float, Struct, Cons, NIL
from .unify import unify, copy_term
from .program import Program, Clause, GuardType
from .builtin import is_builtin, call_builtin, akl_context
from .engine import ExState, AndBox


# =============================================================================
# Solution
# =============================================================================

@dataclass
class Solution:
    """A solution from the interpreter."""
    bindings: dict[str, Term]

    def __repr__(self) -> str:
        if not self.bindings:
            return "true"
        parts = []
        for name, value in self.bindings.items():
            parts.append(f"{name} = {value}")
        return ", ".join(parts)


# =============================================================================
# Interpreter
# =============================================================================

class Interpreter:
    """
    AKL interpreter for executing queries against a program.

    Uses generator-based backtracking for choice points.
    """

    def __init__(self, program: Program) -> None:
        self.program = program
        self.exstate = ExState()
        self.andb = AndBox()

        # Track query variables for collecting bindings
        self.query_vars: dict[str, Var] = {}

        # Debug flag
        self.debug = False

    def solve(self, goal: Term) -> Generator[Solution, None, None]:
        """
        Solve a goal and yield all solutions.

        Args:
            goal: The goal term to solve

        Yields:
            Solution objects with variable bindings
        """
        # Reset state
        self.exstate = ExState()
        self.andb = AndBox()
        self.query_vars = {}

        # Set global context for builtins that need program access
        akl_context.program = self.program
        akl_context.interpreter = self

        # Collect query variables
        self._collect_query_vars(goal)

        # Execute the goal
        for _ in self._execute(goal):
            yield self._get_solution()

    def solve_all(self, goal: Term) -> list[Solution]:
        """Get all solutions for a goal."""
        return list(self.solve(goal))

    def solve_one(self, goal: Term) -> Solution | None:
        """Get first solution for a goal, or None."""
        for sol in self.solve(goal):
            return sol
        return None

    def _collect_query_vars(self, term: Term) -> None:
        """Collect variables from the query for building solutions."""
        term = term.deref()

        if isinstance(term, Var):
            if term.name and term.name != "_" and not term.name.startswith("_"):
                self.query_vars[term.name] = term
        elif isinstance(term, Struct):
            for arg in term.args:
                self._collect_query_vars(arg)
        elif isinstance(term, Cons):
            self._collect_query_vars(term.head)
            self._collect_query_vars(term.tail)

    def _get_solution(self) -> Solution:
        """Build a Solution from current variable bindings."""
        bindings = {}
        for name, var in self.query_vars.items():
            value = var.deref()
            # Only include if bound to something other than itself
            if value is not var:
                bindings[name] = value
        return Solution(bindings)

    def _execute(self, goal: Term) -> Generator[None, None, None]:
        """
        Execute a goal, yielding on each solution.

        This is a generator that yields once per solution found.
        """
        goal = goal.deref()

        if self.debug:
            print(f"DEBUG: execute {goal}")

        # Handle conjunction
        if isinstance(goal, Struct) and goal.functor == Atom(",") and goal.arity == 2:
            yield from self._execute_conjunction(goal.args[0], goal.args[1])
            return

        # Handle disjunction
        if isinstance(goal, Struct) and goal.functor == Atom(";") and goal.arity == 2:
            yield from self._execute_disjunction(goal.args[0], goal.args[1])
            return

        # Handle negation as failure
        if isinstance(goal, Struct) and goal.functor == Atom("\\+") and goal.arity == 1:
            yield from self._execute_negation(goal.args[0])
            return

        if isinstance(goal, Struct) and goal.functor == Atom("not") and goal.arity == 1:
            yield from self._execute_negation(goal.args[0])
            return

        # Handle if-then-else: (Cond -> Then ; Else)
        if isinstance(goal, Struct) and goal.functor == Atom(";") and goal.arity == 2:
            cond_then = goal.args[0]
            if isinstance(cond_then, Struct) and cond_then.functor == Atom("->") and cond_then.arity == 2:
                yield from self._execute_if_then_else(
                    cond_then.args[0], cond_then.args[1], goal.args[1]
                )
                return

        # Handle call/1
        if isinstance(goal, Struct) and goal.functor == Atom("call") and goal.arity >= 1:
            inner_goal = goal.args[0].deref()
            yield from self._execute(inner_goal)
            return

        # Get functor info
        if isinstance(goal, Atom):
            name = goal.name
            arity = 0
            args = ()
        elif isinstance(goal, Struct):
            name = goal.functor.name
            arity = goal.arity
            args = goal.args
        else:
            raise RuntimeError(f"Cannot execute goal: {goal}")

        # Try built-in first
        if is_builtin(name, arity):
            if call_builtin(name, arity, self.exstate, self.andb, args):
                yield
            return

        # Look up predicate
        clauses = self.program.get_clauses(name, arity)
        if not clauses:
            # Unknown predicate - fail
            if self.debug:
                print(f"DEBUG: unknown predicate {name}/{arity}")
            return

        # Try each clause
        yield from self._try_clauses(goal, clauses)

    def _execute_conjunction(self, left: Term, right: Term) -> Generator[None, None, None]:
        """Execute a conjunction (left, right)."""
        for _ in self._execute(left):
            yield from self._execute(right)

    def _execute_disjunction(self, left: Term, right: Term) -> Generator[None, None, None]:
        """Execute a disjunction (left ; right)."""
        # Save trail position for backtracking between branches
        trail_pos = self.exstate.trail_position()

        # Try left branch
        for _ in self._execute(left):
            yield
            # Undo bindings after yielding, before trying next solution
            self.exstate.undo_trail(trail_pos)

        # Ensure trail is clean before right branch
        self.exstate.undo_trail(trail_pos)

        # Try right branch
        for _ in self._execute(right):
            yield
            self.exstate.undo_trail(trail_pos)

    def _execute_negation(self, goal: Term) -> Generator[None, None, None]:
        """Execute negation as failure \\+(goal)."""
        # Save trail position
        trail_pos = self.exstate.trail_position()

        # Try to prove goal
        for _ in self._execute(goal):
            # Goal succeeded - negation fails
            self.exstate.undo_trail(trail_pos)
            return

        # Goal failed - negation succeeds
        self.exstate.undo_trail(trail_pos)
        yield

    def _execute_if_then_else(self, cond: Term, then: Term, else_: Term) -> Generator[None, None, None]:
        """Execute if-then-else (Cond -> Then ; Else)."""
        # Save trail position
        trail_pos = self.exstate.trail_position()

        # Try condition
        cond_succeeded = False
        for _ in self._execute(cond):
            # Condition succeeded - execute Then, commit (don't try Else)
            cond_succeeded = True
            yield from self._execute(then)
            return

        # Condition failed - restore and try Else
        self.exstate.undo_trail(trail_pos)
        yield from self._execute(else_)

    def _try_clauses(self, goal: Term, clauses: list[Clause]) -> Generator[None, None, None]:
        """Try matching goal against a list of clauses."""
        for clause in clauses:
            yield from self._try_clause(goal, clause)

    def _try_clause(self, goal: Term, clause: Clause) -> Generator[None, None, None]:
        """Try matching goal against a single clause."""
        # Save trail position for backtracking
        trail_pos = self.exstate.trail_position()

        if self.debug:
            print(f"DEBUG: try clause {clause.head}")

        # Copy clause with fresh variables
        fresh_head, fresh_guard, fresh_body = self._copy_clause(clause)

        # Try to unify goal with head
        if not unify(goal, fresh_head, self.exstate):
            if self.debug:
                print(f"DEBUG: unification failed")
            self.exstate.undo_trail(trail_pos)
            return

        if self.debug:
            print(f"DEBUG: unification succeeded, head={fresh_head.deref()}")

        # Handle guard if present
        if fresh_guard is not None:
            # For now, just execute guard as goal
            # More sophisticated guard handling would be needed for full AKL
            guard_succeeded = False
            guard_trail = self.exstate.trail_position()

            for _ in self._execute(fresh_guard):
                guard_succeeded = True
                break

            if not guard_succeeded:
                if self.debug:
                    print(f"DEBUG: guard failed")
                self.exstate.undo_trail(trail_pos)
                return

        # Execute body goals
        if fresh_body:
            # Build conjunction of body goals
            body_goal = self._goals_to_conjunction(fresh_body)
            for _ in self._execute(body_goal):
                yield
        else:
            # Fact - succeed immediately
            yield

        # Backtrack - undo bindings
        self.exstate.undo_trail(trail_pos)

    def _copy_clause(self, clause: Clause) -> tuple[Term, Term | None, list[Term]]:
        """
        Copy a clause with fresh variables.

        Returns (head, guard, body) with fresh variables.
        Variables with the same name share the same fresh variable.
        Anonymous variables (_) are always fresh.
        """
        # Map variable NAME to fresh variable (not id, since parser
        # creates separate Var objects for each occurrence)
        var_map: dict[str, Var] = {}
        anon_counter = [0]  # Use list to allow mutation in closure

        def copy_with_fresh_vars(term: Term) -> Term:
            """Copy term, replacing variables with fresh ones."""
            term = term.deref()

            if isinstance(term, Var):
                # Anonymous variables are always unique
                if term.name == "_" or term.name is None:
                    anon_counter[0] += 1
                    return Var(f"_G{anon_counter[0]}")

                # Named variables share by name
                if term.name not in var_map:
                    var_map[term.name] = Var(term.name)
                return var_map[term.name]

            if isinstance(term, (Atom, Integer, Float)):
                return term

            if isinstance(term, Struct):
                new_args = tuple(copy_with_fresh_vars(arg) for arg in term.args)
                return Struct(term.functor, new_args)

            if isinstance(term, Cons):
                return Cons(
                    copy_with_fresh_vars(term.head),
                    copy_with_fresh_vars(term.tail)
                )

            if term is NIL:
                return NIL

            return term

        fresh_head = copy_with_fresh_vars(clause.head)
        fresh_guard = copy_with_fresh_vars(clause.guard) if clause.guard else None
        fresh_body = [copy_with_fresh_vars(g) for g in clause.body]

        return fresh_head, fresh_guard, fresh_body

    def _goals_to_conjunction(self, goals: list[Term]) -> Term:
        """Convert a list of goals to a conjunction term."""
        if not goals:
            return Atom("true")
        if len(goals) == 1:
            return goals[0]

        # Build right-associative conjunction
        result = goals[-1]
        for goal in reversed(goals[:-1]):
            result = Struct(Atom(","), (goal, result))
        return result


# =============================================================================
# Convenience functions
# =============================================================================

def solve(program: Program, goal: Term) -> Generator[Solution, None, None]:
    """
    Solve a goal against a program.

    Args:
        program: The program to query
        goal: The goal term

    Yields:
        Solution objects with variable bindings
    """
    interp = Interpreter(program)
    yield from interp.solve(goal)


def solve_all(program: Program, goal: Term) -> list[Solution]:
    """Get all solutions for a goal."""
    return list(solve(program, goal))


def solve_one(program: Program, goal: Term) -> Solution | None:
    """Get first solution for a goal, or None."""
    for sol in solve(program, goal):
        return sol
    return None


def query(program: Program, query_str: str) -> Generator[Solution, None, None]:
    """
    Solve a query string against a program.

    Args:
        program: The program to query
        query_str: Query string like "member(X, [1,2,3])"

    Yields:
        Solution objects
    """
    from .parser import parse_term
    goal = parse_term(query_str)
    yield from solve(program, goal)


def query_all(program: Program, query_str: str) -> list[Solution]:
    """Get all solutions for a query string."""
    return list(query(program, query_str))


def query_one(program: Program, query_str: str) -> Solution | None:
    """Get first solution for a query string, or None."""
    for sol in query(program, query_str):
        return sol
    return None
