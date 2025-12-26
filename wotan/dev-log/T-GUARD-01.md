# Task: T-GUARD-01

**Status:** DONE
**Parent:** B-GUARD-01
**Created:** 2025-12-05

---

## Objective

Implement proper AKL guard semantics with quiet/noisy distinction, external variable tracking, and correct guard operator behavior.

---

## Acceptance Criteria

- [x] Variables track their creating and-box (environment)
- [x] Quiet guards (`->`, `|`, `??`) cannot bind external variables during guard execution
- [x] Noisy guards (`?`, `!`) CAN bind external variables (noisy promotion)
- [x] Guard pruning: `->`, `|`, `!` prune remaining clauses
- [x] Non-pruning guards: `?`, `??` allow backtracking
- [x] If-then-else works correctly
- [x] All existing tests pass
- [x] New guard semantics tests pass (32 tests)

---

## Context

References:
- `docs/deep-guards.md` - Comprehensive analysis of AKL guard semantics
- `docs/architecture.md` - PyAKL architecture
- `../akl-agents/emulator/engine.c` - Reference implementation
- `../akl-agents/compiler/transform.akl` - Guard operator mapping

Guard operators:
- `?` (noisy_wait) - Noisy, promotes when determinate
- `->` (quiet_cut) - Quiet, requires leftmost, prunes right
- `|` (quiet_commit) - Quiet, prunes all siblings
- `??` (quiet_wait) - Quiet, requires leftmost, for ordered choice
- `!` (noisy_cut) - Noisy, requires leftmost, prunes right

---

## Implementation

### Phase 1: And-box Environment Tracking

Modified `pyakl/interpreter.py` to use proper and-box environment tracking:

1. **And-box per clause**: Each clause execution creates a new `AndBox` with a child `EnvId`:
   ```python
   clause_andb = AndBox()
   clause_andb.env = EnvId(parent=parent_andb.env)
   ```

2. **ConstrainedVar with environments**: Clause variables are created as `ConstrainedVar` with the clause's env:
   ```python
   var_map[term.name] = ConstrainedVar(term.name, andb.env)
   ```

3. **External variable detection**: Variables are external if they're:
   - Plain `Var` (from query, no env)
   - `ConstrainedVar` with no env
   - `ConstrainedVar` with env that is an ancestor of current env

### Phase 2: Quiet/Noisy Guard Semantics

Implemented proper guard semantics for quiet vs noisy guards:

1. **Quiet guards** (`->`, `|`, `??`): Cannot cause external variables to become more bound during guard execution.

2. **Noisy guards** (`?`, `!`): CAN bind external variables.

3. **External binding detection**: Before guard execution, snapshot external variable values. After guard, check if any changed:
   ```python
   external_snapshot = self._snapshot_externals(goal, clause_andb)
   # ... execute guard ...
   changed = self._check_external_changes(external_snapshot, clause_andb)
   if is_quiet_guard and changed:
       # Fail this guard attempt
   ```

### Phase 3: Guard Pruning

1. **Pruning guards** (`->`, `|`, `!`): After guard succeeds, stop trying remaining clauses.

2. **Non-pruning guards** (`?`, `??`): Allow backtracking through all clauses.

### Key Methods Added

- `_is_var_external(var, local_andb)` - Check if variable is external to current and-box
- `_collect_vars_no_deref(term, seen)` - Collect all variables without following bindings
- `_snapshot_externals(goal, local_andb)` - Snapshot external variable values
- `_check_external_changes(snapshot, local_andb)` - Detect if externals changed
- `_copy_clause_with_env(clause, andb)` - Copy clause with ConstrainedVars

---

## Tests

Created `tests/test_guards.py` with 32 tests covering:

- **Guard type parsing** (5 tests): Verify guard operators are correctly parsed
- **Simple guards** (4 tests): Basic guard success/failure
- **Guard pruning** (5 tests): Pruning vs non-pruning behavior
- **Noisy vs quiet** (2 tests): External binding handling
- **Member with guards** (2 tests): Recursive predicates
- **Append with guards** (1 test): List operations
- **If-then-else** (2 tests): Control flow
- **Guarded merge** (1 test): Classic AKL example
- **Quiet guard suspension** (3 tests): Ground/unground args
- **Cut behavior** (2 tests): Noisy cut semantics
- **External bindings** (3 tests): Quiet guard external binding detection
- **Variable environments** (2 tests): Recursive operations

---

## Evidence

```
$ pytest tests/test_guards.py -v
============================= test session starts ==============================
...
============================== 32 passed in 0.02s ==============================

$ pytest
============================= 477 passed in 0.22s ==============================
```

---

## Outcome

**Status:** DONE

Completed:
- Proper and-box environment tracking for variables
- Quiet guard semantics: cannot bind external variables during guard
- Noisy guard semantics: CAN bind external variables
- Guard pruning for `->`, `|`, `!`
- Non-pruning behavior for `?`, `??`
- If-then-else control flow
- 32 guard tests, 477 total tests passing

The implementation correctly distinguishes between:
1. **Head unification**: CAN bind external variables (this is normal parameter passing)
2. **Guard execution**: Quiet guards CANNOT bind external variables

This matches the AKL semantics from `aklintro.tex`:
> A unification must never bind an external variable to a local variable.

For quiet guards, we enforce that the guard cannot make external variables "more bound" (change from variable to non-variable or different value).

---

## Revision History

| Date | Change |
|------|--------|
| 2025-12-05 | Created |
| 2025-12-05 | Implemented guard pruning, fixed if-then-else |
| 2025-12-05 | Added proper quiet/noisy guard semantics with external binding checks |
| 2025-12-05 | Marked DONE - all acceptance criteria met |
