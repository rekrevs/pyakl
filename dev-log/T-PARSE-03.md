# Task: T-PARSE-03

**Status:** READY
**Parent:** B-PARSE-02
**Created:** 2025-12-05

---

## Objective

Research how akl-agents handles `!` (cut/commit) when it appears as a goal
in the clause body (e.g., `:- !,`) vs as a guard operator (e.g., `! body`).

Determine whether PyAKL should support the `:- !,` syntax and document
the semantic differences.

---

## Acceptance Criteria

- [ ] Document how akl-agents parser handles `!` in different positions
- [ ] Document the semantic meaning of `!` as goal vs `!` as guard
- [ ] Determine if `:- !,` is valid AKL or Prolog compatibility
- [ ] Decision: support in PyAKL or document as incompatibility
- [ ] If supporting: implement the syntax handling

---

## Context

References:
- `docs/vision.md` - PyAKL goals
- `docs/architecture.md` - technical design
- `../akl-agents/doc/aklintro.tex` - AKL language introduction
- `../akl-agents/doc/user.texi` - User manual
- `../akl-agents/compiler/` - Parser/compiler source
- `../akl-agents/environment/prolog.akl` - Prolog compatibility

Demos using `:- !,` syntax:
- `../akl-agents/demos/qsort.akl`
- `../akl-agents/demos/mergesort.akl`
- `../akl-agents/demos/iostreams.akl`

Demos using `! body` syntax (works in PyAKL):
- `../akl-agents/demos/lookup.akl`

---

## Research Questions

1. **Parser behavior**: How does the akl-agents parser tokenize and
   parse `:-!,` vs `:-guard!body` vs `:-guard|body`?

2. **Semantic difference**: Is `head :- !, body.` equivalent to
   `head :- true ! body.` (commit with true guard)?

3. **Prolog compatibility**: Is this syntax for running Prolog programs
   in AKL? Does `environment/prolog.akl` transform this?

4. **Guard position**: In AKL, is `!` only valid in guard position, or
   can it appear anywhere in the body?

---

## Implementation

### Approach

TBD based on research findings.

### Files Changed

TBD

---

## Obstacles

(To be filled during research)

---

## Outcome

**Status:** READY

**Summary:** Task created, ready for research.

---

## Revision History

| Date | Change |
|------|--------|
| 2025-12-05 | Created |
