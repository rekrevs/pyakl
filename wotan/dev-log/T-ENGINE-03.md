# Task: T-ENGINE-03

**Status:** DONE
**Parent:** B-ENGINE-04
**Created:** 2025-12-05

---

## Objective

Implement AKL ports for concurrent stream communication.

---

## Acceptance Criteria

- [x] Create `Port` term type with `weakref.finalize()` for automatic closure
- [x] Implement `open_port/2` - creates port/stream pair
- [x] Implement `send/2` and `send/3` - sends message to port
- [x] Support `@` operator as syntactic sugar for send
- [x] Port closes automatically when no references remain
- [x] Stream terminates with `[]` on port closure
- [x] Basic port tests pass
- [x] knights.akl loads and `knights/0` runs

---

## Context

References:
- `docs/ports.md` - Comprehensive design document
- `docs/vision.md` - PyAKL goals
- `../akl-agents/emulator/port.c` - Reference implementation
- `../akl-agents/demos/knights.akl` - Target demo using ports

---

## Implementation

### Approach

1. Added `Port` class to `pyakl/term.py` with `_PortState` helper
2. Used `weakref.finalize()` to detect port garbage collection
3. State holder pattern allows finalizer to access current stream tail
4. Added `open_port/2`, `send/2`, `send/3` builtins
5. Interpreter transforms `@` operator to `send/2` call

### Files Changed

- `pyakl/term.py`:
  - Added `_PortState` class (lines 366-378)
  - Added `Port` class (lines 380-488)
  - Port uses `__weakref__` slot for weak reference support

- `pyakl/builtin.py`:
  - Added `open_port/2` (lines 1287-1312)
  - Added `send/2` (lines 1315-1330)
  - Added `send/3` (lines 1333-1352)
  - Added `format/1` (lines 986-996) - needed by knights.akl

- `pyakl/interpreter.py`:
  - Added `@` operator handling (lines 170-175)

### Key Design Decisions

1. **State holder pattern**: The `_PortState` object holds the current stream
   tail and is passed to the finalizer. This allows the finalizer to close
   the correct (current) tail even after multiple sends have updated it.

2. **Immediate closure**: Python's reference counting + `weakref.finalize()`
   provides immediate closure when the last reference drops, matching AKL
   semantics.

3. **Initial stream capture**: The `stream` property returns `initial_stream`
   (the variable passed to `open_port/2`), not the current tail.

### Test Evidence

```
=== Basic Port Tests ===
Test 1: Create port and send messages
  Created port: {port:1:open}
  Initial stream: _Stream1
  After sends, stream: [hello, 42, world | _Stream1]

Test 2: Port closure via weakref
  Inside function - stream: [msg1, msg2 | _Stream2]
  After function returns and GC - stream: [msg1, msg2]
  Final tail is NIL: True

Test 3: Multiple references keep port alive
  After deleting p1 (p2 still holds ref) - stream: [a | _Stream3]
  Stream still open (tail is Var): True
  After deleting p2 - stream: [a, b]
  Final tail is NIL: True
```

Via interpreter:
```
Test 1: open_port/2
  open_port(P, S): P = {port:1:open}, S = _Stream1

Test 2: send/2
  Result: P = {port:2:open}, S = [hello, world | _Stream2]

Test 3: @ operator
  Result: P = {port:3:open}, S = [hello, 42 | _Stream3]
```

Knights.akl:
```
=== Testing knights/0 ===
THE KNIGHTS TOUR

This demonstration shows that there are a lot of
deterministic steps in a nondeterminstic puzzle.

Try knights(5), knights(6) or all(5).

Result: success
```

---

## Obstacles

**knights(5) times out**: The full knights tour problem requires AKL's
guard semantics (suspension, promotion, splitting) for efficient execution.
Our current interpreter does naive backtracking which is too slow for the
knights problem. This is expected - ports are working, but the concurrency
model that makes knights efficient is not yet implemented.

---

## Outcome

**Status:** DONE

**Summary:**
- Ports fully implemented with automatic closure via `weakref.finalize()`
- `open_port/2`, `send/2`, `send/3` builtins working
- `@` operator works as syntactic sugar for send
- Port closure correctly terminates stream with `[]`
- Multiple references keep port alive as expected
- knights.akl loads and `knights/0` intro message works
- All 445 tests still pass

**Limitations:**
- `knights(5)` requires full AKL guard semantics to run efficiently
- This is tracked in B-GUARD-01 (guard operators)

---

## Revision History

| Date | Change |
|------|--------|
| 2025-12-05 | Created |
| 2025-12-05 | Implemented ports, marked DONE |
