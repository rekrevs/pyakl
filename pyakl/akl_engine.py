"""
AKL Execution Engine - Proper Tree Rewriting Semantics.

This module implements correct AKL execution via tree rewriting:
- NO backtracking - only splitting (copying)
- Suspension on external variable constraints
- Wake mechanism when variables are bound
- Proper guard semantics (wait, commit, cut)

Based on ../akl-agents/doc/internals.tex and ../akl-agents/emulator/engine.c
"""

from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Generator
from collections import deque

from .term import Term, Var, Atom, Integer, Float, Struct, Cons, NIL
from .unify import unify as basic_unify
from .program import Program, Clause, GuardType
from .builtin import is_builtin, call_builtin, akl_context
from .engine import (
    ExState, AndBox, ChoiceBox, EnvId, ConstrainedVar, Status,
    Suspension, SuspensionType, Task, TaskType,
    create_root, create_choice, create_alternative,
    is_local_var, is_external_var, suspend_on_var
)
from .copy import copy_andbox_subtree


# =============================================================================
# Guard Type Properties
# =============================================================================

# Quiet guards: cannot promote if they would bind external variables
QUIET_GUARDS = {GuardType.ARROW, GuardType.COMMIT, GuardType.QUIET_WAIT}

# Pruning guards: kill siblings on commit
PRUNING_GUARDS = {GuardType.ARROW, GuardType.COMMIT, GuardType.CUT}

# Wait guards: wait for determinate to promote (unless quiet)
WAIT_GUARDS = {GuardType.WAIT, GuardType.QUIET_WAIT}


# =============================================================================
# Unifier Record (deferred external binding)
# =============================================================================

@dataclass
class Unifier:
    """A deferred unification on an external variable."""
    var: Var
    value: Term
    next: Unifier | None = None


# =============================================================================
# AKL Worker
# =============================================================================

class AKLWorker:
    """
    AKL execution worker - implements tree rewriting semantics.

    The worker processes the and-box/choice-box tree by:
    1. Expanding goals into choice-boxes
    2. Checking guard conditions
    3. Suspending on external variable constraints
    4. Splitting (copying) for nondeterminism
    5. Promoting when guards succeed
    """

    def __init__(self, program: Program, debug: bool = False) -> None:
        self.program = program
        self.debug = debug
        self.exstate: ExState | None = None
        self.query_vars: dict[str, Var] = {}
        self.solutions: list[dict[str, Term]] = []

        # Set global context for builtins
        akl_context.program = program
        akl_context.interpreter = self

    def solve(self, goal: Term) -> list[dict[str, Term]]:
        """
        Solve a goal and return all solutions.

        Uses proper AKL tree rewriting - no backtracking.
        """
        self.solutions = []
        self.query_vars = {}

        # Collect query variables
        self._collect_query_vars(goal)

        # Create initial execution state
        self.exstate, root_andb = create_root(goal)

        # Store query variables in root and-box
        for name, var in self.query_vars.items():
            root_andb.local_vars[name] = var

        # Main execution loop
        self._run()

        return self.solutions

    def _run(self) -> None:
        """Main worker loop - process until no more work."""
        while True:
            # Process wake queue first
            if self._process_wake():
                continue

            # Process recall queue
            if self._process_recall():
                continue

            # Process task queue
            if self._process_tasks():
                continue

            # Check for splitting opportunity
            if self._try_split():
                continue

            # No more work
            break

    def _process_wake(self) -> bool:
        """Process woken and-boxes. Returns True if work was done."""
        if not self.exstate.wake:
            return False

        andb = self.exstate.wake.popleft()
        if andb.is_dead():
            return True  # Skip dead and-boxes

        if self.debug:
            print(f"WAKE: and-box {id(andb)}")

        # Re-try the and-box
        self._try_andbox(andb)
        return True

    def _process_recall(self) -> bool:
        """Process recalled choice-boxes. Returns True if work was done."""
        if not self.exstate.recall:
            return False

        chb = self.exstate.recall.popleft()
        if chb.cont is None:
            return True  # No more clauses to try

        if self.debug:
            print(f"RECALL: choice-box {id(chb)}")

        # Try next clause
        self._try_next_clause(chb)
        return True

    def _process_tasks(self) -> bool:
        """Process task queue. Returns True if work was done."""
        task = self.exstate.next_task()
        if task is None:
            return False

        if self.debug:
            print(f"TASK: {task.type}")

        if task.type == TaskType.START:
            # Start with root and-box
            root_chb = self.exstate.root
            if root_chb and root_chb.tried:
                self._try_andbox(root_chb.tried)

        elif task.type == TaskType.PROMOTE:
            if task.andbox and not task.andbox.is_dead():
                self._promote_andbox(task.andbox)

        elif task.type == TaskType.SPLIT:
            if task.andbox and not task.andbox.is_dead():
                self._do_split(task.andbox)

        return True

    def _try_split(self) -> bool:
        """
        Try to find a candidate for splitting.

        A candidate is a solved and-box with a wait guard in a
        non-determinate choice-box under a stable and-box.
        """
        # Start from root choice-box
        root_chb = self.exstate.root
        if not root_chb or not root_chb.tried:
            return False

        # Search ALL alternatives in the root choice-box
        # (splitting creates multiple independent computations at root level)
        root_andb = root_chb.tried
        while root_andb is not None:
            if root_andb.is_dead():
                root_andb = root_andb.next
                continue

            # Check if this root and-box is stable
            if self._is_stable(root_andb):
                # Find a candidate under this and-box
                candidate = self._find_candidate(root_andb)
                if candidate is not None:
                    if self.debug:
                        print(f"SPLIT: found candidate {id(candidate)}")
                    self._do_split(candidate)
                    return True

            root_andb = root_andb.next

        return False

    def _is_stable(self, andb: AndBox) -> bool:
        """
        Check if an and-box is locally stable.

        Stable means no external constraints in scope that could wake.
        For now, use a simplified check based on and-box status.
        """
        # For now, consider stable if marked stable
        # TODO: proper stability tracking with marks/counters
        return andb.is_stable()

    def _find_candidate(self, andb: AndBox) -> AndBox | None:
        """
        Find leftmost solved wait-guard and-box for splitting.

        Traverses the tree depth-first, left-to-right.
        """
        # Search child choice-boxes
        chb = andb.tried
        while chb is not None:
            # Search alternatives in this choice-box
            alt = chb.tried
            while alt is not None:
                if alt.is_dead():
                    alt = alt.next
                    continue

                # Check if this is a candidate
                if self._is_candidate(alt, chb):
                    return alt

                # Recurse into children
                child_cand = self._find_candidate(alt)
                if child_cand is not None:
                    return child_cand

                alt = alt.next
            chb = chb.next

        return None

    def _is_candidate(self, andb: AndBox, parent_chb: ChoiceBox) -> bool:
        """
        Check if an and-box is a candidate for splitting.

        Candidate must be:
        - Solved (no pending goals, no child choice-boxes)
        - Have a wait guard (? or ??)
        - Parent choice-box is not determinate (otherwise would promote)
        """
        # Must be solved
        if not andb.is_solved() or andb.goals:
            return False

        # Parent choice-box must have multiple alternatives
        if parent_chb.is_determinate():
            return False

        # Must have wait guard (? or ??) - splitting is only for wait guards
        # Other guard types (|, ->, !) handle nondeterminism via commit/prune
        guard_type = getattr(parent_chb, 'guard_type', GuardType.NONE)
        if guard_type not in WAIT_GUARDS and guard_type != GuardType.NONE:
            # Non-wait guards don't use splitting
            return False

        return True

    def _do_split(self, candidate: AndBox) -> None:
        """
        Perform choice splitting.

        1. Copy the mother subtree
        2. In copy, fork has only the candidate
        3. Insert copy to left of mother
        4. Remove candidate from original fork
        5. Promote the copied candidate
        """
        fork = candidate.father
        if fork is None:
            return

        mother = fork.father
        if mother is None:
            return

        if self.debug:
            print(f"SPLITTING: candidate={id(candidate)}, fork={id(fork)}, mother={id(mother)}")

        # Copy the mother subtree
        # The copy infrastructure should handle:
        # - Local variables: fresh copies
        # - External variables: shared
        # - Suspensions: duplicated for copied and-boxes
        mother_copy = copy_andbox_subtree(mother, self.exstate)

        if mother_copy is None:
            if self.debug:
                print("SPLIT: copy failed")
            return

        # In the copy, find the fork and keep only the copied candidate
        # The copy has same structure as original, find corresponding fork
        copy_fork = self._find_copied_fork(mother_copy, fork, mother)
        if copy_fork is None:
            if self.debug:
                print("SPLIT: could not find copied fork")
            return

        # Find the copied candidate in the fork
        copy_candidate = self._find_copied_candidate(copy_fork, candidate)
        if copy_candidate is None:
            if self.debug:
                print("SPLIT: could not find copied candidate")
            return

        # Remove all siblings of copied candidate (keep only candidate)
        alt = copy_fork.tried
        while alt is not None:
            next_alt = alt.next
            if alt is not copy_candidate:
                copy_fork.remove_alternative(alt)
                alt.mark_dead()
            alt = next_alt

        # Insert copy to left of mother
        root_chb = mother.father
        if root_chb:
            mother_copy.father = root_chb
            mother_copy.next = mother
            mother_copy.prev = mother.prev
            if mother.prev:
                mother.prev.next = mother_copy
            else:
                root_chb.tried = mother_copy
            mother.prev = mother_copy

        # Remove candidate from original fork
        fork.remove_alternative(candidate)
        candidate.mark_dead()

        # If fork now determinate, queue promotion
        if fork.is_determinate() and fork.tried:
            self.exstate.queue_promote(fork.tried)
        elif mother.is_stable():
            # Schedule more splitting
            self.exstate.queue_split(mother)

        # Promote the copied candidate (which we already found)
        # copy_candidate is the correct node - don't search for it again
        self._promote_andbox(copy_candidate)

    def _try_andbox(self, andb: AndBox) -> None:
        """
        Try to make progress on an and-box.

        Following internals.tex:
        1. If untried atomic goals: expand first
        2. If tasks exist: process them
        3. If solved: try parent guarded goal
        4. If stable: attempt splitting
        """
        if andb.is_dead():
            return

        # 1. Process pending goals
        while andb.goals:
            goal = andb.goals.pop(0)
            if not self._try_goal(andb, goal):
                # Goal failed - propagate failure
                self._propagate_failure(andb)
                return

            # Goal may have suspended - check if we should continue
            if andb.is_unstable():
                return

        # 2. Check if solved (no goals, no child choice-boxes)
        if andb.is_solved():
            self._try_guard(andb)
        # else: has child choice-boxes, wait for them

    def _try_goal(self, andb: AndBox, goal: Term) -> bool:
        """
        Try to execute a goal in an and-box.

        Returns True if goal succeeded (or suspended), False if failed.
        """
        goal = goal.deref()

        if self.debug:
            print(f"GOAL: {goal} in and-box {id(andb)}")

        # Handle conjunction
        if isinstance(goal, Struct) and goal.functor == Atom(",") and goal.arity == 2:
            # Add both goals - right first so left is processed first
            andb.goals.insert(0, goal.args[1])
            andb.goals.insert(0, goal.args[0])
            return True

        # Handle disjunction - creates a choice-box
        if isinstance(goal, Struct) and goal.functor == Atom(";") and goal.arity == 2:
            return self._expand_disjunction(andb, goal)

        # Handle negation
        if isinstance(goal, Struct) and goal.functor == Atom("\\+") and goal.arity == 1:
            return self._try_negation(andb, goal.args[0])

        # Handle true/fail
        if goal == Atom("true"):
            return True
        if goal == Atom("fail") or goal == Atom("false"):
            return False

        # Handle unification
        if isinstance(goal, Struct) and goal.functor == Atom("=") and goal.arity == 2:
            return self._try_unification(andb, goal.args[0], goal.args[1])

        # Get functor info
        if isinstance(goal, Atom):
            name, arity, args = goal.name, 0, ()
        elif isinstance(goal, Struct):
            name, arity, args = goal.functor.name, goal.arity, goal.args
        else:
            return False

        # Try builtin
        if is_builtin(name, arity):
            return call_builtin(name, arity, self.exstate, andb, args)

        # Expand predicate call - creates choice-box
        return self._expand_predicate(andb, name, arity, goal)

    def _try_unification(self, andb: AndBox, t1: Term, t2: Term) -> bool:
        """
        Try to unify two terms.

        If unification would bind an external variable, suspend instead.
        """
        t1 = t1.deref()
        t2 = t2.deref()

        # Check for external variable bindings
        if isinstance(t1, Var) and is_external_var(t1, andb):
            # Would bind external - add to unifier list, suspend
            self._add_unifier(andb, t1, t2)
            andb.mark_unstable()
            return True  # Suspended, not failed

        if isinstance(t2, Var) and is_external_var(t2, andb):
            # Would bind external - add to unifier list, suspend
            self._add_unifier(andb, t2, t1)
            andb.mark_unstable()
            return True  # Suspended, not failed

        # Both local or ground - unify normally
        return basic_unify(t1, t2, self.exstate)

    def _add_unifier(self, andb: AndBox, var: Var, value: Term) -> None:
        """Add a deferred unification to an and-box."""
        andb.add_unifier(var, value)

        # Add suspension to variable
        if isinstance(var, ConstrainedVar):
            susp = Suspension.for_andbox(andb)
            var.add_suspension(susp)

    def _expand_predicate(self, andb: AndBox, name: str, arity: int, goal: Term) -> bool:
        """
        Expand a predicate call into a choice-box.

        Creates one and-box per matching clause.
        """
        clauses = self.program.get_clauses(name, arity)
        if not clauses:
            return False  # No matching predicate

        # Create choice-box
        chb = create_choice(andb, predicate=f"{name}/{arity}")

        # Store guard type in choice-box for later
        # (Use first clause's guard type - all should match)
        if hasattr(chb, 'guard_type'):
            chb.guard_type = clauses[0].guard_type

        # Create and-box for each clause
        for clause in clauses:
            alt_andb = create_alternative(chb, clause)

            # Copy clause with fresh variables
            fresh_head, fresh_guard, fresh_body = self._copy_clause(clause, alt_andb.env)

            # Also copy the goal with fresh local variables for this and-box
            # This is critical: each branch needs independent goal variables!
            local_goal = self._copy_term_to_local(goal, alt_andb)

            # Add unification of local_goal with fresh_head as a goal
            # This will be processed when the and-box runs
            unify_goal = Struct(Atom("="), (local_goal, fresh_head))
            alt_andb.goals.append(unify_goal)

            # Add guard goals (if any)
            if fresh_guard is not None:
                alt_andb.goals.append(fresh_guard)

            # Body will be added after guard succeeds
            alt_andb.body_goals = fresh_body  # Store body for later (to add after guard succeeds)

        # Remove dead alternatives
        self._cleanup_dead_alternatives(chb)

        # If no alternatives remain, fail
        if chb.tried is None:
            return False

        # If determinate, can promote immediately
        if chb.is_determinate():
            self._try_andbox(chb.tried)
        else:
            # Process all alternatives
            alt = chb.tried
            while alt is not None:
                if not alt.is_dead():
                    self._try_andbox(alt)
                alt = alt.next

        return True

    def _expand_disjunction(self, andb: AndBox, goal: Struct) -> bool:
        """Expand a disjunction into a choice-box."""
        left = goal.args[0]
        right = goal.args[1]

        # Check for if-then-else: (Cond -> Then ; Else)
        if isinstance(left, Struct) and left.functor == Atom("->") and left.arity == 2:
            return self._expand_if_then_else(andb, left.args[0], left.args[1], right)

        # Regular disjunction - create choice-box
        chb = create_choice(andb)

        # Left alternative
        left_andb = create_alternative(chb)
        left_andb.goals.append(left)

        # Right alternative
        right_andb = create_alternative(chb)
        right_andb.goals.append(right)

        # Process both
        self._try_andbox(left_andb)
        self._try_andbox(right_andb)

        return True

    def _expand_if_then_else(self, andb: AndBox, cond: Term, then: Term, else_: Term) -> bool:
        """
        Expand if-then-else with commit semantics.

        (Cond -> Then ; Else)
        - If Cond succeeds quietly, commit to Then
        - Otherwise, try Else
        """
        # Create choice-box with arrow guard type
        chb = create_choice(andb)

        # Then alternative (with condition as guard)
        then_andb = create_alternative(chb)
        then_andb.goals.append(cond)  # Guard
        then_andb.body_goals = [then]  # Body

        # Else alternative
        else_andb = create_alternative(chb)
        else_andb.goals.append(else_)

        # Try condition first
        self._try_andbox(then_andb)

        # If then branch is solved and quiet, commit
        if then_andb.is_solved() and then_andb.is_quiet():
            else_andb.mark_dead()
            # Add body goals
            if hasattr(then_andb, 'body_goals') and then_andb.body_goals:
                then_andb.goals.extend(then_andb.body_goals)
                then_andb.body_goals = None
                self._try_andbox(then_andb)
        else:
            # Also try else
            self._try_andbox(else_andb)

        return True

    def _try_negation(self, andb: AndBox, goal: Term) -> bool:
        """
        Try negation as failure.

        Creates a nested computation that doesn't affect bindings.
        """
        # Save trail position
        trail_pos = self.exstate.trail_position()

        # Try to prove goal in isolated context
        # For proper AKL, this would create a nested and-box
        # For now, simple approach: if goal can succeed, negation fails

        # Create temporary and-box for negation test
        temp_andb = AndBox()
        temp_andb.env = EnvId(parent=andb.env)
        temp_andb.goals.append(goal)

        # Save state
        saved_solutions = self.solutions
        self.solutions = []

        # Try goal
        self._try_andbox(temp_andb)

        # Check if it succeeded
        goal_succeeded = len(self.solutions) > 0 or (temp_andb.is_solved() and not temp_andb.is_dead())

        # Restore state
        self.solutions = saved_solutions
        self.exstate.undo_trail(trail_pos)

        # Negation succeeds if goal failed
        return not goal_succeeded

    def _try_guard(self, andb: AndBox) -> None:
        """
        Check guard conditions and promote/suspend accordingly.

        Called when an and-box is solved (no pending goals).
        """
        if andb.is_dead():
            return

        chb = andb.father
        if chb is None:
            # No parent choice-box - shouldn't happen normally
            return

        # Check if this is at the root level (parent choice-box has no parent)
        if chb.father is None:
            # Root level - record solution
            self._record_solution(andb)
            andb.mark_dead()  # Prevent re-processing
            return

        # Get guard type (stored in clause or choice-box)
        guard_type = getattr(chb, 'guard_type', GuardType.NONE)

        if self.debug:
            print(f"GUARD: type={guard_type}, quiet={andb.is_quiet()}, determinate={chb.is_determinate()}")

        # Check promotion conditions based on guard type
        can_promote = False
        should_prune = False

        if guard_type == GuardType.NONE:
            # No explicit guard - treated like wait guard (?)
            # Only promote if determinate (last alternative)
            if chb.is_determinate():
                can_promote = True
            # Else: need to split to explore all alternatives

        elif guard_type == GuardType.COMMIT:  # |
            # Quiet commit: if quiet, promote and kill all siblings
            if andb.is_quiet():
                can_promote = True
                should_prune = True

        elif guard_type == GuardType.ARROW:  # ->
            # Quiet cut: if quiet AND leftmost, promote and kill right
            if andb.is_quiet() and andb.prev is None:  # Leftmost
                can_promote = True
                should_prune = True

        elif guard_type == GuardType.CUT:  # !
            # Noisy cut: if leftmost, can promote with bindings
            if andb.prev is None:  # Leftmost
                can_promote = True
                should_prune = True

        elif guard_type in WAIT_GUARDS:  # ? or ??
            # Wait guard: only promote if determinate (last alternative)
            if chb.is_determinate():
                # For quiet wait, still need to be quiet
                if guard_type == GuardType.QUIET_WAIT:
                    can_promote = andb.is_quiet()
                else:
                    can_promote = True  # Noisy allowed

        if can_promote:
            if should_prune:
                self._prune_siblings(andb, guard_type)
            self._promote_andbox(andb)
        # else: suspend and wait

    def _prune_siblings(self, andb: AndBox, guard_type: GuardType) -> None:
        """Kill sibling and-boxes based on guard type."""
        chb = andb.father
        if chb is None:
            return

        if guard_type in {GuardType.COMMIT}:
            # Kill all siblings
            alt = chb.tried
            while alt is not None:
                if alt is not andb:
                    alt.mark_dead()
                alt = alt.next

        elif guard_type in {GuardType.ARROW, GuardType.CUT}:
            # Kill right siblings
            alt = andb.next
            while alt is not None:
                alt.mark_dead()
                alt = alt.next

    def _rehome_local_vars(self, andb: AndBox, parent: AndBox) -> None:
        """
        Re-home local variables from promoted and-box to parent.

        When an and-box is promoted, its local variables should become local to
        the parent. This ensures body goals referencing these variables won't
        be treated as external when executed in the parent context.
        """
        # Update env pointer for all local variables in the and-box
        for name, var in andb.local_vars.items():
            if isinstance(var, ConstrainedVar) and var.env is andb.env:
                var.env = parent.env
                # Also add to parent's local_vars for tracking
                if name not in parent.local_vars:
                    parent.local_vars[name] = var

        # Also need to re-home variables in body_goals that have this and-box's env
        if hasattr(andb, 'body_goals') and andb.body_goals:
            self._rehome_term_vars(andb.body_goals, andb.env, parent.env)

    def _rehome_term_vars(self, terms: list[Term], old_env: EnvId, new_env: EnvId) -> None:
        """Recursively update env pointers for variables in terms."""
        for term in terms:
            self._rehome_term_var(term, old_env, new_env)

    def _rehome_term_var(self, term: Term, old_env: EnvId, new_env: EnvId) -> None:
        """Recursively update env pointer for variables in a term."""
        term = term.deref()

        if isinstance(term, ConstrainedVar):
            if term.env is old_env:
                term.env = new_env
        elif isinstance(term, Struct):
            for arg in term.args:
                self._rehome_term_var(arg, old_env, new_env)
        elif isinstance(term, Cons):
            self._rehome_term_var(term.head, old_env, new_env)
            self._rehome_term_var(term.tail, old_env, new_env)

    def _promote_andbox(self, andb: AndBox) -> None:
        """
        Promote a solved and-box to its parent.

        The body goals become goals of the parent and-box.
        Deferred unifications are processed.
        Local variables are re-homed to parent's environment.
        """
        if andb.is_dead():
            return

        chb = andb.father
        if chb is None:
            return

        parent = chb.father
        if parent is None:
            # At root - record solution (but don't double-record)
            if not andb.is_dead():
                self._record_solution(andb)
                andb.mark_dead()
            return

        if self.debug:
            print(f"PROMOTE: and-box {id(andb)} to parent {id(parent)}")

        # Re-home local variables: variables that were local to the promoted and-box
        # should become local to the parent. This ensures that when body goals reference
        # these variables, they won't be treated as external by the parent.
        self._rehome_local_vars(andb, parent)

        # Process deferred unifications
        # Key insight: discharge interface bindings as soon as they are not external to parent
        # Use is_external_var (not is_local_var) - variables from descendant envs should be bound
        for var, value in andb.unifiers:
            # Resolve value through child's bindings
            resolved = value.deref() if hasattr(value, 'deref') else value

            if not is_external_var(var, parent):
                # Variable is local to parent or descendant - can bind now
                if not basic_unify(var, resolved, self.exstate):
                    # Unification failed - mark parent as dead
                    parent.mark_dead()
                    return
            else:
                # Still external to parent - propagate resolved value
                parent.add_unifier(var, resolved)

        # Add body goals to parent at FRONT (prepend, not append)
        # This ensures inner goals are processed before outer goals.
        # NOTE: Do NOT deref here! Body goals keep their original variable references.
        # Variables will be dereferenced at execution time. Dereferencing during promotion
        # would break the variable chain when a variable is bound to another unbound variable.
        if hasattr(andb, 'body_goals') and andb.body_goals:
            # Insert at front in reverse order to maintain goal order
            for goal in reversed(andb.body_goals):
                parent.goals.insert(0, goal)

        # Remove choice-box if empty
        chb.remove_alternative(andb)
        if chb.tried is None:
            # Remove empty choice-box from parent
            if chb.prev:
                chb.prev.next = chb.next
            else:
                parent.tried = chb.next
            if chb.next:
                chb.next.prev = chb.prev

        # Continue with parent
        self._try_andbox(parent)

    def _propagate_failure(self, andb: AndBox) -> None:
        """Handle failure of an and-box."""
        andb.mark_dead()

        chb = andb.father
        if chb is None:
            return

        # Remove from choice-box
        chb.remove_alternative(andb)

        # Check if choice-box is now empty
        if chb.tried is None:
            # All alternatives failed - propagate to parent
            parent = chb.father
            if parent:
                self._propagate_failure(parent)
        elif chb.is_determinate():
            # Now determinate - process remaining alternative
            # It may still have pending goals to process
            self._try_andbox(chb.tried)

    def _cleanup_dead_alternatives(self, chb: ChoiceBox) -> None:
        """Remove dead and-boxes from a choice-box."""
        alt = chb.tried
        while alt is not None:
            next_alt = alt.next
            if alt.is_dead():
                chb.remove_alternative(alt)
            alt = next_alt

    def _record_solution(self, andb: AndBox) -> None:
        """Record current variable bindings as a solution."""
        # Collect all deferred unifiers from this and-box up to root
        all_unifiers = []
        current = andb
        while current is not None:
            all_unifiers.extend(current.unifiers)
            if current.father and current.father.father:
                current = current.father.father
            else:
                break

        # Build a mapping from variable id to value
        var_to_value = {}
        for var, value in all_unifiers:
            var_to_value[id(var)] = value

        # Resolve a variable to its final value through the unifier chain
        def resolve(var, visited=None):
            if visited is None:
                visited = set()
            if id(var) in visited:
                return var  # Cycle detected, return as-is
            visited.add(id(var))

            val = var.deref()
            if val is not var:
                # Already bound
                return val
            # Check unifier chain
            if id(var) in var_to_value:
                next_val = var_to_value[id(var)].deref()
                if isinstance(next_val, Var):
                    return resolve(next_val, visited)
                return next_val
            return var

        # Build bindings for query variables
        bindings = {}
        for name, qvar in self.query_vars.items():
            val = resolve(qvar)
            if val is not qvar:
                bindings[name] = self._ground_copy(val)

        if self.debug:
            print(f"SOLUTION: {bindings}")

        self.solutions.append(bindings)

    def _deref_term(self, term: Term) -> Term:
        """Dereference a term, following all variable bindings recursively."""
        term = term.deref()

        if isinstance(term, Var):
            return term  # Unbound variable stays as is
        if isinstance(term, (Atom, Integer, Float)):
            return term
        if term is NIL:
            return NIL
        if isinstance(term, Struct):
            return Struct(term.functor, tuple(self._deref_term(a) for a in term.args))
        if isinstance(term, Cons):
            return Cons(self._deref_term(term.head), self._deref_term(term.tail))
        return term

    def _ground_copy(self, term: Term) -> Term:
        """Create a ground copy of a term, following all bindings."""
        # This is the same as _deref_term for now
        return self._deref_term(term)

    def _find_copied_fork(self, mother_copy: AndBox, original_fork: ChoiceBox, original_mother: AndBox) -> ChoiceBox | None:
        """Find the choice-box in the copy that corresponds to the original fork."""
        # The fork is a direct child of mother
        # Find it by position (first choice-box)
        copy_fork = mother_copy.tried
        orig_fork = original_mother.tried

        while copy_fork is not None and orig_fork is not None:
            if orig_fork is original_fork:
                return copy_fork
            copy_fork = copy_fork.next
            orig_fork = orig_fork.next

        return None

    def _find_copied_candidate(self, copy_fork: ChoiceBox, original_candidate: AndBox) -> AndBox | None:
        """Find the and-box in the copy that corresponds to the original candidate."""
        # Find by position
        original_fork = original_candidate.father
        if original_fork is None:
            return None

        copy_alt = copy_fork.tried
        orig_alt = original_fork.tried

        while copy_alt is not None and orig_alt is not None:
            if orig_alt is original_candidate:
                return copy_alt
            copy_alt = copy_alt.next
            orig_alt = orig_alt.next

        return None

    def _copy_term_to_local(self, term: Term, andb: AndBox, var_map: dict | None = None) -> Term:
        """
        Copy a term, making external variables into unification constraints.

        External variables (from query) are kept as references but will cause
        suspension if bound directly. Local copies link back to the externals.

        Uses variable identity (id()) for mapping, not names, to correctly handle
        variables with reused names across scopes.
        """
        if var_map is None:
            var_map = {}

        term = term.deref()

        if isinstance(term, Var):
            # Only true anonymous variable "_" gets fresh copies every time
            if term.name == "_":
                return ConstrainedVar(None, andb.env)

            # Use variable identity for mapping (not name)
            var_id = id(term)
            if var_id in var_map:
                return var_map[var_id]

            # Create local variable that links to external
            local_name = f"_{term.name}_local" if term.name else None
            local_var = ConstrainedVar(local_name, andb.env)
            var_map[var_id] = local_var

            # Store in local_vars for debugging/introspection
            if local_name:
                andb.local_vars[local_name] = local_var

            # Store the external binding for later
            andb.add_unifier(term, local_var)
            return local_var

        if isinstance(term, (Atom, Integer, Float)):
            return term

        if term is NIL:
            return NIL

        if isinstance(term, Struct):
            return Struct(term.functor, tuple(self._copy_term_to_local(a, andb, var_map) for a in term.args))

        if isinstance(term, Cons):
            return Cons(self._copy_term_to_local(term.head, andb, var_map),
                       self._copy_term_to_local(term.tail, andb, var_map))

        return term

    def _copy_clause(self, clause: Clause, env: EnvId) -> tuple[Term, Term | None, list[Term]]:
        """Create fresh copy of clause with new variables."""
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

    def _collect_query_vars(self, term: Term) -> None:
        """Collect variables from query."""
        term = term.deref()
        if isinstance(term, Var):
            if term.name and term.name != "_" and not term.name.startswith("_"):
                if term.name not in self.query_vars:
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

def akl_solve(program: Program, goal: Term, debug: bool = False) -> list[dict[str, Term]]:
    """Solve a goal using proper AKL semantics."""
    worker = AKLWorker(program, debug=debug)
    return worker.solve(goal)
