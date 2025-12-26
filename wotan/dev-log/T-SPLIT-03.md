# Task: T-SPLIT-03

**Status:** IN_PROGRESS
**Parent:** User request (debugging qsort demo failure)
**Created:** 2025-12-09

---

## Objective

Fix variable environment tracking in split/copy to match akl-agents semantics. Currently, variables at the split boundary (mother's env) are incorrectly shared, causing spurious solutions with unbound variables (e.g., `quicksort([3,1,2], S)` returning `[1,2,3,H]`).

---

## Acceptance Criteria

- [ ] `quicksort([3,1,2], S)` returns exactly 1 solution: `S = [1,2,3]`
- [ ] `quicksort([3,1,4,1,5,9,2,6], S)` returns exactly 1 correct solution
- [ ] All demos in `pyakl/library/demos/` that should work, do work
- [ ] All existing tests continue to pass
- [ ] No spurious unbound variables (like `H`) in solutions

---

## Context

### Problem Discovery

When running `pyakl/library/demos/qsort.akl`:
```
quicksort([3,1,2], S) -> 2 solutions:
  {'S': [1, 2, 3]}      # correct
  {'S': [1, 2, 3, H]}   # SPURIOUS - unbound H
```

Other inputs like `[3,2,1]`, `[2,1]`, `[]`, `[1]` work correctly. The bug is specific to certain recursion patterns.

### Root Cause Analysis

Comparing `pyakl/copy.py` with `akl-agents/emulator/copy.c`:

**akl-agents approach:**
1. Variables are identified by their `env` pointer, not by dictionary membership
2. When copying, `NewEnv(old_env)` creates a fresh env that is a child of the copied parent
3. `InCopyEnv(var.env)` checks if variable's env is in the copied subtree
4. AndBox.env is set to NULL during copy to mark it as "being copied"
5. Forwarding pointers (`SaveTRM`) track original-to-copy mappings

**pyakl current approach:**
1. `is_local_env()` checks env hierarchy - similar concept
2. `is_split_copy=True` treats mother's env as EXTERNAL
3. `_copy_env()` returns external envs as-is (shared)
4. Variables at mother's env level get the SAME env object
5. `local_vars` dictionary exists but isn't authoritative

**The bug:**
With `is_split_copy=True`, variables at mother's env level are treated as external. Their env is NOT copied - they get the same env object. This means:
- Multiple split copies share the same env for boundary variables
- When checking locality later, these variables appear identical
- Bindings affect all copies because the variable object is shared

### Key Code References

**akl-agents/emulator/copy.c:**
- Lines 189-191: `InCopyUVA`, `InCopyGVA` - locality by env
- Lines 992-1025: `CopyUnbound` macro - creates fresh vars with `NewEnv()`
- Lines 395-407: AndBox marking during copy
- Lines 128-135: `SaveTRM` - forwarding pointer mechanism

**pyakl/copy.py:**
- Lines 58-76: `is_local_env()` - split_copy treats mother's env as external
- Lines 250-274: `_copy_env()` - external envs returned as-is
- Lines 329-435: `_copy_term()` - variable copying logic

---

## Implementation Plan

### Phase 1: Understand the exact failure mode

1. Add tracing to identify which variable `H` is and where it comes from
2. Track env IDs through the copy process
3. Identify the exact clause instantiation that creates the orphan variable

### Phase 2: Fix env copying for split boundary

Two possible approaches:

**Approach A: Copy mother's env but share variables**
- In split copies, copy mother's env to a fresh env
- Variables at mother's env become local (get fresh copies)
- But their VALUES should be shared (follow bindings)
- This matches akl-agents' `CopyUnbound` semantics

**Approach B: Track variables by identity, not env**
- Use forwarding pointers like akl-agents
- When a variable is copied, record the mapping
- On subsequent encounters, return the same copy
- More faithful to C implementation

### Phase 3: Verify and test

1. Run all demos
2. Run full test suite
3. Test edge cases (empty lists, single elements, duplicates)

---

## Subtasks

| ID | Description | Status |
|----|-------------|--------|
| T-SPLIT-03-1 | Add tracing to identify spurious H variable | READY |
| T-SPLIT-03-2 | Implement fix (approach TBD) | READY |
| T-SPLIT-03-3 | Verify demos work | READY |
| T-SPLIT-03-4 | Run full test suite | READY |

---

## Implementation

### Approach

TBD after Phase 1 investigation.

### Files Changed

- `pyakl/copy.py` - fix env/variable copying
- `pyakl/akl_engine.py` - potentially adjust split processing

### Key Decisions

TBD

---

## Testing

### Tests to Verify

```bash
# Demo tests
python -c "from pyakl.program import load_file; from pyakl.akl_engine import AKLWorker; from pyakl.parser import parse_term; p=load_file('pyakl/library/demos/qsort.akl'); w=AKLWorker(p,max_steps=10000); print(list(w.solve(parse_term('quicksort([3,1,2],S)'))))"

# Full test suite
pytest tests/ -v
```

---

## Evidence

TBD

---

## Obstacles

### Obstacle 1: Split copy variable sharing

**Observed:** `quicksort([3,1,2], S)` returns spurious `[1,2,3,H]`
**Expected:** Single solution `[1,2,3]`
**Tried:** Synchronous split processing with context isolation (T-SPLIT-02)
**Hypothesis:** Variables at mother's env aren't properly copied - they share the same env object, causing incorrect locality checks
**Resolution:** In progress

---

## Outcome

**Status:** IN_PROGRESS

---

## Revision History

| Date | Change |
|------|--------|
| 2025-12-09 | Created from debugging session |
