# PyAKL Status Report

**Date:** 2025-12-06
**Task:** T-ENGINE-02-FIX - Correct AKL Execution Model

---

## Current State

The AKL execution engine (`pyakl/akl_engine.py`) now correctly handles basic recursive predicates including `member/2`, `append/3`, `len/2`, and `reverse/2`. All 507 existing tests pass.

### Working Features

- **Splitting (not backtracking)**: Nondeterminism is handled via tree copying, not Prolog-style backtracking
- **Basic guard types**: WAIT (`?`), COMMIT (`|`), ARROW (`->`), CUT (`!`)
- **Recursive predicates**: `member/2`, `append/3`, `len/2`, `reverse/2` all work correctly
- **Arithmetic**: `is/2` works correctly with proper variable resolution
- **Deferred unification**: External variable bindings are properly deferred and propagated

### Test Results

```
member(X, [1,2,3])     → 3 solutions: X=1, X=2, X=3 ✓
append([1,2], [3,4], X) → X=[1,2,3,4] ✓
append(X, Y, [1,2,3])   → 4 solutions ✓
len([a,b,c], X)        → X=3 ✓
reverse([1,2,3], X)    → X=[3,2,1] ✓
```

---

## Bugs Fixed (This Session)

### 1. `_try_split` only searched first root alternative
**File:** `pyakl/akl_engine.py`
**Fix:** Iterate through ALL alternatives in root choice-box since splitting creates multiple independent computations.

### 2. `is_solved` didn't check pending goals
**File:** `pyakl/engine.py`
**Fix:** Return False when `andb.goals` is non-empty. Prevents premature promotion.

### 3. Determinate promotion called `_try_guard` instead of `_try_andbox`
**File:** `pyakl/akl_engine.py`
**Fix:** `_propagate_failure` now calls `_try_andbox` when choice-box becomes determinate, ensuring pending goals are processed.

### 4. Unifier values not resolved on promotion
**File:** `pyakl/akl_engine.py`
**Fix:** Call `value.deref()` before propagating unifiers to parent. Fixes variable chain for recursive predicates.

### 5. `body_goals` not copied during subtree copy
**File:** `pyakl/copy.py`
**Fix:** Added copying of `body_goals` so split copies have their own body goals with proper variable substitution.

### 6. `is_external_var` returned False for plain `Var`
**File:** `pyakl/engine.py`
**Fix:** Query-level variables (plain `Var` without env) are now treated as external to all child and-boxes. Changed return value from `False` to `True` for non-ConstrainedVar.

### 7. Promotion used `is_local_var` instead of `not is_external_var`
**File:** `pyakl/akl_engine.py`
**Fix:** Changed condition to `not is_external_var(var, parent)` to correctly identify which variables should be bound during promotion.

### 8. Body goals appended instead of prepended during promotion
**File:** `pyakl/akl_engine.py`
**Fix:** Body goals are now inserted at the FRONT of parent's goal list (prepended). This ensures inner recursive calls complete before outer calls.

### 9. Body goals dereferenced during promotion
**File:** `pyakl/akl_engine.py`
**Fix:** Removed `_deref_term` call on body goals during promotion. Variables keep their original references and are dereferenced at execution time.

---

## Known Issues (Not Yet Fixed)

These issues were identified during code review:

### Priority 3: `??` (quiet wait) guard semantics wrong
**Severity:** Low
**Description:** `??` requires leftmost + determinate and should prune right siblings. Current `_try_guard` only checks determinate + quiet, not leftmost. Pruning is disabled for WAIT-type guards.

**Location:** `pyakl/akl_engine.py`, `_try_guard()` method

### Priority 6: Query vars are plain `Var`
**Severity:** Low
**Description:** Query variables stored as plain `Var` without upgrading to `ConstrainedVar`. Copy system treats non-ConstrainedVar as external and shares them across splits.

**Location:** `pyakl/akl_engine.py`, `solve()` and `_collect_query_vars()` methods

### Priority 7: Stability bookkeeping incomplete
**Severity:** Low
**Description:** No robust "make stable again / ancestor mark maintenance" mechanism. Can get stuck in wrong stability states (unstable forever or stable too early).

**Reference:** C implementation has `STABLE / XSTABLE / UNSTABLE / XUNSTABLE` states

### Priority 8: Negation not isolated
**Severity:** Medium
**Description:** `_try_negation` runs a "temp" and-box but shares the same engine instance, task queues, and `self.solutions`. Not a safe simulation of AKL negation.

**Location:** `pyakl/akl_engine.py`, `_try_negation()` method

---

## Fixed Issues (2025-12-06)

### Priority 1: Promotion missing environment merging ✓
**Fix:** Added `_rehome_local_vars()` method that updates the `env` pointer of all local variables from the promoted and-box to point to the parent's env.

### Priority 2: Candidate selection ignores WAIT-guard requirement ✓
**Fix:** Added guard type check in `_is_candidate()` to only allow splitting for WAIT guards.

### Priority 4: `_do_split` promotes wrong node ✓
**Fix:** Use `copy_candidate` directly instead of searching via `mother_copy.tried.tried`.

### Priority 5: `_copy_term_to_local` uses name-based mapping ✓
**Fix:** Use `id(var)` for variable identity mapping; only treat `_` (not `_X`) as truly anonymous

---

## File Structure

### Core Files

| File | Purpose |
|------|---------|
| `pyakl/akl_engine.py` | Main AKL execution engine with splitting semantics |
| `pyakl/engine.py` | Data structures: AndBox, ChoiceBox, EnvId, ConstrainedVar, ExState |
| `pyakl/copy.py` | Subtree copying for nondeterministic splitting |
| `pyakl/interpreter.py` | Alternative interpreter (generator-based, used by tests) |
| `pyakl/unify.py` | Unification algorithm |
| `pyakl/term.py` | Term representation (Var, Atom, Struct, Cons, etc.) |
| `pyakl/program.py` | Program and Clause representation |
| `pyakl/parser.py` | Prolog/AKL parser |
| `pyakl/builtin.py` | Built-in predicates |

### Documentation

| File | Purpose |
|------|---------|
| `docs/deep-guards.md` | Comprehensive analysis of guard semantics |
| `docs/architecture.md` | Technical design |
| `docs/vision.md` | Project goals |
| `dev-log/T-ENGINE-02-FIX.md` | Task documentation with all fixes |

### Reference Implementation

The C reference implementation is in `../akl-agents/`:
- `emulator/engine.c` - Guard handlers, splitting
- `emulator/copy.c` - Copying algorithm
- `emulator/exstate.c` - Suspension/wake
- `emulator/tree.h` - Data structures
- `doc/internals.tex` - Design document

---

## How to Continue

### Running Tests

```bash
# Run all tests
pytest

# Run specific test file
pytest tests/test_interpreter.py

# Run with verbose output
pytest -v
```

### Testing the AKL Engine Directly

```python
from pyakl.akl_engine import AKLWorker
from pyakl.program import load_string
from pyakl.parser import parse_term

prog = load_string('''
len([], 0).
len([_|T], N) :- len(T, M), N is M + 1.
''')

worker = AKLWorker(prog, debug=True)  # debug=True for trace output
solutions = worker.solve(parse_term('len([a,b,c], X)'))
print(solutions)  # [{'X': 3}]
```

### Next Steps (Recommended Order)

1. **Fix Priority 2 (candidate selection)** - Simple check to add WAIT-guard requirement
2. **Fix Priority 4 (`_do_split` wrong node)** - Track actual `copy_candidate` through the split
3. **Fix Priority 5 (variable identity)** - Use `id(var)` instead of `var.name` for mapping
4. **Fix Priority 1 (env merging)** - Most complex, may require refactoring EnvId handling

### Debugging Tips

- Use `debug=True` when creating `AKLWorker` for execution trace
- Key methods to instrument:
  - `_try_andbox()` - Main and-box processing
  - `_promote_andbox()` - Guard success handling
  - `_do_split()` - Nondeterministic splitting
  - `_try_unification()` - Unification with external var handling

---

## Architecture Notes

### AKL vs Prolog

AKL differs from Prolog in fundamental ways:

1. **No backtracking**: Nondeterminism is handled by COPYING computation trees (splitting)
2. **Guards**: Clauses have guards that must succeed before body executes
3. **External variables**: Variables from parent scopes cannot be bound directly - bindings are deferred
4. **Suspension**: Goals suspend when they would bind external variables
5. **Promotion**: When guard succeeds, and-box content moves to parent scope

### Key Invariants

1. **External variables**: Never bound directly, always through unifiers
2. **Splitting**: Only for solved WAIT-guard candidates
3. **Goal order**: Inner goals must complete before outer goals (prepend, not append)
4. **Variable identity**: Track by object identity, not name

### Data Flow

```
Query → create_root() → root ChoiceBox with one AndBox
                           ↓
                    _try_andbox() loop
                           ↓
              expand goals → new ChoiceBoxes
                           ↓
              guard succeeds → _promote_andbox()
                           ↓
              all solved → _record_solution()
                           ↓
              not solved, stable → _try_split()
```

---

## Contact

See `CLAUDE.md` for project conventions and task management workflow.
