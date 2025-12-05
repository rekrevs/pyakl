"""
Printer for AKL terms.

Converts Term objects back to valid AKL syntax with proper operator
notation and precedence-based parenthesization.

Based on Richard O'Keefe's write.pl, adapted for AKL by Sverker Janson.
"""

from __future__ import annotations
from typing import TYPE_CHECKING

from .term import Term, Var, Atom, Integer, Float, Struct, Cons, NIL
from .parser import OPERATORS, PREFIX_OPS

if TYPE_CHECKING:
    pass


def needs_quoting(name: str) -> bool:
    """
    Check if an atom name needs to be quoted.

    An atom needs quoting if it:
    - Is empty
    - Starts with uppercase or digit
    - Contains characters outside [a-z][A-Za-z0-9_]*
    - Is not a valid operator sequence
    - Contains spaces or special characters
    """
    if not name:
        return True

    # Special atoms that don't need quoting
    if name in ('[]', '{}', '!', ';'):
        return False

    # Check if it's a valid simple atom: [a-z][A-Za-z0-9_]*
    if name[0].islower() and all(c.isalnum() or c == '_' for c in name):
        return False

    # Check if it's a valid operator sequence
    operator_chars = set('+-*/\\^<>=`~:.?@#$&|')
    if all(c in operator_chars for c in name):
        # But not if it starts with /* (comment)
        if not name.startswith('/*'):
            return False

    return True


def quote_atom(name: str) -> str:
    """Quote an atom name, escaping embedded quotes."""
    escaped = name.replace("'", "''")
    return f"'{escaped}'"


def print_term(term: Term, *, deref: bool = True) -> str:
    """
    Convert a Term to AKL syntax string.

    Args:
        term: The term to print
        deref: If True, follow variable bindings (default True)

    Returns:
        String representation in AKL syntax
    """
    return _write_out(term, priority=1200, deref=deref)


def _write_out(term: Term, priority: int, deref: bool) -> str:
    """
    Write out a term in a context of given priority.

    Operators with greater priority than the context need parentheses.
    """
    if deref:
        term = term.deref()

    if isinstance(term, Var):
        return term.name

    if isinstance(term, Atom):
        name = term.name
        # Check if atom is an operator with priority > context
        if name in OPERATORS:
            op_prec, _ = OPERATORS[name]
            if op_prec > priority:
                # Need to quote or parenthesize
                if needs_quoting(name):
                    return quote_atom(name)
                return f"({name})"
        if needs_quoting(name):
            return quote_atom(name)
        return name

    if isinstance(term, Integer):
        return str(term.value)

    if isinstance(term, Float):
        s = str(term.value)
        if '.' not in s and 'e' not in s.lower():
            s += '.0'
        return s

    if isinstance(term, Cons):
        return _write_list(term, deref=deref)

    if isinstance(term, Struct):
        return _write_struct(term, priority, deref)

    # Fallback
    return repr(term)


def _write_struct(term: Struct, priority: int, deref: bool) -> str:
    """Write a structure, using operator notation where applicable."""
    functor = term.functor
    if not isinstance(functor, Atom):
        # Non-atom functor - use canonical form
        functor_str = _write_out(functor, 1200, deref)
        args_str = ', '.join(_write_out(a, 999, deref) for a in term.args)
        return f"{functor_str}({args_str})"

    name = functor.name
    arity = term.arity

    # Check for curly braces: {}(X) -> {X}
    if name == '{}' and arity == 1:
        inner = _write_out(term.args[0], 1200, deref)
        return '{' + inner + '}'

    # Check for list cons: '.'(H, T) -> handled by Cons type
    # (In case someone constructs it manually as Struct)
    if name == '.' and arity == 2:
        # Convert to list notation
        return _write_dotlist(term, deref)

    # Check for binary operators
    if arity == 2 and name in OPERATORS:
        op_prec, assoc = OPERATORS[name]
        return _write_infix(term, name, op_prec, assoc, priority, deref)

    # Check for prefix operators
    if arity == 1 and name in PREFIX_OPS:
        op_prec, assoc = PREFIX_OPS[name]
        return _write_prefix(term, name, op_prec, assoc, priority, deref)

    # Check for postfix operators
    if arity == 1 and name in OPERATORS:
        op_prec, assoc = OPERATORS[name]
        if assoc in ('xf', 'yf'):
            return _write_postfix(term, name, op_prec, assoc, priority, deref)

    # Canonical form: functor(args)
    functor_str = _write_atom(name)
    if arity == 0:
        return f"{functor_str}()"
    args_str = ', '.join(_write_out(a, 999, deref) for a in term.args)
    return f"{functor_str}({args_str})"


def _write_atom(name: str) -> str:
    """Write an atom, quoting if necessary."""
    if needs_quoting(name):
        return quote_atom(name)
    return name


def _write_infix(term: Struct, op: str, op_prec: int, assoc: str,
                 priority: int, deref: bool) -> str:
    """Write an infix operator expression."""
    # Determine argument priorities based on associativity
    # xfx: both args must be strictly lower (P-1)
    # xfy: left must be strictly lower, right can be equal
    # yfx: left can be equal, right must be strictly lower
    if assoc == 'xfx':
        left_prec = op_prec - 1
        right_prec = op_prec - 1
    elif assoc == 'xfy':
        left_prec = op_prec - 1
        right_prec = op_prec
    elif assoc == 'yfx':
        left_prec = op_prec
        right_prec = op_prec - 1
    else:
        # Fallback
        left_prec = op_prec - 1
        right_prec = op_prec - 1

    left = _write_out(term.args[0], left_prec, deref)
    right = _write_out(term.args[1], right_prec, deref)

    # Add spaces around operator (except for comma which is tight on left)
    if op == ',':
        result = f"{left}, {right}"
    elif op_prec >= 700:
        # Higher precedence operators get spaces
        result = f"{left} {op} {right}"
    else:
        # Tighter operators (arithmetic) - spaces for clarity
        result = f"{left} {op} {right}"

    # Parenthesize if needed
    if op_prec > priority:
        return f"({result})"
    return result


def _write_prefix(term: Struct, op: str, op_prec: int, assoc: str,
                  priority: int, deref: bool) -> str:
    """Write a prefix operator expression."""
    # fx: arg must be strictly lower
    # fy: arg can be equal
    if assoc == 'fx':
        arg_prec = op_prec - 1
    else:  # fy
        arg_prec = op_prec

    arg = _write_out(term.args[0], arg_prec, deref)

    # Special case: negative numbers look nicer without space
    if op == '-' and arg and arg[0].isdigit():
        result = f"-{arg}"
    else:
        result = f"{op} {arg}"

    if op_prec > priority:
        return f"({result})"
    return result


def _write_postfix(term: Struct, op: str, op_prec: int, assoc: str,
                   priority: int, deref: bool) -> str:
    """Write a postfix operator expression."""
    # xf: arg must be strictly lower
    # yf: arg can be equal
    if assoc == 'xf':
        arg_prec = op_prec - 1
    else:  # yf
        arg_prec = op_prec

    arg = _write_out(term.args[0], arg_prec, deref)
    result = f"{arg} {op}"

    if op_prec > priority:
        return f"({result})"
    return result


def _write_list(lst: Term, *, deref: bool) -> str:
    """
    Print a list in AKL list notation.
    Handles proper lists [a, b, c] and improper lists [a, b | T].
    """
    if deref:
        lst = lst.deref()

    if lst is NIL:
        return '[]'

    elements: list[str] = []
    current = lst

    while isinstance(current, Cons):
        elements.append(_write_out(current.head, 999, deref))
        current = current.tail
        if deref:
            current = current.deref()

    if current is NIL:
        return '[' + ', '.join(elements) + ']'
    else:
        tail_str = _write_out(current, 999, deref)
        return '[' + ', '.join(elements) + ' | ' + tail_str + ']'


def _write_dotlist(term: Struct, deref: bool) -> str:
    """Write a .(H, T) structure as list notation."""
    elements: list[str] = []
    current: Term = term

    while isinstance(current, Struct) and current.functor == Atom('.') and current.arity == 2:
        elements.append(_write_out(current.args[0], 999, deref))
        current = current.args[1]
        if deref:
            current = current.deref()

    if current == NIL or (isinstance(current, Atom) and current.name == '[]'):
        return '[' + ', '.join(elements) + ']'
    else:
        tail_str = _write_out(current, 999, deref)
        return '[' + ', '.join(elements) + ' | ' + tail_str + ']'


# Legacy function for compatibility
def print_clause(head: Term, body: list[Term] | None = None, *,
                 guard: list[Term] | None = None,
                 guard_op: str = ':-') -> str:
    """
    Print an AKL clause (legacy interface).

    For new code, prefer constructing the clause as a term and using print_term.
    """
    head_str = print_term(head)

    if body is None and guard is None:
        return head_str

    parts = [head_str]

    if guard:
        guard_str = ', '.join(print_term(g) for g in guard)
        if guard_op == ':-':
            parts.append(' :- ')
            parts.append(guard_str)
        else:
            parts.append(' :- ')
            parts.append(guard_str)
            parts.append(f' {guard_op} ')
    elif body:
        parts.append(' :- ')

    if body:
        body_str = ', '.join(print_term(g) for g in body)
        if guard:
            parts.append(body_str)
        else:
            parts.append(body_str)

    return ''.join(parts)
