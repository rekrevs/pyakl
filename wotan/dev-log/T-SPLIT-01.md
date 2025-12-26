# Task: T-SPLIT-01

**Status:** PARTIAL
**Parent:** B-SPLIT-01
**Created:** 2025-12-05

---

## Objective

Implement and-box copying for nondeterministic splitting in AKL. This allows the interpreter to handle nondeterminism by copying computation state when multiple alternatives need to be explored.

---

## Acceptance Criteria

- [x] Implement deep copy of and-box subtrees
- [x] Copy local variables with fresh instances
- [x] External variables remain shared (not copied)
- [x] Implement candidate finding (leftmost solved wait-guard)
- [ ] Integrate splitting into execution scheduler (deferred)
- [x] Tests for nondeterministic programs (e.g., queens)
- [x] All existing tests pass

---

## Context

References:
- `docs/deep-guards.md` - Nondeterministic Splitting section
- `../akl-agents/emulator/copy.c` - Reference implementation of copying
- `../akl-agents/emulator/candidate.c` - Candidate finding algorithm
- `../akl-agents/doc/internals.tex` - Conceptual overview

### Key Concepts from Reference Implementation

**Splitting Process (from internals.tex):**
1. Find a candidate for choice splitting (leftmost solved wait-guard and-box)
2. Given candidate A, parent choice-box B, B's parent and-box C, parent choice-box D:
   - Apply choice splitting rule to A
   - Create copy A' of A
   - If choice-box B is determinate, promote remaining branch
   - Else if and-box C is stable, create task for more splitting
   - Promote the and-box A'

**Candidate Finding (from candidate.c):**
- Find leftmost and-box with GUARD_WAIT instruction that is solved (no pending goals)
- Search recursively through choice-box tree
- A candidate must not have a deeper candidate in its scope

**Copy Process (from copy.c):**
1. Copy is done top-down from "mother" and-box
2. When and-box is copied, env field set to NULL, status points to copy (for variable locality detection)
3. Variables are copied if local to copied subtree
4. External variables get their suspensions duplicated
5. Constraints and unifiers are copied
6. After copy, reset forwarding pointers and restore tree structure

### PyAKL Approach

Unlike the C implementation which uses low-level copying with forwarding pointers, we'll use Python's capabilities:

1. **Deep copy using dataclasses**: Use `copy.deepcopy()` with custom `__deepcopy__` methods
2. **Variable mapping**: Maintain a dict mapping old variables to new during copy
3. **Environment tracking**: Already in place from T-GUARD-01
4. **Generator-based backtracking**: Current interpreter uses generators; splitting will create parallel execution paths

### Design Considerations

The current interpreter uses generator-based backtracking which naturally handles choice points. The question is: do we need explicit splitting, or can we leverage the existing generator mechanism?

**Option A: True Splitting (copying)**
- More faithful to AKL semantics
- Needed for concurrent/parallel execution
- More complex to implement

**Option B: Generator-based nondeterminism**
- Simpler, already partially implemented
- Works for sequential execution
- May not handle all AKL idioms correctly

For this task, we'll implement Option A (true splitting) as it's required for proper AKL semantics, particularly for programs like N-queens where nondeterminism is essential.

---

## Implementation

### Phase 1: And-box Copying Infrastructure - DONE

Created `pyakl/copy.py` with:
- `CopyState`: Tracks mapping from original to copied objects
- `copy_andbox_subtree()`: Deep copy of and-box tree
- `_copy_term()`: Copy term with local variable substitution
- `_copy_env()`: Copy environment chain

Key insight: Local variables (created in copied subtree) get fresh copies; external variables (from parent scopes) remain shared.

### Phase 2: Candidate Finding - DONE

Implemented `find_candidate()` which finds the leftmost solved and-box suitable for nondeterministic promotion.

### Phase 3: Solution Capture Fix

Fixed issue where solutions showed unresolved variables. Added `ground_copy()` to `unify.py` which creates a copy of a term following all variable bindings, used when capturing solutions.

### Phase 4: Task-Based Scheduler - IN PROGRESS

Created `pyakl/scheduler.py` as an experimental task-based scheduler. Current status:

**Attempted approaches:**
1. Task queue with wake/recall/split handlers - Works for simple cases
2. Eager processing of all alternatives - Causes infinite loops with recursive predicates
3. Sequential processing with trail-based undo - Loses bindings when recording solutions

**Key insights:**
- The generator-based interpreter in `interpreter.py` is a valid sequential simulation
- True task-based execution requires fundamentally different binding management
- Each parallel branch needs truly independent variable bindings (copying)
- The copy infrastructure is in place but scheduler integration is complex

**Why trail-based undo doesn't work for parallel branches:**
When processing multiple clauses that each match a goal, each creates different bindings.
With a single trail, undoing for one branch affects all branches. Example:
```
foo(X) :- clause1, X=1.   % Branch 1: X=1
foo(X) :- clause2, X=2.   % Branch 2: X=2
```
If we process Branch 1, bind X=1, record solution, then undo for Branch 2,
the solution's binding is also undone (variables are shared references).

**Correct approach:** Use `copy_andbox_subtree()` to create independent copies.
Each copy has its own local variables, so bindings don't interfere.

**Remaining work:**
- Proper integration of splitting into scheduler (when stable, copy and explore)
- Guard suspension semantics
- Wake queue handling for suspended goals
- This will be needed for B-ENGINE-02/03 (promotion/splitting tasks)

---

## Files Changed

- `pyakl/copy.py` - New module with and-box copying logic
- `pyakl/scheduler.py` - Experimental task-based scheduler (not yet working)
- `pyakl/unify.py` - Added `ground_copy()` for solution capture
- `pyakl/interpreter.py` - Use `ground_copy()` in `_get_solution()`
- `tests/test_copy.py` - 30 tests for copy functionality and nondeterminism

---

## Testing

Tests in `tests/test_copy.py`:
- `TestCopyState`: 5 tests for locality detection
- `TestCopyEnv`: 2 tests for environment copying
- `TestCopyTerm`: 9 tests for term copying
- `TestCopyAndBox`: 4 tests for and-box tree copying
- `TestVarIndependence`: 2 tests for variable isolation
- `TestFindCandidate`: 3 tests for candidate finding
- `TestNondeterminism`: 4 integration tests (permutation, 4-queens, append, member)

---

## Evidence

```
$ pytest tests/test_copy.py -v
============================== 30 passed in 0.03s ==============================

$ pytest
============================== 507 passed in 0.23s ==============================
```

4-queens working correctly:
```python
>>> query_all(prog, "queens(4, Q)")
Found 2 solutions
  Solution 1: [3, 1, 4, 2]
  Solution 2: [2, 4, 1, 3]
```

---

## Outcome

**Status:** PARTIAL

**Summary:** Implemented core and-box copying infrastructure with proper local/external variable handling. Fixed solution capture to properly ground terms. Nondeterminism works correctly for sequential execution using generator-based interpreter. Created experimental task-based scheduler but integration is incomplete.

**What works:**
- Copy infrastructure (`copy.py`) - full and-box tree copying with proper local/external variable handling
- Candidate finding - leftmost solved wait-guard detection
- Generator-based interpreter - correctly handles nondeterminism (507 tests pass)
- Solution capture with `ground_copy()`

**What needs more work:**
- Task-based scheduler (`scheduler.py`) - experimental, binding management issues
- Guard suspension semantics
- True parallel branch exploration with proper copying

**Remaining work:**
- Fix scheduler binding management (each branch needs independent variables via copying)
- Integration of splitting into execution scheduler (when stable, copy and explore)
- This will be needed when implementing B-ENGINE-02/03 (promotion/splitting tasks)

---

## Revision History

| Date | Change |
|------|--------|
| 2025-12-05 | Created |
| 2025-12-05 | Implemented copy.py with and-box copying |
| 2025-12-05 | Added ground_copy for solution capture |
| 2025-12-05 | Added nondeterminism tests including 4-queens |
| 2025-12-05 | Marked PARTIAL - core done, scheduler deferred |
| 2025-12-05 | Added scheduler.py - experimental task-based scheduler |
| 2025-12-05 | Scheduler has binding management issues - needs redesign |
