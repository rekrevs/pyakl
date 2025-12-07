# Deep Guards and Suspension in AKL

This document provides a comprehensive analysis of how guards, suspension, and nondeterministic promotion work in the Andorra Kernel Language (AKL), based on the akl-agents reference implementation.

## Table of Contents

1. [Overview](#overview)
2. [Core Data Structures](#core-data-structures)
3. [Guard Operators](#guard-operators)
4. [Suspension Mechanics](#suspension-mechanics)
5. [Stability and Quietness](#stability-and-quietness)
6. [Promotion Rules](#promotion-rules)
7. [Nondeterministic Splitting](#nondeterministic-splitting)
8. [Implementation in PyAKL](#implementation-in-pyakl)

---

## Overview

AKL is based on concurrent constraint programming where:

1. **Agents** execute concurrently, sharing a constraint store
2. **Guards** test conditions before committing to a clause body
3. **Suspension** pauses execution when guards cannot yet be evaluated
4. **Promotion** moves successful guard computations to the parent scope
5. **Splitting** handles nondeterministic choices by copying computation state

The key innovation of AKL is that guards can contain **general statements** (deep guards), not just constraint tests. This means:

- Guards execute in a **local computation** with their own constraint store
- **Asked constraints** are checked against the union of local and external stores
- **Told constraints** go only to the local store (not visible externally)
- Guards can contain arbitrary goals, including recursive calls

### Local vs External Variables

A fundamental concept in AKL is the distinction between:

- **Local variables**: Created in the current and-box, can be bound freely
- **External variables**: From parent scopes, binding creates constraints that affect stability

From `aklintro.tex` (lines 762-773):
> A unification must never bind an external variable to a local variable.

This ensures that local computations cannot "leak" uncommitted bindings to the outside world.

---

## Core Data Structures

### And-Box (from `tree.h`)

```c
typedef struct andbox {
  sflag           status;       // DEAD, STABLE, UNSTABLE, XSTABLE, XUNSTABLE
  struct envid    *env;         // Environment identifier (for variable locality)
  struct unifier  *unify;       // Deferred unifications (external bindings)
  struct constraint *constr;    // Constraints on external variables
  struct choicebox *tried;      // Child choice-boxes (tried goals)
  struct andcont  *cont;        // Continuation (remaining goals + guard instruction)
  struct choicebox *father;     // Parent choice-box
  struct andbox   *next, *previous;  // Siblings in parent choice-box
} andbox;
```

Key predicates on and-boxes (`tree.h`):

```c
#define Leftmost(A)  ((A)->previous == NULL)
#define Rightmost(A) ((A)->next == NULL)
#define Quiet(A)     (((A)->unify == NULL) && \
                      ((A)->constr == NULL || entailed(&(A)->constr)))
#define Solved(A)    ((A)->tried == NULL)
#define Dead(A)      ((A)->status == DEAD)
#define Stable(A)    ((A)->status == STABLE || (A)->status == XSTABLE)
#define UnStable(A)  ((A)->status == UNSTABLE || (A)->status == XUNSTABLE)
```

### Choice-Box (from `tree.h`)

```c
typedef struct choicebox {
  struct choicecont *cont;      // Continuation for remaining alternatives
  struct choicebox  *next, *previous;  // Siblings
  struct andbox     *father;    // Parent and-box
  struct predicate  *def;       // Definition being tried
  struct andbox     *tried;     // Tried alternatives (and-boxes)
  int               type;       // Guard type
} choicebox;
```

### Suspension (from `tree.h`)

```c
typedef enum { CHB, ANDB } susptag;

typedef struct suspension {
  susptag          type;        // Suspended on choice-box or and-box
  struct suspension *next;
  union {
    andbox      *andb;
    choicebox   *chb;
  } suspended;
} suspension;
```

### Variable Structure (from `term.h`)

Variables in AKL have an **environment identifier** that tracks which and-box they belong to:

```c
typedef struct svainfo {
  struct gvamethod *method;     // NULL for simple variables (SVA)
  envid            *env;        // Points to creating and-box
  struct suspension *susp;      // Suspended goals on this variable
} svainfo;
```

The `env` field is crucial: it allows the system to determine if a variable is local or external to a given and-box.

---

## Guard Operators

AKL provides several guard operators. The key distinction is between:

- **Quiet guards**: Cannot have bindings on external variables (must be quiet)
- **Noisy guards**: CAN have bindings on external variables

From `compiler/transform.akl`:
```prolog
translate_gop(('->'), quiet_cut).     % Arrow/Then - quiet
translate_gop(('|'),  quiet_commit).  % Commit - quiet
translate_gop(('??'), quiet_wait).    % Ordered wait - quiet
translate_gop(('?'),  noisy_wait).    % Wait - noisy (CAN have bindings)
translate_gop(('||'), noisy_commit).  % Noisy commit
translate_gop(('!'),  noisy_cut).     % Cut - noisy (CAN have bindings)
```

### Guard Operator Summary

| Syntax | Internal Name | Quiet/Noisy | Requires Leftmost | Prunes | Commits |
|--------|---------------|-------------|-------------------|--------|---------|
| `->` | quiet_cut | Quiet | Yes | Right | When leftmost |
| `\|` | quiet_commit | Quiet | No | All | When quiet |
| `??` | quiet_wait | Quiet | Yes | Right | When leftmost & determinate |
| `?` | noisy_wait | **Noisy** | No | None | When determinate |
| `!` | noisy_cut | **Noisy** | Yes (for commit) | Right | When leftmost |
| `\|\|` | noisy_commit | **Noisy** | No | All | Always |

### 1. Wait Guard (`?`) - noisy_wait / GUARD_WAIT

From `aklintro.tex` (lines 544-624):

```prolog
p(X) :- guard ? body.
```

**Semantics:**
- **Noisy**: CAN have bindings on external variables
- Waits until the guard becomes **determinate** (only one alternative remains)
- Promotes when the parent choice-box has exactly one remaining clause
- Does NOT commit immediately - allows backtracking
- This is the standard nondeterminate choice operator

**Implementation** (`engine.c` lines 641-650):
```c
if(Solved(andb) && Last(chb,andb)) {
  // Promote only when determinate (last alternative)
  goto promotion;  // Note: does NOT check Quiet!
}
goto guardhandler;
```

**Key points:**
- Guard is **solved** (no pending goals)
- Must be the **last** (only remaining) alternative
- Does NOT require quiet - can promote with external bindings ("noisy promotion")

### 2. Arrow/Then Guard (`->`) - quiet_cut / GUARD_CUT or GUARD_COND

```prolog
p(X) :- guard -> body.
% or in if-then-else:
( Cond -> Then ; Else )
```

**Semantics:**
- **Quiet**: CANNOT have bindings on external variables
- Requires **leftmost** position to commit
- Prunes alternatives to the right
- Used for conditional/if-then-else constructs

**Implementation** (`engine.c` lines 569-610):
```c
if(Solved(andb)) {
  if (Quiet(andb) && EmptyTrail(exs)) {  // Must be quiet!
    if(Leftmost(andb)) {
      // Prune right siblings and promote
      KillAll(chb);
      promote_andbox();
    }
    RemoveChoiceCont(chb);
    KillLeft(andb);
  }
  // If not quiet but determinate, can still promote
  if(Last(chb,andb)) {
    goto promotion;  // "noisy" promotion allowed for cut
  }
}
```

### 3. Commit Guard (`|`) - quiet_commit / GUARD_COMMIT

From `aklintro.tex` (lines 471-503):

```prolog
merge([E|X], Y, Z) :- X1 : X = [E|X1] | Z = [E|Z1], merge(X1, Y, Z1).
```

**Semantics:**
- **Quiet**: CANNOT have bindings on external variables
- **Don't care nondeterminism**: commits to first guard that becomes quiet
- Prunes ALL siblings when guard succeeds
- Does not require leftmost position
- Used for reactive/concurrent programming (GHC-style)

**Implementation** (`engine.c` lines 612-639):
```c
if(Quiet(andb) && EmptyTrail(exs) && Solved(andb)) {  // Must be quiet!
  // Kill all siblings and promote
  KillAll(chb);
  promote_andbox();
}
```

### 4. Cut Guard (`!`) - noisy_cut

```prolog
p(X) :- guard ! body.
```

**Semantics:**
- **Noisy**: CAN have bindings on external variables
- Requires **leftmost** position to commit
- Prunes alternatives to the right
- Similar to Prolog cut but with AKL suspension semantics

**Note:** The `!` operator is actually `noisy_cut` according to the compiler, meaning it CAN have external bindings. However, GUARD_CUT in the emulator checks for quiet when leftmost. The distinction is that `!` can promote when determinate even if not quiet.

### 5. Quiet Wait Guard (`??`) - quiet_wait

```prolog
p(X) :- guard ?? body.
```

**Semantics:**
- **Quiet**: CANNOT have bindings on external variables
- Requires **leftmost** position
- Used for **ordered** nondeterminate choice
- Ensures alternatives are explored in order

**Note:** The `??` operator is used in ordered bagof operations (GUARD_ORDER/GUARD_UNORDER in the emulator). It ensures that when collecting solutions, they come out in clause order.

### Quiet vs Noisy Summary

The key semantic distinction:

- **Quiet guards** (`->`, `|`, `??`): Cannot commit if there are bindings on external variables. Must wait until those bindings are resolved or fail.

- **Noisy guards** (`?`, `!`): CAN commit even with bindings on external variables. The bindings are "promoted" along with the guard - this is called **noisy promotion**.

From `tree.h`:
```c
#define Quiet(A) (((A)->unify == NULL) && \
                  ((A)->constr == NULL || entailed(&(A)->constr)))
```

An and-box is quiet when:
1. No pending unifications on external variables (`unify == NULL`)
2. No constraints on external variables, OR all such constraints are entailed

---

## Suspension Mechanics

### When Suspension Occurs

An and-box suspends when its guard cannot complete:

1. **External variable test**: Guard needs a variable that's external and unbound
2. **Not quiet**: External constraints exist that aren't entailed
3. **Not solved**: Goals remain in the guard
4. **Position requirement not met**: e.g., `??` guard but not leftmost

### Suspension Process (from `internals.tex`)

1. **Trail external bindings**: Record which external variables were bound
2. **Create constraints**: For each trailed external variable, add constraint to and-box
3. **Add suspensions**: Register the and-box on each constrained variable
4. **Update stability**: Mark ancestor and-boxes as potentially unstable

From `exstate.h`:
```c
#define SuspendTrail(W,A) suspend_trail(W,A);
```

### Wake Mechanism

When a constrained variable is bound:

1. **Wake suspended and-boxes**: All and-boxes suspended on this variable are added to wake queue
2. **Process wake queue**: Each woken and-box is re-installed and re-evaluated

From `exstate.h`:
```c
#define WakeAll(W,V)\
{\
  gvainfo *Gv = RefGva(V);\
  if (GvaIsSva(Gv)) {\
    suspension *S;\
    for(S = SvaSusp(GvaSva(Gv)); S != NULL; S = S->next){\
      switch(S->type) {\
       case CHB:\
         Recall(W,S->suspended.chb);\
         break;\
       case ANDB:\
         Wake(W,S->suspended.andb);\
         break;\
      }\
    }\
    SvaSusp(GvaSva(Gv)) = NULL;\
  }\
}
```

---

## Stability and Quietness

### Quietness

An and-box is **quiet** when it has no constraints on external variables that affect the outside world.

From `tree.h`:
```c
#define Quiet(A) (((A)->unify == NULL) && \
                  ((A)->constr == NULL || entailed(&(A)->constr)))
```

This means:
- No pending unifications (`unify == NULL`)
- No external constraints, OR all constraints are entailed

### Stability

An and-box is **stable** when no external action can enable further computation.

From `internals.tex` (lines 817-822):
> A state is (locally) stable if no computation step other than copying in nondeterminate choice is possible, and no such computation step can be made possible by adding constraints to external constraint stores.

**Stability tracking** uses marks/counters:
- When a constraint on external variable is added, mark ancestor and-boxes as unstable
- When constraint is removed (failure/promotion), update stability
- An and-box is stable if it has no marks AND no constraints on variables external to it

The implementation uses a simplified scheme with dirty bits:
```c
#define Stable(Andb) ((Andb)->status == STABLE || (Andb)->status == XSTABLE)
```

---

## Promotion Rules

### Determinate Promotion

When a guard completes successfully:

1. **Check conditions**: Quiet, solved, appropriate position
2. **Prune siblings**: Based on guard type
3. **Promote constraints**: Move external constraints to parent
4. **Promote continuation**: Move body goals to parent
5. **Remove choice-box**: If only one alternative remains

From `exstate.h`:
```c
#define PromoteConstraints(W,P,A) promote_constraints(W,P,A);
#define PromoteContext(W,A) promote_context(W,A);
```

### What Gets Promoted

From `internals.tex` (lines 798-800):
> When an and-box is promoted the constraints containing a variable that is external to the parent and-box are moved to the parent and-box.

1. **Constraints**: External variable bindings move to parent scope
2. **Goals**: Body of the guarded clause becomes active in parent
3. **Local variables**: Become local to parent and-box
4. **Suspensions**: Wake any goals suspended on promoted variables

---

## Nondeterministic Splitting

**IMPORTANT**: AKL nondeterminism is fundamentally different from Prolog backtracking:
- **Prolog**: One computation, undo bindings and try next alternative on failure
- **AKL**: Multiple parallel computations, no backtracking, split to create independent branches

When an and-box is **stable** (no more computation steps possible) but contains nondeterministic choices (wait guards with multiple alternatives), AKL uses **copying** to explore alternatives.

### Key Terminology

- **Candidate**: A solved and-box with a wait guard (`?`) that can be promoted
- **Fork**: The parent choice-box of the candidate
- **Mother**: The parent and-box of the fork (root of subtree to copy)

### When Splitting Occurs

From `engine.c` (line 3120):
```c
if(!Solved(andb) && EmptyTrail(exs) && Stable(andb)) {
    cand = candidate(andb->tried);
    if(cand != NULL) {
        goto splithandler;
    }
}
```

Splitting happens when:
1. The and-box is **not solved** (has child choice-boxes)
2. The **trail is empty** (no pending constraint work)
3. The and-box is **stable** (no suspended goals can make progress)
4. A **candidate** exists (leftmost solved wait-guard)

### Finding Candidates (from `candidate.c`)

```c
andbox *candidate(choicebox *chb) {
    return leftmost(chb);
}
```

The algorithm searches left-to-right through the choice-box tree:
1. For each and-box under the choice-box
2. If it has a `GUARD_WAIT` instruction and is solved (no children), it's a candidate
3. Otherwise, recursively search its children
4. Return the leftmost candidate found, preferring deeper candidates

Candidates must:
1. Have a **wait guard** (`?`)
2. Be **solved** (guard completed, no pending goals)
3. Be the **leftmost** such candidate (ensures ordered exploration)

### Splitting Process (from `engine.c` splithandler, lines 3276-3347)

```
Given: candidate A with parent choice-box B (fork), B's parent C (mother)

1. Deinstall current and-box if it equals mother
2. Copy the subtree rooted at mother:
   - The copy is identical EXCEPT:
   - The copy of fork has ONLY a copy of candidate A
   - Local variables in subtree get fresh copies
   - External variables remain SHARED (not copied)
   - Suspensions on external variables are duplicated for copied and-boxes
3. Insert the copy to the LEFT of mother (in mother's parent choice-box)
4. Remove candidate from original fork (leaving remaining siblings)
5. Schedule:
   - If fork now has only one and-box: promote it (deterministic)
   - Else if mother is stable: schedule another split attempt
6. Install and promote the copied candidate
```

### What Gets Copied

From `internals.tex` (lines 1047-1058):

**Copied (fresh instances)**:
- And-boxes in the subtree
- Choice-boxes in the subtree
- Local variables (variables whose environment is within the subtree)
- Terms containing local variables
- Suspensions (pointing to copied and-boxes)

**Shared (NOT copied)**:
- External variables (from parent scopes)
- Atoms, integers, floats (immutable)
- But: if an external variable has suspensions on and-boxes in the original subtree, a new suspension is added for the copy

### Why This Architecture?

1. **No backtracking**: Each branch is independent, no undo needed
2. **Parallel execution**: Different branches can run on different processors
3. **Deep guards**: Guards can contain arbitrary computation, not just tests
4. **Concurrent agents**: Multiple agents can interact via shared external variables

### Difference from Prolog

```
Prolog member/2:
  member(X, [X|_]).
  member(X, [_|T]) :- member(X, T).

  ?- member(X, [1,2,3]).
  X = 1 ; X = 2 ; X = 3.  % Sequential backtracking

AKL member/2:
  member(X, [X|_]) :- true ? true.
  member(X, [_|T]) :- true ? member(X, T).

  ?- member(X, [1,2,3]).
  % Creates 3 parallel computations:
  % Branch 1: X = 1
  % Branch 2: X = 2
  % Branch 3: X = 3
```

In AKL, all solutions exist simultaneously as parallel branches, not sequentially via backtracking.

---

## Implementation in PyAKL

### Current State (after T-GUARD-01)

PyAKL currently has:
- ✅ Basic and-box/choice-box structures (`engine.py`)
- ✅ Variable binding with environment tracking (`engine.py`, `ConstrainedVar`)
- ✅ Trail for undo on guard failure (`engine.py`)
- ✅ Guard execution with quiet/noisy distinction (`interpreter.py`)
- ✅ External variable detection via `EnvId` chains
- ✅ And-box copying infrastructure (`copy.py`)
- ❌ **True splitting-based execution** (currently uses Prolog-style backtracking!)
- ❌ Suspension on external variables
- ❌ Wake queue mechanism
- ❌ Stability detection
- ❌ Task-based scheduler

### Current Interpreter: Generator-Based Sequential Simulation

The current interpreter uses **generator-based backtracking** which is Prolog-style:
- Tries clauses sequentially
- Undoes bindings on backtrack
- Single computation path at a time

**Important clarification**: While this differs from true AKL splitting semantics, it is a **valid sequential simulation** that produces correct results:
- All solutions are found (same as splitting would produce)
- Order may differ (depth-first vs breadth-first)
- Observable behavior is equivalent for sequential execution

The generator-based approach is **sufficient for**:
- Sequential execution
- Finding all solutions
- Programs without concurrent agents

**True splitting is needed for**:
- Parallel/concurrent execution
- Multiple agents interacting via shared external variables
- Full AKL guard suspension semantics

### Task-Based Scheduler (Experimental)

An experimental task-based scheduler exists in `scheduler.py` but has issues:

**The fundamental challenge**: Each parallel branch needs truly independent variable bindings. With trail-based undo, bindings are shared and undoing affects all branches.

**Solution approach** (not yet implemented):
1. When splitting, use `copy.py` to create independent copy of computation state
2. Each copied branch has its own variables (local vars copied, external vars shared)
3. Process branches independently, no trail-based undo between branches
4. Collect solutions from all successful branches

### What's Needed

#### Phase 1: Task-Based Execution Model

Replace generator-based interpreter with task-based:
1. **Task queue**: List of and-boxes to process
2. **Worker loop**: Process tasks until queue empty or stable
3. **No generators for choice points**: All alternatives exist as and-boxes

#### Phase 2: Suspension and Wake

1. **Suspend on external variables**: When guard cannot proceed, suspend and-box
2. **Wake queue**: When variable bound, wake suspended and-boxes
3. **Stability tracking**: Count suspensions on external variables

#### Phase 3: Splitting Integration

1. **Detect stability**: No progress possible, check for candidates
2. **Find candidate**: Leftmost solved wait-guard
3. **Copy subtree**: Use `copy.py` infrastructure
4. **Schedule new work**: Add tasks for split branches

### Design Considerations

1. **Python GC**: Automatic memory management for copied structures
2. **No generators for backtracking**: Use explicit and-box tree instead
3. **Sequential simulation**: Process one branch at a time, but all branches exist
4. **Solution collection**: All successful branches contribute solutions

---

## References

- `aklintro.tex` - Introduction to AKL (language semantics)
- `internals.tex` - Design of Sequential Prototype Implementation
- `emulator/tree.h` - Data structures for and-boxes and choice-boxes
- `emulator/exstate.h` - Execution state and suspension macros
- `emulator/engine.c` - Guard instruction implementation
- `emulator/candidate.c` - Candidate finding for splitting
- `emulator/term.h` - Term representation and variable structure
