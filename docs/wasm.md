# WebAssembly Feasibility Analysis for AGENTS

**Date:** December 2025
**Status:** Analysis Complete
**Author:** Generated with assistance from Claude Code

---

## Executive Summary

This document analyzes the feasibility of compiling the AGENTS system (AKL concurrent constraint programming) to WebAssembly (WASM). The analysis covers three approaches:

1. **Direct Emscripten Compilation** - Compile existing C code to WASM
2. **Adaptation to WasmGC** - Modify to use WASM's native garbage collection
3. **Full Rewrite** - Reimplement in a modern, memory-safe language

**Conclusion:** Direct compilation is theoretically possible but would require significant work. A full rewrite in Rust targeting WASM may be the most future-proof approach for serious production use.

---

## Table of Contents

1. [AGENTS Architecture Overview](#agents-architecture-overview)
2. [WebAssembly Capabilities (2025)](#webassembly-capabilities-2025)
3. [Compatibility Analysis](#compatibility-analysis)
4. [Option 1: Direct Emscripten Compilation](#option-1-direct-emscripten-compilation)
5. [Option 2: WasmGC Integration](#option-2-wasmgc-integration)
6. [Option 3: Full Rewrite](#option-3-full-rewrite)
7. [Precedents: Other Prologs in WASM](#precedents-other-prologs-in-wasm)
8. [Recommendations](#recommendations)
9. [Parallel Repository Strategy](#parallel-repository-strategy)

---

## AGENTS Architecture Overview

### Memory Management

AGENTS uses **explicit memory management with tagged pointers** - a technique common in 1990s Prolog/Lisp implementations:

```c
// From emulator/term.h - Tagged pointer scheme:
// Reference:                    0:::::::::::::::::::::::::::::00
// Unbound unconstrained var:    0:::::::::::::::::::::::::::::01
// List cell:                    0:::::::::::::::::::::::::::0010
// Small integer:                0::::::::::::::::::::::::::00110
// Atom:                         0::::::::::::::::::::::::::10110
```

Key characteristics:
- **Tagged pointers:** Low bits encode type information (2-5 bits)
- **Mark bit:** High bit (bit 63 on 64-bit) used for GC marking
- **Small integers:** Encoded directly in pointer bits (57-bit range on 64-bit)
- **Direct addressing:** No indirection through object headers

### Garbage Collection

Custom mark-and-sweep GC in `emulator/gc.c`:
- Uses the high bit of tagged pointers as mark bit
- Forwarding pointers during compaction
- Scavenger algorithm for efficient copying
- Integrates with constraint system for suspended goals

### Abstract Machine

Warren Abstract Machine (WAM) variant with concurrency extensions:
- **Threaded code:** Uses GCC's computed goto (`&&label`) for fast dispatch
- **Hard register allocation:** Maps VM registers to CPU registers via `asm("r15")` etc.
- **Three-box model:** AND boxes, choice boxes, and contexts for concurrent execution

---

## WebAssembly Capabilities (2025)

### WASM 3.0 (September 2025)

The [Wasm 3.0 specification](https://webassembly.org/news/2025-09-17-wasm-3.0/) includes:

1. **WasmGC (Garbage Collection)**
   - Struct and array heap types
   - Managed by host VM's garbage collector
   - Unboxed tagged integers supported
   - No built-in object system - compilers define layout

2. **64-bit Memory (memory64)**
   - Memories can use i64 addresses instead of i32
   - Expands from 4GB to theoretical 16EB

3. **Tail Call Optimization**
   - Essential for interpreter dispatch loops
   - ~12% performance benefit over trampolining

### What WASM Lacks

1. **No computed goto**
   - WASM has structured control flow only (no arbitrary jumps)
   - [Design issue #796](https://github.com/WebAssembly/design/issues/796) - rejected
   - Must use switch dispatch or tail calls

2. **No direct hardware register access**
   - Can't map VM registers to CPU registers
   - All register allocation done by WASM runtime

3. **No raw pointer manipulation**
   - Pointers are i32 offsets into linear memory
   - Can't use pointer high bits for tags in the native CPU sense
   - Tagged pointers must be simulated in linear memory

---

## Compatibility Analysis

### Tagged Pointers

| Aspect | AGENTS Approach | WASM Compatibility |
|--------|-----------------|-------------------|
| Low-bit tags | Use 2-5 low bits of pointers | **Works** - i32 arithmetic preserves this |
| High-bit mark | Use bit 63 for GC marking | **Works** - i64 arithmetic, but limited to 4GB memory with i32 |
| Pointer extraction | Mask off tag bits | **Works** - standard bitwise ops |
| Type dispatch | Switch on tag bits | **Works** - but slower than native |

**Verdict:** Tagged pointers **work in linear memory** but lose the hardware-level efficiency they were designed for.

### Threaded Code / Computed Goto

The core execution loop in `emulator/engine.c` uses:

```c
#ifdef THREADED_CODE
static address label_table[] = {
    &&CaseLabel(OPCODE1),
    &&CaseLabel(OPCODE2),
    // ...50+ opcodes
};
// Dispatch: goto *label_table[op];
#endif
```

**WASM Alternative:** Use tail calls or switch dispatch:

```c
// Tail call approach (with -O2 and __attribute__((musttail)))
void dispatch(int op, State *s) {
    switch(op) {
        case OP1: return [[musttail]] handle_op1(s);
        case OP2: return [[musttail]] handle_op2(s);
        // ...
    }
}
```

**Verdict:** **Significant refactoring required.** Expect 20-40% performance loss vs native threaded code.

### Hard Register Allocation

From `emulator/regdefs.h`:
```c
#if defined(__x86_64__)
#define REGISTER1 asm("r15")   // write_mode
#define REGISTER2 asm("r14")   // andb
#define REGISTER5 asm("rbx")   // areg
#define REGISTER6 asm("rbp")   // yreg
#endif
```

**WASM Impact:** These pragmas are simply ignored - no CPU register control in WASM.

**Verdict:** **No code change needed** - pragmas become no-ops. Some performance loss.

### Garbage Collection

Two options for WASM:

1. **Keep custom GC in linear memory**
   - Compile existing gc.c
   - Works but doesn't benefit from host GC optimizations
   - Memory limited to WASM linear memory growth rules

2. **Convert to WasmGC**
   - Fundamental rewrite of memory representation
   - Terms become WasmGC structs/arrays
   - Host GC manages lifetime automatically
   - Much smaller binary (no GC code shipped)

**Verdict:** Custom GC is **easier initially**, WasmGC is **better long-term**.

---

## Option 1: Direct Emscripten Compilation

### Approach

Use [Emscripten](https://emscripten.org/) to compile existing C code to WASM with minimal changes.

### Required Changes

1. **Disable threaded code**
   ```c
   // In engine.c - use switch dispatch instead
   #undef THREADED_CODE
   ```

2. **Handle setjmp/longjmp**
   - Used for exception handling in AGENTS
   - Emscripten supports this but with overhead
   - Consider refactoring to explicit error returns

3. **File I/O abstraction**
   - AGENTS uses `fopen`, `fread`, etc.
   - Emscripten provides virtual filesystem (MEMFS, IDBFS)
   - Need to bundle boot.pam, comp.pam as preloaded assets

4. **Parser compatibility**
   - Bison-generated parser should work
   - May need `%pure-parser` directive (already required for ARM64)

5. **Build system**
   ```bash
   emconfigure ./configure --without-gmp --without-fd
   emmake make
   ```

### Estimated Effort

| Task | Effort |
|------|--------|
| Build system adaptation | 2-3 days |
| Disable/refactor threaded code | 1-2 weeks |
| setjmp/longjmp handling | 3-5 days |
| File I/O adaptation | 2-3 days |
| Testing and debugging | 2-3 weeks |
| **Total** | **5-8 weeks** |

### Pros
- Preserves existing codebase
- Builds on working x86-64/ARM64 ports
- Maintains compatibility with native builds

### Cons
- Carries 30-year-old code patterns
- Custom GC in linear memory (not optimal)
- Performance likely 50-70% of native
- Large binary size (Emscripten overhead)

---

## Option 2: WasmGC Integration

### Approach

Rewrite memory management to use [WasmGC](https://v8.dev/blog/wasm-gc-porting) structs and arrays, keeping the rest of the system in C compiled via Emscripten.

### Architecture Changes

```
Current:                        WasmGC:
┌─────────────────┐            ┌─────────────────┐
│  Tagged Terms   │            │  WasmGC Structs │
│  in Linear Mem  │     →      │  (managed heap) │
├─────────────────┤            ├─────────────────┤
│  Custom GC      │            │  Host GC        │
│  (gc.c)         │     →      │  (V8/SpiderMon) │
├─────────────────┤            ├─────────────────┤
│  WAM Engine     │            │  WAM Engine     │
│  (engine.c)     │     →      │  (adapted)      │
└─────────────────┘            └─────────────────┘
```

### Required Rewrites

1. **Term representation** (term.h)
   - Define WasmGC struct types for each term type
   - Replace tagged pointer macros with WasmGC accessors

2. **Allocation** (storage.h)
   - Replace `NEW()` macros with WasmGC allocation
   - Remove heap management code

3. **GC integration** (gc.c)
   - Delete most of gc.c
   - Keep only root registration for stacks

4. **Engine adaptation** (engine.c)
   - Update term access patterns
   - Keep dispatch logic (switch-based)

### Estimated Effort

| Task | Effort |
|------|--------|
| WasmGC struct definitions | 2-3 weeks |
| Term access layer rewrite | 3-4 weeks |
| Storage system removal | 1-2 weeks |
| Engine adaptation | 2-3 weeks |
| Constraint system updates | 2-3 weeks |
| Testing and debugging | 4-6 weeks |
| **Total** | **14-21 weeks** |

### Pros
- Modern memory management
- Smaller binary (no GC code)
- Better integration with browser GC
- More future-proof

### Cons
- Massive rewrite effort
- Two divergent codebases to maintain
- WasmGC still evolving

---

## Option 3: Full Rewrite

### Approach

Reimplement AGENTS in a modern, memory-safe language (Rust recommended) that compiles cleanly to WASM.

### Why Rust?

1. **Native WASM target** - `wasm32-unknown-unknown`
2. **Memory safety** - No manual memory management bugs
3. **WasmGC integration** - Rust GC crates can target WasmGC
4. **Modern tooling** - Cargo, clippy, excellent IDE support
5. **Precedent** - Scryer Prolog is written in Rust

### Architecture

```
┌─────────────────────────────────────┐
│          akl-agents-rs              │
├─────────────────────────────────────┤
│  Parser        │  Bison-like (LALR) │
│  (parser/)     │  or Pratt parser   │
├────────────────┼────────────────────┤
│  Terms         │  Rust enums        │
│  (term.rs)     │  with tagged union │
├────────────────┼────────────────────┤
│  Engine        │  Match dispatch    │
│  (engine.rs)   │  or trait objects  │
├────────────────┼────────────────────┤
│  GC            │  Rust ownership or │
│  (gc.rs)       │  WasmGC via crate  │
├────────────────┼────────────────────┤
│  Constraints   │  Trait-based       │
│  (fd.rs)       │  constraint system │
└─────────────────────────────────────┘
```

### Estimated Effort

| Component | Effort |
|-----------|--------|
| Term representation & unification | 3-4 weeks |
| Parser (AKL syntax) | 4-6 weeks |
| WAM-style engine | 6-8 weeks |
| Compiler (AKL → bytecode) | 6-8 weeks |
| Concurrency model (and/choice boxes) | 4-6 weeks |
| FD constraint solver | 4-6 weeks |
| Built-in predicates | 4-6 weeks |
| WASM-specific integration | 2-3 weeks |
| Testing with AKL programs | 4-6 weeks |
| **Total** | **37-53 weeks** (~9-12 months) |

### Pros
- Clean, modern codebase
- Memory-safe by construction
- Excellent WASM support
- Maintainable long-term
- Can exceed original performance

### Cons
- Largest effort by far
- Need to rediscover/reimplement 1990s research
- Risk of diverging from original semantics

---

## Precedents: Other Prologs in WASM

### SWI-Prolog WASM

[SWI-Prolog](https://github.com/SWI-Prolog/swipl-wasm) successfully runs in browsers via Emscripten:

- Uses custom GC in linear memory
- Virtual filesystem for file I/O
- Full feature set except native C extensions
- [NPM package available](https://www.npmjs.com/package/swipl-wasm)

**Relevance:** Demonstrates that a complex Prolog with custom GC can work in WASM.

### Scryer Prolog

[Scryer Prolog](https://www.scryer.pl/wasm) is written in Rust:

- Native WASM target via Rust toolchain
- Modern implementation of ISO Prolog
- [WASM module](https://www.scryer.pl/wasm) for browser integration

**Relevance:** Demonstrates Rust as viable implementation language for Prolog in WASM.

### Trealla Prolog

C-based Prolog compiled to WASM:

- Uses Emscripten
- Simpler than SWI-Prolog
- Shows minimal viable approach

---

## Recommendations

### Short-term (Proof of Concept)

**Approach:** Option 1 - Direct Emscripten compilation

1. Create branch `wasm-poc`
2. Add Emscripten build configuration
3. Disable threaded code, use switch dispatch
4. Bundle boot files as MEMFS assets
5. Target: Working REPL in browser

**Goal:** Validate feasibility, identify blockers

### Medium-term (Production WASM)

**Approach:** Option 2 - WasmGC adaptation OR clean Emscripten port

Based on POC results:
- If Emscripten works well → Polish and optimize
- If major issues → Consider WasmGC integration

### Long-term (Next Generation)

**Approach:** Option 3 - Rust rewrite

Consider creating `akl-agents-rs` if:
- Serious production use is intended
- Modern IDE/tooling is important
- Memory safety is a priority
- Team has Rust expertise

---

## Parallel Repository Strategy

If pursuing Option 3 (Rust rewrite), structure as:

```
akl-agents/           # Original C codebase (reference)
├── emulator/
├── compiler/
├── docs/
└── ...

akl-agents-rs/        # New Rust implementation
├── src/
│   ├── term.rs       # Term representation
│   ├── engine.rs     # WAM engine
│   ├── parser.rs     # AKL parser
│   ├── compiler.rs   # AKL → bytecode
│   ├── gc.rs         # GC integration
│   ├── fd.rs         # FD constraints
│   └── wasm.rs       # WASM-specific bindings
├── tests/
│   └── akl/          # Test programs from original
├── Cargo.toml
└── README.md
```

### Incremental Approach

1. **Phase 1:** Core term representation + unification
2. **Phase 2:** Simple WAM (no concurrency)
3. **Phase 3:** Parser + basic compiler
4. **Phase 4:** Concurrency (and/choice boxes)
5. **Phase 5:** Constraint system
6. **Phase 6:** WASM optimization

Each phase produces a working subset that can be tested against original.

---

## Conclusion

Compiling AGENTS to WebAssembly is **feasible** but requires significant work regardless of approach:

| Approach | Effort | Risk | Future-Proof |
|----------|--------|------|--------------|
| Emscripten (Option 1) | Medium (5-8 weeks) | Low | Medium |
| WasmGC (Option 2) | High (14-21 weeks) | Medium | High |
| Rust Rewrite (Option 3) | Very High (9-12 months) | Medium | Very High |

**Recommendation:** Start with Option 1 as a proof of concept. If successful and WASM deployment is a priority, consider Option 3 for a clean, maintainable implementation.

The tagged pointer scheme and custom GC **do work** in WASM's linear memory - they just lose the hardware-level optimizations they were designed for. Modern WasmGC provides a better path forward but requires fundamental architectural changes.

---

## References

- [WebAssembly 3.0 Announcement](https://webassembly.org/news/2025-09-17-wasm-3.0/)
- [WasmGC Porting Guide (V8)](https://v8.dev/blog/wasm-gc-porting)
- [Emscripten Documentation](https://emscripten.org/docs/)
- [SWI-Prolog WASM Build](https://www.swi-prolog.org/build/WebAssembly.md)
- [Scryer Prolog](https://github.com/mthom/scryer-prolog)
- [WASM Design: Goto Discussion](https://github.com/WebAssembly/design/issues/796)
- [Interpreter Dispatch in WASM (Python discussion)](https://discuss.python.org/t/interpreter-dispatch-and-performance-on-webassembly/27246)
