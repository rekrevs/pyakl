"""
AKL Interpreter with proper guard semantics.

This module implements a proper AKL interpreter that handles:
- Guard operators with quiet/noisy distinction
- External variable tracking
- Suspension on external variables (for quiet guards)
- Proper promotion semantics

Key components:
- solve(): Main entry point for queries
- _execute(): Execute a single goal
- _try_clause(): Try matching a clause with proper guard semantics
- Backtracking via generator-based choice points

Guard semantics:
- Quiet guards (->. |, ??): Cannot bind external variables
- Noisy guards (?, !): CAN bind external variables
"""

from __future__ import annotations
from typing import Iterator, Generator, Any
from dataclasses import dataclass

from .term import Term, Var, Atom, Integer, Float, Struct, Cons, NIL
from .unify import unify, copy_term, ground_copy
from .program import Program, Clause, GuardType
from .builtin import is_builtin, call_builtin, akl_context
from .engine import (
    ExState, AndBox, EnvId, ConstrainedVar,
    is_local_var, is_external_var
)


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

    Implements proper AKL guard semantics:
    - Quiet guards (->. |, ??): Cannot bind external variables
    - Noisy guards (?, !): CAN bind external variables (noisy promotion)
    - Pruning guards (->. |, !): Prevent backtracking to remaining clauses
    - Non-pruning guards (?, ??): Allow backtracking
    """

    def __init__(self, program: Program) -> None:
        self.program = program
        self.exstate = ExState()

        # Root and-box for the query
        self.root_andb = AndBox()

        # Current and-box (changes during clause execution)
        self.current_andb = self.root_andb

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
        self.root_andb = AndBox()
        self.current_andb = self.root_andb
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
                # Use ground_copy to capture the value with all bindings followed
                bindings[name] = ground_copy(value)
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

        # Handle if-then-else: (Cond -> Then ; Else)
        # Must check BEFORE plain disjunction
        if isinstance(goal, Struct) and goal.functor == Atom(";") and goal.arity == 2:
            cond_then = goal.args[0]
            if isinstance(cond_then, Struct) and cond_then.functor == Atom("->") and cond_then.arity == 2:
                yield from self._execute_if_then_else(
                    cond_then.args[0], cond_then.args[1], goal.args[1]
                )
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

        # Handle call/1
        if isinstance(goal, Struct) and goal.functor == Atom("call") and goal.arity >= 1:
            inner_goal = goal.args[0].deref()
            yield from self._execute(inner_goal)
            return

        # Handle @ operator (send to port): Message@Port -> send(Message, Port)
        if isinstance(goal, Struct) and goal.functor == Atom("@") and goal.arity == 2:
            # Transform to send/2 call
            send_goal = Struct(Atom("send"), (goal.args[0], goal.args[1]))
            yield from self._execute(send_goal)
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
            if call_builtin(name, arity, self.exstate, self.current_andb, args):
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
        for i, clause in enumerate(clauses):
            # Try this clause
            for result in self._try_clause(goal, clause):
                if result is True:
                    # Pruning guard succeeded - stop trying other clauses
                    yield
                    return
                else:
                    # Normal success - yield and allow backtracking
                    yield

    def _try_clause(self, goal: Term, clause: Clause) -> Generator[bool | None, None, None]:
        """
        Try matching goal against a single clause.

        Implements proper AKL guard semantics:
        - Creates a new and-box for clause execution
        - Tracks external vs local variables
        - Quiet guards fail if they bind external variables
        - Noisy guards can bind external variables

        Yields True if a pruning guard succeeded (should cut alternatives).
        Yields None for normal success (allow backtracking).
        """
        # Save trail position for backtracking
        trail_pos = self.exstate.trail_position()

        if self.debug:
            print(f"DEBUG: try clause {clause.head}")

        # Save parent and-box
        parent_andb = self.current_andb

        # Create new and-box for this clause with child environment
        clause_andb = AndBox()
        clause_andb.env = EnvId(parent=parent_andb.env)
        self.current_andb = clause_andb

        # Copy clause with fresh constrained variables (local to clause_andb)
        fresh_head, fresh_guard, fresh_body = self._copy_clause_with_env(clause, clause_andb)

        # Try to unify goal with head
        # Note: Head unification CAN bind external variables - this is normal.
        # The quiet/noisy distinction applies to the GUARD, not the head.
        if not unify(goal, fresh_head, self.exstate):
            if self.debug:
                print(f"DEBUG: unification failed")
            self.exstate.undo_trail(trail_pos)
            self.current_andb = parent_andb
            return

        if self.debug:
            print(f"DEBUG: unification succeeded, head={fresh_head.deref()}")

        # Determine guard type properties
        is_quiet_guard = clause.guard_type in (
            GuardType.ARROW, GuardType.COMMIT, GuardType.QUIET_WAIT
        )
        is_pruning_guard = clause.guard_type in (
            GuardType.ARROW, GuardType.COMMIT, GuardType.CUT
        )

        # Handle guard if present
        if fresh_guard is not None:
            guard_trail = self.exstate.trail_position()

            # For quiet guards, snapshot external variable values before guard
            external_snapshot: dict[int, Term] = {}
            if is_quiet_guard:
                external_snapshot = self._snapshot_externals(goal, clause_andb)

            guard_succeeded = False
            for _ in self._execute(fresh_guard):
                # Check guard result for external bindings
                # Quiet guards must not cause external variables to become
                # more constrained (bound to a non-variable value)
                if is_quiet_guard:
                    changed = self._check_external_changes(external_snapshot, clause_andb)
                    if changed:
                        if self.debug:
                            print(f"DEBUG: quiet guard changed external bindings: {changed}")
                        # Undo guard bindings and try next solution
                        self.exstate.undo_trail(guard_trail)
                        continue

                guard_succeeded = True
                break

            if not guard_succeeded:
                if self.debug:
                    print(f"DEBUG: guard failed")
                self.exstate.undo_trail(trail_pos)
                self.current_andb = parent_andb
                return

        # Execute body goals
        if fresh_body:
            # Build conjunction of body goals
            body_goal = self._goals_to_conjunction(fresh_body)
            for _ in self._execute(body_goal):
                # Restore parent context before yielding
                self.current_andb = parent_andb
                # Yield True to signal pruning, None otherwise
                yield True if is_pruning_guard else None
                # Restore clause context for next solution
                self.current_andb = clause_andb
        else:
            # Fact - succeed immediately
            self.current_andb = parent_andb
            yield True if is_pruning_guard else None
            self.current_andb = clause_andb

        # Backtrack - undo bindings and restore parent
        self.exstate.undo_trail(trail_pos)
        self.current_andb = parent_andb

    def _unify_tracking_external(
        self, t1: Term, t2: Term,
        local_andb: AndBox,
        external_bindings: list[tuple[Var, Term]]
    ) -> bool:
        """
        Unify two terms, tracking which external variables get bound.

        External variables are those whose env is an ancestor of local_andb's env.
        """
        t1 = t1.deref()
        t2 = t2.deref()

        if t1 is t2:
            return True

        # Handle variable cases
        if isinstance(t1, Var):
            return self._bind_var_tracking(t1, t2, local_andb, external_bindings)

        if isinstance(t2, Var):
            return self._bind_var_tracking(t2, t1, local_andb, external_bindings)

        # Non-variable cases
        if isinstance(t1, Atom):
            return isinstance(t2, Atom) and t1 is t2

        if isinstance(t1, Integer):
            return isinstance(t2, Integer) and t1.value == t2.value

        if isinstance(t1, Float):
            return isinstance(t2, Float) and t1.value == t2.value

        if isinstance(t1, Struct):
            if not isinstance(t2, Struct):
                return False
            if t1.functor != t2.functor or t1.arity != t2.arity:
                return False
            return all(
                self._unify_tracking_external(a1, a2, local_andb, external_bindings)
                for a1, a2 in zip(t1.args, t2.args)
            )

        if isinstance(t1, Cons):
            if not isinstance(t2, Cons):
                return False
            return (
                self._unify_tracking_external(t1.head, t2.head, local_andb, external_bindings) and
                self._unify_tracking_external(t1.tail, t2.tail, local_andb, external_bindings)
            )

        return False

    def _bind_var_tracking(
        self, var: Var, term: Term,
        local_andb: AndBox,
        external_bindings: list[tuple[Var, Term]]
    ) -> bool:
        """Bind variable and track if it's external."""
        # Check if variable is external to local_andb
        is_external = False
        if isinstance(var, ConstrainedVar) and var.env is not None:
            # Variable is external if its env is NOT local_andb's env
            # and is an ancestor of local_andb's env
            is_external = (var.env is not local_andb.env and
                          var.env.is_ancestor_of(local_andb.env))

        # Trail the binding
        self.exstate.trail_binding(var, var.binding)

        # Perform binding
        var.binding = term

        # Track external binding
        if is_external:
            external_bindings.append((var, term))

        # Wake suspended goals
        if isinstance(var, ConstrainedVar):
            var.wake_all(self.exstate)

        return True

    def _is_var_external(self, var: Var, local_andb: AndBox) -> bool:
        """Check if a variable is external to local_andb."""
        if isinstance(var, ConstrainedVar):
            if var.env is None:
                return True  # No env means external
            if var.env is not local_andb.env:
                return var.env.is_ancestor_of(local_andb.env)
            return False
        else:
            # Plain Var without env is external (query variable)
            return True

    def _collect_vars_no_deref(self, term: Term, seen: set[int]) -> list[Var]:
        """Collect all variables from term WITHOUT following bindings."""
        result = []

        if isinstance(term, Var):
            var_id = id(term)
            if var_id in seen:
                return result
            seen.add(var_id)
            result.append(term)
            # Also follow the binding if present
            if term.binding is not None:
                result.extend(self._collect_vars_no_deref(term.binding, seen))
            return result

        if isinstance(term, Struct):
            for arg in term.args:
                result.extend(self._collect_vars_no_deref(arg, seen))

        if isinstance(term, Cons):
            result.extend(self._collect_vars_no_deref(term.head, seen))
            result.extend(self._collect_vars_no_deref(term.tail, seen))

        return result

    def _snapshot_externals(self, goal: Term, local_andb: AndBox) -> dict[int, Term]:
        """Snapshot the current deref values of external variables reachable from goal."""
        all_vars = self._collect_vars_no_deref(goal, set())
        external_vars = [v for v in all_vars if self._is_var_external(v, local_andb)]
        return {id(v): v.deref() for v in external_vars}

    def _check_external_changes(
        self, snapshot: dict[int, Term], local_andb: AndBox
    ) -> list[tuple[Var, Term, Term]]:
        """Check if any external variables changed from their snapshot.

        Returns list of (var, old_value, new_value) for changed externals.
        """
        changes = []
        for var_id, old_deref in snapshot.items():
            # Find the variable - we need to get it from somewhere
            # The old_deref tells us what it used to point to
            # If old_deref was a Var, check if it's now bound
            if isinstance(old_deref, Var):
                new_deref = old_deref.deref()
                if new_deref is not old_deref:
                    # The external became more bound
                    changes.append((old_deref, old_deref, new_deref))
        return changes

    def _copy_clause_with_env(self, clause: Clause, andb: AndBox) -> tuple[Term, Term | None, list[Term]]:
        """
        Copy a clause with fresh constrained variables local to andb.

        Returns (head, guard, body) with fresh ConstrainedVar instances
        that have their env set to andb.env.
        """
        # Map variable NAME to fresh variable
        var_map: dict[str, ConstrainedVar] = {}
        anon_counter = [0]

        def copy_with_fresh_vars(term: Term) -> Term:
            """Copy term, replacing variables with fresh constrained ones."""
            term = term.deref()

            if isinstance(term, Var):
                # Anonymous variables are always unique
                if term.name == "_" or term.name is None:
                    anon_counter[0] += 1
                    return ConstrainedVar(f"_G{anon_counter[0]}", andb.env)

                # Named variables share by name
                if term.name not in var_map:
                    var_map[term.name] = ConstrainedVar(term.name, andb.env)
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

    def _copy_clause(self, clause: Clause) -> tuple[Term, Term | None, list[Term]]:
        """
        Copy a clause with fresh variables (legacy method).

        Uses current_andb for the environment.
        """
        return self._copy_clause_with_env(clause, self.current_andb)

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
