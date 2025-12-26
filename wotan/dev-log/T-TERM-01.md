# Task: T-TERM-01

**Status:** DONE
**Parent:** B-TERM-01
**Created:** 2025-12-04

---

## Objective

Implement the fundamental term representation classes for PyAKL.

---

## Acceptance Criteria

- [x] Variables have identity (same name != same var)
- [x] Atoms are interned (same name == same object)
- [x] Variables support binding and dereferencing
- [x] Lists can be constructed and deconstructed
- [x] All term types implement `deref()` method
- [x] Tests pass for all term types

---

## Context

- `docs/vision.md` - Terms are the fundamental data representation
- `docs/architecture.md` - Detailed class designs
- `../akl-agents/doc/internals.tex` - Original term specification

From internals.tex:
> "There are three types of terms: atomic, structures and variables. Implicitly, all terms have an identity."

Key insight: Variables must support **identity** via Python's `is` operator, not just equality.

---

## Subtasks

None - this is a focused implementation task.

---

## Implementation

### Approach

1. Create `pyakl/term.py` with all term classes
2. Create `tests/test_term.py` with comprehensive tests
3. Use `__slots__` for memory efficiency and clear attribute definitions
4. Use atom interning via `__new__` override

### Files Changed

- `pyakl/__init__.py` - Package init with exports
- `pyakl/term.py` - Term classes (Term, Var, Atom, Integer, Float, Struct, Cons, NIL)
- `pyproject.toml` - Project configuration with pytest
- `tests/__init__.py` - Test package init
- `tests/test_term.py` - 60 comprehensive tests

### Key Decisions

1. **Var uses `__slots__`** - Ensures predictable memory layout and prevents accidental attribute addition
2. **Atom interning via `__new__`** - Atoms with same name are identical objects
3. **NIL is an Atom** - Empty list represented as interned Atom("[]")
4. **Cons for lists** - Separate class rather than special Struct for clarity
5. **deref() is abstract** - All terms must implement, ensures consistent interface

---

## Testing

### Tests Added

- `tests/test_term.py` - 60 tests covering:
  - TestVar: 12 tests (identity, binding, deref chains, unbind)
  - TestAtom: 8 tests (interning, equality, repr)
  - TestInteger: 5 tests (value, equality, hash)
  - TestFloat: 4 tests (value, equality)
  - TestStruct: 7 tests (creation, equality with vars)
  - TestList: 14 tests (Cons, make_list, repr, list_to_python)
  - TestDeref: 3 tests (nested vars, in structs/lists)
  - TestTermIsInstance: 7 tests (all types are Term)

### Test Results

```
============================== 60 passed in 0.02s ==============================
```

---

## Evidence

All acceptance criteria verified by passing tests:

1. **Variables have identity**: `test_var_identity_different_objects` - two `Var("X")` are different objects
2. **Atoms are interned**: `test_atom_interning` - two `Atom("foo")` are same object
3. **Variables support binding/deref**: `test_var_bind`, `test_var_deref_bound`, `test_var_deref_chain`
4. **Lists constructable**: `test_make_list_*`, `test_list_to_python`
5. **All terms implement deref()**: `TestTermIsInstance` tests all types
6. **All tests pass**: 60/60 passed

---

## Obstacles

### Obstacle 1: NIL repr was quoted

**Observed:** `repr(NIL)` returned `"'[]'"` instead of `"[]"`
**Expected:** `"[]"` without quotes
**Resolution:** Added special case for `[]` in Atom.__repr__

---

## Outcome

**Status:** DONE

**Summary:** Implemented complete term representation with all required classes (Var, Atom, Integer, Float, Struct, Cons, NIL) and helper functions (make_list, list_to_python). All 60 tests pass.

---

## Revision History

| Date | Change |
|------|--------|
| 2025-12-04 | Created |
| 2025-12-04 | Completed - all tests passing |
