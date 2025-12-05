# Task: T-BOX-01

**Status:** DONE
**Parent:** B-BOX-01, B-ENGINE-01
**Created:** 2025-12-04

---

## Objective

Implement the core execution state data structures for the AKL engine: and-boxes, choice-boxes, execution state, task queues, and suspension mechanism.

---

## Acceptance Criteria

- [x] AndBox with status, env, unifiers, constraints, continuations
- [x] ChoiceBox with alternatives chain, father link
- [x] Status enum (DEAD, STABLE, UNSTABLE)
- [x] EnvId for scope tracking with ancestor chain
- [x] ConstrainedVar extending Var with suspension support
- [x] Suspension records linking goals to variables
- [x] ExState with task/wake/recall queues
- [x] Trail for variable bindings with undo
- [x] Context stack for save/restore
- [x] Helper functions: create_root, create_choice, create_alternative
- [x] Scope operations: is_local_var, is_external_var, suspend_on_var, bind_var

---

## Context

- `docs/akl-execution-state.md` - Design document for execution state
- `../akl-agents/emulator/tree.h` - Original C implementation
- `../akl-agents/emulator/exstate.h` - Original execution state

---

## Implementation

### Files Created

- `pyakl/engine.py` - Core execution state structures (620 lines)
- `tests/test_engine.py` - 49 tests for execution state

### Key Classes

**EnvId** - Environment identifier for scope tracking:
- Forms linked chain showing nesting context
- `is_ancestor_of()` checks scope relationship

**ConstrainedVar** - Variable with suspension support:
- Extends `Var` with `env` and `suspensions`
- `add_suspension()` links waiting goals
- `wake_all()` queues suspended goals when bound

**Suspension** - Links suspended goal to variable:
- Type: ANDBOX or CHOICEBOX
- Target: the suspended goal
- Linked list via `next`

**AndBox** - Goal execution context:
- `status`: DEAD/STABLE/UNSTABLE
- `env`: EnvId for scope
- `unifiers`: pending equality constraints
- `constraints`: posted constraints
- `tried`: child choice-boxes
- `cont`: continuations
- `father`: parent choice-box
- `goals`: remaining goals
- `local_vars`: local variable map

**ChoiceBox** - Choice point:
- `cont`: remaining clauses
- `father`: parent and-box
- `tried`: alternative and-boxes
- Doubly-linked list of alternatives

**Task** - Work queue entry:
- Types: PROMOTE, SPLIT, START, ROOT
- Target and-box

**ExState** - Global execution state:
- `andb`: current and-box
- `root`: root choice-box
- `tasks`: work queue (deque)
- `wake`: and-boxes to resume
- `recall`: choice-boxes to retry
- `trail`: variable bindings for undo
- `contexts`: save/restore stack

### Helper Functions

- `create_root(goal)` - Create initial execution state
- `create_choice(parent)` - Create choice-box under and-box
- `create_alternative(chb)` - Create and-box in choice-box
- `is_local_var(var, andb)` - Check if variable is local
- `is_external_var(var, andb)` - Check if variable is in ancestor
- `suspend_on_var(exstate, andb, var)` - Suspend and-box on variable
- `bind_var(exstate, andb, var, value)` - Bind variable, wake suspended

---

## Testing

### Tests Added

- `tests/test_engine.py` - 49 tests:
  - TestEnvId: 6 tests (scope tracking)
  - TestConstrainedVar: 5 tests (suspension support)
  - TestSuspension: 2 tests (suspension records)
  - TestAndBox: 6 tests (and-box operations)
  - TestChoiceBox: 7 tests (choice-box operations)
  - TestTask: 4 tests (task types)
  - TestExState: 9 tests (execution state)
  - TestCreateHelpers: 3 tests (helper functions)
  - TestVariableScope: 5 tests (scope operations)
  - TestWakeAll: 2 tests (wake mechanism)

### Test Results

```
============================= 49 passed in 0.02s ==============================
```

---

## Obstacles

### Obstacle 1: is_external_var logic inverted

**Observed:** `is_external_var(external, andb)` returned False for external variable
**Expected:** Should return True
**Root cause:** Checked if `andb.env.is_ancestor_of(var.env)` instead of vice versa
**Resolution:** Fixed to `var.env.is_ancestor_of(andb.env)`

---

## Outcome

**Status:** DONE

**Summary:** Implemented all core execution state data structures needed for the AKL engine. The implementation closely follows the original AKL emulator design with Python adaptations. All 49 tests pass.

---

## Revision History

| Date | Change |
|------|--------|
| 2025-12-04 | Created - implemented all structures |
| 2025-12-04 | Fixed is_external_var bug - 49 tests passing |
