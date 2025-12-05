r"""
Built-in predicates for PyAKL.

This module provides essential built-in predicates:
- Control: true, fail
- Unification: =, \=
- Arithmetic: is, <, >, =<, >=, =:=, =\=
- I/O: write, nl, writeln
- Meta: functor, arg, =.., copy_term
- Type checking: var, nonvar, atom, number, integer, float, compound, is_list
"""

from __future__ import annotations
from typing import Callable, TYPE_CHECKING
import operator
import sys
import time

from .term import Term, Var, Atom, Integer, Float, Struct, Cons, NIL, Port, make_list, list_to_python
from .unify import unify, copy_term as copy_term_impl

if TYPE_CHECKING:
    from .engine import ExState, AndBox
    from .program import Program


# Type alias for built-in implementations
BuiltinFunc = Callable[['ExState', 'AndBox', tuple[Term, ...]], bool]


# Registry of built-ins: (name, arity) -> implementation
_BUILTINS: dict[tuple[str, int], BuiltinFunc] = {}


# =============================================================================
# Global context for builtins that need access to interpreter/program
# =============================================================================

class AKLContext:
    """
    Global context providing access to interpreter state.

    Set by the interpreter before executing goals.
    """
    program: 'Program | None' = None
    interpreter: any = None  # Interpreter instance

    # Statistics tracking
    _start_time: float = 0.0  # Process start time
    _last_runtime_call: float = 0.0  # Time of last statistics(runtime, _) call
    _total_nondet: int = 0  # Total nondeterministic steps
    _last_nondet_call: int = 0  # Nondet count at last statistics(nondet, _) call

    @classmethod
    def reset(cls) -> None:
        cls.program = None
        cls.interpreter = None
        cls._start_time = time.time()
        cls._last_runtime_call = cls._start_time
        cls._total_nondet = 0
        cls._last_nondet_call = 0

    @classmethod
    def init_statistics(cls) -> None:
        """Initialize statistics tracking."""
        cls._start_time = time.time()
        cls._last_runtime_call = cls._start_time
        cls._total_nondet = 0
        cls._last_nondet_call = 0

    @classmethod
    def increment_nondet(cls) -> None:
        """Increment nondeterministic step counter."""
        cls._total_nondet += 1


akl_context = AKLContext
# Initialize statistics on module load
akl_context.init_statistics()


def register_builtin(name: str, arity: int) -> Callable[[BuiltinFunc], BuiltinFunc]:
    """Decorator to register a built-in predicate."""
    def decorator(func: BuiltinFunc) -> BuiltinFunc:
        _BUILTINS[(name, arity)] = func
        return func
    return decorator


def is_builtin(name: str, arity: int) -> bool:
    """Check if a predicate is a built-in."""
    return (name, arity) in _BUILTINS


def get_builtin(name: str, arity: int) -> BuiltinFunc | None:
    """Get a built-in implementation."""
    return _BUILTINS.get((name, arity))


def call_builtin(name: str, arity: int, exstate: 'ExState',
                 andb: 'AndBox', args: tuple[Term, ...]) -> bool:
    """Call a built-in predicate."""
    func = _BUILTINS.get((name, arity))
    if func is None:
        raise ValueError(f"Unknown built-in: {name}/{arity}")
    return func(exstate, andb, args)


# =============================================================================
# Control
# =============================================================================

@register_builtin("true", 0)
def builtin_true(exstate: 'ExState', andb: 'AndBox', args: tuple[Term, ...]) -> bool:
    """true/0 - Always succeeds."""
    return True


@register_builtin("fail", 0)
def builtin_fail(exstate: 'ExState', andb: 'AndBox', args: tuple[Term, ...]) -> bool:
    """fail/0 - Always fails."""
    return False


@register_builtin("false", 0)
def builtin_false(exstate: 'ExState', andb: 'AndBox', args: tuple[Term, ...]) -> bool:
    """false/0 - Always fails (alias for fail)."""
    return False


# =============================================================================
# Unification
# =============================================================================

@register_builtin("=", 2)
def builtin_unify(exstate: 'ExState', andb: 'AndBox', args: tuple[Term, ...]) -> bool:
    """=/2 - Unify two terms."""
    return unify(args[0], args[1], exstate)


@register_builtin("\\=", 2)
def builtin_not_unify(exstate: 'ExState', andb: 'AndBox', args: tuple[Term, ...]) -> bool:
    """\\=/2 - Succeed if terms do not unify."""
    # Save trail position
    pos = exstate.trail_position()
    # Try to unify
    result = unify(args[0], args[1], exstate)
    # Undo any bindings
    exstate.undo_trail(pos)
    # Succeed if unification failed
    return not result


@register_builtin("dif", 2)
def builtin_dif(exstate: 'ExState', andb: 'AndBox', args: tuple[Term, ...]) -> bool:
    """dif/2 - Disequality constraint.

    Succeeds if the two terms cannot unify.
    In full AKL, this would suspend if the terms contain unbound variables
    that might later become equal. For now, we use a simplified version
    that just checks current unifiability (same as \\=/2).
    """
    # Save trail position
    pos = exstate.trail_position()
    # Try to unify
    result = unify(args[0], args[1], exstate)
    # Undo any bindings
    exstate.undo_trail(pos)
    # Succeed if unification failed (terms are different)
    return not result


@register_builtin("==", 2)
def builtin_eq(exstate: 'ExState', andb: 'AndBox', args: tuple[Term, ...]) -> bool:
    """==/2 - Succeed if terms are identical (without unification)."""
    return _identical(args[0].deref(), args[1].deref())


@register_builtin("\\==", 2)
def builtin_neq(exstate: 'ExState', andb: 'AndBox', args: tuple[Term, ...]) -> bool:
    """\\==/2 - Succeed if terms are not identical."""
    return not _identical(args[0].deref(), args[1].deref())


def _identical(t1: Term, t2: Term) -> bool:
    """Check if two terms are structurally identical."""
    if t1 is t2:
        return True

    if type(t1) != type(t2):
        return False

    if isinstance(t1, Var):
        return t1 is t2

    if isinstance(t1, Atom):
        return t1 is t2  # Atoms are interned

    if isinstance(t1, Integer):
        return t1.value == t2.value

    if isinstance(t1, Float):
        return t1.value == t2.value

    if isinstance(t1, Struct):
        if t1.functor != t2.functor or t1.arity != t2.arity:
            return False
        return all(_identical(a.deref(), b.deref())
                   for a, b in zip(t1.args, t2.args))

    if isinstance(t1, Cons):
        return (_identical(t1.head.deref(), t2.head.deref()) and
                _identical(t1.tail.deref(), t2.tail.deref()))

    return False


# =============================================================================
# Term Comparison (Standard Order)
# =============================================================================

def _term_compare(t1: Term, t2: Term) -> int:
    """
    Compare two terms in standard order.
    Returns: -1 if t1 < t2, 0 if t1 == t2, 1 if t1 > t2

    Standard order (from Prolog/AKL):
    1. Variables < Numbers < Atoms < Compound terms
    2. Variables are compared by some internal ordering
    3. Numbers are compared by value (floats before integers with same value)
    4. Atoms are compared alphabetically
    5. Compound terms: first by arity, then by functor name, then by args left-to-right
    """
    t1 = t1.deref()
    t2 = t2.deref()

    # Get type order
    def type_order(t: Term) -> int:
        if isinstance(t, Var):
            return 0
        if isinstance(t, Float):
            return 1
        if isinstance(t, Integer):
            return 2
        if isinstance(t, Atom):
            return 3
        if isinstance(t, (Struct, Cons)):
            return 4
        return 5

    o1, o2 = type_order(t1), type_order(t2)
    if o1 != o2:
        return -1 if o1 < o2 else 1

    # Same type category
    if isinstance(t1, Var):
        # Variables compared by id
        if t1 is t2:
            return 0
        return -1 if id(t1) < id(t2) else 1

    if isinstance(t1, (Integer, Float)):
        v1, v2 = t1.value, t2.value
        if v1 == v2:
            return 0
        return -1 if v1 < v2 else 1

    if isinstance(t1, Atom):
        if t1 is t2:
            return 0
        if t1.name == t2.name:
            return 0
        return -1 if t1.name < t2.name else 1

    if isinstance(t1, Cons):
        # Lists: compare as ./2 compound terms
        # First compare heads, then tails
        cmp = _term_compare(t1.head, t2.head)
        if cmp != 0:
            return cmp
        return _term_compare(t1.tail, t2.tail)

    if isinstance(t1, Struct):
        # Compare by arity first
        if t1.arity != t2.arity:
            return -1 if t1.arity < t2.arity else 1
        # Then by functor name
        if t1.functor.name != t2.functor.name:
            return -1 if t1.functor.name < t2.functor.name else 1
        # Then by arguments
        for a1, a2 in zip(t1.args, t2.args):
            cmp = _term_compare(a1, a2)
            if cmp != 0:
                return cmp
        return 0

    return 0


@register_builtin("@<", 2)
def builtin_term_lt(exstate: 'ExState', andb: 'AndBox', args: tuple[Term, ...]) -> bool:
    """@</2 - Term is less than in standard order."""
    return _term_compare(args[0], args[1]) < 0


@register_builtin("@>", 2)
def builtin_term_gt(exstate: 'ExState', andb: 'AndBox', args: tuple[Term, ...]) -> bool:
    """@>/2 - Term is greater than in standard order."""
    return _term_compare(args[0], args[1]) > 0


@register_builtin("@=<", 2)
def builtin_term_le(exstate: 'ExState', andb: 'AndBox', args: tuple[Term, ...]) -> bool:
    """@=</2 - Term is less than or equal in standard order."""
    return _term_compare(args[0], args[1]) <= 0


@register_builtin("@>=", 2)
def builtin_term_ge(exstate: 'ExState', andb: 'AndBox', args: tuple[Term, ...]) -> bool:
    """@>=/2 - Term is greater than or equal in standard order."""
    return _term_compare(args[0], args[1]) >= 0


@register_builtin("compare", 3)
def builtin_compare(exstate: 'ExState', andb: 'AndBox', args: tuple[Term, ...]) -> bool:
    """compare/3 - Compare two terms, unify first arg with <, =, or >."""
    cmp = _term_compare(args[1], args[2])
    if cmp < 0:
        result = Atom("<")
    elif cmp > 0:
        result = Atom(">")
    else:
        result = Atom("=")
    return unify(args[0], result, exstate)


# =============================================================================
# Arithmetic
# =============================================================================

def _eval_arith(term: Term) -> int | float:
    """Evaluate an arithmetic expression."""
    term = term.deref()

    if isinstance(term, Integer):
        return term.value

    if isinstance(term, Float):
        return term.value

    if isinstance(term, Struct):
        op = term.functor.name
        args = [_eval_arith(a) for a in term.args]

        if term.arity == 2:
            a, b = args
            if op == "+":
                return a + b
            if op == "-":
                return a - b
            if op == "*":
                return a * b
            if op == "/":
                return a / b
            if op == "//":
                return int(a) // int(b)
            if op == "mod":
                return int(a) % int(b)
            if op == "**":
                return a ** b
            if op == "^":
                return a ** b
            if op == "/\\":
                return int(a) & int(b)
            if op == "\\/":
                return int(a) | int(b)
            if op == "xor":
                return int(a) ^ int(b)
            if op == "<<":
                return int(a) << int(b)
            if op == ">>":
                return int(a) >> int(b)
            if op == "min":
                return min(a, b)
            if op == "max":
                return max(a, b)

        if term.arity == 1:
            a = args[0]
            if op == "-":
                return -a
            if op == "abs":
                return abs(a)
            if op == "sign":
                return (a > 0) - (a < 0)
            if op == "\\":
                return ~int(a)
            if op == "sqrt":
                return a ** 0.5
            if op == "sin":
                import math
                return math.sin(a)
            if op == "cos":
                import math
                return math.cos(a)
            if op == "float":
                return float(a)
            if op == "integer":
                return int(a)
            if op == "truncate":
                return int(a)
            if op == "round":
                return round(a)
            if op == "ceiling":
                import math
                return math.ceil(a)
            if op == "floor":
                import math
                return math.floor(a)

    raise ValueError(f"Cannot evaluate arithmetic expression: {term}")


@register_builtin("is", 2)
def builtin_is(exstate: 'ExState', andb: 'AndBox', args: tuple[Term, ...]) -> bool:
    """is/2 - Evaluate arithmetic expression and unify."""
    try:
        result = _eval_arith(args[1])
        if isinstance(result, float) and result == int(result):
            result = int(result)
        if isinstance(result, int):
            return unify(args[0], Integer(result), exstate)
        else:
            return unify(args[0], Float(result), exstate)
    except (ValueError, ZeroDivisionError, TypeError):
        return False


@register_builtin("=:=", 2)
def builtin_arith_eq(exstate: 'ExState', andb: 'AndBox', args: tuple[Term, ...]) -> bool:
    """=:=/2 - Arithmetic equality."""
    try:
        return _eval_arith(args[0]) == _eval_arith(args[1])
    except ValueError:
        return False


@register_builtin("=\\=", 2)
def builtin_arith_neq(exstate: 'ExState', andb: 'AndBox', args: tuple[Term, ...]) -> bool:
    """=\\=/2 - Arithmetic inequality."""
    try:
        return _eval_arith(args[0]) != _eval_arith(args[1])
    except ValueError:
        return False


@register_builtin("<", 2)
def builtin_lt(exstate: 'ExState', andb: 'AndBox', args: tuple[Term, ...]) -> bool:
    """</2 - Arithmetic less than."""
    try:
        return _eval_arith(args[0]) < _eval_arith(args[1])
    except ValueError:
        return False


@register_builtin(">", 2)
def builtin_gt(exstate: 'ExState', andb: 'AndBox', args: tuple[Term, ...]) -> bool:
    """>/2 - Arithmetic greater than."""
    try:
        return _eval_arith(args[0]) > _eval_arith(args[1])
    except ValueError:
        return False


@register_builtin("=<", 2)
def builtin_le(exstate: 'ExState', andb: 'AndBox', args: tuple[Term, ...]) -> bool:
    """=</2 - Arithmetic less than or equal."""
    try:
        return _eval_arith(args[0]) <= _eval_arith(args[1])
    except ValueError:
        return False


@register_builtin(">=", 2)
def builtin_ge(exstate: 'ExState', andb: 'AndBox', args: tuple[Term, ...]) -> bool:
    """>=/2 - Arithmetic greater than or equal."""
    try:
        return _eval_arith(args[0]) >= _eval_arith(args[1])
    except ValueError:
        return False


@register_builtin("int_not_equal", 2)
def builtin_int_not_equal(exstate: 'ExState', andb: 'AndBox', args: tuple[Term, ...]) -> bool:
    """int_not_equal/2 - Integer inequality test (blocking if uninstantiated)."""
    t1, t2 = args[0], args[1]
    if isinstance(t1, Integer) and isinstance(t2, Integer):
        return t1.value != t2.value
    # If not both integers, fail (like in reference AKL)
    return False


# =============================================================================
# I/O
# =============================================================================

@register_builtin("write", 1)
def builtin_write(exstate: 'ExState', andb: 'AndBox', args: tuple[Term, ...]) -> bool:
    """write/1 - Write a term."""
    from .printer import print_term
    print(print_term(args[0]), end='')
    return True


@register_builtin("writeln", 1)
def builtin_writeln(exstate: 'ExState', andb: 'AndBox', args: tuple[Term, ...]) -> bool:
    """writeln/1 - Write a term followed by newline."""
    from .printer import print_term
    print(print_term(args[0]))
    return True


@register_builtin("nl", 0)
def builtin_nl(exstate: 'ExState', andb: 'AndBox', args: tuple[Term, ...]) -> bool:
    """nl/0 - Print newline."""
    print()
    return True


@register_builtin("put", 1)
def builtin_put(exstate: 'ExState', andb: 'AndBox', args: tuple[Term, ...]) -> bool:
    """put/1 - Write a character code."""
    arg = args[0].deref()
    if isinstance(arg, Integer):
        print(chr(arg.value), end='')
        return True
    return False


# =============================================================================
# File loading
# =============================================================================

def _get_path_string(arg: Term) -> str | None:
    """Extract a file path from a term (atom or string)."""
    arg = arg.deref()
    if isinstance(arg, Atom):
        return arg.name
    # Could also handle string terms here
    return None


@register_builtin("consult", 1)
def builtin_consult(exstate: 'ExState', andb: 'AndBox', args: tuple[Term, ...]) -> bool:
    """consult/1 - Load clauses from a file into the current program."""
    from pathlib import Path
    from .program import load_file

    path_str = _get_path_string(args[0])
    if path_str is None:
        return False

    if akl_context.program is None:
        print("Error: no program context for consult/1")
        return False

    # Try with and without .akl extension
    paths = [Path(path_str), Path(path_str + ".akl"), Path(path_str + ".pl")]

    for path in paths:
        if path.exists():
            try:
                load_file(path, akl_context.program)
                return True
            except Exception as e:
                print(f"Error loading {path}: {e}")
                return False

    print(f"File not found: {path_str}")
    return False


@register_builtin("load", 1)
def builtin_load(exstate: 'ExState', andb: 'AndBox', args: tuple[Term, ...]) -> bool:
    """load/1 - Alias for consult/1."""
    return builtin_consult(exstate, andb, args)


# =============================================================================
# Meta predicates
# =============================================================================

@register_builtin("functor", 3)
def builtin_functor(exstate: 'ExState', andb: 'AndBox', args: tuple[Term, ...]) -> bool:
    """functor/3 - Get/construct functor and arity."""
    term = args[0].deref()
    name = args[1].deref()
    arity = args[2].deref()

    # Mode: +Term, -Name, -Arity
    if isinstance(term, Atom):
        return (unify(args[1], term, exstate) and
                unify(args[2], Integer(0), exstate))
    if isinstance(term, Integer):
        return (unify(args[1], term, exstate) and
                unify(args[2], Integer(0), exstate))
    if isinstance(term, Float):
        return (unify(args[1], term, exstate) and
                unify(args[2], Integer(0), exstate))
    if isinstance(term, Struct):
        return (unify(args[1], term.functor, exstate) and
                unify(args[2], Integer(term.arity), exstate))
    if isinstance(term, Cons):
        # Lists are ./2 structures
        return (unify(args[1], Atom("."), exstate) and
                unify(args[2], Integer(2), exstate))

    # Mode: -Term, +Name, +Arity
    if isinstance(term, Var) and isinstance(name, Atom) and isinstance(arity, Integer):
        if arity.value == 0:
            return unify(term, name, exstate)
        elif name.name == "." and arity.value == 2:
            # Create a list cell
            new_term = Cons(Var(), Var())
            return unify(term, new_term, exstate)
        else:
            # Create structure with fresh variables
            new_args = tuple(Var() for _ in range(arity.value))
            new_term = Struct(name, new_args)
            return unify(term, new_term, exstate)

    return False


@register_builtin("functor_to_term", 3)
def builtin_functor_to_term(exstate: 'ExState', andb: 'AndBox', args: tuple[Term, ...]) -> bool:
    """functor_to_term/3 - Create term from name and arity.

    functor_to_term(+Name, +Arity, -Term)
    Like functor/3 but with different argument order.
    """
    name = args[0].deref()
    arity = args[1].deref()
    term = args[2].deref()

    if not isinstance(name, Atom) or not isinstance(arity, Integer):
        return False

    if arity.value == 0:
        return unify(args[2], name, exstate)
    elif name.name == "." and arity.value == 2:
        new_term = Cons(Var(), Var())
        return unify(args[2], new_term, exstate)
    else:
        new_args = tuple(Var() for _ in range(arity.value))
        new_term = Struct(name, new_args)
        return unify(args[2], new_term, exstate)


@register_builtin("term_to_functor", 3)
def builtin_term_to_functor(exstate: 'ExState', andb: 'AndBox', args: tuple[Term, ...]) -> bool:
    """term_to_functor/3 - Decompose term into name and arity.

    term_to_functor(+Term, -Name, -Arity)
    Like functor/3 but with different argument order.
    """
    term = args[0].deref()

    if isinstance(term, Atom):
        return (unify(args[1], term, exstate) and
                unify(args[2], Integer(0), exstate))
    if isinstance(term, Integer):
        return (unify(args[1], term, exstate) and
                unify(args[2], Integer(0), exstate))
    if isinstance(term, Float):
        return (unify(args[1], term, exstate) and
                unify(args[2], Integer(0), exstate))
    if isinstance(term, Struct):
        return (unify(args[1], term.functor, exstate) and
                unify(args[2], Integer(term.arity), exstate))
    if isinstance(term, Cons):
        return (unify(args[1], Atom("."), exstate) and
                unify(args[2], Integer(2), exstate))

    return False


@register_builtin("arg", 3)
def builtin_arg(exstate: 'ExState', andb: 'AndBox', args: tuple[Term, ...]) -> bool:
    """arg/3 - Get argument of structure."""
    n = args[0].deref()
    term = args[1].deref()
    value = args[2]

    if not isinstance(n, Integer):
        return False

    idx = n.value

    # Handle lists (./2)
    if isinstance(term, Cons):
        if idx == 1:
            return unify(value, term.head, exstate)
        elif idx == 2:
            return unify(value, term.tail, exstate)
        else:
            return False

    if not isinstance(term, Struct):
        return False

    if idx < 1 or idx > term.arity:
        return False

    return unify(value, term.args[idx - 1], exstate)


@register_builtin("=..", 2)
def builtin_univ(exstate: 'ExState', andb: 'AndBox', args: tuple[Term, ...]) -> bool:
    """=../2 - Univ: convert between term and list."""
    term = args[0].deref()
    lst = args[1].deref()

    # Mode: +Term, -List
    if not isinstance(term, Var):
        if isinstance(term, Atom):
            return unify(args[1], make_list([term]), exstate)
        if isinstance(term, Integer):
            return unify(args[1], make_list([term]), exstate)
        if isinstance(term, Float):
            return unify(args[1], make_list([term]), exstate)
        if isinstance(term, Struct):
            elems = [term.functor] + list(term.args)
            return unify(args[1], make_list(elems), exstate)
        return False

    # Mode: -Term, +List
    if isinstance(lst, Cons):
        try:
            elems = list_to_python(lst)
            if not elems:
                return False
            functor = elems[0].deref()
            if len(elems) == 1:
                return unify(term, functor, exstate)
            if isinstance(functor, Atom):
                new_term = Struct(functor, tuple(elems[1:]))
                return unify(term, new_term, exstate)
        except ValueError:
            pass
    return False


@register_builtin("copy_term", 2)
def builtin_copy_term(exstate: 'ExState', andb: 'AndBox', args: tuple[Term, ...]) -> bool:
    """copy_term/2 - Copy term with fresh variables."""
    copy = copy_term_impl(args[0])
    return unify(args[1], copy, exstate)


# =============================================================================
# Type checking
# =============================================================================

@register_builtin("var", 1)
def builtin_var(exstate: 'ExState', andb: 'AndBox', args: tuple[Term, ...]) -> bool:
    """var/1 - Check if argument is an unbound variable."""
    return isinstance(args[0].deref(), Var)


@register_builtin("nonvar", 1)
def builtin_nonvar(exstate: 'ExState', andb: 'AndBox', args: tuple[Term, ...]) -> bool:
    """nonvar/1 - Check if argument is not an unbound variable."""
    return not isinstance(args[0].deref(), Var)


@register_builtin("data", 1)
def builtin_data(exstate: 'ExState', andb: 'AndBox', args: tuple[Term, ...]) -> bool:
    """data/1 - Check if argument has data (is not an unbound variable).

    In full AKL, this suspends if the argument is unbound.
    For now, we treat it as nonvar/1.
    """
    return not isinstance(args[0].deref(), Var)


@register_builtin("atom", 1)
def builtin_atom(exstate: 'ExState', andb: 'AndBox', args: tuple[Term, ...]) -> bool:
    """atom/1 - Check if argument is an atom."""
    term = args[0].deref()
    return isinstance(term, Atom) and term is not NIL


@register_builtin("number", 1)
def builtin_number(exstate: 'ExState', andb: 'AndBox', args: tuple[Term, ...]) -> bool:
    """number/1 - Check if argument is a number."""
    return isinstance(args[0].deref(), (Integer, Float))


@register_builtin("integer", 1)
def builtin_integer(exstate: 'ExState', andb: 'AndBox', args: tuple[Term, ...]) -> bool:
    """integer/1 - Check if argument is an integer."""
    return isinstance(args[0].deref(), Integer)


@register_builtin("float", 1)
def builtin_float(exstate: 'ExState', andb: 'AndBox', args: tuple[Term, ...]) -> bool:
    """float/1 - Check if argument is a float."""
    return isinstance(args[0].deref(), Float)


@register_builtin("compound", 1)
def builtin_compound(exstate: 'ExState', andb: 'AndBox', args: tuple[Term, ...]) -> bool:
    """compound/1 - Check if argument is a compound term."""
    term = args[0].deref()
    return isinstance(term, (Struct, Cons))


@register_builtin("is_list", 1)
def builtin_is_list(exstate: 'ExState', andb: 'AndBox', args: tuple[Term, ...]) -> bool:
    """is_list/1 - Check if argument is a proper list."""
    term = args[0].deref()
    while isinstance(term, Cons):
        term = term.tail.deref()
    return term is NIL


@register_builtin("atomic", 1)
def builtin_atomic(exstate: 'ExState', andb: 'AndBox', args: tuple[Term, ...]) -> bool:
    """atomic/1 - Check if argument is atomic (atom or number)."""
    return isinstance(args[0].deref(), (Atom, Integer, Float))


# =============================================================================
# List predicates
# =============================================================================

@register_builtin("length", 2)
def builtin_length(exstate: 'ExState', andb: 'AndBox', args: tuple[Term, ...]) -> bool:
    """length/2 - Get/check length of a list."""
    lst = args[0].deref()
    n = args[1].deref()

    # Mode: +List, ?N
    if isinstance(lst, Cons) or lst is NIL:
        length = 0
        current = lst
        while isinstance(current, Cons):
            length += 1
            current = current.tail.deref()
        if current is not NIL:
            return False  # Improper list
        return unify(args[1], Integer(length), exstate)

    return False


# =============================================================================
# Stream I/O - for qa.akl REPL
# =============================================================================

# Stream handles - use Python objects wrapped as terms
class StreamHandle(Term):
    """Wrapper for Python file objects as AKL terms."""
    __slots__ = ('stream', 'name')

    def __init__(self, stream, name: str) -> None:
        self.stream = stream
        self.name = name

    def deref(self) -> Term:
        return self

    def __repr__(self) -> str:
        return f"<stream:{self.name}>"


# Global stream handles
_stdin_handle = None
_stdout_handle = None


def _get_stdin() -> StreamHandle:
    global _stdin_handle
    if _stdin_handle is None:
        _stdin_handle = StreamHandle(sys.stdin, "stdin")
    return _stdin_handle


def _get_stdout() -> StreamHandle:
    global _stdout_handle
    if _stdout_handle is None:
        _stdout_handle = StreamHandle(sys.stdout, "stdout")
    return _stdout_handle


@register_builtin("stdin", 1)
def builtin_stdin(exstate: 'ExState', andb: 'AndBox', args: tuple[Term, ...]) -> bool:
    """stdin/1 - Get standard input stream."""
    return unify(args[0], _get_stdin(), exstate)


@register_builtin("stdout", 1)
def builtin_stdout(exstate: 'ExState', andb: 'AndBox', args: tuple[Term, ...]) -> bool:
    """stdout/1 - Get standard output stream."""
    return unify(args[0], _get_stdout(), exstate)


@register_builtin("fflush", 1)
def builtin_fflush(exstate: 'ExState', andb: 'AndBox', args: tuple[Term, ...]) -> bool:
    """fflush/1 - Flush a stream."""
    stream = args[0].deref()
    if isinstance(stream, StreamHandle):
        stream.stream.flush()
        return True
    return False


@register_builtin("getc", 2)
def builtin_getc(exstate: 'ExState', andb: 'AndBox', args: tuple[Term, ...]) -> bool:
    """getc/2 - Read a character from stream. getc(Stream, Char)."""
    stream = args[0].deref()
    if not isinstance(stream, StreamHandle):
        return False

    try:
        ch = stream.stream.read(1)
        if ch == '':
            # End of file
            return unify(args[1], Integer(-1), exstate)
        return unify(args[1], Integer(ord(ch)), exstate)
    except Exception:
        return unify(args[1], Integer(-1), exstate)


@register_builtin("read_term", 2)
def builtin_read_term(exstate: 'ExState', andb: 'AndBox', args: tuple[Term, ...]) -> bool:
    """read_term/2 - Read a term from stream. read_term(Stream, Result)."""
    from .parser import parse_term, ParseError

    stream = args[0].deref()
    if not isinstance(stream, StreamHandle):
        return False

    try:
        # Read until we get a complete term (ending with .)
        line = ""
        while True:
            ch = stream.stream.read(1)
            if ch == '':
                if line.strip():
                    # EOF with partial input
                    result = Struct(Atom("exception"), (Atom("end_of_file"),))
                    return unify(args[1], result, exstate)
                else:
                    result = Struct(Atom("exception"), (Atom("end_of_file"),))
                    return unify(args[1], result, exstate)
            line += ch
            if ch == '.':
                # Try to parse
                try:
                    term = parse_term(line[:-1])  # Remove trailing .
                    # Consume trailing whitespace up to and including newline
                    # This is important for interactive use where the user
                    # types "query." followed by Enter
                    while True:
                        next_ch = stream.stream.read(1)
                        if next_ch == '':
                            break  # EOF
                        if next_ch == '\n':
                            break  # Found newline, stop
                        if not next_ch.isspace():
                            # Non-whitespace found - we can't push back
                            # For now, this is a limitation
                            break
                    result = Struct(Atom("term"), (term,))
                    return unify(args[1], result, exstate)
                except ParseError:
                    # Might need more input (e.g., '.' inside a string)
                    continue
    except Exception as e:
        result = Struct(Atom("exception"), (Atom(str(e)),))
        return unify(args[1], result, exstate)


@register_builtin("format", 1)
def builtin_format_1(exstate: 'ExState', andb: 'AndBox', args: tuple[Term, ...]) -> bool:
    """format/1 - Formatted output with no arguments. format(Format)."""
    fmt = args[0].deref()

    if not isinstance(fmt, Atom):
        return False

    output = _format_string(fmt.name, [])
    print(output, end='')
    return True


@register_builtin("format", 2)
def builtin_format_2(exstate: 'ExState', andb: 'AndBox', args: tuple[Term, ...]) -> bool:
    """format/2 - Formatted output. format(Format, Args)."""
    # This is the simple version - format(FormatString, ArgList)
    # The -Out accumulator syntax is not yet supported
    fmt = args[0].deref()
    arg_list = args[1].deref()

    if not isinstance(fmt, Atom):
        return False

    # Parse format string and substitute arguments
    try:
        fmt_args = list_to_python(arg_list) if isinstance(arg_list, Cons) else []
    except ValueError:
        fmt_args = [arg_list] if arg_list is not NIL else []

    output = _format_string(fmt.name, fmt_args)
    print(output, end='')
    return True


def _format_string(fmt: str, args: list) -> str:
    """Format a string with Prolog-style format codes."""
    from .printer import print_term

    result = []
    arg_idx = 0
    i = 0
    while i < len(fmt):
        if fmt[i] == '~':
            i += 1
            if i >= len(fmt):
                result.append('~')
                break
            code = fmt[i]
            if code == 'w':
                # Write term - no quoting for atoms
                if arg_idx < len(args):
                    t = args[arg_idx].deref()
                    if isinstance(t, Atom):
                        result.append(t.name)  # No quoting
                    else:
                        result.append(print_term(t))
                    arg_idx += 1
            elif code == 'q':
                # Write term quoted
                if arg_idx < len(args):
                    result.append(print_term(args[arg_idx]))
                    arg_idx += 1
            elif code == 'n':
                # Newline
                result.append('\n')
            elif code == 'a':
                # Atom - always unquoted
                if arg_idx < len(args):
                    t = args[arg_idx].deref()
                    if isinstance(t, Atom):
                        result.append(t.name)
                    else:
                        result.append(print_term(t))
                    arg_idx += 1
            elif code == '~':
                result.append('~')
            else:
                result.append('~')
                result.append(code)
            i += 1
        else:
            result.append(fmt[i])
            i += 1
    return ''.join(result)


@register_builtin("fnl", 1)
def builtin_fnl(exstate: 'ExState', andb: 'AndBox', args: tuple[Term, ...]) -> bool:
    """fnl/1 - Write newline to stream."""
    stream = args[0].deref()
    if isinstance(stream, StreamHandle):
        stream.stream.write('\n')
        return True
    return False


# =============================================================================
# Reflection - for meta-level control of computations
# =============================================================================

@register_builtin("reflective_call", 3)
def builtin_reflective_call(exstate: 'ExState', andb: 'AndBox', args: tuple[Term, ...]) -> bool:
    """
    reflective_call(Refl, Goal, Stream) - Start a sub-computation.

    Creates a new execution state for Goal, runs until first result,
    and returns the result through Stream (a difference list).

    Results are one of:
    - solution(VarBindings) - Goal succeeded with bindings
    - suspended - Goal suspended (waiting on variables)
    - fail - Goal failed

    Refl is unified with a reflection object that can be used with
    reflective_next/2 to get more solutions.
    """
    from .term import Reflection
    from .interpreter import Interpreter

    refl_arg = args[0].deref()
    goal = args[1].deref()
    stream = args[2].deref()

    # refl_arg must be an unbound variable
    if not isinstance(refl_arg, Var):
        return False

    # goal must be a callable term
    if not isinstance(goal, (Atom, Struct)):
        return False

    # Create a new interpreter for the sub-computation
    program = akl_context.program
    if program is None:
        return False

    sub_interp = Interpreter(program)

    # The goal in qa.akl is qacall(Query) which calls the actual goal
    # and returns a variable dictionary. For now, we just run the goal directly.
    generator = sub_interp.solve(goal)

    # Create the reflection object with the stream
    reflection = Reflection(generator, sub_interp, stream)

    # Bind refl_arg to the reflection object
    if not unify(args[0], reflection, exstate):
        return False

    # Get the first result and add to stream
    return _advance_reflection(reflection, exstate)


@register_builtin("reflective_next", 2)
def builtin_reflective_next(exstate: 'ExState', andb: 'AndBox', args: tuple[Term, ...]) -> bool:
    """
    reflective_next(Refl, Refl1) - Continue a sub-computation.

    Advances the reflection to the next solution and adds the result
    to the stream. Refl1 is unified with the (possibly updated) reflection.
    """
    from .term import Reflection

    refl = args[0].deref()

    if not isinstance(refl, Reflection):
        return False

    if refl.exhausted:
        return False

    # Advance to next solution
    if not _advance_reflection(refl, exstate):
        return False

    # Unify Refl1 with Refl (they're the same object)
    return unify(args[1], refl, exstate)


@register_builtin("reflective_print", 2)
def builtin_reflective_print(exstate: 'ExState', andb: 'AndBox', args: tuple[Term, ...]) -> bool:
    """
    reflective_print(Refl, Refl1) - Print the state of a sub-computation.

    For debugging - prints the current state of the reflection.
    """
    from .term import Reflection

    refl = args[0].deref()

    if not isinstance(refl, Reflection):
        return False

    print(f"{{reflection state: exhausted={refl.exhausted}}}")

    return unify(args[1], refl, exstate)


@register_builtin("reflection", 1)
def builtin_reflection(exstate: 'ExState', andb: 'AndBox', args: tuple[Term, ...]) -> bool:
    """reflection/1 - Check if argument is a reflection object."""
    from .term import Reflection
    return isinstance(args[0].deref(), Reflection)


def _advance_reflection(refl: 'Reflection', exstate: 'ExState') -> bool:
    """
    Advance a reflection to the next solution.

    Adds the result to the reflection's stream as a difference list element.
    Returns True if successful, False if there's an error.
    """
    from .term import Reflection, Var, Cons

    if refl.exhausted:
        # No more solutions - add 'fail' to stream
        fail_term = Atom("fail")
        new_tail = Var()
        cons = Cons(fail_term, new_tail)

        stream_point = refl.stream.deref()
        if not unify(stream_point, cons, exstate):
            return False
        refl.stream = new_tail
        return True

    try:
        solution = next(refl.generator)

        # Build solution(VarBindings) term
        # VarBindings is a list of Name = Value pairs
        bindings_list = []
        for name, value in solution.bindings.items():
            pair = Struct(Atom("="), (Atom(name), value))
            bindings_list.append(pair)

        bindings_term = make_list(bindings_list)
        solution_term = Struct(Atom("solution"), (bindings_term,))

        # Add to stream as difference list
        new_tail = Var()
        cons = Cons(solution_term, new_tail)

        stream_point = refl.stream.deref()
        if not unify(stream_point, cons, exstate):
            return False
        refl.stream = new_tail
        return True

    except StopIteration:
        refl.exhausted = True

        # Add 'fail' to stream (no more solutions)
        fail_term = Atom("fail")
        new_tail = Var()
        cons = Cons(fail_term, new_tail)

        stream_point = refl.stream.deref()
        if not unify(stream_point, cons, exstate):
            return False
        refl.stream = new_tail
        return True


# =============================================================================
# Aggregation (numberof, bagof, etc.)
# =============================================================================

@register_builtin("numberof", 2)
def builtin_numberof(exstate: 'ExState', andb: 'AndBox', args: tuple[Term, ...]) -> bool:
    """numberof/2 - Count the number of solutions.

    numberof(Template\\Goal, Count) - counts solutions to Goal.
    The Template\\Goal syntax uses \\ as lambda operator.

    Example: numberof(X\\member(X, [1,2,3]), N) binds N to 3.
    """
    from .interpreter import Interpreter
    from .unify import copy_term

    lambda_term = args[0].deref()

    # Parse Template\Goal syntax - the \ operator creates a Struct with functor \
    if isinstance(lambda_term, Struct) and lambda_term.functor.name == "\\" and lambda_term.arity == 2:
        # Template is first arg, Goal is second arg
        goal = lambda_term.args[1].deref()
    else:
        # Assume the whole thing is the goal (no template variable)
        goal = lambda_term

    if not isinstance(goal, (Atom, Struct)):
        return False

    # Get program from context
    program = akl_context.program
    if program is None:
        return False

    # Create a fresh copy of the goal for each solution search
    goal_copy = copy_term(goal)

    # Create a sub-interpreter to find all solutions
    sub_interp = Interpreter(program)
    solutions = sub_interp.solve_all(goal_copy)
    count = len(solutions)

    return unify(args[1], Integer(count), exstate)


# =============================================================================
# Ports (streams)
# =============================================================================

@register_builtin("open_port", 2)
def builtin_open_port(exstate: 'ExState', andb: 'AndBox', args: tuple[Term, ...]) -> bool:
    """open_port/2 - Create a port/stream pair.

    open_port(Port, Stream) creates a new port and unifies:
    - Port: The port object (for sending messages)
    - Stream: A stream (list) that will receive sent messages

    The stream grows as messages are sent to the port.
    When all references to the port are gone, the stream is
    terminated with [] (empty list).
    """
    port = Port()
    # The stream starts as an unbound variable (the initial tail)
    # We need to capture this BEFORE any sends happen
    initial_stream = port.stream

    # Unify Port argument with the port object
    if not unify(args[0], port, exstate):
        return False

    # Unify Stream argument with the initial stream variable
    if not unify(args[1], initial_stream, exstate):
        return False

    return True


@register_builtin("send", 2)
def builtin_send_2(exstate: 'ExState', andb: 'AndBox', args: tuple[Term, ...]) -> bool:
    """send/2 - Send a message to a port.

    send(Message, Port) sends Message to Port.
    The message appears on the port's stream immediately.

    Fails if Port is not a port or if the port is closed.
    """
    message = args[0].deref()
    port = args[1].deref()

    if not isinstance(port, Port):
        return False

    return port.send(message)


@register_builtin("send", 3)
def builtin_send_3(exstate: 'ExState', andb: 'AndBox', args: tuple[Term, ...]) -> bool:
    """send/3 - Send a message to a port with sequencing.

    send(Message, Port, Port2) sends Message to Port and unifies
    Port2 with Port (for sequencing sends in deterministic code).

    This form allows chaining: send(M1, P, P1), send(M2, P1, P2), ...
    """
    message = args[0].deref()
    port = args[1].deref()

    if not isinstance(port, Port):
        return False

    if not port.send(message):
        return False

    # Unify Port2 with Port (they're the same port)
    return unify(args[2], port, exstate)


# =============================================================================
# Statistics
# =============================================================================

@register_builtin("statistics", 2)
def builtin_statistics(exstate: 'ExState', andb: 'AndBox', args: tuple[Term, ...]) -> bool:
    """statistics/2 - Get runtime statistics.

    statistics(runtime, [Total, SinceLast]) - Time in milliseconds
    statistics(nondet, [Total, SinceLast]) - Nondeterministic steps

    When called with an unbound second argument, resets the "since last" counter.
    """
    key = args[0].deref()
    value = args[1].deref()

    if not isinstance(key, Atom):
        return False

    now = time.time()

    if key.name == "runtime":
        total_ms = int((now - akl_context._start_time) * 1000)
        since_last_ms = int((now - akl_context._last_runtime_call) * 1000)

        # Update last call time
        akl_context._last_runtime_call = now

        # If value is unbound variable, just reset (succeed without binding list)
        if isinstance(value, Var):
            return True

        # Otherwise unify with [Total, SinceLast]
        result = make_list([Integer(total_ms), Integer(since_last_ms)])
        return unify(args[1], result, exstate)

    elif key.name == "nondet":
        total = akl_context._total_nondet
        since_last = total - akl_context._last_nondet_call

        # Update last call count
        akl_context._last_nondet_call = total

        # If value is unbound variable, just reset (succeed without binding list)
        if isinstance(value, Var):
            return True

        # Otherwise unify with [Total, SinceLast]
        result = make_list([Integer(total), Integer(since_last)])
        return unify(args[1], result, exstate)

    return False


# =============================================================================
# Utilities
# =============================================================================

def list_builtins() -> list[tuple[str, int]]:
    """Get list of all registered built-ins."""
    return sorted(_BUILTINS.keys())
