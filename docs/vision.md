# PyAKL Vision

**Date:** December 2025
**Status:** Draft
**Purpose:** Define the goals and approach for PyAKL

---

## What is PyAKL?

PyAKL is a Python implementation of the **Andorra Kernel Language (AKL)**, a concurrent constraint programming language developed at SICS in the early 1990s. Rather than porting the low-level C implementation, PyAKL implements the AKL semantics at a high level, leveraging Python's garbage collection and dynamic nature.

---

## Goals

### Primary Goals

1. **Semantic Fidelity** - Correctly implement AKL semantics as described in the original papers and documentation
2. **Readability** - The implementation should serve as a readable specification of AKL
3. **Correctness over Performance** - Get it working correctly first; optimize later if needed

### Secondary Goals

1. **Educational Value** - Help people understand AKL and concurrent constraint programming
2. **WASM Deployment** - Eventually run in browsers via Pyodide
3. **Experimentation Platform** - Enable exploration of AKL extensions and variations

### Non-Goals (for now)

1. **Performance Parity** - We will not match the C implementation's speed
2. **Full Compatibility** - Some low-level features may be omitted or simplified
3. **Production Use** - This is primarily a research/educational implementation

---

## Approach: High-Level Interpretation

### Why Not a WAM-Style Engine?

The original AGENTS system compiles AKL to bytecode for a Warren Abstract Machine (WAM) variant. This approach:

- Requires explicit memory management with tagged pointers
- Uses complex control stacks (trail, wake, task, etc.)
- Optimizes for 1990s hardware constraints

In Python, we get garbage collection for free. Fighting Python's memory model to implement tagged pointers and manual GC would be counterproductive.

### Our Approach: Direct Semantic Implementation

Instead of compiling to bytecode, we:

1. **Parse** AKL source to an AST
2. **Represent** the AST as AKL Terms (using Python objects)
3. **Interpret** by directly executing the semantic rules

This is analogous to how teaching Prologs (like miniKanren implementations) work - they prioritize clarity over speed.

---

## Core Concepts

### Terms

AKL terms are the fundamental data representation:

| Term Type | Description | Python Representation |
|-----------|-------------|----------------------|
| **Variable** | Unbound placeholder | `Var` class with identity |
| **Atom** | Named constant | `Atom` class or interned string |
| **Integer** | Numeric value | Python `int` |
| **Float** | Floating point | Python `float` |
| **Structure** | `functor(arg1, ..., argN)` | `Struct` class |
| **List** | `[H|T]` or `[]` | `Cons` / `Nil` classes |

**Critical:** Variables must support **identity** (not just equality). Two variables with the same name but different creation points are distinct. Python's `is` operator and `id()` function provide this.

### Unification

Unification binds variables to terms:

```python
# X = foo(Y, Z) binds X to the structure foo(Y, Z)
# If X was already bound to foo(A, B), then Y=A and Z=B
```

Key properties:
- **Symmetric:** `X = Y` is the same as `Y = X`
- **Transitive:** If `X = Y` and `Y = Z`, then `X = Z`
- **Occurs Check:** `X = f(X)` fails (unless allowing rational trees)

### And-Boxes and Choice-Boxes

AKL's concurrent execution is structured around two types of "boxes":

**And-Box:** Represents a conjunction of goals executing concurrently
- Contains local variables, constraints, and child choice-boxes
- Has a "guard" and "body" separated by a guard operator
- Can be in states: alive, solved, suspended, failed

**Choice-Box:** Represents a disjunction (alternative clauses)
- Contains multiple and-boxes (one per clause)
- Only one alternative succeeds; others are pruned or explored

```
choice-box
├── and-box (clause 1)
│   ├── guard goals...
│   └── body goals...
├── and-box (clause 2)
│   └── ...
└── and-box (clause 3)
    └── ...
```

### Guard Operators

AKL has three guard operators controlling clause selection:

| Operator | Syntax | Meaning |
|----------|--------|---------|
| **Wait** | `?` or default | Nondeterminate choice (don't know) |
| **Commit** | `\|` | Committed choice (don't care), first success wins |
| **Cut** | `!` | Like Prolog cut, prunes siblings |

### Constraint Store and Suspension

Goals can **suspend** waiting for variables to become bound:

```akl
append([], Y, Y).
append([H|T], Y, [H|R]) :- append(T, Y, R).
```

If called with `append(X, Y, Z)` where all are unbound, execution suspends until X is bound.

---

## Execution Model

### No Explicit Stacks

Unlike the C implementation with its trail, wake, task, and context stacks, we use:

- **Python's call stack** for procedure calls
- **Python's GC** for memory management
- **Python data structures** (lists, dicts) for collections

### Scheduler

A simple scheduler manages and-box execution:

1. Pick an and-box to work on
2. Try to make progress (reduce a goal, unify, etc.)
3. If suspended, move to another and-box
4. If stable (no progress possible), attempt choice splitting
5. Repeat until solved or failed

### Choice Splitting (Nondeterminate Promotion)

When computation is "stuck" (stable), we pick a candidate choice-box and:

1. Copy the subtree for one alternative
2. Promote that alternative determinately
3. Continue with remaining alternatives in the original

This implements AKL's "don't know" nondeterminism.

---

## Phase 1: Foundation

The first implementation phase focuses on:

### 1.1 Term Representation

- `Term` base class
- `Var` with identity and optional binding
- `Atom`, `Integer`, `Float`
- `Struct` with functor and args
- `Cons` and `Nil` for lists

### 1.2 Term Read/Write

- Parser for AKL term syntax
- Pretty-printer for terms
- This validates our term representation

### 1.3 Unification

- Basic unification algorithm
- Occurs check (optional, can be disabled)
- Variable dereferencing (follow binding chains)

### 1.4 Simple Execution

- And-box and choice-box structures
- Basic goal reduction (procedure call)
- Suspension and waking

---

## Success Criteria

Phase 1 is complete when we can:

```python
# Parse and print terms
t = parse_term("foo(X, [1,2,3], bar)")
print(t)  # foo(X, [1, 2, 3], bar)

# Unify terms
X = Var("X")
unify(X, Atom("hello"))
assert X.value == Atom("hello")

# Run simple programs
result = run("""
    append([], Y, Y).
    append([H|T], Y, [H|R]) :- append(T, Y, R).
    ?- append([1,2], [3,4], Z).
""")
assert result["Z"] == parse_term("[1,2,3,4]")
```

---

## References

### Original Documentation

- `../akl-agents/doc/aklintro.tex` - Introduction to AKL
- `../akl-agents/doc/internals.tex` - Implementation design (PAM)
- `../akl-agents/doc/user.texi` - AGENTS User Manual

### Key Papers

- Haridi & Janson: "Kernel Andorra Prolog and its Computation Model" (1990)
- Janson: "AKL - A Multiparadigm Programming Language" (PhD thesis, 1994)
- Saraswat: "Concurrent Constraint Programming" (1993)

### Related Implementations

- MiniKanren (Scheme) - Similar high-level approach
- Scryer Prolog (Rust) - Modern Prolog implementation
- SWI-Prolog - Reference Prolog implementation
