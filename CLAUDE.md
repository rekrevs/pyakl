# CLAUDE.md

## Role

Ensure that all non-trivial work is traceable, reproducible, and aligned with the architecture. All meaningful work is a Task or a Backlog item.

## Project Context

PyAKL is a Python implementation of the Andorra Kernel Language (AKL). We are implementing AKL semantics at a high level using Python's garbage collection rather than porting the low-level C implementation.

Key documents:
- `docs/vision.md` - Goals and approach
- `docs/architecture.md` - Technical design
- `docs/wasm.md` - Background on WASM considerations
- `../akl-agents/` - Reference C implementation

## 1. Work Types

* **Tasks**
  Self contained work units with objective, acceptance criteria, tests, implementation, evidence, and explicit outcome. May have subtasks.
* **Backlog items**
  Future work seeds in `docs/backlog.md` (`B-*`). Not executable until turned into a Task.

## 2. IDs and Files

All work history lives under `dev-log/`.

* **Backlog items**
  * ID: `B-{CATEGORY}-{NN}`
  * Categories: `TERM`, `UNIFY`, `PARSE`, `ENGINE`, `BOX`, `BUILTIN`, `TEST`, `DOC`

* **Tasks**
  * ID: `T-{CATEGORY}-{NN}`
  * File: `dev-log/T-{CATEGORY}-{NN}.md`
  * Category should match source backlog item.

* **Subtasks**
  * ID: parent ID + `-{N}` (nesting allowed):
    `T-TERM-01-1`, `T-TERM-01-1-1`, etc.

* **ID allocation**
  For a new Task in a category, find highest `T-{CATEGORY}-NN`, increment `NN`, or start at `01`.

* **Template**
  All tasks and subtasks use `docs/TASK-TEMPLATE.md`.

## 3. Task States

Every Task has one state:

* `READY` - Can be started.
* `IN_PROGRESS` - Being worked on.
* `BLOCKED` - Waiting on subtasks or external dependency.
* `DONE` - All acceptance criteria met.
* `FAILED` - Attempted but not successful.
* `PARTIAL` - Some criteria met, rest deferred.

A parent Task becomes `BLOCKED` when it spawns subtasks and unblocks when they finish.

## 4. Parent Relationships

Each Task declares one parent in its header:

* **Backlog item `B-*`**
  On state change, update `docs/backlog.md`.

* **Task `T-*` (subtask)**
  On state change, update parent Task's Subtasks table.

* **User request**
  No file update required.

Child points to parent; parent lists children.

## 5. When To Create Subtasks

Create subtasks when:

1. Work naturally splits into several distinct subtasks.
2. Debugging is non-trivial and needs structured investigation.
3. A significant part of the task cannot proceed until another non-trivial part completes.

Do not create subtasks when:

* A single focused change will resolve the issue.
* Steps are sequential but tightly cohesive.
* You would create exactly one subtask.

Out of scope discoveries become new backlog items, not subtasks.

## 6. How Tasks Start

Tasks may come from:

1. **Backlog items** `B-*`.
2. **Direct user requests** to fix, debug, implement, or investigate.
3. **Reactive discovery** while working:
   * In scope for current Task: handle within that Task (with subtasks if needed).
   * Out of scope: create or update backlog item.
4. **Subtasks** spawned from parent Tasks.

## 7. Problem Solving and Debugging

When something fails or misbehaves in a non-trivial way:

1. **Stop** further execution.

2. **Document** under `## Obstacles` in the current Task:
   * Observed error.
   * Expected behavior.
   * What has already been tried.
   * Hypotheses what could be the problem.

3. **Remind yourself about the context**:
   * Read `docs/vision.md` and ensure to keep on track.
   * Read `docs/architecture.md` for design constraints.
   * Consult `../akl-agents/doc/` for reference behavior.

4. **Write a problem statement** and a proposed plan.

5. **Decide**:
   * Clear, in scope resolution: continue.
   * Out of scope for task: create or update backlog item, keep main Task focused.
   * No clear path: stop and present full context and problem description to the user.

Never iterate through multiple blind fix attempts without this pause and documentation.

## 8. Mapping Natural Language To Actions

The agent infers intent and chooses one of:

1. **Create Task now**
   Phrases like "Implement term classes", "Fix the parser bug".
   * Create new Task using template and next `T-{CATEGORY}-{NN}`.
   * Fill Objective, Acceptance Criteria, Parent, Context.
   * Start Task lifecycle.

2. **Add to backlog**
   Phrases like "Later", "Add to backlog", "Park this".
   * Create or update `B-XXX-NN` in `docs/backlog.md`.
   * Do not start a Task unless user also requests that.

3. **Work on existing Task**
   Phrases like "Continue that task", "Pick up T-TERM-01".
   * Resolve Task by ID or recent context.
   * Open its file and continue lifecycle.

4. **Work from backlog**
   Phrases like "Work on B-PARSE-02", "Take next parser backlog item".
   * From backlog item, create Task (with subtasks if multi step).
   * Set Parent to backlog ID.
   * Run Task lifecycle.

5. **Continue working, agent chooses**
   Phrases like "Continue working", "Do the next sensible step".
   Priority:
   1. Resume most recent open Task (Outcome not set).
   2. Otherwise choose a `[READY]` backlog item, create Task.
   3. If nothing is ready, report that and suggest options.

When intent is unclear, ask a brief clarifying question.

## 9. Task Lifecycle

All Tasks follow this sequence.

### 9.1 Create Task file

Using `docs/TASK-TEMPLATE.md`, fill:

* `ID` - next `T-{CATEGORY}-{NN}`.
* `Parent` - backlog ID, Task ID, or "User request".
* `Objective`.
* `Acceptance Criteria`.
* `Context` referencing:
  * `vision.md`, `architecture.md`,
  * relevant backlog or design doc details.

### 9.2 Tests first

Design or update tests required to prove the Acceptance Criteria:

* Unit tests for individual functions.
* Integration tests for component interaction.
* Comparison tests against reference behavior (if applicable).

Never weaken or remove regression tests without explicit justification in the Task file.

### 9.3 Minimal implementation

Make clean, well-designed and concise implementations that satisfy the Acceptance Criteria:

* Follow the architecture in `docs/architecture.md`.
* Use Python idioms (dataclasses, type hints, etc.).
* Avoid speculative abstractions or unrelated refactoring.

### 9.4 Verification

A Task is complete only when:

1. All new tests pass.
2. The relevant test suite passes (`pytest`).
3. Evidence (test outputs) is recorded in the Task file.

Tests may not be skipped without explaining why.

### 9.5 Outcome

Set one Outcome:

* `DONE` - All acceptance criteria met, evidence recorded.
* `FAILED` - Criteria not met; document why.
* `BLOCKED` - Cannot proceed; document blocker.
* `PARTIAL` - Some criteria met; record remaining work.

If not `DONE`:

* Explain in the Task.
* Update related backlog items (`[BLOCKED]`, refined description).
* Mention this explicitly when user next asks to "continue working".

### 9.6 Parent updates

On Task state change:

* Parent `B-*`: update `docs/backlog.md`.
* Parent `T-*`: update parent Task's Subtasks table.
* Parent "User request": no extra file changes.

### 9.7 Commit policy

One Task per commit (or a tight commit cluster).

* Commit message:
  `T-{CATEGORY}-{NN}: short description`
  Example: `T-TERM-01: implement basic term classes`.

## 10. `docs/backlog.md`

Each backlog item contains:

* ID: `B-{CATEGORY}-{NN}`.
* Readiness tag: `[READY]`, `[NEEDS-SPEC]`, `[BLOCKED]`, `[DONE]`.
* Short intent.
* "Next" pointer to Task(s).
* A Details section with context.

Using backlog items:

* Header informs Task Objective and Parent reference.
* Details inform Context and Acceptance Criteria.
* If item is multi step, plan subtasks accordingly.

Maintaining `docs/backlog.md`:

* When a Task resolves an item, mark `[DONE]`.
* If Task partially addresses it, update Details.
* If Task ends `BLOCKED`, mark backlog item `[BLOCKED]` with explanation.

## 11. Agent Behavior Checklist

While working:

* Always map user language to an intent type (create Task, backlog, existing Task, backlog Task, or continue).
* Never perform significant code or test edits without a Task file.
* Use the error handling protocol for non-trivial issues.
* If stuck with no clear plan, stop and present full context to the user.

After finishing work:

* Ensure Task file has updated Objective, Acceptance Criteria, Evidence, and Outcome.
* Ensure parent backlog item or Task is updated.
* Leave the repository in a coherent state (tests passing, docs consistent).

## 12. Reference Documentation

**IMPORTANT**: Always consult `../akl-agents/` as the ground truth for AKL behavior. This is NOT Prolog - AKL has its own semantics (concurrent constraint programming with committed choice).

When implementing AKL features, consult:

* `../akl-agents/doc/aklintro.tex` - Language introduction and semantics
* `../akl-agents/doc/internals.tex` - Implementation design (boxes, execution model)
* `../akl-agents/doc/user.texi` - Syntax, built-ins, and **REPL behavior**
* `../akl-agents/docs/porting/` - Architecture analysis
* `../akl-agents/emulator/` - C implementation source

Key AKL REPL conventions (from user.texi):
* Prompt: `| ?- `
* Success: shows bindings then `yes`
* Failure: `no`
* After bindings: `? ` prompt, press return to continue

For Python patterns:

* Use dataclasses for data structures
* Use type hints throughout
* Use pytest for testing
* Follow PEP 8 style

## 13. General Rules

- Run tests with `pytest` before marking tasks complete.
- Use type hints for all public functions and classes.
- Keep functions focused and small.
- Prefer composition over inheritance.
- Document non-obvious design decisions in code comments.
