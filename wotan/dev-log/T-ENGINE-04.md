# T-ENGINE-04: PyAKL Compliance with AKL Execution Model v2

## Parent
User request: Implement exact AKL semantics per docs/akl-execution-model-v2.md

## Objective
Bring PyAKL into full compliance with the reference AKL implementation semantics as documented in `docs/akl-execution-model-v2.md`.

## Acceptance Criteria
1. Status flags include all five states (DEAD, STABLE, UNSTABLE, XSTABLE, XUNSTABLE)
2. Trail stores (var, old_value) pairs correctly
3. Context stack stores four pointers (task, recall, wake, trail)
4. SuspendTrail converts trail to constraints + suspensions
5. Reinstall mechanism restores bindings on wake
6. Guard semantics check Solved AND Quiet AND EmptyTrail
7. Promotion uses promote_constraints and promote_context patterns
8. Candidate finding checks guard types correctly
9. Copy operation duplicates suspensions properly
10. All existing tests pass
11. New compliance tests pass

## Implementation Phases

### Phase 1: Status Flags (XSTABLE/XUNSTABLE)
- Add XSTABLE and XUNSTABLE to Status enum
- Add ResetState/SetState operations
- Verify: Unit tests for status transitions

### Phase 2: Field Name Correction
- Rename AndBox.prev to AndBox.previous (match reference)
- Update all references
- Verify: All existing tests still pass

### Phase 3: EmptyTrail Check
- Add empty_trail() method to ExState
- Implement based on context.trail position comparison
- Verify: Unit tests for empty_trail in various states

### Phase 4: Guard Semantics
- Update guard checks to require Solved AND Quiet AND EmptyTrail
- GUARD_WAIT: Solved AND Last
- GUARD_COMMIT: Solved AND Quiet AND EmptyTrail
- GUARD_CUT: Solved AND Quiet AND EmptyTrail AND Leftmost (or Last fallback)
- Verify: Guard behavior tests

### Phase 5: SuspendTrail Operation
- Implement suspend_trail() function
- Convert each trail entry to unifier constraint
- Add suspension to each variable
- Unbind variable back to old value
- Upgrade UVA to SVA (ConstrainedVar) if needed
- Verify: Unit tests for suspend/wake cycle

### Phase 6: Reinstall Mechanism
- Implement reinstall_andbox() function
- Re-bind variables from unifier constraints
- Re-trail the bindings
- Verify: Wake correctly restores bindings

### Phase 7: Promote Constraints
- Implement promote_constraints() per exstate.c
- Unbind each constraint
- Check if variable now local to parent
- If local: wake and rebind
- If external: re-link to parent
- Verify: Promotion correctly handles variables

### Phase 8: Promote Context
- Implement promote_context() per exstate.c
- Compact trail (remove now-local entries)
- Wake suspensions on promoted variables
- RestoreContext and PopContext
- Verify: Context correctly managed on promotion

### Phase 9: Candidate Finding
- Update _find_candidate to check guard types
- GUARD_WAIT: candidate if solved
- GUARD_CUT: candidate if solved AND leftmost
- Others: recurse but don't return as candidate
- Verify: Candidate finding tests

### Phase 10: Copy Suspension Handling
- Implement copy_local_suspensions()
- Implement update_external_suspensions()
- Verify: Copied computations have correct suspensions

### Phase 11: Integration Testing
- Run all existing tests
- Add comprehensive compliance tests
- Test suspension/wake cycles
- Test promotion with constraints
- Test splitting with shared externals

## Context
- Reference: ../akl-agents/emulator/engine.c, exstate.c, copy.c
- Documentation: docs/akl-execution-model-v2.md
- Existing: pyakl/engine.py, akl_engine.py, copy.py

## Status
DONE

## Evidence

All 11 phases completed with passing tests:

### Phase 1: Status Flags ✓
- Added XSTABLE (value=3) and XUNSTABLE (value=4) to Status enum
- Added reset_state() and set_state() methods to AndBox
- Updated is_stable() and is_unstable() to include X-states

### Phase 2: Field Name Correction ✓
- Renamed ChoiceBox.prev to ChoiceBox.previous (AndBox already had previous)
- Updated all references in engine.py, akl_engine.py, copy.py

### Phase 3: EmptyTrail Check ✓
- Added empty_trail() method to ExState
- Compares context trail position to current trail length

### Phase 4: Guard Semantics ✓
- Updated _try_guard in akl_engine.py with proper conditions:
  - GUARD_WAIT/NONE: Solved AND Last
  - GUARD_COMMIT: Quiet AND EmptyTrail AND Solved
  - GUARD_ARROW: Solved AND Quiet AND EmptyTrail AND Leftmost
  - GUARD_CUT: Solved AND (Quiet AND EmptyTrail AND Leftmost OR Last)

### Phase 5: SuspendTrail ✓
- Implemented suspend_trail() in engine.py
- Converts trail entries to unifier constraints + suspensions
- Unbinds variables and upgrades to ConstrainedVar if needed

### Phase 6: Reinstall Mechanism ✓
- Implemented reinstall_andbox() in engine.py
- Re-binds variables from unifier constraints
- Calls set_state() to remove suspended marker

### Phase 7: Promote Constraints ✓
- Implemented promote_constraints() in engine.py
- Handles local/external variable transitions
- Wakes suspensions and updates bindings appropriately

### Phase 8: Promote Context ✓
- Implemented promote_context() in engine.py
- Compacts trail, wakes suspensions on local variables
- RestoreContext and PopContext properly handled

### Phase 9: Candidate Finding ✓
- Updated _is_candidate() in akl_engine.py
- GUARD_WAIT/NONE: candidate if solved
- GUARD_CUT: candidate if solved AND leftmost
- Other guards: NOT candidates

### Phase 10: Copy Suspension Handling ✓
- Implemented _copy_suspension_list() in copy.py
- Added _duplicate_external_suspensions()
- Properly maps and-box references in copied suspensions

### Phase 11: Integration Testing ✓
All integration tests pass:
```
=== PyAKL Compliance Integration Tests ===
1. Testing module imports... PASS
2. Testing status flags... PASS
3. Testing field naming... PASS
4. Testing EmptyTrail check... PASS
5. Testing guard semantics... PASS
6. Testing SuspendTrail... PASS
7. Testing reinstall... PASS
8. Testing promote_constraints... PASS
9. Testing promote_context... PASS
10. Testing copy subtree... PASS
=== All Integration Tests Passed! ===
```

## Outcome
DONE - PyAKL now implements the AKL execution model semantics as documented in docs/akl-execution-model-v2.md.

Key changes:
- engine.py: Status flags, EmptyTrail, SuspendTrail, reinstall, promote_constraints, promote_context
- akl_engine.py: Guard semantics, candidate finding
- copy.py: Suspension handling during copy
