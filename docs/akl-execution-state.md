# AKL Execution State

This document describes the dynamic execution state structures in AKL and how they will be represented in PyAKL.

## Overview

AKL execution is based on a tree of **and-boxes** and **choice-boxes**:

```
                    root choice-box
                          |
                    root and-box
                    /           \
            choice-box        choice-box
            /      \              |
        and-box  and-box      and-box
           |
       choice-box
       /        \
   and-box    and-box
```

- **And-box**: Represents a single goal execution context (a "guarded goal")
- **Choice-box**: Represents a choice point where multiple clauses could apply

## Core Data Structures

### And-Box

An and-box contains all local state for one computation branch:

```
andbox:
  status      : DEAD | STABLE | UNSTABLE
  env         : environment identifier (for scope tracking)
  unify       : list of pending unification constraints
  constr      : list of posted constraints
  tried       : chain of alternative solutions (child choice-boxes)
  cont        : continuation(s) - code to execute after guard
  father      : parent choice-box
  next, prev  : sibling and-boxes (alternatives in same choice)
```

**Status meanings:**
- `DEAD`: Execution finished or failed
- `STABLE`: No suspended goals - can continue execution
- `UNSTABLE`: Has goals suspended on unbound variables

**PyAKL representation:**
```python
@dataclass
class AndBox:
    status: Status
    env: EnvId
    unifiers: list[tuple[Term, Term]]  # Pending unifications
    constraints: list[Constraint]
    tried: ChoiceBox | None  # First child choice-box
    cont: AndCont | None
    father: ChoiceBox | None
    next: AndBox | None
    prev: AndBox | None
```

### Choice-Box

A choice-box manages alternatives from clause matching:

```
choicebox:
  cont        : choice continuation (clauses to try)
  next, prev  : choice-box chain
  father      : parent and-box
  def         : predicate definition
  tried       : chain of and-boxes already tried
```

**PyAKL representation:**
```python
@dataclass
class ChoiceBox:
    cont: ChoiceCont | None  # Remaining clauses to try
    father: AndBox | None
    predicate: Predicate
    tried: AndBox | None  # First alternative and-box
    next: ChoiceBox | None
    prev: ChoiceBox | None
```

### Continuations

**And-continuation** - what to do after guard succeeds:
```python
@dataclass
class AndCont:
    code: Callable  # Code to execute
    next: AndCont | None
    yreg: list[Term]  # Local variables
```

**Choice-continuation** - next clause to try:
```python
@dataclass
class ChoiceCont:
    clause: Clause
    next: ChoiceCont | None
    args: tuple[Term, ...]  # Saved arguments
```

### Suspensions

When a goal must wait for a variable to be bound:

```python
@dataclass
class Suspension:
    type: Literal["andbox", "choicebox"]
    target: AndBox | ChoiceBox
    next: Suspension | None
```

Variables with suspensions are "constrained variables" (SVA/GVA in AKL):

```python
class ConstrainedVar(Var):
    env: EnvId  # Scope tracking
    suspensions: Suspension | None  # Goals waiting on this var
```

## Execution State

The engine maintains execution state:

```python
@dataclass
class ExState:
    andb: AndBox  # Current and-box
    root: ChoiceBox  # Root choice-box

    # Task queues
    trail: list[TrailEntry]  # Variable bindings (for undo)
    tasks: deque[Task]  # Work queue
    recall: deque[ChoiceBox]  # Choice-boxes to retry
    wake: deque[AndBox]  # And-boxes to wake

    # Context stack (for save/restore)
    context: list[Context]
```

### Task Queue

The engine is driven by a task queue:

```python
@dataclass
class Task:
    type: Literal["promote", "split", "start", "root"]
    target: AndBox | None
```

- `PROMOTE`: Guard succeeded, merge with parent
- `SPLIT`: Copy and-box for nondeterministic exploration
- `START`: Begin initial execution
- `ROOT`: Reached termination

### Trail (Undo Log)

All variable bindings are recorded for backtracking:

```python
@dataclass
class TrailEntry:
    var: Var
    old_value: Term | None
```

On failure, `UndoTrail()` restores all variables.

### Context Stack

Save/restore execution state when entering/leaving goals:

```python
@dataclass
class Context:
    task_pos: int
    recall_pos: int
    wake_pos: int
    trail_pos: int
```

## Guard Operators

AKL supports multiple guard types:

| Guard | Syntax | Condition for Success |
|-------|--------|----------------------|
| `?`   | `p :- ? G` | G is quiet AND leftmost alternative |
| `??`  | `p :- ?? G` | G is quiet AND leftmost (ordered) |
| `->`  | `p :- G -> B` | G solves deterministically |
| `\|`  | `p :- G \| B` | G succeeds (local cut) |
| `!`   | `p :- G ! B` | Always (hard cut) |

**Key predicates:**
- **Quiet(A)**: No pending unifications or unsatisfied constraints
- **Solved(A)**: No remaining alternatives (determinate)
- **Stable(A)**: No suspended goals
- **Leftmost(A)**: First alternative in parent choice

## Execution Flow

### Main Loop

```python
def execute(exstate):
    while not empty(exstate.tasks):
        task = exstate.tasks.popleft()

        match task.type:
            case "start":
                # Begin executing root goal
                execute_goal(exstate, initial_goal)

            case "promote":
                # Guard succeeded - merge with parent
                andb = task.target
                if andb.status == DEAD:
                    continue
                reinstall_constraints(andb)
                resume_continuation(andb.cont)

            case "split":
                # Copy and-box for later exploration
                copy = copy_andbox(task.target)
                add_alternative(copy)

            case "root":
                # Done
                return SUCCESS

    return FAILURE  # No more work
```

### Goal Execution

When executing a goal like `p(X)`:

1. Look up predicate `p/1`
2. Create choice-box with all matching clauses
3. Try first clause:
   - Create and-box
   - Unify head with arguments
   - Execute guard
   - If guard succeeds: queue PROMOTE task
   - If guard suspends: mark UNSTABLE, wait
   - If guard fails: try next clause

### Unification with And-Boxes

Unification interacts with the and-box structure:

1. **Local variable**: Bind directly, trail for undo
2. **External variable** (belongs to ancestor):
   - May need to suspend
   - Binding affects parent scope
   - Wake all goals suspended on this variable

```python
def bind_var(exstate, andb, var, value):
    if is_local(var, andb):
        # Direct binding
        trail(exstate, var)
        var.bind(value)
    else:
        # External - check constraints, may suspend
        if not can_bind_external(var, value):
            return FAIL
        trail(exstate, var)
        var.bind(value)
        wake_all(exstate, var)
```

### Suspension and Waking

When a goal needs an unbound variable:

```python
def suspend_on(exstate, andb, var):
    # Convert to constrained variable if needed
    if not is_constrained(var):
        var = make_constrained(var, andb.env)

    # Add suspension
    susp = Suspension(type="andbox", target=andb)
    susp.next = var.suspensions
    var.suspensions = susp

    # Mark and-box as unstable
    andb.status = UNSTABLE
```

When the variable gets bound:

```python
def wake_all(exstate, var):
    susp = var.suspensions
    while susp:
        if susp.type == "andbox":
            exstate.wake.append(susp.target)
        else:
            exstate.recall.append(susp.target)
        susp = susp.next
    var.suspensions = None
```

### Promotion

When a guard succeeds, the and-box is "promoted" to its parent:

1. Unlink from choice-box alternatives
2. Copy constraints to parent scope
3. Merge continuations
4. Jump to body code

```python
def promote(exstate, andb):
    # Move constraints to parent
    parent = andb.father.father  # choice-box's parent and-box
    for c in andb.constraints:
        c.promote(parent)

    # Merge continuations
    andb.cont.next = parent.cont
    parent.cont = andb.cont

    # Resume at guard body
    execute_continuation(parent.cont)
```

### Nondeterministic Splitting

When multiple alternatives exist and we need to explore them:

```python
def split(exstate, andb):
    # Copy entire and-box subtree
    copy = deep_copy_andbox(andb)

    # Add as alternative in parent choice-box
    chb = andb.father
    copy.next = chb.tried
    chb.tried = copy

    # Continue with original
    # Copy will be tried on backtrack
```

## Environment and Scope

Each and-box has an environment ID for tracking variable scope:

```python
@dataclass
class EnvId:
    parent: EnvId | None

def is_local(var, andb):
    """Check if variable belongs to this and-box."""
    return var.env is andb.env

def is_external(var, andb):
    """Check if variable belongs to an ancestor."""
    env = andb.env.parent
    while env:
        if var.env is env:
            return True
        env = env.parent
    return False
```

## Example: Executing `p(X), q(X, Y)`

Initial state:
```
root-choice-box
    └── root-and-box [STABLE]
            goals: [p(X), q(X, Y)]
            env: E0
            vars: {X: unbound, Y: unbound}
```

After `p(X)` creates choice:
```
root-choice-box
    └── root-and-box [STABLE]
            └── choice-box (p/1)
                    └── and-box [guards...]
                            trying: p(X) :- ... ? ...
```

If guard suspends on X:
```
                    └── and-box [UNSTABLE]
                            suspended on: X
                            waiting for: X to be bound
```

When X gets bound (e.g., by q/2):
```
                    └── and-box [woken → STABLE]
                            X = some_value
                            → re-evaluate guard
```

## PyAKL Implementation Plan

### Phase 1: Core Structures
- [ ] `AndBox`, `ChoiceBox` classes
- [ ] `EnvId` for scope tracking
- [ ] `Suspension` linked list
- [ ] `ExState` with queues

### Phase 2: Basic Execution
- [ ] Task queue processing
- [ ] Trail-based undo
- [ ] Context save/restore

### Phase 3: Unification Integration
- [ ] Local vs external variable handling
- [ ] Suspension on unbound variables
- [ ] Wake mechanism

### Phase 4: Guards
- [ ] Guard type dispatch
- [ ] Quiet/Solved/Stable predicates
- [ ] Promotion mechanism

### Phase 5: Nondeterminism
- [ ] And-box copying
- [ ] Split task handling
- [ ] Alternative management

### Phase 6: Constraints
- [ ] Constraint interface
- [ ] FD constraints (optional)
- [ ] Constraint propagation on promotion
