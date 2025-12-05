"""
Unification algorithm for AKL terms.

Implements Robinson's unification algorithm with:
- Optional occurs check
- Trail-based binding for backtracking
- Support for all term types
"""

from __future__ import annotations
from typing import TYPE_CHECKING

from .term import Term, Var, Atom, Integer, Float, Struct, Cons, NIL
from .engine import ExState, AndBox, ConstrainedVar, is_constrained

if TYPE_CHECKING:
    pass


def unify(t1: Term, t2: Term, exstate: ExState | None = None,
          occurs_check: bool = False) -> bool:
    """
    Unify two terms.

    Args:
        t1: First term
        t2: Second term
        exstate: Execution state for trailing bindings (optional)
        occurs_check: If True, fail on circular unification

    Returns:
        True if unification succeeds, False otherwise
    """
    # Dereference both terms
    t1 = t1.deref()
    t2 = t2.deref()

    # Same object - trivially succeed
    if t1 is t2:
        return True

    # At least one is a variable
    if isinstance(t1, Var):
        return _bind_var(t1, t2, exstate, occurs_check)

    if isinstance(t2, Var):
        return _bind_var(t2, t1, exstate, occurs_check)

    # Both are non-variables - must match structurally
    return _unify_nonvar(t1, t2, exstate, occurs_check)


def _bind_var(var: Var, term: Term, exstate: ExState | None,
              occurs_check: bool) -> bool:
    """Bind a variable to a term."""
    # Occurs check
    if occurs_check and _occurs_in(var, term):
        return False

    # Trail the binding if we have execution state
    if exstate is not None:
        exstate.trail_binding(var, var.binding)

    # Perform binding
    var.binding = term

    # Wake suspended goals if constrained variable
    if exstate is not None and isinstance(var, ConstrainedVar):
        var.wake_all(exstate)

    return True


def _occurs_in(var: Var, term: Term) -> bool:
    """Check if var occurs in term (for occurs check)."""
    term = term.deref()

    if term is var:
        return True

    if isinstance(term, Struct):
        return any(_occurs_in(var, arg) for arg in term.args)

    if isinstance(term, Cons):
        return _occurs_in(var, term.head) or _occurs_in(var, term.tail)

    return False


def _unify_nonvar(t1: Term, t2: Term, exstate: ExState | None,
                  occurs_check: bool) -> bool:
    """Unify two non-variable terms."""
    # Atoms - must be identical (interned)
    if isinstance(t1, Atom):
        return isinstance(t2, Atom) and t1 is t2

    # Integers
    if isinstance(t1, Integer):
        return isinstance(t2, Integer) and t1.value == t2.value

    # Floats
    if isinstance(t1, Float):
        return isinstance(t2, Float) and t1.value == t2.value

    # Structures
    if isinstance(t1, Struct):
        if not isinstance(t2, Struct):
            return False
        if t1.functor != t2.functor or t1.arity != t2.arity:
            return False
        return all(unify(a1, a2, exstate, occurs_check)
                   for a1, a2 in zip(t1.args, t2.args))

    # Lists (Cons)
    if isinstance(t1, Cons):
        if not isinstance(t2, Cons):
            return False
        return (unify(t1.head, t2.head, exstate, occurs_check) and
                unify(t1.tail, t2.tail, exstate, occurs_check))

    # Unknown types - fail
    return False


def unify_with_occurs_check(t1: Term, t2: Term,
                            exstate: ExState | None = None) -> bool:
    """Unify with occurs check enabled."""
    return unify(t1, t2, exstate, occurs_check=True)


def can_unify(t1: Term, t2: Term) -> bool:
    """
    Check if two terms can unify without actually binding.

    This creates temporary bindings and then undoes them.
    Useful for testing without side effects.
    """
    # Create a temporary execution state for trailing
    temp_exstate = ExState()

    # Attempt unification
    result = unify(t1, t2, temp_exstate)

    # Undo all bindings
    temp_exstate.undo_trail()

    return result


def copy_term(term: Term) -> Term:
    """
    Create a copy of a term with fresh variables.

    All variables in the original term are replaced with new
    variables in the copy. Structure is preserved.
    """
    var_map: dict[int, Var] = {}
    return _copy_term_impl(term, var_map)


def _copy_term_impl(term: Term, var_map: dict[int, Var]) -> Term:
    """Implementation of copy_term with variable mapping."""
    term = term.deref()

    if isinstance(term, Var):
        # Create new variable for each unique original variable
        var_id = id(term)
        if var_id not in var_map:
            var_map[var_id] = Var(term.name)
        return var_map[var_id]

    if isinstance(term, (Atom, Integer, Float)):
        # Constants are immutable, return as-is
        return term

    if isinstance(term, Struct):
        new_args = tuple(_copy_term_impl(arg, var_map) for arg in term.args)
        return Struct(term.functor, new_args)

    if isinstance(term, Cons):
        new_head = _copy_term_impl(term.head, var_map)
        new_tail = _copy_term_impl(term.tail, var_map)
        return Cons(new_head, new_tail)

    # Unknown type - return as-is
    return term


def variant(t1: Term, t2: Term) -> bool:
    """
    Check if two terms are variants (identical up to variable renaming).

    Two terms are variants if they can be made identical by consistently
    renaming variables.
    """
    return _variant_impl(t1.deref(), t2.deref(), {}, {})


def _variant_impl(t1: Term, t2: Term,
                  map1: dict[int, int], map2: dict[int, int]) -> bool:
    """Implementation of variant check."""
    if isinstance(t1, Var) and isinstance(t2, Var):
        id1, id2 = id(t1), id(t2)
        # Check consistent mapping
        if id1 in map1:
            return map1[id1] == id2
        if id2 in map2:
            return map2[id2] == id1
        # New pair - record mapping
        map1[id1] = id2
        map2[id2] = id1
        return True

    if isinstance(t1, Var) or isinstance(t2, Var):
        return False

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
        return all(_variant_impl(a1.deref(), a2.deref(), map1, map2)
                   for a1, a2 in zip(t1.args, t2.args))

    if isinstance(t1, Cons):
        if not isinstance(t2, Cons):
            return False
        return (_variant_impl(t1.head.deref(), t2.head.deref(), map1, map2) and
                _variant_impl(t1.tail.deref(), t2.tail.deref(), map1, map2))

    return False


def collect_vars(term: Term) -> list[Var]:
    """
    Collect all variables in a term.

    Returns a list of unique variables in left-to-right order.
    """
    seen: set[int] = set()
    result: list[Var] = []
    _collect_vars_impl(term.deref(), seen, result)
    return result


def _collect_vars_impl(term: Term, seen: set[int], result: list[Var]) -> None:
    """Implementation of collect_vars."""
    if isinstance(term, Var):
        var_id = id(term)
        if var_id not in seen:
            seen.add(var_id)
            result.append(term)
        return

    if isinstance(term, Struct):
        for arg in term.args:
            _collect_vars_impl(arg.deref(), seen, result)
        return

    if isinstance(term, Cons):
        _collect_vars_impl(term.head.deref(), seen, result)
        _collect_vars_impl(term.tail.deref(), seen, result)
