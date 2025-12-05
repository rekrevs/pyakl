# PyAKL Architecture

**Date:** December 2025
**Status:** Draft
**Purpose:** Detailed technical architecture for PyAKL implementation

---

## Overview

PyAKL implements AKL semantics through direct interpretation of syntax trees represented as AKL terms. This document describes the key data structures, algorithms, and module organization.

---

## Module Structure

```
pyakl/
├── __init__.py
├── term.py          # Term representation (Var, Atom, Struct, etc.)
├── unify.py         # Unification algorithm
├── parser.py        # AKL syntax parser
├── printer.py       # Term pretty-printing
├── box.py           # And-box and choice-box structures
├── engine.py        # Execution engine / scheduler
├── builtin.py       # Built-in predicates
├── constraint.py    # Constraint store (equality, FD)
└── main.py          # REPL and entry point

tests/
├── test_term.py
├── test_unify.py
├── test_parser.py
└── test_engine.py
```

---

## Term Representation (`term.py`)

### Base Class

```python
from abc import ABC, abstractmethod
from typing import Any, Optional
from dataclasses import dataclass

class Term(ABC):
    """Base class for all AKL terms."""

    @abstractmethod
    def deref(self) -> 'Term':
        """Follow variable bindings to get actual value."""
        return self
```

### Variables

```python
class Var(Term):
    """
    Logic variable with identity.

    Two Var instances are the same variable iff they are the same object
    (Python identity). The name is for display purposes only.
    """
    _counter = 0

    def __init__(self, name: Optional[str] = None):
        if name is None:
            Var._counter += 1
            name = f"_G{Var._counter}"
        self.name = name
        self.binding: Optional[Term] = None  # None = unbound
        self.suspensions: list['AndBox'] = []  # And-boxes suspended on this var
        self.env: Optional['AndBox'] = None    # And-box where created (for locality)

    def is_bound(self) -> bool:
        return self.binding is not None

    def deref(self) -> Term:
        """Follow binding chain."""
        if self.binding is None:
            return self
        return self.binding.deref()

    def bind(self, term: Term) -> None:
        """Bind this variable to a term."""
        assert self.binding is None, "Cannot rebind variable"
        self.binding = term
        # Wake suspended and-boxes
        for box in self.suspensions:
            box.wake()
        self.suspensions.clear()

    def __repr__(self):
        if self.binding is not None:
            return f"{self.name}={self.binding!r}"
        return self.name
```

### Atoms

```python
# Atom interning for efficiency
_atom_table: dict[str, 'Atom'] = {}

@dataclass(frozen=True)
class Atom(Term):
    """
    Named constant (symbol).

    Atoms are interned: Atom("foo") is Atom("foo").
    """
    name: str

    def __new__(cls, name: str):
        if name in _atom_table:
            return _atom_table[name]
        instance = super().__new__(cls)
        _atom_table[name] = instance
        return instance

    def deref(self) -> Term:
        return self

    def __repr__(self):
        return self.name
```

### Numbers

```python
@dataclass(frozen=True)
class Integer(Term):
    """Integer constant."""
    value: int

    def deref(self) -> Term:
        return self

    def __repr__(self):
        return str(self.value)

@dataclass(frozen=True)
class Float(Term):
    """Floating-point constant."""
    value: float

    def deref(self) -> Term:
        return self

    def __repr__(self):
        return str(self.value)
```

### Structures

```python
@dataclass
class Struct(Term):
    """
    Compound term: functor(arg1, arg2, ..., argN)

    The functor is an Atom, args is a tuple of Terms.
    """
    functor: Atom
    args: tuple[Term, ...]

    def deref(self) -> Term:
        return self

    @property
    def arity(self) -> int:
        return len(self.args)

    def __repr__(self):
        if not self.args:
            return f"{self.functor}()"
        args_str = ", ".join(repr(a.deref()) for a in self.args)
        return f"{self.functor}({args_str})"
```

### Lists

```python
# Special atoms for lists
NIL = Atom("[]")

class Cons(Term):
    """
    List cell: [Head|Tail]

    Represented as a special structure for efficiency and clarity.
    """
    def __init__(self, head: Term, tail: Term):
        self.head = head
        self.tail = tail

    def deref(self) -> Term:
        return self

    def __repr__(self):
        """Pretty-print as [a, b, c] or [a, b | T]."""
        elements = []
        current = self
        while isinstance(current, Cons):
            elements.append(repr(current.head.deref()))
            current = current.tail.deref()

        if current == NIL:
            return f"[{', '.join(elements)}]"
        else:
            return f"[{', '.join(elements)} | {current!r}]"

def make_list(elements: list[Term], tail: Term = NIL) -> Term:
    """Build a list from Python list."""
    result = tail
    for elem in reversed(elements):
        result = Cons(elem, result)
    return result
```

---

## Unification (`unify.py`)

### Algorithm

```python
from typing import Optional
from .term import Term, Var, Atom, Integer, Float, Struct, Cons, NIL

class UnificationError(Exception):
    """Raised when unification fails."""
    pass

def unify(t1: Term, t2: Term, occurs_check: bool = True) -> bool:
    """
    Unify two terms, binding variables as needed.

    Returns True if unification succeeds, False otherwise.
    Side effect: variables may be bound.

    Args:
        t1, t2: Terms to unify
        occurs_check: If True, fail on circular bindings (X = f(X))
    """
    t1 = t1.deref()
    t2 = t2.deref()

    # Same object (includes same variable)
    if t1 is t2:
        return True

    # Variable cases
    if isinstance(t1, Var):
        if occurs_check and occurs_in(t1, t2):
            return False
        t1.bind(t2)
        return True

    if isinstance(t2, Var):
        if occurs_check and occurs_in(t2, t1):
            return False
        t2.bind(t1)
        return True

    # Atom equality
    if isinstance(t1, Atom) and isinstance(t2, Atom):
        return t1 is t2  # Interned, so identity = equality

    # Number equality
    if isinstance(t1, Integer) and isinstance(t2, Integer):
        return t1.value == t2.value

    if isinstance(t1, Float) and isinstance(t2, Float):
        return t1.value == t2.value

    # List unification
    if isinstance(t1, Cons) and isinstance(t2, Cons):
        return unify(t1.head, t2.head, occurs_check) and \
               unify(t1.tail, t2.tail, occurs_check)

    # Structure unification
    if isinstance(t1, Struct) and isinstance(t2, Struct):
        if t1.functor != t2.functor or t1.arity != t2.arity:
            return False
        for a1, a2 in zip(t1.args, t2.args):
            if not unify(a1, a2, occurs_check):
                return False
        return True

    # Type mismatch
    return False

def occurs_in(var: Var, term: Term) -> bool:
    """Check if var occurs in term (for occurs check)."""
    term = term.deref()

    if term is var:
        return True

    if isinstance(term, Struct):
        return any(occurs_in(var, arg) for arg in term.args)

    if isinstance(term, Cons):
        return occurs_in(var, term.head) or occurs_in(var, term.tail)

    return False
```

---

## Execution Boxes (`box.py`)

### And-Box

```python
from enum import Enum, auto
from typing import Optional, List
from dataclasses import dataclass, field
from .term import Term, Var

class AndBoxState(Enum):
    ACTIVE = auto()      # Currently being executed
    SUSPENDED = auto()   # Waiting for variable binding
    SOLVED = auto()      # Guard completed successfully
    FAILED = auto()      # Failed
    DEAD = auto()        # Removed by pruning

@dataclass
class AndBox:
    """
    And-box: represents a guard + body of a clause.

    From internals.tex: "An and-box contains the state of the guard computation,
    stability information, constraints, a sequence of choice-boxes,
    and-continuations and a reference to its parent choice-box."
    """
    parent: Optional['ChoiceBox']

    # State
    state: AndBoxState = AndBoxState.ACTIVE

    # Local variables created in this and-box
    local_vars: list[Var] = field(default_factory=list)

    # Goals remaining to execute (the "and-continuation")
    goals: list[Term] = field(default_factory=list)

    # Child choice-boxes created during guard execution
    children: list['ChoiceBox'] = field(default_factory=list)

    # Constraints on external variables (bindings to propagate)
    constraints: list[tuple[Var, Term]] = field(default_factory=list)

    # Stability: count of constraints on external variables in subtree
    stability_count: int = 0

    # Guard operator: 'wait', 'commit', or 'cut'
    guard_op: str = 'wait'

    # Body goals (after guard succeeds)
    body: list[Term] = field(default_factory=list)

    def is_stable(self) -> bool:
        """And-box is stable if no external constraints pending."""
        return self.stability_count == 0 and not self.goals

    def is_solved(self) -> bool:
        """And-box is solved if guard completed and no pending goals."""
        return self.state == AndBoxState.SOLVED

    def is_quiet(self) -> bool:
        """And-box is quiet if no constraints on external variables."""
        return len(self.constraints) == 0

    def add_local_var(self, var: Var) -> None:
        """Register a variable as local to this and-box."""
        var.env = self
        self.local_vars.append(var)

    def is_local(self, var: Var) -> bool:
        """Check if variable is local to this and-box."""
        return var.env is self

    def suspend_on(self, var: Var) -> None:
        """Suspend this and-box waiting for var to be bound."""
        self.state = AndBoxState.SUSPENDED
        var.suspensions.append(self)

    def wake(self) -> None:
        """Wake up suspended and-box."""
        if self.state == AndBoxState.SUSPENDED:
            self.state = AndBoxState.ACTIVE

    def fail(self) -> None:
        """Mark this and-box as failed."""
        self.state = AndBoxState.FAILED
        # Unbind local variables (backtrack)
        for var in self.local_vars:
            var.binding = None
```

### Choice-Box

```python
@dataclass
class ChoiceBox:
    """
    Choice-box: represents a disjunction (clause alternatives).

    From internals.tex: "A choice-box contains the representation of tried
    guarded goals (and-boxes), the information needed to try the remaining
    guarded goals and a reference to its parent and-box."
    """
    parent: Optional[AndBox]

    # And-boxes for each clause (tried alternatives)
    alternatives: list[AndBox] = field(default_factory=list)

    # Remaining untried clauses (as callable thunks or instruction pointers)
    untried: list = field(default_factory=list)

    def is_determinate(self) -> bool:
        """Choice-box is determinate if only one alternative remains."""
        live = [a for a in self.alternatives if a.state != AndBoxState.FAILED]
        return len(live) == 1 and not self.untried

    def live_alternatives(self) -> list[AndBox]:
        """Get non-failed alternatives."""
        return [a for a in self.alternatives
                if a.state not in (AndBoxState.FAILED, AndBoxState.DEAD)]

    def prune_except(self, keep: AndBox) -> None:
        """Remove all alternatives except one (for commit/cut)."""
        for alt in self.alternatives:
            if alt is not keep:
                alt.state = AndBoxState.DEAD
        self.untried.clear()
```

---

## Execution Engine (`engine.py`)

### Configuration

```python
@dataclass
class Configuration:
    """
    The global computation state.

    Contains the root choice-box and execution queues.
    """
    root: ChoiceBox

    # Work queues
    active: list[AndBox] = field(default_factory=list)    # And-boxes to process
    wake_queue: list[AndBox] = field(default_factory=list)  # Woken and-boxes

    # Predicate definitions
    predicates: dict[tuple[str, int], list] = field(default_factory=dict)
```

### Scheduler

```python
class Engine:
    """
    AKL execution engine.

    Implements the execution model from internals.tex Chapter 2.
    """
    def __init__(self):
        self.config: Optional[Configuration] = None

    def run(self, goal: Term) -> bool:
        """
        Execute a goal.

        Returns True if goal succeeds, False if it fails.
        """
        # Initialize configuration
        root_choice = ChoiceBox(parent=None)
        root_and = AndBox(parent=root_choice, goals=[goal])
        root_choice.alternatives.append(root_and)

        self.config = Configuration(root=root_choice, active=[root_and])

        # Main loop
        while self.config.active or self.config.wake_queue:
            # Process wake queue first
            if self.config.wake_queue:
                box = self.config.wake_queue.pop(0)
                if box.state == AndBoxState.SUSPENDED:
                    box.state = AndBoxState.ACTIVE
                    self.config.active.append(box)
                continue

            # Get next active and-box
            box = self.config.active.pop(0)

            # Try to make progress
            result = self.step(box)

            if result == 'continue':
                self.config.active.append(box)
            elif result == 'suspend':
                pass  # Box added itself to suspension list
            elif result == 'done':
                self.try_promote(box)
            elif result == 'fail':
                self.handle_failure(box)

        # Check final state
        return self.is_solved()

    def step(self, box: AndBox) -> str:
        """
        Execute one step in an and-box.

        Returns: 'continue', 'suspend', 'done', or 'fail'
        """
        if not box.goals:
            box.state = AndBoxState.SOLVED
            return 'done'

        goal = box.goals.pop(0)
        goal = goal.deref()

        # Handle different goal types
        if isinstance(goal, Struct):
            return self.call_predicate(box, goal)
        elif self.is_constraint(goal):
            return self.apply_constraint(box, goal)
        else:
            # Unknown goal type
            return 'fail'

    def call_predicate(self, box: AndBox, goal: Struct) -> str:
        """Call a predicate, creating a choice-box if multiple clauses."""
        key = (goal.functor.name, goal.arity)
        clauses = self.config.predicates.get(key, [])

        if not clauses:
            return 'fail'  # No matching predicate

        # Create choice-box
        choice = ChoiceBox(parent=box)
        box.children.append(choice)

        # Create and-box for each clause
        for clause in clauses:
            alt = self.instantiate_clause(clause, goal.args, choice)
            choice.alternatives.append(alt)
            self.config.active.append(alt)

        return 'suspend'  # Wait for alternatives to resolve

    def try_promote(self, box: AndBox) -> None:
        """Try to promote a solved and-box."""
        parent_choice = box.parent
        if parent_choice is None:
            return

        if parent_choice.is_determinate():
            # Determinate promotion
            self.promote(box)
        elif box.guard_op == 'commit' and box.is_quiet():
            # Commit: prune siblings
            parent_choice.prune_except(box)
            self.promote(box)
        elif box.guard_op == 'cut' and box.is_quiet():
            # Cut: similar to commit
            parent_choice.prune_except(box)
            self.promote(box)

    def promote(self, box: AndBox) -> None:
        """Promote an and-box to its parent."""
        parent_choice = box.parent
        if parent_choice is None:
            return

        grandparent = parent_choice.parent
        if grandparent is None:
            return

        # Move body goals to grandparent
        grandparent.goals.extend(box.body)

        # Propagate constraints
        for var, term in box.constraints:
            if not grandparent.is_local(var):
                grandparent.constraints.append((var, term))

        # Mark as promoted
        box.state = AndBoxState.DEAD

        # Continue execution in grandparent
        if grandparent.state == AndBoxState.SUSPENDED:
            grandparent.state = AndBoxState.ACTIVE
            self.config.active.append(grandparent)

    def handle_failure(self, box: AndBox) -> None:
        """Handle failure of an and-box."""
        box.fail()

        parent_choice = box.parent
        if parent_choice is None:
            return

        # Check if any alternatives remain
        live = parent_choice.live_alternatives()
        if len(live) == 1:
            # Became determinate - try to promote
            self.try_promote(live[0])
        elif len(live) == 0:
            # All alternatives failed - propagate failure
            grandparent = parent_choice.parent
            if grandparent:
                self.handle_failure(grandparent)
```

---

## Parser (`parser.py`)

### Grammar (simplified)

```
term      ::= variable | constant | structure | list
variable  ::= UPPER_NAME | '_' | '_' NAME
constant  ::= atom | number
atom      ::= LOWER_NAME | QUOTED_ATOM
number    ::= INTEGER | FLOAT
structure ::= atom '(' args ')'
args      ::= term (',' term)*
list      ::= '[' ']' | '[' items ']' | '[' items '|' term ']'
items     ::= term (',' term)*

clause    ::= head '.' | head ':-' body '.'
head      ::= atom | structure
body      ::= goal (',' goal)*
goal      ::= term
```

### Implementation Approach

Use a simple recursive descent parser (or Python's `lark` library for robustness):

```python
from dataclasses import dataclass
from typing import Iterator
import re

@dataclass
class Token:
    type: str
    value: str
    line: int
    col: int

class Lexer:
    """Tokenize AKL source."""

    TOKEN_SPEC = [
        ('FLOAT',     r'\d+\.\d+'),
        ('INTEGER',   r'\d+'),
        ('VARIABLE',  r'[A-Z_][A-Za-z0-9_]*'),
        ('ATOM',      r'[a-z][A-Za-z0-9_]*'),
        ('QUOTED',    r"'[^']*'"),
        ('STRING',    r'"[^"]*"'),
        ('LPAREN',    r'\('),
        ('RPAREN',    r'\)'),
        ('LBRACKET',  r'\['),
        ('RBRACKET',  r'\]'),
        ('PIPE',      r'\|'),
        ('COMMA',     r','),
        ('DOT',       r'\.'),
        ('IMPLIES',   r':-'),
        ('COMMIT',    r'\|'),
        ('WAIT',      r'\?'),
        ('ARROW',     r'->'),
        ('WS',        r'\s+'),
        ('COMMENT',   r'%[^\n]*'),
    ]

    def __init__(self, source: str):
        self.source = source
        self.pos = 0
        self.line = 1
        self.col = 1

    def tokens(self) -> Iterator[Token]:
        """Generate tokens from source."""
        regex = '|'.join(f'(?P<{name}>{pattern})'
                         for name, pattern in self.TOKEN_SPEC)
        for match in re.finditer(regex, self.source):
            kind = match.lastgroup
            value = match.group()
            if kind in ('WS', 'COMMENT'):
                continue
            yield Token(kind, value, self.line, self.col)

class Parser:
    """Parse AKL terms and programs."""

    def __init__(self, source: str):
        self.lexer = Lexer(source)
        self.tokens = list(self.lexer.tokens())
        self.pos = 0

    def parse_term(self) -> Term:
        """Parse a single term."""
        token = self.current()

        if token.type == 'VARIABLE':
            return self.parse_variable()
        elif token.type == 'INTEGER':
            return self.parse_integer()
        elif token.type == 'FLOAT':
            return self.parse_float()
        elif token.type == 'ATOM' or token.type == 'QUOTED':
            return self.parse_atom_or_struct()
        elif token.type == 'LBRACKET':
            return self.parse_list()
        else:
            raise ParseError(f"Unexpected token: {token}")

    # ... remaining parser methods
```

---

## Built-in Predicates (`builtin.py`)

### Registry

```python
BUILTINS: dict[tuple[str, int], callable] = {}

def builtin(name: str, arity: int):
    """Decorator to register a built-in predicate."""
    def decorator(func):
        BUILTINS[(name, arity)] = func
        return func
    return decorator

@builtin('=', 2)
def builtin_unify(engine: Engine, box: AndBox, args: tuple[Term, Term]) -> str:
    """Unification: X = Y"""
    if unify(args[0], args[1]):
        return 'continue'
    return 'fail'

@builtin('is', 2)
def builtin_is(engine: Engine, box: AndBox, args: tuple[Term, Term]) -> str:
    """Arithmetic evaluation: X is Expr"""
    result = evaluate(args[1])
    if result is None:
        return 'fail'
    if unify(args[0], result):
        return 'continue'
    return 'fail'

@builtin('true', 0)
def builtin_true(engine: Engine, box: AndBox, args: tuple) -> str:
    """Always succeeds."""
    return 'continue'

@builtin('fail', 0)
def builtin_fail(engine: Engine, box: AndBox, args: tuple) -> str:
    """Always fails."""
    return 'fail'

@builtin('write', 1)
def builtin_write(engine: Engine, box: AndBox, args: tuple[Term]) -> str:
    """Print a term."""
    print(args[0].deref(), end='')
    return 'continue'

@builtin('nl', 0)
def builtin_nl(engine: Engine, box: AndBox, args: tuple) -> str:
    """Print newline."""
    print()
    return 'continue'
```

---

## Testing Strategy

### Unit Tests

```python
# test_term.py
def test_var_identity():
    x = Var("X")
    y = Var("X")  # Same name, different var
    assert x is not y
    assert id(x) != id(y)

def test_atom_interning():
    a1 = Atom("foo")
    a2 = Atom("foo")
    assert a1 is a2

def test_list_construction():
    lst = make_list([Integer(1), Integer(2), Integer(3)])
    assert isinstance(lst, Cons)
    assert lst.head == Integer(1)

# test_unify.py
def test_var_binding():
    x = Var("X")
    assert unify(x, Integer(42))
    assert x.deref() == Integer(42)

def test_struct_unify():
    x = Var("X")
    s1 = Struct(Atom("foo"), (x, Integer(2)))
    s2 = Struct(Atom("foo"), (Integer(1), Integer(2)))
    assert unify(s1, s2)
    assert x.deref() == Integer(1)

def test_occurs_check():
    x = Var("X")
    s = Struct(Atom("f"), (x,))
    assert not unify(x, s, occurs_check=True)
```

### Integration Tests

Run actual AKL programs and verify output:

```python
def test_append():
    engine = Engine()
    engine.load("""
        append([], Y, Y).
        append([H|T], Y, [H|R]) :- append(T, Y, R).
    """)

    result = engine.query("append([1,2], [3,4], Z)")
    assert result['Z'] == parse_term("[1,2,3,4]")

def test_member():
    engine = Engine()
    engine.load("""
        member(X, [X|_]).
        member(X, [_|T]) :- member(X, T).
    """)

    results = list(engine.query_all("member(X, [a,b,c])"))
    assert len(results) == 3
    assert results[0]['X'] == Atom('a')
```

---

## Implementation Phases

### Phase 1: Terms and Unification
- [ ] Term classes (Var, Atom, Integer, Float, Struct, Cons)
- [ ] Term parser (basic syntax)
- [ ] Term printer
- [ ] Unification algorithm

### Phase 2: Basic Execution
- [ ] And-box and choice-box structures
- [ ] Simple goal execution (call, unify)
- [ ] Clause matching and instantiation
- [ ] Basic built-ins (=, true, fail)

### Phase 3: Guards and Promotion
- [ ] Guard operators (wait, commit, cut)
- [ ] Suspension and waking
- [ ] Determinate promotion
- [ ] Guard promotion rules

### Phase 4: Nondeterminism
- [ ] Choice splitting (nondeterminate promotion)
- [ ] Stability detection
- [ ] Candidate selection
- [ ] Full AKL nondeterminism

### Phase 5: Constraints and Extensions
- [ ] Finite domain constraints
- [ ] Ports
- [ ] bagof/setof
- [ ] Additional built-ins

---

## References

- `../akl-agents/doc/internals.tex` - Original implementation design
- `../akl-agents/doc/aklintro.tex` - Language introduction
- `vision.md` - Project goals and approach
