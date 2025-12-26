# Task: T-BUILTIN-02

**Status:** PARTIAL
**Parent:** B-BUILTIN-02
**Created:** 2025-12-05

---

## Objective

Add missing built-in predicates needed for the knights tour demo
(`../akl-agents/demos/knights.akl`).

---

## Acceptance Criteria

- [x] Implement `functor_to_term/3` - create term with functor and arity
- [x] Implement `term_to_functor/3` - decompose term to functor and arity
- [x] Implement `dif/2` - disequality constraint
- [x] Implement `numberof/2` - count solutions
- [x] Implement `statistics/2` - runtime statistics
- [x] Implement `data/1` - nonvar check (used in guards)
- [ ] `knights(5)` demo runs and produces correct output

---

## Context

References:
- `docs/vision.md` - PyAKL goals
- `docs/architecture.md` - technical design
- `../akl-agents/environment/builtin.akl` - reference builtin definitions
- `../akl-agents/demos/knights.akl` - target demo

### Builtins Required by knights.akl

From code analysis:
- `functor_to_term(Name, Arity, Term)` - creates `Name(_,_,..._)` with Arity args
- `term_to_functor(Term, Name, Arity)` - extracts functor info from term
- `dif(X, Y)` - disequality (constraint that X and Y cannot unify)
- `numberof(Goal\Template, Count)` - count solutions to Goal
- `statistics(runtime, [Total, SinceLast])` - timing info
- `statistics(nondet, [Total, SinceLast])` - nondeterminism steps
- `data(X)` - check if X is non-variable (in guards)

### Notes

- `dif/2` in full AKL is a constraint - it may suspend if args are unbound.
  For PyAKL, we use a simpler version that just checks current unifiability.

- `numberof/2` uses sub-interpreter to collect all solutions.

- Ports (`open_port/2`, `@/2`) are NOT in scope for this task - see B-ENGINE-04.
  Knights.akl uses ports so full demo cannot run yet.

---

## Implementation

### Approach

1. Study `../akl-agents/environment/builtin.akl` for reference semantics
2. Implement `functor_to_term/3` and `term_to_functor/3` (straightforward)
3. Implement simple `dif/2` (fail if args unify, succeed otherwise)
4. Implement `statistics/2` with at least `runtime` support
5. Implement `numberof/2` using solution collection
6. Test with simplified knights.akl (without ports)

### Files Changed

- `pyakl/builtin.py` - added new builtins:
  - `functor_to_term/3` (lines 605-627)
  - `term_to_functor/3` (lines 630-655)
  - `dif/2` (lines 128-144)
  - `data/1` (lines 777-784)
  - `statistics/2` (lines 1277-1323)
  - `numberof/2` (lines 1232-1270)

### Test Evidence

```
Testing dif/2:
  dif(1, 2): pass
  dif(1, 1): FAIL (correctly fails)

Testing functor_to_term/3:
  functor_to_term(foo, 2, T): T = foo(_G7, _G9)

Testing term_to_functor/3:
  term_to_functor(bar(1,2,3), N, A): N = bar, A = 3

Testing statistics/2:
  statistics(runtime, _): pass
  statistics(runtime, [T, S]): T = 0, S = 0

Testing numberof/2:
  numberof(X\member(X, [1,2,3]), N): N = 3
```

Knights.akl loading and partial tests:
```
Loaded knights.akl successfully!
Predicates: 27

Testing make_board(3, B):
  Result: B = a(r(_G129, _G131, _G133), r(_G116, _G118, _G120), r(_G103, _G105, _G107))

Testing make_tiles(5, T):
  Result: T = tiles(t(_G1, _G2), ...)
```

---

## Obstacles

**Blocker: Ports not yet implemented**

Knights.akl uses `open_port/2` and the `@` send operator for concurrent
communication between monitors. These are complex primitives that require:
- Port/stream data structures
- Reference counting for automatic port closure
- The `@` operator for sending messages

This is tracked separately in B-ENGINE-04. The builtins implemented here
work correctly, but the full knights demo cannot run until ports are added.

---

## Outcome

**Status:** PARTIAL

**Summary:**
- All requested builtins implemented and tested:
  - `functor_to_term/3` ✓
  - `term_to_functor/3` ✓
  - `dif/2` ✓
  - `numberof/2` ✓
  - `statistics/2` ✓
  - `data/1` ✓ (bonus - needed by knights.akl guards)

- Knights.akl loads successfully
- Basic predicates (make_board, make_tiles) work
- Full demo blocked on ports implementation (B-ENGINE-04)

**Next:** Implement ports (B-ENGINE-04) to complete knights demo

---

## Revision History

| Date | Change |
|------|--------|
| 2025-12-05 | Created |
| 2025-12-05 | Implemented all builtins, marked PARTIAL (blocked on ports) |
