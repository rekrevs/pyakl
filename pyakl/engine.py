"""
AKL Execution Engine - Core Data Structures.

This module implements the execution state structures for the AKL engine:
- AndBox: Goal execution context
- ChoiceBox: Choice point for clause alternatives
- ExState: Global execution state with task queues
- Suspension: Goals waiting on variables

Based on the AKL emulator design from akl-agents.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Callable, Any
from collections import deque

from .term import Term, Var, Atom, Struct


# =============================================================================
# Status Flags
# =============================================================================

class Status(Enum):
    """And-box status flags."""
    DEAD = auto()      # Execution finished or failed
    STABLE = auto()    # No suspended goals - can continue
    UNSTABLE = auto()  # Has suspended goals


class TaskType(Enum):
    """Task types for the work queue."""
    PROMOTE = auto()   # Guard succeeded, merge with parent
    SPLIT = auto()     # Copy and-box for nondeterministic exploration
    START = auto()     # Begin initial execution
    ROOT = auto()      # Reached termination


class SuspensionType(Enum):
    """What kind of thing is suspended."""
    ANDBOX = auto()
    CHOICEBOX = auto()


# =============================================================================
# Environment ID (for scope tracking)
# =============================================================================

class EnvId:
    """
    Environment identifier for tracking variable scope.

    Forms a linked chain showing nesting context. Used to determine
    whether a variable is local to an and-box or external (belongs
    to an ancestor).
    """
    __slots__ = ('parent', '_id')

    _counter: int = 0

    def __init__(self, parent: EnvId | None = None) -> None:
        self.parent = parent
        EnvId._counter += 1
        self._id = EnvId._counter

    def __repr__(self) -> str:
        return f"Env#{self._id}"

    def is_ancestor_of(self, other: EnvId | None) -> bool:
        """Check if this environment is an ancestor of other."""
        current = other
        while current is not None:
            if current is self:
                return True
            current = current.parent
        return False


# =============================================================================
# Constrained Variable (extends Var with suspension support)
# =============================================================================

class ConstrainedVar(Var):
    """
    A variable that can have goals suspended on it.

    When this variable gets bound, all suspended goals are woken.
    """
    __slots__ = ('env', 'suspensions')

    def __init__(self, name: str | None = None, env: EnvId | None = None) -> None:
        super().__init__(name)
        self.env = env
        self.suspensions: Suspension | None = None

    def add_suspension(self, susp: Suspension) -> None:
        """Add a suspension to this variable."""
        susp.next = self.suspensions
        self.suspensions = susp

    def wake_all(self, exstate: ExState) -> None:
        """Wake all goals suspended on this variable."""
        susp = self.suspensions
        while susp is not None:
            if susp.type == SuspensionType.ANDBOX:
                exstate.wake.append(susp.andbox)
            else:
                exstate.recall.append(susp.choicebox)
            susp = susp.next
        self.suspensions = None


def make_constrained(var: Var, env: EnvId) -> ConstrainedVar:
    """Convert a simple Var to a ConstrainedVar."""
    cvar = ConstrainedVar(var.name, env)
    if var.binding is not None:
        cvar.binding = var.binding
    return cvar


def is_constrained(var: Var) -> bool:
    """Check if a variable is constrained (can have suspensions)."""
    return isinstance(var, ConstrainedVar)


# =============================================================================
# Suspension
# =============================================================================

@dataclass
class Suspension:
    """
    Links a suspended goal to a variable.

    When the variable is bound, the suspended goal is woken.
    """
    type: SuspensionType
    andbox: AndBox | None = None
    choicebox: ChoiceBox | None = None
    next: Suspension | None = None

    @classmethod
    def for_andbox(cls, andb: AndBox) -> Suspension:
        """Create a suspension for an and-box."""
        return cls(type=SuspensionType.ANDBOX, andbox=andb)

    @classmethod
    def for_choicebox(cls, chb: ChoiceBox) -> Suspension:
        """Create a suspension for a choice-box."""
        return cls(type=SuspensionType.CHOICEBOX, choicebox=chb)


# =============================================================================
# Continuations
# =============================================================================

@dataclass
class AndCont:
    """
    And-continuation: what to execute after guard succeeds.

    Stores the code to run and local variables (Y registers).
    """
    code: Callable[[ExState], None] | None = None
    next: AndCont | None = None
    yreg: list[Term] = field(default_factory=list)


@dataclass
class ChoiceCont:
    """
    Choice-continuation: next clause to try.

    Stores the clause and saved argument values.
    """
    clause: Any = None  # Will be Clause type
    next: ChoiceCont | None = None
    args: tuple[Term, ...] = ()


# =============================================================================
# And-Box
# =============================================================================

@dataclass
class AndBox:
    """
    And-box: represents a single goal execution context.

    Contains all local state for one computation branch including
    status, pending constraints, and continuations.
    """
    status: Status = Status.STABLE
    env: EnvId = field(default_factory=EnvId)

    # Pending unification constraints: list of (term1, term2) pairs
    unifiers: list[tuple[Term, Term]] = field(default_factory=list)

    # Posted constraints (for future constraint system)
    constraints: list[Any] = field(default_factory=list)

    # First child choice-box (alternatives from this and-box)
    tried: ChoiceBox | None = None

    # Continuation(s) - code to execute after guard
    cont: AndCont | None = None

    # Parent choice-box
    father: ChoiceBox | None = None

    # Sibling and-boxes (alternatives in same choice)
    next: AndBox | None = None
    prev: AndBox | None = None

    # Goals remaining to execute
    goals: list[Term] = field(default_factory=list)

    # Local variables
    local_vars: dict[str, Var] = field(default_factory=dict)

    def is_dead(self) -> bool:
        """Check if this and-box has failed or completed."""
        return self.status == Status.DEAD

    def is_stable(self) -> bool:
        """Check if this and-box has no suspended goals."""
        return self.status == Status.STABLE

    def is_unstable(self) -> bool:
        """Check if this and-box has suspended goals."""
        return self.status == Status.UNSTABLE

    def is_quiet(self) -> bool:
        """Check if no pending unifications or unsatisfied constraints."""
        return len(self.unifiers) == 0 and len(self.constraints) == 0

    def is_solved(self) -> bool:
        """Check if no remaining alternatives (determinate)."""
        return self.tried is None

    def mark_dead(self) -> None:
        """Mark this and-box as dead."""
        self.status = Status.DEAD

    def mark_stable(self) -> None:
        """Mark this and-box as stable."""
        self.status = Status.STABLE

    def mark_unstable(self) -> None:
        """Mark this and-box as unstable (has suspended goals)."""
        self.status = Status.UNSTABLE

    def add_goal(self, goal: Term) -> None:
        """Add a goal to execute."""
        self.goals.append(goal)

    def pop_goal(self) -> Term | None:
        """Pop next goal to execute."""
        if self.goals:
            return self.goals.pop(0)
        return None

    def add_unifier(self, t1: Term, t2: Term) -> None:
        """Add a pending unification constraint."""
        self.unifiers.append((t1, t2))

    def get_var(self, name: str) -> Var:
        """Get or create a local variable."""
        if name not in self.local_vars:
            self.local_vars[name] = ConstrainedVar(name, self.env)
        return self.local_vars[name]


# =============================================================================
# Choice-Box
# =============================================================================

@dataclass
class ChoiceBox:
    """
    Choice-box: represents a choice point with multiple clause alternatives.

    Manages the alternatives from clause matching and links them together.
    """
    # Remaining clauses to try
    cont: ChoiceCont | None = None

    # Parent and-box
    father: AndBox | None = None

    # Predicate being called
    predicate: Any = None  # Will be Predicate type

    # First alternative and-box
    tried: AndBox | None = None

    # Sibling choice-boxes
    next: ChoiceBox | None = None
    prev: ChoiceBox | None = None

    def add_alternative(self, andb: AndBox) -> None:
        """Add an and-box as an alternative."""
        andb.father = self
        if self.tried is None:
            self.tried = andb
        else:
            # Add to end of chain
            last = self.tried
            while last.next is not None:
                last = last.next
            last.next = andb
            andb.prev = last

    def remove_alternative(self, andb: AndBox) -> None:
        """Remove an and-box from alternatives."""
        if andb.prev is not None:
            andb.prev.next = andb.next
        else:
            self.tried = andb.next

        if andb.next is not None:
            andb.next.prev = andb.prev

        andb.father = None
        andb.next = None
        andb.prev = None

    def is_determinate(self) -> bool:
        """Check if only one alternative remains."""
        return self.tried is not None and self.tried.next is None

    def alternatives(self) -> list[AndBox]:
        """Get list of all alternatives."""
        result = []
        current = self.tried
        while current is not None:
            result.append(current)
            current = current.next
        return result


# =============================================================================
# Task
# =============================================================================

@dataclass
class Task:
    """A task in the work queue."""
    type: TaskType
    andbox: AndBox | None = None

    @classmethod
    def promote(cls, andb: AndBox) -> Task:
        return cls(type=TaskType.PROMOTE, andbox=andb)

    @classmethod
    def split(cls, andb: AndBox) -> Task:
        return cls(type=TaskType.SPLIT, andbox=andb)

    @classmethod
    def start(cls) -> Task:
        return cls(type=TaskType.START)

    @classmethod
    def root(cls) -> Task:
        return cls(type=TaskType.ROOT)


# =============================================================================
# Trail Entry (for undo)
# =============================================================================

@dataclass
class TrailEntry:
    """Records a variable binding for undo on backtrack."""
    var: Var
    old_binding: Term | None


# =============================================================================
# Context (execution snapshot)
# =============================================================================

@dataclass
class Context:
    """Snapshot of execution state for save/restore."""
    task_pos: int
    recall_pos: int
    wake_pos: int
    trail_pos: int


# =============================================================================
# Execution State
# =============================================================================

@dataclass
class ExState:
    """
    Global execution state.

    Contains the current and-box, task queues, trail, and context stack.
    """
    # Current and-box being executed
    andb: AndBox | None = None

    # Root choice-box
    root: ChoiceBox | None = None

    # Task queues
    tasks: deque[Task] = field(default_factory=deque)
    wake: deque[AndBox] = field(default_factory=deque)
    recall: deque[ChoiceBox] = field(default_factory=deque)

    # Trail for variable bindings (undo log)
    trail: list[TrailEntry] = field(default_factory=list)

    # Context stack for save/restore
    contexts: list[Context] = field(default_factory=list)

    # ==========================================================================
    # Task queue operations
    # ==========================================================================

    def add_task(self, task: Task) -> None:
        """Add a task to the work queue."""
        self.tasks.append(task)

    def next_task(self) -> Task | None:
        """Pop next task from work queue."""
        if self.tasks:
            return self.tasks.popleft()
        return None

    def has_tasks(self) -> bool:
        """Check if there are pending tasks."""
        return len(self.tasks) > 0

    def queue_promote(self, andb: AndBox) -> None:
        """Queue an and-box for promotion."""
        self.tasks.append(Task.promote(andb))

    def queue_split(self, andb: AndBox) -> None:
        """Queue an and-box for splitting."""
        self.tasks.append(Task.split(andb))

    def queue_wake(self, andb: AndBox) -> None:
        """Queue an and-box to wake."""
        self.wake.append(andb)

    def queue_recall(self, chb: ChoiceBox) -> None:
        """Queue a choice-box to retry."""
        self.recall.append(chb)

    # ==========================================================================
    # Trail operations (for backtracking)
    # ==========================================================================

    def trail_binding(self, var: Var, old_binding: Term | None = None) -> None:
        """Record a variable binding for potential undo."""
        self.trail.append(TrailEntry(var, old_binding))

    def undo_trail(self, to_pos: int | None = None) -> None:
        """Undo variable bindings back to position."""
        if to_pos is None:
            to_pos = 0
        while len(self.trail) > to_pos:
            entry = self.trail.pop()
            entry.var.binding = entry.old_binding

    def trail_position(self) -> int:
        """Get current trail position."""
        return len(self.trail)

    # ==========================================================================
    # Context operations (for nested execution)
    # ==========================================================================

    def push_context(self) -> None:
        """Save current execution state."""
        ctx = Context(
            task_pos=len(self.tasks),
            recall_pos=len(self.recall),
            wake_pos=len(self.wake),
            trail_pos=len(self.trail),
        )
        self.contexts.append(ctx)

    def pop_context(self) -> Context | None:
        """Restore previous execution state."""
        if self.contexts:
            return self.contexts.pop()
        return None

    def restore_context(self, ctx: Context) -> None:
        """Restore execution state from context."""
        # Truncate queues to saved positions
        while len(self.tasks) > ctx.task_pos:
            self.tasks.pop()
        while len(self.recall) > ctx.recall_pos:
            self.recall.pop()
        while len(self.wake) > ctx.wake_pos:
            self.wake.pop()
        # Undo trail
        self.undo_trail(ctx.trail_pos)


# =============================================================================
# Helper functions for creating execution structures
# =============================================================================

def create_root(goal: Term) -> tuple[ExState, AndBox]:
    """
    Create initial execution state for a goal.

    Returns the execution state and root and-box.
    """
    exstate = ExState()

    # Create root choice-box
    root_chb = ChoiceBox()
    exstate.root = root_chb

    # Create root and-box
    root_andb = AndBox()
    root_andb.add_goal(goal)
    root_chb.add_alternative(root_andb)

    exstate.andb = root_andb

    # Queue initial task
    exstate.add_task(Task.start())

    return exstate, root_andb


def create_choice(parent: AndBox, predicate: Any = None) -> ChoiceBox:
    """Create a choice-box under a parent and-box."""
    chb = ChoiceBox(father=parent, predicate=predicate)

    # Link into parent's tried chain
    if parent.tried is None:
        parent.tried = chb
    else:
        last = parent.tried
        while last.next is not None:
            last = last.next
        last.next = chb
        chb.prev = last

    return chb


def create_alternative(chb: ChoiceBox, clause: Any = None) -> AndBox:
    """Create an and-box as an alternative in a choice-box."""
    andb = AndBox()
    andb.env = EnvId(parent=chb.father.env if chb.father else None)
    chb.add_alternative(andb)
    return andb


# =============================================================================
# Variable scope operations
# =============================================================================

def is_local_var(var: Var, andb: AndBox) -> bool:
    """Check if variable belongs to this and-box."""
    if isinstance(var, ConstrainedVar):
        return var.env is andb.env
    return False


def is_external_var(var: Var, andb: AndBox) -> bool:
    """Check if variable belongs to an ancestor and-box."""
    if isinstance(var, ConstrainedVar):
        # Variable's env must be an ancestor of andb's env (but not same)
        return var.env.is_ancestor_of(andb.env) and var.env is not andb.env
    return False


def suspend_on_var(exstate: ExState, andb: AndBox, var: Var) -> ConstrainedVar:
    """
    Suspend an and-box on a variable.

    Converts var to ConstrainedVar if needed, adds suspension,
    and marks and-box as unstable.
    """
    # Ensure variable is constrained
    if not isinstance(var, ConstrainedVar):
        cvar = make_constrained(var, andb.env)
    else:
        cvar = var

    # Add suspension
    susp = Suspension.for_andbox(andb)
    cvar.add_suspension(susp)

    # Mark and-box as unstable
    andb.mark_unstable()

    return cvar


def bind_var(exstate: ExState, andb: AndBox, var: Var, value: Term) -> bool:
    """
    Bind a variable to a value.

    Handles local vs external variables appropriately.
    Returns True on success, False on failure.
    """
    var = var.deref()
    value = value.deref()

    # Already bound to same value
    if var is value:
        return True

    # Not a variable - can't bind
    if not isinstance(var, Var):
        return False

    # Trail the binding
    exstate.trail_binding(var, var.binding)

    # Perform binding
    var.binding = value

    # Wake suspended goals if constrained
    if isinstance(var, ConstrainedVar):
        var.wake_all(exstate)

    return True
