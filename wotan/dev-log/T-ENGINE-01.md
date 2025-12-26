# Task: T-ENGINE-01

**Status:** DONE
**Parent:** User request
**Created:** 2025-12-05

---

## Objective

Adapt `../akl-agents/environment/qa.akl` to work as the PyAKL REPL instead of the current Python-based REPL. This ensures the REPL follows authentic AKL semantics.

---

## Acceptance Criteria

- [x] `qa.akl` (or simplified version) loads and runs in PyAKL
- [x] REPL uses AKL's reflection mechanism for query execution
- [x] Prompt shows `| ?- `
- [x] Solutions displayed with ` ? ` prompt for more
- [x] `yes`/`no` printed appropriately
- [x] Basic commands work: `halt`
- [ ] History (`h`) - deferred to future task

---

## Context

The current Python REPL (`pyakl/repl.py`) implements its own iteration over solutions using Python generators. This is not how AKL works.

The real AKL REPL (`qa.akl`) uses:
- `reflective_call(W, Goal, Stream)` - creates execution state, runs goal
- `reflective_next(W, W1)` - continues to next solution
- Stream-based I/O with accumulator syntax (`-In-Out`)

### Dependencies Needed

From `qa.akl`, the following primitives are required:

1. **Reflection builtins** (from `reflection.c`):
   - `reflective_call/3`
   - `reflective_next/2`
   - `reflective_print/2`

2. **I/O with accumulators**:
   - `stdin/1`, `stdout/1`
   - `format/2` with `~w`, `~q`, `~n`
   - `getc/1`, `fflush/1`
   - `read_term/1`

3. **Guard execution**:
   - `->` (commit)
   - `|` (guard test)

4. **Other builtins**:
   - `garbage_collect/0`
   - `instance/4` (term copying with variable dict)

---

## Implementation

### Phase 1: Reflection Primitives (DONE)

Added `Reflection` class to `pyakl/term.py`:
- Wraps a generator from `interpreter.solve()`
- Tracks interpreter instance and result stream
- Has `exhausted` flag for completion state

Added builtins to `pyakl/builtin.py`:
- `reflective_call/3` - Creates reflection object, advances to first result
- `reflective_next/2` - Advances to next result
- `reflective_print/2` - Prints reflection state (for debugging)
- `reflection/1` - Type check for reflection objects

### Phase 2: Stream I/O Builtins (DONE)

Added `StreamHandle` class for wrapping Python file objects.

Added builtins:
- `stdin/1`, `stdout/1` - Get stream handles
- `fflush/1` - Flush output stream
- `getc/2` - Read character from stream (returns code or -1 for EOF)
- `read_term/2` - Read and parse a term, returns `term(T)` or `exception(E)`
- `format/2` - Format string with `~w`, `~q`, `~n` codes
- `fnl/1` - Write newline

### Phase 3: qa.akl Adaptation (DONE)

Created `pyakl/library/qa.akl` - simplified REPL:
- Main loop reads terms and processes them
- Uses reflection for query execution
- Handles EOF, parse errors, `halt` command
- Displays bindings with ` ? ` prompt
- Supports `;` for more solutions

Updated `pyakl/repl.py`:
- `run_akl_repl()` loads qa.akl and runs `main/0`
- Falls back to Python REPL if qa.akl fails to load
- Python REPL class retained for testing and fallback

---

## Evidence

All 448 tests pass:
```
============================= 448 passed in 0.22s ==============================
```

REPL output:
```
$ echo -e "X = 1 ; X = 2.\n;\nhalt." | python -m pyakl.repl
PyAKL REPL
Type halt. to exit

| ?-
X = 1 ?
X = 2 ?
no
| ?-
```

---

## Outcome

**Status:** DONE

All acceptance criteria met except history command, which is deferred.

---

## Revision History

| Date | Change |
|------|--------|
| 2025-12-05 | Created |
| 2025-12-05 | Completed - reflection primitives, I/O builtins, qa.akl adaptation |
