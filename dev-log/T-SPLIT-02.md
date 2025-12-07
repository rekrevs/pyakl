# Task: T-SPLIT-02

**Status:** DONE
**Parent:** B-SPLIT-01
**Created:** 2025-12-05

---

## Objective

Fix the task-based scheduler to properly handle nondeterminism using continuation-passing style.

---

## Acceptance Criteria

- [x] Scheduler handles recursive predicates (member, append) without infinite loops
- [x] Each branch has independent variable bindings via trail save/restore
- [x] Solutions are correctly captured
- [x] All existing tests pass
- [x] Nondeterministic programs work (permutation, 4-queens)

---

## Context

**References:**
- `dev-log/T-SPLIT-01.md` - Previous attempt and insights
- `docs/deep-guards.md` - Splitting semantics

**Key insight from T-SPLIT-01:**
The previous scheduler had binding management issues because it tried to maintain
multiple active branches with shared variables. Trail-based undo affected all branches.

**Solution approach:**
Use continuation-passing style (CPS):
1. Each goal is processed with an explicit continuation (remaining goals)
2. Predicate calls pass continuation through to `_try_clauses`
3. Solutions recorded only when continuation is empty
4. Trail save/restore at each choice point

This avoids mutable state issues because goals lists are passed explicitly, not modified in place.

---

## Implementation

### Design: Continuation-Passing Style

The key insight is to pass the "rest of the computation" explicitly:

```python
def _try_clauses(goal, clauses, continuation):
    for clause in clauses:
        save_trail()
        if unify(goal, clause.head):
            new_goals = clause.body + continuation
            _try_goals(new_goals)  # May record multiple solutions
        restore_trail()

def _try_goals(goals):
    if not goals:
        record_solution()
        return True
    return _try_goal(goals[0], goals[1:])

def _try_goal(goal, continuation):
    if is_builtin(goal):
        if call_builtin(goal):
            return _try_goals(continuation)
        return False
    return _try_clauses(goal, clauses, continuation)
```

This design:
1. Never modifies shared state (goals lists are passed, not mutated)
2. Records solutions at the right time (when continuation is empty)
3. Properly handles nondeterminism (each clause explored with full continuation)

---

## Files Changed

- `pyakl/scheduler.py` - Complete rewrite with CPS design

---

## Testing

```
$ python -c "from pyakl.scheduler import query_all; ..."

member(X, [a,b,c]) → [X=a, X=b, X=c]
append(X, Y, [1,2,3]) → 4 solutions
perm([1,2,3], P) → 6 solutions
queens(4, Q) → [Q=[3,1,4,2], Q=[2,4,1,3]]
```

---

## Evidence

```
$ pytest
============================= 507 passed in 0.24s ==============================
```

---

## Outcome

**Status:** DONE

**Summary:** Rewrote scheduler using continuation-passing style, which correctly
handles nondeterminism without the binding management issues of the previous approach.

The key difference from T-SPLIT-01's approach:
- T-SPLIT-01 tried to maintain multiple active branches (and-boxes) simultaneously
- T-SPLIT-02 processes one branch at a time with explicit continuation passing
- Trail save/restore at choice points provides proper isolation

This is functionally equivalent to the generator-based interpreter but with
explicit continuation management rather than Python generators.

---

## Revision History

| Date | Change |
|------|--------|
| 2025-12-05 | Created |
| 2025-12-05 | Implemented CPS-based scheduler |
| 2025-12-05 | All 507 tests pass, 4-queens works |
