# Task: T-ENGINE-02

**Status:** DONE
**Parent:** B-ENGINE-04
**Created:** 2025-12-05

---

## Objective

Research and design an approach for implementing AKL ports in Python.

The key challenge is: ports need to detect when they have no more references
(senders) and then close. In akl-agents this is handled by garbage collection.
We need to find a Python-idiomatic approach.

**Design Document:** [docs/ports.md](../docs/ports.md)

---

## Acceptance Criteria

- [x] Document how ports work in akl-agents (reference implementation)
- [x] Research Python GC mechanisms (weakref, __del__, gc module)
- [x] Evaluate different approaches for reference tracking
- [x] Design a solution suitable for PyAKL
- [x] Document trade-offs and limitations
- [x] Create implementation plan (may spawn subtasks)

---

## Context

References:
- `docs/vision.md` - PyAKL goals (use Python GC, not low-level)
- `docs/architecture.md` - technical design
- `../akl-agents/doc/aklintro.tex` - port semantics
- `../akl-agents/emulator/` - C implementation of ports

### How Ports Work in AKL

From `../akl-agents` documentation and code:

1. `open_port(Port, Stream)` creates a connected pair:
   - Port: receives messages via `@` operator
   - Stream: produces messages as a list (grows as messages arrive)

2. `Message@Port` sends Message to Port, which appears on Stream

3. Port closes when no more processes can send to it (no references)
   - Stream then terminates (becomes a proper list ending in `[]`)
   - This is detected via garbage collection

4. Ports are used for:
   - Concurrent communication between processes
   - Collecting results from multiple computations
   - Stream-based programming patterns

### Python GC Challenges

Python's garbage collection differs from WAM-style GC:

1. **Reference counting + cycle detector**: Objects freed when refcount
   hits zero, but cycles detected periodically

2. **__del__ timing**: Not guaranteed to run immediately or at all

3. **weakref**: Can track objects without preventing collection, but
   callbacks are tricky in multi-step operations

4. **No explicit scope**: Unlike WAM where variable scope is stack-based,
   Python objects live on heap with complex ownership

---

## Research Questions

1. **akl-agents mechanism**: How exactly does the C emulator detect
   that a port has no more references? Is it via:
   - Reference counting on port objects?
   - Trail-based tracking of who holds port references?
   - WAM heap GC detecting unreachable ports?

2. **Python approaches**:
   - Can we use `weakref.finalize()` to detect port abandonment?
   - Can we track which and-boxes hold port references and close
     when all such boxes die?
   - Can we use explicit reference counting (incref on copy, decref
     on box death)?
   - Can we use `gc.callbacks` for detection?

3. **Simplifications**: Can we implement a simpler port model that:
   - Requires explicit close?
   - Closes based on scope/and-box lifetime?
   - Uses Python asyncio patterns?

---

## Research Plan

### Phase 1: Understand akl-agents implementation

1. Read port-related code in `../akl-agents/emulator/`
2. Read `../akl-agents/doc/internals.tex` for design docs
3. Document the exact mechanism used

### Phase 2: Evaluate Python options

1. Prototype with `weakref.finalize()`
2. Prototype with explicit scope tracking
3. Prototype with manual refcounting
4. Test each with port usage patterns

### Phase 3: Design decision

1. Compare approaches on:
   - Correctness (ports close at right time)
   - Simplicity (maintainable code)
   - Performance (acceptable overhead)
   - Python-idiomaticness

2. Document chosen approach with rationale

---

## Research Findings

### Python `weakref.finalize()` Works!

Tested 2025-12-05: Python's reference counting + `weakref.finalize()` provides
exactly what we need:

```python
import weakref

class Port:
    def __init__(self):
        self.stream = []
        self._finalizer = weakref.finalize(self, Port._close_stream, self.stream)

    @staticmethod
    def _close_stream(stream):
        stream.append('$end')  # End marker - stream becomes proper list

    def send(self, msg):
        self.stream.append(msg)
```

**Key findings:**

1. **Immediate cleanup**: Unlike `__del__`, `finalize()` callbacks fire
   immediately when refcount hits zero (no waiting for cycle GC)

2. **Multiple references work**: Callback only fires when ALL references
   are gone - exactly like AKL port semantics

3. **Clean separation**: Stream can outlive port - stream is just a list
   that gets closed (terminated with marker) when port dies

**Remaining challenges for PyAKL integration:**

1. Port references embedded in Var bindings must count as references
2. When and-box dies/is pruned, its bindings must be released
3. Need to handle port in Struct args, list elements, etc.

The core mechanism is solved - the challenge is proper integration with
PyAKL's term/binding system.

---

## Implementation

### Approach

TBD - need to design integration with term system.

### Files Changed

TBD

---

## Obstacles

(To be filled during research)

---

## Outcome

**Status:** DONE

**Summary:** Completed comprehensive research on AKL ports. Key findings:

1. **akl-agents mechanism**: Uses a "close list" maintained during GC. When
   a port is not copied (unreachable), its `deallocate` method is called,
   which closes the stream by unifying its tail with NIL.

2. **Python solution**: `weakref.finalize()` provides exactly what we need.
   Reference counting triggers callback immediately when last reference
   drops, allowing us to close the stream.

3. **Design**: Created comprehensive design document at `docs/ports.md`
   covering:
   - Port data structures
   - open_port/2, send/2 implementation
   - Stream closure mechanism
   - Integration challenges and recommendations

**Next steps**: Implementation task (update B-ENGINE-04 to READY)

---

## Revision History

| Date | Change |
|------|--------|
| 2025-12-05 | Created |
| 2025-12-05 | Completed research, created docs/ports.md |
