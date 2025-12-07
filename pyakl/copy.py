"""
And-box copying for nondeterministic splitting.

This module implements deep copying of and-box subtrees for AKL nondeterminism.
Key principle: Local variables are copied to fresh instances, external variables
are shared between the original and copy.

Based on the AKL emulator's copy.c implementation.
"""

from __future__ import annotations
from typing import TYPE_CHECKING
from dataclasses import dataclass, field

from .term import Term, Var, Atom, Integer, Float, Struct, Cons, NIL
from .engine import (
    AndBox, ChoiceBox, EnvId, ConstrainedVar, Status,
    Suspension, SuspensionType, AndCont, ChoiceCont
)

if TYPE_CHECKING:
    from .engine import ExState


# =============================================================================
# Copy State
# =============================================================================

@dataclass
class CopyState:
    """
    State maintained during a copy operation.

    Tracks the mapping from original to copied objects.
    """
    # The root and-box being copied (the "mother")
    mother: AndBox

    # The copy of the mother
    copy: AndBox | None = None

    # Mapping from original and-boxes to copies
    andbox_map: dict[int, AndBox] = field(default_factory=dict)

    # Mapping from original choice-boxes to copies
    choicebox_map: dict[int, ChoiceBox] = field(default_factory=dict)

    # Mapping from original local variables to copies
    var_map: dict[int, ConstrainedVar] = field(default_factory=dict)

    # Mapping from original EnvIds to copies
    env_map: dict[int, EnvId] = field(default_factory=dict)

    def is_local_env(self, env: EnvId | None) -> bool:
        """Check if an environment is local to the copied subtree."""
        if env is None:
            return False
        # An env is local if it is or descends from mother's env
        return self.mother.env.is_ancestor_of(env) or env is self.mother.env

    def is_local_var(self, var: Var) -> bool:
        """Check if a variable is local to the copied subtree."""
        if isinstance(var, ConstrainedVar):
            return self.is_local_env(var.env)
        return False


# =============================================================================
# Copy Functions
# =============================================================================

def copy_andbox_subtree(mother: AndBox, exstate: ExState) -> AndBox:
    """
    Create a deep copy of an and-box subtree.

    The copy shares external variables with the original but has fresh
    copies of all local variables. This enables independent exploration
    of nondeterministic alternatives.

    Args:
        mother: The root and-box to copy
        exstate: Execution state (for suspension handling)

    Returns:
        The copied and-box
    """
    state = CopyState(mother=mother)

    # Copy the and-box tree
    copy = _copy_andbox(mother, state)
    state.copy = copy

    # Update suspension references
    _update_suspensions(state, exstate)

    return copy


def _copy_andbox(andb: AndBox, state: CopyState) -> AndBox:
    """Copy a single and-box and its subtree."""
    # Check if already copied
    if id(andb) in state.andbox_map:
        return state.andbox_map[id(andb)]

    # Create new and-box
    new_andb = AndBox()
    state.andbox_map[id(andb)] = new_andb

    # Copy status
    new_andb.status = andb.status

    # Copy environment - create new env with copied parent chain
    new_andb.env = _copy_env(andb.env, state)

    # Copy local variables (mapping old to new)
    new_andb.local_vars = {}
    for name, var in andb.local_vars.items():
        new_var = _copy_local_var(var, new_andb.env, state)
        new_andb.local_vars[name] = new_var

    # Copy goals with variable substitution
    new_andb.goals = [_copy_term(g, state) for g in andb.goals]

    # Copy body_goals with variable substitution
    if hasattr(andb, 'body_goals') and andb.body_goals:
        new_andb.body_goals = [_copy_term(g, state) for g in andb.body_goals]
    else:
        new_andb.body_goals = []

    # Copy unifiers with variable substitution
    new_andb.unifiers = [
        (_copy_term(t1, state), _copy_term(t2, state))
        for t1, t2 in andb.unifiers
    ]

    # Copy constraints (shallow for now - extend when constraint system is added)
    new_andb.constraints = list(andb.constraints)

    # Copy continuation
    if andb.cont is not None:
        new_andb.cont = _copy_andcont(andb.cont, state)

    # Copy child choice-boxes
    if andb.tried is not None:
        new_andb.tried = _copy_choicebox_chain(andb.tried, new_andb, state)

    # Note: father, next, prev are set by parent during chain copying

    return new_andb


def _copy_choicebox_chain(first: ChoiceBox, parent: AndBox, state: CopyState) -> ChoiceBox:
    """Copy a chain of sibling choice-boxes."""
    new_first = None
    new_prev = None

    current = first
    while current is not None:
        new_chb = _copy_choicebox(current, parent, state)

        if new_first is None:
            new_first = new_chb

        if new_prev is not None:
            new_prev.next = new_chb
            new_chb.prev = new_prev

        new_prev = new_chb
        current = current.next

    return new_first


def _copy_choicebox(chb: ChoiceBox, parent: AndBox, state: CopyState) -> ChoiceBox:
    """Copy a single choice-box and its alternatives."""
    # Check if already copied
    if id(chb) in state.choicebox_map:
        return state.choicebox_map[id(chb)]

    new_chb = ChoiceBox()
    state.choicebox_map[id(chb)] = new_chb

    new_chb.father = parent
    new_chb.predicate = chb.predicate  # Share predicate reference

    # Copy continuation
    if chb.cont is not None:
        new_chb.cont = _copy_choicecont(chb.cont, state)

    # Copy alternative and-boxes
    if chb.tried is not None:
        new_chb.tried = _copy_andbox_chain(chb.tried, new_chb, state)

    return new_chb


def _copy_andbox_chain(first: AndBox, parent: ChoiceBox, state: CopyState) -> AndBox:
    """Copy a chain of sibling and-boxes."""
    new_first = None
    new_prev = None

    current = first
    while current is not None:
        new_andb = _copy_andbox(current, state)
        new_andb.father = parent

        if new_first is None:
            new_first = new_andb

        if new_prev is not None:
            new_prev.next = new_andb
            new_andb.prev = new_prev

        new_prev = new_andb
        current = current.next

    return new_first


def _copy_env(env: EnvId, state: CopyState) -> EnvId:
    """
    Copy an environment ID.

    Creates new EnvIds for local environments, keeps external ones.
    """
    if env is None:
        return None

    # If not local, return the original (shared external)
    if not state.is_local_env(env):
        return env

    # Check if already copied
    if id(env) in state.env_map:
        return state.env_map[id(env)]

    # Copy parent first
    new_parent = _copy_env(env.parent, state) if env.parent else None

    # Create new env
    new_env = EnvId(parent=new_parent)
    state.env_map[id(env)] = new_env

    return new_env


def _copy_local_var(var: ConstrainedVar, new_env: EnvId, state: CopyState) -> ConstrainedVar:
    """Copy a local variable to a fresh instance."""
    # Check if already copied
    if id(var) in state.var_map:
        return state.var_map[id(var)]

    new_var = ConstrainedVar(var.name, new_env)
    state.var_map[id(var)] = new_var

    # Copy binding if present
    if var.binding is not None:
        new_var.binding = _copy_term(var.binding, state)

    # Suspensions are handled separately

    return new_var


def _copy_term(term: Term, state: CopyState) -> Term:
    """
    Copy a term, substituting local variables with their copies.

    External variables remain shared (not copied).
    """
    if term is None:
        return None

    term = term.deref()

    # Variable handling
    if isinstance(term, Var):
        if isinstance(term, ConstrainedVar) and state.is_local_var(term):
            # Local variable - return copy (or create if not yet copied)
            if id(term) in state.var_map:
                return state.var_map[id(term)]
            # Create new var with copied env
            new_env = _copy_env(term.env, state)
            new_var = ConstrainedVar(term.name, new_env)
            state.var_map[id(term)] = new_var
            # Copy binding if present
            if term.binding is not None:
                new_var.binding = _copy_term(term.binding, state)
            return new_var
        else:
            # External variable - return as-is (shared)
            return term

    # Atoms, integers, floats - immutable, share
    if isinstance(term, (Atom, Integer, Float)):
        return term

    # NIL - singleton, share
    if term is NIL:
        return NIL

    # Structure - copy with copied args
    if isinstance(term, Struct):
        new_args = tuple(_copy_term(arg, state) for arg in term.args)
        return Struct(term.functor, new_args)

    # List cons - copy with copied head/tail
    if isinstance(term, Cons):
        new_head = _copy_term(term.head, state)
        new_tail = _copy_term(term.tail, state)
        return Cons(new_head, new_tail)

    # Unknown term type - return as-is
    return term


def _copy_andcont(cont: AndCont, state: CopyState) -> AndCont:
    """Copy an and-continuation."""
    new_cont = AndCont()
    new_cont.code = cont.code
    new_cont.yreg = [_copy_term(t, state) for t in cont.yreg]

    if cont.next is not None:
        new_cont.next = _copy_andcont(cont.next, state)

    return new_cont


def _copy_choicecont(cont: ChoiceCont, state: CopyState) -> ChoiceCont:
    """Copy a choice-continuation."""
    new_cont = ChoiceCont()
    new_cont.clause = cont.clause
    new_cont.args = tuple(_copy_term(arg, state) for arg in cont.args)

    if cont.next is not None:
        new_cont.next = _copy_choicecont(cont.next, state)

    return new_cont


def _update_suspensions(state: CopyState, exstate: ExState) -> None:
    """
    Update suspensions after copying.

    For local variables in the copy, create new suspensions pointing
    to the copied and-boxes. For external variables, add suspensions
    for the copied and-boxes.
    """
    # Iterate over copied variables
    for old_id, new_var in state.var_map.items():
        # Find original variable (not efficient, but simple)
        for old_andb in state.andbox_map.keys():
            # This is just the ID, we need the actual variable
            pass

    # For now, suspensions are handled by the execution engine
    # when goals are executed. This is a placeholder for full
    # suspension copying if needed.
    pass


# =============================================================================
# Candidate Finding
# =============================================================================

def find_candidate(andb: AndBox) -> AndBox | None:
    """
    Find a candidate for nondeterministic splitting.

    A candidate is the leftmost solved and-box with a GUARD_WAIT instruction
    that doesn't have a deeper candidate in its scope.

    Args:
        andb: The root and-box to search within

    Returns:
        The candidate and-box, or None if no candidate found
    """
    return _find_leftmost_candidate(andb.tried)


def _find_leftmost_candidate(chb: ChoiceBox | None) -> AndBox | None:
    """Search for leftmost candidate in choice-box chain."""
    while chb is not None:
        candidate = _search_choicebox(chb)
        if candidate is not None:
            return candidate
        chb = chb.next
    return None


def _search_choicebox(chb: ChoiceBox) -> AndBox | None:
    """Search a choice-box for candidates."""
    andb = chb.tried

    while andb is not None:
        # Check if this and-box is a candidate
        # A candidate must:
        # 1. Be solved (no pending goals/tried choice-boxes)
        # 2. Have a wait guard (for now, check if not dead and no tried)

        if andb.is_solved() and not andb.is_dead():
            # Check for deeper candidates first
            if andb.tried is not None:
                deeper = _find_leftmost_candidate(andb.tried)
                if deeper is not None:
                    return deeper
            # This and-box is a candidate
            return andb

        # If not solved, search children
        if andb.tried is not None:
            deeper = _find_leftmost_candidate(andb.tried)
            if deeper is not None:
                return deeper

        andb = andb.next

    return None


# =============================================================================
# Split Operation
# =============================================================================

def split_at_candidate(candidate: AndBox, exstate: ExState) -> AndBox:
    """
    Perform nondeterministic splitting at a candidate.

    Given candidate A with parent choice-box B, parent and-box C:
    1. Copy the subtree rooted at C
    2. In the copy, B has only A (promoted)
    3. In the original, B has remaining siblings of A
    4. Return the promoted copy of A

    Args:
        candidate: The candidate and-box
        exstate: Execution state

    Returns:
        The promoted copy of the candidate
    """
    # Get the structure
    fork = candidate.father  # Parent choice-box B
    if fork is None:
        raise RuntimeError("Candidate has no parent choice-box")

    mother = fork.father  # Parent and-box C
    if mother is None:
        raise RuntimeError("Fork has no parent and-box")

    # Unlink candidate from siblings
    if candidate.prev is not None:
        candidate.prev.next = candidate.next
    else:
        fork.tried = candidate.next

    if candidate.next is not None:
        candidate.next.prev = candidate.prev

    # Save siblings
    siblings = fork.tried

    # Temporarily make candidate the only alternative
    fork.tried = candidate
    candidate.next = None
    candidate.prev = None

    # Copy the mother subtree
    copy = copy_andbox_subtree(mother, exstate)

    # Find the copied candidate (it's the only one under the copied fork)
    # The copied fork is the first tried of the copied mother that corresponds to fork
    # This requires finding it by position or other means

    # Restore siblings in original
    fork.tried = siblings

    # Mark original candidate as dead
    candidate.status = Status.DEAD

    # Insert copy to the left of mother in its parent
    if mother.father is not None:
        copy.father = mother.father
        copy.next = mother
        copy.prev = mother.prev
        if mother.prev is not None:
            mother.prev.next = copy
        else:
            mother.father.tried = copy
        mother.prev = copy

    # The promoted candidate is in the copy
    # Since we made candidate the only one, the copy's fork also has only one
    # Find and return it
    if copy.tried is not None:
        copied_fork = copy.tried
        if copied_fork.tried is not None:
            return copied_fork.tried

    return copy
