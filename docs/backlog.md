# PyAKL Backlog

## Categories

| Category | Description |
|----------|-------------|
| TERM | Term representation (Var, Atom, Struct, etc.) |
| UNIFY | Unification algorithm |
| PARSE | Parser and lexer |
| PRINT | Term pretty-printing |
| ENGINE | Execution engine and scheduler |
| BOX | And-box and choice-box structures |
| PROG | Program storage and clause compilation |
| BUILTIN | Built-in predicates |
| REPL | Interactive interpreter |
| CONSTRAINT | Constraint system (equality, FD) |
| MODULE | Module system |
| TEST | Testing infrastructure |
| DOC | Documentation |

---

## Phase 1: Foundation

### B-TERM-01 [DONE] Implement basic Term classes

Implement the fundamental term representation classes.

**Details:**
- `Term` base class with `deref()` method
- `Var` class with identity, binding, and suspension list
- `Atom` class with interning
- `Integer` and `Float` classes
- `Struct` class with functor and args
- `Cons` and `Nil` for lists
- `make_list()` helper function

**Acceptance Criteria:**
- Variables have identity (same name != same var)
- Atoms are interned (same name == same object)
- Variables support binding and dereferencing
- Lists can be constructed and deconstructed

**Completed:** T-TERM-01 (60 tests passing)

---

### B-PARSE-01 [DONE] Implement term parser

Parse AKL term syntax into Term objects.

**Details:**
- Lexer for AKL tokens (variables, atoms, numbers, operators)
- Parser for terms (atoms, structures, lists)
- Handle operator syntax (infix =, arithmetic)
- Support quoted atoms and strings
- Full clause parsing with operator precedence

**Acceptance Criteria:**
- Parse atoms: `foo`, `'hello world'`
- Parse numbers: `42`, `3.14`
- Parse variables: `X`, `_`, `_Foo`
- Parse structures: `foo(X, Y)`, `bar(1, baz(Z))`
- Parse lists: `[]`, `[1,2,3]`, `[H|T]`, `[a,b|Rest]`
- Parse full clauses: `head :- guard ? body.`

**Depends on:** B-TERM-01

**Completed:** T-PARSE-01 (178 tests passing, all 45 AKL demo files parse)

---

### B-PRINT-01 [DONE] Implement term printer

Pretty-print terms back to AKL syntax.

**Details:**
- Print all term types
- Handle operator precedence for infix notation
- Print lists in readable form
- Show variable bindings optionally

**Acceptance Criteria:**
- Round-trip: `parse(print(t)) == t` for all terms
- Lists print as `[a, b, c]` not `[a|[b|[c|[]]]]`
- Operators print in infix: `head :- body` not `:-(...)`
- Variables print with their names

**Depends on:** B-TERM-01

**Completed:** T-PARSE-01 (combined with parser task)

---

### B-UNIFY-01 [DONE] Implement unification

Implement the unification algorithm for terms.

**Details:**
- Basic unification: var-var, var-term, term-term
- Occurs check (optional, can be disabled)
- Handle all term types
- Trail bindings via ExState
- Integrate with local vs external variable handling

**Acceptance Criteria:**
- `unify(X, 42)` binds X to 42
- `unify(f(X,Y), f(1,2))` binds X=1, Y=2
- `unify(X, f(X))` fails with occurs check
- `unify([H|T], [1,2,3])` binds H=1, T=[2,3]

**Depends on:** B-TERM-01, B-BOX-01

**Completed:** T-UNIFY-01 (59 tests passing)

---

## Phase 2: Execution Structures

### B-BOX-01 [DONE] Implement And-box and Choice-box

Implement the And-box and Choice-box structures for goal execution.

**Details:**
- And-box: status, env, unifiers, constraints, continuations
- Choice-box: alternatives chain, predicate reference
- Status management (DEAD, STABLE, UNSTABLE)
- Environment IDs for scope tracking
- Constrained variables with suspension support
- Suspension records linking goals to variables

**Acceptance Criteria:**
- And-boxes track execution state and local variables
- Choice-boxes manage clause alternatives
- Variables can have suspended goals
- Scope tracking distinguishes local vs external variables

**Depends on:** B-TERM-01

**Completed:** T-BOX-01 (49 tests passing)

---

### B-ENGINE-01 [DONE] Implement ExState and task queues

Implement the global execution state structure.

**Details:**
- Task queue (PROMOTE, SPLIT, START, ROOT)
- Wake queue for and-boxes
- Recall queue for choice-boxes
- Trail for variable bindings (undo support)
- Context stack for save/restore

**Acceptance Criteria:**
- Tasks can be queued and dequeued
- Trail supports binding and undo
- Context can be saved and restored

**Depends on:** B-BOX-01

**Completed:** T-BOX-01 (combined with box structures)

---

### B-PROG-01 [DONE] Implement program storage and clause compilation

Implement predicate database and clause preprocessing.

**Details:**
- `Clause` dataclass: head, guard, guard_type, body, variable info
- `Predicate` dataclass: functor, arity, clause list
- `Program` class: predicate lookup by name/arity
- `compile_clause()`: parse clause term into Clause structure
- `load_file()`: load .akl source files
- Guard type enum: NONE, WAIT, QUIET_WAIT, ARROW, COMMIT, CUT

**Acceptance Criteria:**
- Clauses are parsed and stored by predicate
- Guard structure is recognized and extracted
- Head/guard/body are separated correctly
- Variables in clause are collected
- Files can be loaded into program

**Depends on:** B-PARSE-01

**Completed:** T-PROG-01 (43 tests passing)

---

### B-BUILTIN-01 [DONE] Implement core built-ins

Implement essential built-in predicates.

**Details:**
- Control: `true`, `fail`
- Unification: `=`, `\=`, `==`, `\==`
- Arithmetic: `is`, `<`, `>`, `=<`, `>=`, `=:=`, `=\=`
- I/O: `write`, `writeln`, `nl`, `put`
- Meta: `functor`, `arg`, `=..`, `copy_term`
- Type checking: `var`, `nonvar`, `atom`, `number`, `integer`, `float`, `compound`, `is_list`, `atomic`
- List: `length`

**Acceptance Criteria:**
- `true` succeeds, `fail` fails
- `X = Y` unifies X and Y
- `X is 1 + 2` binds X to 3
- `write(hello), nl` prints "hello\n"

**Depends on:** B-UNIFY-01

**Completed:** T-BUILTIN-01 (51 tests passing)

---

### B-INTERP-01 [DONE] Implement simple interpreter (Horn clauses)

Implement basic interpreter for Horn clause programs.

**Details:**
- Goal execution: predicate lookup, clause matching
- Conjunction (`,`) and disjunction (`;`) handling
- Generator-based backtracking for choice points
- Negation as failure (`\+`)
- Basic guard support (guards execute as goals)
- Fresh variable renaming for clauses

**Acceptance Criteria:**
- Facts can be queried
- Rules with bodies execute correctly
- Backtracking finds multiple solutions
- Recursive predicates work (member, append, factorial, quicksort)
- Guarded clauses work with basic semantics

**Depends on:** B-PROG-01, B-UNIFY-01, B-BUILTIN-01

**Completed:** T-INTERP-01 (47 tests passing)

---

### B-GUARD-01 [BLOCKED] Implement guard operators

Implement wait, commit, and cut guard operators.

**Details:**
- Wait (?) - nondeterminate guard
- Quiet wait (??) - ordered guard
- Commit (|) - committed choice
- Arrow (->) - conditional
- Cut (!) - prune siblings
- Guard evaluation in execution loop
- Promotion mechanism

**Acceptance Criteria:**
- Guards suspend when needed
- Promotion occurs when guards succeed
- Cut prunes alternatives

**Depends on:** B-INTERP-01

**Blocked by:** Need basic interpreter working first

---

### B-SPLIT-01 [BLOCKED] Implement and-box copying

Implement and-box copying for nondeterministic splitting.

**Details:**
- Deep copy of and-box subtree
- Copy local variables
- Copy suspensions
- Copy constraints
- Handle forwarding pointers

**Depends on:** B-GUARD-01

**Blocked by:** Need guards working first

---

### B-REPL-01 [DONE] Implement REPL

Implement interactive read-eval-print loop.

**Details:**
- Query parsing from user input (`?- query.`)
- Clause addition for building programs
- Solution display with variable bindings
- "More?" prompting for multiple solutions
- File loading command (`[file].`)
- `listing.` to show loaded predicates
- Command-line entry point

**Acceptance Criteria:**
- User can enter queries
- Solutions are displayed
- User can request more solutions
- Files can be loaded
- Programs can be built interactively

**Depends on:** B-INTERP-01

**Completed:** T-REPL-01 (21 tests passing)

---

## Phase 3: Full AKL

### B-GUARD-02 [BLOCKED] Full guard semantics

Complete guard implementation with all AKL semantics.

**Details:**
- External variable suspension
- Stability detection
- Leftmost alternative checking
- Quiet vs non-quiet guards

**Depends on:** B-GUARD-01, B-SPLIT-01

---

### B-ENGINE-02 [BLOCKED] Implement promotion

Implement determinate and nondeterminate promotion.

**Details:**
- Determinate promotion (single alternative)
- Guard promotion rules
- Constraint propagation on promotion

**Depends on:** B-GUARD-02

---

### B-ENGINE-03 [BLOCKED] Implement choice splitting

Implement nondeterminate promotion via copying.

**Details:**
- Stability detection
- Candidate selection
- Subtree copying
- Scheduling after split

**Depends on:** B-ENGINE-02

---

## Phase 4: Extensions

### B-MODULE-01 [BLOCKED] Implement module system

Implement module system for program organization.

**Details:**
- Module declarations
- Import/export
- Qualified names

**Blocked by:** Need basic interpreter first

---

### B-CONSTRAINT-01 [BLOCKED] Implement FD constraints

Implement finite domain constraint solver.

**Details:**
- Domain variables
- Basic constraints: `#=`, `#<`, `#>`, etc.
- Propagation
- Labeling

**Blocked by:** Need basic engine working first

---

## Infrastructure

### B-TEST-01 [DONE] Set up pytest infrastructure

Set up testing framework.

**Details:**
- pytest configuration
- Test fixtures for terms
- Helper functions for testing

**Completed:** Part of initial setup

---

### B-DOC-01 [DONE] Create initial documentation

Create vision and architecture docs.

**Details:**
- vision.md
- architecture.md
- CLAUDE.md
- backlog.md
- TASK-TEMPLATE.md
- akl-execution-state.md

**Completed:** Initial setup and T-BOX-01

---

## Superseded Items

### OLD-B-BOX-01 [SUPERSEDED]
Superseded by B-BOX-01.

### OLD-B-BOX-02 [SUPERSEDED]
Superseded by B-BOX-01.

### OLD-B-ENGINE-01 [SUPERSEDED]
Superseded by B-ENGINE-01.

### OLD-B-PARSE-02 [SUPERSEDED]
Clause parsing included in B-PARSE-01/T-PARSE-01.

---

## Implementation Order

**Sprint 1: Basic Interpreter - COMPLETED**

1. ✅ B-UNIFY-01 - Unification (59 tests)
2. ✅ B-PROG-01 - Program storage (43 tests)
3. ✅ B-BUILTIN-01 - Built-ins (51 tests)
4. ✅ B-INTERP-01 - Simple interpreter (47 tests)
5. ✅ B-REPL-01 - REPL (21 tests)

**Total: 448 tests passing**

**Sprint 2: Full AKL Semantics - NEXT**

1. B-GUARD-01 - Guard operators (suspension, promotion)
2. B-SPLIT-01 - And-box copying (nondeterministic promotion)
3. B-ENGINE-02 - Promotion mechanism
4. B-ENGINE-03 - Choice splitting

**Test Programs (in order):**
1. ✅ Facts only: `likes(mary, food).`
2. ✅ Simple recursion: `member/2` (Horn clause version)
3. ✅ Arithmetic: `factorial/2`, `fibonacci/2`
4. ✅ Lists: `append/3`, `reverse/2`, `quicksort/2`
5. With guards: `member/2` with `??` (after B-GUARD-01)
6. Nondeterminism: `queens/1` (after B-SPLIT-01)

---

## Phase 5: Advanced Features

### B-BUILTIN-02 [PARTIAL] Add builtins for knights.akl demo

Add missing built-in predicates needed for the knights tour demo.

**Details:**
- `dif/2` - Disequality constraint (fail if args unify)
- `functor_to_term/3` - Create term with functor and arity (unbound args)
- `term_to_functor/3` - Decompose term to functor and arity
- `numberof/2` - Count solutions (like bagof but returns count)
- `statistics/2` - Runtime statistics (at least `runtime` and `nondet`)
- `data/1` - Check if argument is non-variable

**Acceptance Criteria:**
- [x] `functor_to_term(foo, 3, T)` creates `foo(_,_,_)`
- [x] `term_to_functor(foo(a,b), F, N)` binds F=foo, N=2
- [x] `dif(X, Y)` succeeds when X and Y cannot unify
- [x] `numberof(X\goal(X), N)` counts solutions
- [x] `statistics/2` returns runtime and nondet counts
- [x] `data/1` works as nonvar check
- [ ] knights(5) demo runs successfully (blocked on ports)

**Depends on:** B-INTERP-01

**Task:** T-BUILTIN-02 (PARTIAL)

**Notes:**
- All builtins implemented and tested
- Full demo blocked on ports (B-ENGINE-04)

---

### B-ENGINE-04 [DONE] Implement ports (streams)

Implement AKL ports for concurrent stream communication.

**Design Document:** [docs/ports.md](ports.md)

**Details:**
- `open_port/2` - Create port/stream pair
- Port receives messages via `@` operator (send to port)
- Stream produces messages as they arrive
- Ports must detect when no more references exist and close
- Use Python `weakref.finalize()` for automatic closure

**Acceptance Criteria:**
- [x] `open_port(Port, Stream)` creates connected port/stream
- [x] `X@Port` sends X to Port, appears on Stream
- [x] Port closes when no more senders reference it
- [ ] cipher.akl and knights.akl demos work (requires guard semantics)

**Depends on:** B-INTERP-01

**Tasks:**
- T-ENGINE-02 (research) - DONE
- T-ENGINE-03 (implementation) - DONE

**Notes:**
- Ports implemented and working
- Full demos (knights, cipher) require guard semantics (B-GUARD-01)

---

### B-PARSE-02 [READY] Investigate `!` as goal vs guard

Research how akl-agents handles `!` (cut/commit) in different positions.

**Details:**
- In AKL, `!` can appear as:
  - Guard operator: `head :- guard ! body.` (commit)
  - Goal in body: `head :- !, body.` (Prolog-style cut?)
- Some demos (qsort.akl, mergesort.akl, iostreams.akl) use `:- !,`
- lookup.akl uses `! true` which parses as commit guard

**Questions to answer:**
1. Is `:- !,` valid AKL syntax or legacy Prolog compatibility?
2. How does the akl-agents parser/compiler handle this?
3. Should PyAKL support both forms?
4. What is the semantic difference (if any)?

**Files to consult:**
- `../akl-agents/doc/aklintro.tex` - Language syntax
- `../akl-agents/doc/user.texi` - User manual
- `../akl-agents/compiler/` - Parser/compiler code
- `../akl-agents/environment/prolog.akl` - Prolog compatibility layer

**Acceptance Criteria:**
- Document the intended semantics of `!` in all positions
- Decide whether PyAKL should support `:- !,` syntax
- If yes, implement; if no, document as incompatibility

---

## Notes

- Keep everything simple first - no indexing, no optimization
- Error handling should follow ../akl-agents patterns
- Module system deferred to Phase 4
- FD constraints deferred until basic engine works
