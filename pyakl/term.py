"""
Term representation for PyAKL.

This module implements the fundamental data structures for AKL terms:
- Var: Logic variables with identity
- Atom: Named constants (interned)
- Integer, Float: Numeric constants
- Struct: Compound terms (functor + args)
- Cons, NIL: List cells

Key design decisions:
- Variables use object identity (Python's `is`), not name equality
- Atoms are interned for efficient comparison
- All terms implement deref() to follow variable bindings
"""

from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Optional, TYPE_CHECKING
import weakref

if TYPE_CHECKING:
    from typing import List as TypingList


class Term(ABC):
    """
    Base class for all AKL terms.

    All terms must implement deref() which follows variable bindings
    to get the actual value.
    """

    __slots__ = ()

    @abstractmethod
    def deref(self) -> Term:
        """Follow variable bindings to get actual value."""
        pass


class Var(Term):
    """
    Logic variable with identity.

    Two Var instances are the same variable if and only if they are
    the same Python object (identity via `is`). The name is purely
    for display purposes.

    Attributes:
        name: Display name for the variable
        binding: The term this variable is bound to, or None if unbound
    """

    __slots__ = ('name', 'binding', '_id')

    _counter: int = 0

    def __init__(self, name: Optional[str] = None) -> None:
        if name is None:
            Var._counter += 1
            name = f"_G{Var._counter}"
        self.name = name
        self.binding: Optional[Term] = None
        # Unique ID for debugging (not used for identity)
        Var._counter += 1
        self._id = Var._counter

    def is_bound(self) -> bool:
        """Check if this variable is bound to a term."""
        return self.binding is not None

    def deref(self) -> Term:
        """Follow binding chain to get actual value."""
        if self.binding is None:
            return self
        return self.binding.deref()

    def bind(self, term: Term) -> None:
        """
        Bind this variable to a term.

        Raises:
            AssertionError: If variable is already bound
        """
        assert self.binding is None, f"Cannot rebind variable {self.name}"
        self.binding = term

    def unbind(self) -> None:
        """Unbind this variable (for backtracking)."""
        self.binding = None

    def __repr__(self) -> str:
        if self.binding is not None:
            return f"{self.name}={self.binding.deref()!r}"
        return self.name

    def __str__(self) -> str:
        if self.binding is not None:
            return str(self.binding.deref())
        return self.name


# Atom interning table
_atom_table: dict[str, Atom] = {}


class Atom(Term):
    """
    Named constant (symbol).

    Atoms are interned: Atom("foo") is Atom("foo") (same object).
    This allows efficient comparison via identity.

    Attributes:
        name: The atom's name
    """

    __slots__ = ('name',)

    name: str

    def __new__(cls, name: str) -> Atom:
        """Create or return existing interned atom."""
        if name in _atom_table:
            return _atom_table[name]
        instance = super().__new__(cls)
        instance.name = name
        _atom_table[name] = instance
        return instance

    def deref(self) -> Term:
        return self

    def __repr__(self) -> str:
        # Quote if needed (contains spaces, starts with uppercase, etc.)
        if not self.name:
            return "''"
        # Special case for [] (empty list)
        if self.name == "[]":
            return "[]"
        if self.name[0].isupper() or ' ' in self.name or not self.name[0].isalpha():
            if "'" not in self.name:
                return f"'{self.name}'"
        return self.name

    def __str__(self) -> str:
        return self.name

    def __hash__(self) -> int:
        return hash(self.name)

    def __eq__(self, other: object) -> bool:
        # Due to interning, atoms with same name are same object
        # But we also support comparison with non-Atom for convenience
        if isinstance(other, Atom):
            return self is other
        return False


class Integer(Term):
    """
    Integer constant.

    Attributes:
        value: The integer value
    """

    __slots__ = ('value',)

    def __init__(self, value: int) -> None:
        self.value = value

    def deref(self) -> Term:
        return self

    def __repr__(self) -> str:
        return str(self.value)

    def __str__(self) -> str:
        return str(self.value)

    def __eq__(self, other: object) -> bool:
        if isinstance(other, Integer):
            return self.value == other.value
        return False

    def __hash__(self) -> int:
        return hash(self.value)


class Float(Term):
    """
    Floating-point constant.

    Attributes:
        value: The float value
    """

    __slots__ = ('value',)

    def __init__(self, value: float) -> None:
        self.value = value

    def deref(self) -> Term:
        return self

    def __repr__(self) -> str:
        return str(self.value)

    def __str__(self) -> str:
        return str(self.value)

    def __eq__(self, other: object) -> bool:
        if isinstance(other, Float):
            return self.value == other.value
        return False

    def __hash__(self) -> int:
        return hash(self.value)


class Struct(Term):
    """
    Compound term: functor(arg1, arg2, ..., argN).

    Attributes:
        functor: The functor (an Atom)
        args: Tuple of argument terms
    """

    __slots__ = ('functor', 'args')

    def __init__(self, functor: Atom, args: tuple[Term, ...]) -> None:
        self.functor = functor
        self.args = args

    @property
    def arity(self) -> int:
        """Number of arguments."""
        return len(self.args)

    def deref(self) -> Term:
        return self

    def __repr__(self) -> str:
        if not self.args:
            return f"{self.functor!r}()"
        args_str = ", ".join(repr(a.deref()) for a in self.args)
        return f"{self.functor!r}({args_str})"

    def __str__(self) -> str:
        if not self.args:
            return f"{self.functor}()"
        args_str = ", ".join(str(a.deref()) for a in self.args)
        return f"{self.functor}({args_str})"

    def __eq__(self, other: object) -> bool:
        if isinstance(other, Struct):
            if self.functor != other.functor or self.arity != other.arity:
                return False
            return all(a.deref() == b.deref() for a, b in zip(self.args, other.args))
        return False


class Cons(Term):
    """
    List cell: [Head|Tail].

    Represents a non-empty list with a head element and a tail.
    The tail is typically another Cons or NIL.

    Attributes:
        head: The first element
        tail: The rest of the list
    """

    __slots__ = ('head', 'tail')

    def __init__(self, head: Term, tail: Term) -> None:
        self.head = head
        self.tail = tail

    def deref(self) -> Term:
        return self

    def __repr__(self) -> str:
        """Pretty-print as [a, b, c] or [a, b | T]."""
        elements: TypingList[str] = []
        current: Term = self
        while isinstance(current, Cons):
            elements.append(repr(current.head.deref()))
            current = current.tail.deref()

        if current is NIL:
            return f"[{', '.join(elements)}]"
        else:
            return f"[{', '.join(elements)} | {current!r}]"

    def __str__(self) -> str:
        """Pretty-print as [a, b, c] or [a, b | T]."""
        elements: TypingList[str] = []
        current: Term = self
        while isinstance(current, Cons):
            elements.append(str(current.head.deref()))
            current = current.tail.deref()

        if current is NIL:
            return f"[{', '.join(elements)}]"
        else:
            return f"[{', '.join(elements)} | {current}]"

    def __eq__(self, other: object) -> bool:
        if isinstance(other, Cons):
            return (self.head.deref() == other.head.deref() and
                    self.tail.deref() == other.tail.deref())
        return False


# The empty list atom - interned singleton
NIL = Atom("[]")


class Reflection(Term):
    """
    Reflection object for controlling sub-computations.

    Wraps a generator that produces solutions, allowing the computation
    to be paused and resumed via reflective_call/3 and reflective_next/2.

    This corresponds to the 'reflection' type in the C implementation
    (akl-agents/emulator/reflection.c).
    """

    __slots__ = ('generator', 'interpreter', 'stream', 'exhausted', '_id')

    _counter: int = 0

    def __init__(self, generator, interpreter, stream: Term) -> None:
        """
        Create a reflection object.

        Args:
            generator: The solution generator from interpreter.solve()
            interpreter: The Interpreter instance running the sub-computation
            stream: The stream (difference list) for results
        """
        from typing import Generator
        Reflection._counter += 1
        self._id = Reflection._counter
        self.generator = generator
        self.interpreter = interpreter
        self.stream = stream
        self.exhausted = False

    def deref(self) -> Term:
        return self

    def __repr__(self) -> str:
        return f"{{reflection: {self._id}}}"

    def __str__(self) -> str:
        return repr(self)


class _PortState:
    """
    Holder for port state that survives the port itself.

    This allows the finalizer to access the current stream tail
    at the time the port is garbage collected.
    """
    __slots__ = ('initial_stream', 'stream_tail', 'closed')

    def __init__(self, initial_tail: Var) -> None:
        self.initial_stream = initial_tail  # Never changes - for open_port/2
        self.stream_tail = initial_tail     # Updated on each send
        self.closed = False


class Port(Term):
    """
    AKL port for multi-sender communication.

    A port provides a communication channel where multiple senders can
    send messages that appear on a shared stream. The key feature is
    automatic closure: when no more references to the port exist, the
    stream is terminated with NIL.

    This uses Python's weakref.finalize() to detect when the port
    becomes unreachable and close the stream.

    Attributes:
        _state: Shared state object holding current stream tail
        _id: Unique identifier for debugging
    """

    __slots__ = ('_state', '_id', '_finalizer', '__weakref__')

    _counter: int = 0

    def __init__(self) -> None:
        """Create a new port with an unbound stream tail."""
        Port._counter += 1
        self._id = Port._counter

        # Create state holder with initial stream tail
        self._state = _PortState(Var(f"_Stream{self._id}"))

        # Register finalizer to close stream when port is garbage collected.
        # We pass the _state object which holds the current tail.
        # When the port dies, the callback can access the current tail.
        self._finalizer = weakref.finalize(
            self, Port._do_close, self._state
        )

    @staticmethod
    def _do_close(state: _PortState) -> None:
        """
        Called when port has no more references.

        Binds the stream tail to NIL to signal end of stream.
        """
        if state.closed:
            return
        state.closed = True

        # Only close if stream tail is still unbound
        tail = state.stream_tail.deref()
        if isinstance(tail, Var) and tail.binding is None:
            tail.binding = NIL

    @property
    def stream(self) -> Var:
        """Get the initial stream variable (head of stream)."""
        return self._state.initial_stream

    def send(self, message: Term) -> bool:
        """
        Send a message to this port.

        The message appears on the stream immediately.

        Args:
            message: The term to send

        Returns:
            True if successful, False if port is closed
        """
        if self._state.closed:
            return False

        # Get current stream tail
        tail = self._state.stream_tail.deref()

        # If tail is already bound to NIL, port is closed
        if tail is NIL:
            self._state.closed = True
            return False

        # If tail is not a variable, something is wrong
        if not isinstance(tail, Var):
            return False

        # Create new cons cell: [message | NewTail]
        new_tail = Var(f"_Stream{self._id}")
        cons = Cons(message, new_tail)

        # Bind old tail to the cons cell (extends the stream)
        tail.binding = cons

        # Update state to point to the new tail
        self._state.stream_tail = new_tail

        return True

    def close(self) -> None:
        """Explicitly close the port."""
        Port._do_close(self._state)

    def deref(self) -> Term:
        return self

    def __repr__(self) -> str:
        status = "closed" if self._state.closed else "open"
        return f"{{port:{self._id}:{status}}}"

    def __str__(self) -> str:
        return repr(self)


def make_list(elements: TypingList[Term], tail: Term = NIL) -> Term:
    """
    Build a list from Python list of terms.

    Args:
        elements: List of terms to include
        tail: The tail of the list (default: NIL for proper list)

    Returns:
        A Cons chain ending in tail, or tail if elements is empty

    Example:
        make_list([Integer(1), Integer(2)]) -> [1, 2]
        make_list([Integer(1)], Var("T")) -> [1 | T]
    """
    result = tail
    for elem in reversed(elements):
        result = Cons(elem, result)
    return result


def list_to_python(term: Term) -> TypingList[Term]:
    """
    Convert an AKL list to a Python list.

    Args:
        term: A proper list (Cons chain ending in NIL)

    Returns:
        Python list of the elements

    Raises:
        ValueError: If term is not a proper list
    """
    result: TypingList[Term] = []
    current = term.deref()
    while isinstance(current, Cons):
        result.append(current.head.deref())
        current = current.tail.deref()

    if current is not NIL:
        raise ValueError(f"Not a proper list: tail is {current!r}")

    return result
