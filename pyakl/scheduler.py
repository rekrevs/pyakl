"""
AKL Scheduler with Continuation-Passing Style.

This module implements a sequential execution model using CPS:
- Each goal is processed with an explicit continuation (remaining goals)
- Predicate calls pass continuation through to clause matching
- Solutions recorded only when continuation is empty
- Trail save/restore at each choice point for proper isolation

Key design principles:
1. Never modify shared state (goals lists are passed, not mutated)
2. Record solutions at the right time (when continuation is empty)
3. Handle nondeterminism (each clause explored with full continuation)

This is functionally equivalent to the generator-based interpreter but with
explicit continuation management. It produces correct results for all
nondeterministic programs (member, append, permutation, n-queens, etc.)

See dev-log/T-SPLIT-02.md for design rationale and docs/deep-guards.md for
AKL semantics background.
"""

from __future__ import annotations
from typing import Generator
from dataclasses import dataclass, field

from .term import Term, Var, Atom, Integer, Float, Struct, Cons, NIL
from .unify import unify, ground_copy
from .program import Program, Clause, GuardType
from .builtin import is_builtin, call_builtin, akl_context
from .engine import (
    ExState, AndBox, ChoiceBox, EnvId, ConstrainedVar, Status
)
from .copy import copy_andbox_subtree


# Guard type properties
QUIET_GUARDS = {GuardType.ARROW, GuardType.COMMIT, GuardType.QUIET_WAIT}
PRUNING_GUARDS = {GuardType.ARROW, GuardType.COMMIT, GuardType.CUT}


# =============================================================================
# Solution
# =============================================================================

@dataclass
class Solution:
    """A solution from the scheduler."""
    bindings: dict[str, Term]

    def __repr__(self) -> str:
        if not self.bindings:
            return "true"
        parts = []
        for name, value in self.bindings.items():
            parts.append(f"{name} = {value}")
        return ", ".join(parts)


# =============================================================================
# Scheduler
# =============================================================================

class Scheduler:
    """
    AKL scheduler with copy-based state preservation.

    Uses sequential exploration (one branch at a time) with proper
    state save/restore via and-box copying.
    """

    def __init__(self, program: Program, debug: bool = False) -> None:
        self.program = program
        self.debug = debug
        self.exstate = ExState()
        self.query_vars: dict[str, Var] = {}
        self.solutions: list[Solution] = []
        self._depth = 0
        self._in_guard = False  # Don't record solutions during guard execution

        # Set global context for builtins
        akl_context.program = program
        akl_context.interpreter = self

    def _indent(self) -> str:
        return "  " * self._depth

    def solve(self, goal: Term) -> list[Solution]:
        """Solve a goal and return all solutions."""
        self.exstate = ExState()
        self.solutions = []
        self.query_vars = {}

        # Collect query variables
        self._collect_query_vars(goal)

        # Execute the goal
        self._try_goals([goal])

        return self.solutions

    def _try_clauses(self, goal: Term, clauses: list[Clause], continuation: list[Term]) -> bool:
        """
        Try matching goal against clauses.

        Uses copy-based state preservation: save state before each clause,
        restore if we need to try another.

        Handles guard semantics:
        - Quiet guards (->. |, ??): Cannot bind external variables in guard
        - Pruning guards (->, |, !): Stop after first success (commit)

        Args:
            goal: The goal to match
            clauses: List of clauses to try
            continuation: Goals to execute after this goal succeeds

        This is the ONLY place where solutions are recorded.
        """
        found_solution = False

        for i, clause in enumerate(clauses):
            trail_pos = self.exstate.trail_position()

            if self.debug:
                print(f"{self._indent()}_try_clauses[{i}]: trying clause {clause.head}")

            # Create fresh copy of clause with new variables
            fresh_head, fresh_guard, fresh_body = self._copy_clause(clause, None)

            # Try to unify
            if unify(goal, fresh_head, self.exstate):
                if self.debug:
                    print(f"{self._indent()}_try_clauses[{i}]: unified, body={[str(g) for g in fresh_body]}")

                # Handle guard if present
                if fresh_guard is not None:
                    # For quiet guards, take snapshot of external variable values
                    is_quiet = clause.guard_type in QUIET_GUARDS
                    external_snapshot = {}
                    if is_quiet:
                        external_snapshot = self._snapshot_query_vars()

                    guard_trail = self.exstate.trail_position()

                    # Try to execute guard (without recording solutions)
                    self._in_guard = True
                    guard_succeeded = self._try_goals([fresh_guard])
                    self._in_guard = False

                    if guard_succeeded:
                        # Check if quiet guard changed external variables
                        if is_quiet and self._query_vars_changed(external_snapshot):
                            if self.debug:
                                print(f"{self._indent()}_try_clauses[{i}]: quiet guard changed externals, rejecting")
                            self.exstate.undo_trail(guard_trail)
                            guard_succeeded = False

                    if not guard_succeeded:
                        if self.debug:
                            print(f"{self._indent()}_try_clauses[{i}]: guard failed")
                        self.exstate.undo_trail(trail_pos)
                        continue

                # Execute body + continuation
                new_goals = list(fresh_body) + continuation
                if self._try_goals(new_goals):
                    found_solution = True

                    # For pruning guards, stop after first success
                    if clause.guard_type in PRUNING_GUARDS:
                        if self.debug:
                            print(f"{self._indent()}_try_clauses[{i}]: pruning guard, stopping")
                        self.exstate.undo_trail(trail_pos)
                        return True
            else:
                if self.debug:
                    print(f"{self._indent()}_try_clauses[{i}]: unification failed")

            # Restore state for next clause
            self.exstate.undo_trail(trail_pos)

        return found_solution

    def _snapshot_query_vars(self) -> dict[str, Term | None]:
        """Take a snapshot of query variable bindings."""
        snapshot = {}
        for name, var in self.query_vars.items():
            val = var.deref()
            snapshot[name] = val if val is not var else None
        return snapshot

    def _query_vars_changed(self, snapshot: dict[str, Term | None]) -> bool:
        """Check if any query variable was bound since snapshot."""
        for name, old_val in snapshot.items():
            var = self.query_vars.get(name)
            if var is None:
                continue
            new_val = var.deref()
            if old_val is None:
                # Was unbound, check if now bound
                if new_val is not var:
                    return True
            # If was bound, we don't check for changes (more restrictive)
        return False

    def _try_goals(self, goals: list[Term]) -> bool:
        """
        Try to complete a list of goals, recording solutions when successful.

        Returns True if at least one solution was found.
        """
        if not goals:
            # All goals succeeded - only record if not in guard
            if not self._in_guard:
                self._record_solution()
            return True

        goal = goals[0]
        rest = goals[1:]

        return self._try_goal(goal, rest)

    def _try_goal(self, goal: Term, continuation: list[Term]) -> bool:
        """
        Try a single goal with a continuation.

        Returns True if at least one solution was found.
        """
        goal = goal.deref()

        if self.debug:
            print(f"EXEC: {goal}")

        # Handle conjunction - flatten into continuation
        if isinstance(goal, Struct) and goal.functor == Atom(",") and goal.arity == 2:
            return self._try_goals([goal.args[0], goal.args[1]] + continuation)

        # Handle disjunction
        if isinstance(goal, Struct) and goal.functor == Atom(";") and goal.arity == 2:
            left = goal.args[0]
            if isinstance(left, Struct) and left.functor == Atom("->") and left.arity == 2:
                return self._try_if_then_else(left.args[0], left.args[1], goal.args[1], continuation)
            return self._try_disjunction(goal.args[0], goal.args[1], continuation)

        # Handle negation
        if isinstance(goal, Struct) and goal.functor == Atom("\\+") and goal.arity == 1:
            return self._try_negation(goal.args[0], continuation)
        if isinstance(goal, Struct) and goal.functor == Atom("not") and goal.arity == 1:
            return self._try_negation(goal.args[0], continuation)

        # Handle call/1
        if isinstance(goal, Struct) and goal.functor == Atom("call") and goal.arity >= 1:
            return self._try_goals([goal.args[0]] + continuation)

        # Get functor info
        if isinstance(goal, Atom):
            name, arity, args = goal.name, 0, ()
        elif isinstance(goal, Struct):
            name, arity, args = goal.functor.name, goal.arity, goal.args
        else:
            return False

        # Try built-in
        if is_builtin(name, arity):
            if call_builtin(name, arity, self.exstate, None, args):
                return self._try_goals(continuation)
            return False

        # Look up predicate
        clauses = self.program.get_clauses(name, arity)
        if not clauses:
            return False

        return self._try_clauses(goal, clauses, continuation)

    def _try_disjunction(self, left: Term, right: Term, continuation: list[Term]) -> bool:
        """Try both branches of a disjunction."""
        found = False
        trail_pos = self.exstate.trail_position()

        if self._try_goals([left] + continuation):
            found = True
        self.exstate.undo_trail(trail_pos)

        if self._try_goals([right] + continuation):
            found = True
        self.exstate.undo_trail(trail_pos)

        return found

    def _try_if_then_else(self, cond: Term, then: Term, else_: Term, continuation: list[Term]) -> bool:
        """Try if-then-else with commit semantics."""
        trail_pos = self.exstate.trail_position()

        # Try condition - if it succeeds at all, commit to Then
        # Execute condition as if in guard (don't record solutions)
        old_in_guard = self._in_guard
        self._in_guard = True
        cond_succeeded = self._try_goals([cond])
        self._in_guard = old_in_guard

        if cond_succeeded:
            # Condition succeeded (at least once) - execute Then
            # Note: we don't undo here, we keep the condition bindings
            return self._try_goals([then] + continuation)
        else:
            # Condition failed - undo and try Else
            self.exstate.undo_trail(trail_pos)
            return self._try_goals([else_] + continuation)

    def _try_negation(self, goal: Term, continuation: list[Term]) -> bool:
        """Try negation as failure."""
        trail_pos = self.exstate.trail_position()

        # Try to prove goal (don't record solutions during test)
        old_in_guard = self._in_guard
        self._in_guard = True
        goal_succeeded = self._try_goals([goal])
        self._in_guard = old_in_guard

        if goal_succeeded:
            # Goal succeeded - negation fails
            self.exstate.undo_trail(trail_pos)
            return False
        else:
            # Goal failed - negation succeeds, continue
            self.exstate.undo_trail(trail_pos)
            return self._try_goals(continuation)

    def _copy_clause(self, clause: Clause, parent_env: EnvId) -> tuple[Term, Term | None, list[Term]]:
        """Create fresh copy of clause with new variables."""
        env = EnvId(parent=parent_env)
        var_map: dict[str, ConstrainedVar] = {}
        anon_counter = [0]

        def copy_term(term: Term) -> Term:
            term = term.deref()

            if isinstance(term, Var):
                if term.name == "_" or term.name is None:
                    anon_counter[0] += 1
                    return ConstrainedVar(f"_G{anon_counter[0]}", env)
                if term.name not in var_map:
                    var_map[term.name] = ConstrainedVar(term.name, env)
                return var_map[term.name]

            if isinstance(term, (Atom, Integer, Float)):
                return term

            if term is NIL:
                return NIL

            if isinstance(term, Struct):
                return Struct(term.functor, tuple(copy_term(a) for a in term.args))

            if isinstance(term, Cons):
                return Cons(copy_term(term.head), copy_term(term.tail))

            return term

        return (
            copy_term(clause.head),
            copy_term(clause.guard) if clause.guard else None,
            [copy_term(g) for g in clause.body]
        )

    def _record_solution(self) -> None:
        """Record current variable bindings as a solution."""
        bindings = {}
        for name, var in self.query_vars.items():
            value = var.deref()
            if value is not var:
                bindings[name] = ground_copy(value)
        sol = Solution(bindings)
        if self.debug:
            print(f"RECORD: {sol}")
        self.solutions.append(sol)

    def _collect_query_vars(self, term: Term) -> None:
        """Collect variables from query."""
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


# =============================================================================
# Convenience Functions
# =============================================================================

def solve_all(program: Program, goal: Term) -> list[Solution]:
    """Solve a goal and return all solutions."""
    return Scheduler(program).solve(goal)


def query_all(program: Program, query_str: str) -> list[Solution]:
    """Solve a query string and return all solutions."""
    from .parser import parse_term
    return solve_all(program, parse_term(query_str))
