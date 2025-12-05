"""
Tests for AKL execution engine data structures.
"""

import pytest
from pyakl.term import Var, Atom, Integer, Struct
from pyakl.engine import (
    # Status enums
    Status, TaskType, SuspensionType,
    # Core classes
    EnvId, ConstrainedVar, Suspension,
    AndBox, ChoiceBox, AndCont, ChoiceCont,
    Task, TrailEntry, Context, ExState,
    # Helper functions
    create_root, create_choice, create_alternative,
    is_local_var, is_external_var, suspend_on_var, bind_var,
    make_constrained, is_constrained,
)


class TestEnvId:
    """Tests for environment ID scope tracking."""

    def test_create_env(self):
        env = EnvId()
        assert env.parent is None

    def test_create_child_env(self):
        parent = EnvId()
        child = EnvId(parent)
        assert child.parent is parent

    def test_is_ancestor_of_self(self):
        env = EnvId()
        assert env.is_ancestor_of(env)

    def test_is_ancestor_of_child(self):
        parent = EnvId()
        child = EnvId(parent)
        assert parent.is_ancestor_of(child)

    def test_is_not_ancestor_of_parent(self):
        parent = EnvId()
        child = EnvId(parent)
        assert not child.is_ancestor_of(parent)

    def test_is_ancestor_chain(self):
        e1 = EnvId()
        e2 = EnvId(e1)
        e3 = EnvId(e2)
        assert e1.is_ancestor_of(e3)
        assert e2.is_ancestor_of(e3)
        assert not e3.is_ancestor_of(e1)


class TestConstrainedVar:
    """Tests for constrained variables with suspension support."""

    def test_create_constrained_var(self):
        env = EnvId()
        var = ConstrainedVar("X", env)
        assert var.name == "X"
        assert var.env is env
        assert var.suspensions is None

    def test_make_constrained(self):
        var = Var("X")
        env = EnvId()
        cvar = make_constrained(var, env)
        assert isinstance(cvar, ConstrainedVar)
        assert cvar.name == "X"
        assert cvar.env is env

    def test_is_constrained(self):
        var = Var("X")
        env = EnvId()
        cvar = ConstrainedVar("Y", env)
        assert not is_constrained(var)
        assert is_constrained(cvar)

    def test_add_suspension(self):
        env = EnvId()
        var = ConstrainedVar("X", env)
        andb = AndBox()
        susp = Suspension.for_andbox(andb)
        var.add_suspension(susp)
        assert var.suspensions is susp

    def test_add_multiple_suspensions(self):
        env = EnvId()
        var = ConstrainedVar("X", env)
        andb1 = AndBox()
        andb2 = AndBox()
        susp1 = Suspension.for_andbox(andb1)
        susp2 = Suspension.for_andbox(andb2)
        var.add_suspension(susp1)
        var.add_suspension(susp2)
        # Most recent first
        assert var.suspensions is susp2
        assert var.suspensions.next is susp1


class TestSuspension:
    """Tests for suspension records."""

    def test_for_andbox(self):
        andb = AndBox()
        susp = Suspension.for_andbox(andb)
        assert susp.type == SuspensionType.ANDBOX
        assert susp.andbox is andb
        assert susp.choicebox is None

    def test_for_choicebox(self):
        chb = ChoiceBox()
        susp = Suspension.for_choicebox(chb)
        assert susp.type == SuspensionType.CHOICEBOX
        assert susp.choicebox is chb
        assert susp.andbox is None


class TestAndBox:
    """Tests for and-box execution context."""

    def test_create_andbox(self):
        andb = AndBox()
        assert andb.status == Status.STABLE
        assert andb.is_stable()
        assert not andb.is_dead()
        assert not andb.is_unstable()

    def test_status_transitions(self):
        andb = AndBox()
        assert andb.is_stable()

        andb.mark_unstable()
        assert andb.is_unstable()
        assert not andb.is_stable()

        andb.mark_dead()
        assert andb.is_dead()
        assert not andb.is_unstable()

    def test_is_quiet(self):
        andb = AndBox()
        assert andb.is_quiet()

        andb.add_unifier(Integer(1), Integer(2))
        assert not andb.is_quiet()

    def test_is_solved(self):
        andb = AndBox()
        assert andb.is_solved()  # No child choice-boxes

        chb = ChoiceBox()
        andb.tried = chb
        assert not andb.is_solved()

    def test_add_goal(self):
        andb = AndBox()
        goal = Struct(Atom("foo"), (Var("X"),))
        andb.add_goal(goal)
        assert len(andb.goals) == 1
        assert andb.pop_goal() is goal
        assert andb.pop_goal() is None

    def test_get_var(self):
        andb = AndBox()
        x1 = andb.get_var("X")
        x2 = andb.get_var("X")
        y = andb.get_var("Y")
        assert x1 is x2  # Same variable
        assert x1 is not y
        assert isinstance(x1, ConstrainedVar)


class TestChoiceBox:
    """Tests for choice-box clause alternatives."""

    def test_create_choicebox(self):
        chb = ChoiceBox()
        assert chb.tried is None
        assert chb.father is None

    def test_add_alternative(self):
        chb = ChoiceBox()
        andb = AndBox()
        chb.add_alternative(andb)
        assert chb.tried is andb
        assert andb.father is chb

    def test_add_multiple_alternatives(self):
        chb = ChoiceBox()
        andb1 = AndBox()
        andb2 = AndBox()
        andb3 = AndBox()
        chb.add_alternative(andb1)
        chb.add_alternative(andb2)
        chb.add_alternative(andb3)

        assert chb.tried is andb1
        assert andb1.next is andb2
        assert andb2.next is andb3
        assert andb3.next is None
        assert andb2.prev is andb1
        assert andb3.prev is andb2

    def test_remove_alternative(self):
        chb = ChoiceBox()
        andb1 = AndBox()
        andb2 = AndBox()
        andb3 = AndBox()
        chb.add_alternative(andb1)
        chb.add_alternative(andb2)
        chb.add_alternative(andb3)

        chb.remove_alternative(andb2)
        assert andb1.next is andb3
        assert andb3.prev is andb1
        assert andb2.father is None

    def test_remove_first_alternative(self):
        chb = ChoiceBox()
        andb1 = AndBox()
        andb2 = AndBox()
        chb.add_alternative(andb1)
        chb.add_alternative(andb2)

        chb.remove_alternative(andb1)
        assert chb.tried is andb2

    def test_is_determinate(self):
        chb = ChoiceBox()
        andb1 = AndBox()
        andb2 = AndBox()

        assert not chb.is_determinate()  # No alternatives

        chb.add_alternative(andb1)
        assert chb.is_determinate()  # One alternative

        chb.add_alternative(andb2)
        assert not chb.is_determinate()  # Two alternatives

    def test_alternatives_list(self):
        chb = ChoiceBox()
        andb1 = AndBox()
        andb2 = AndBox()
        chb.add_alternative(andb1)
        chb.add_alternative(andb2)

        alts = chb.alternatives()
        assert len(alts) == 2
        assert alts[0] is andb1
        assert alts[1] is andb2


class TestTask:
    """Tests for task queue entries."""

    def test_promote_task(self):
        andb = AndBox()
        task = Task.promote(andb)
        assert task.type == TaskType.PROMOTE
        assert task.andbox is andb

    def test_split_task(self):
        andb = AndBox()
        task = Task.split(andb)
        assert task.type == TaskType.SPLIT
        assert task.andbox is andb

    def test_start_task(self):
        task = Task.start()
        assert task.type == TaskType.START
        assert task.andbox is None

    def test_root_task(self):
        task = Task.root()
        assert task.type == TaskType.ROOT


class TestExState:
    """Tests for global execution state."""

    def test_create_exstate(self):
        exs = ExState()
        assert exs.andb is None
        assert exs.root is None
        assert len(exs.tasks) == 0

    def test_task_queue(self):
        exs = ExState()
        andb = AndBox()

        assert not exs.has_tasks()

        exs.queue_promote(andb)
        assert exs.has_tasks()

        task = exs.next_task()
        assert task.type == TaskType.PROMOTE
        assert task.andbox is andb

        assert not exs.has_tasks()
        assert exs.next_task() is None

    def test_wake_queue(self):
        exs = ExState()
        andb = AndBox()
        exs.queue_wake(andb)
        assert len(exs.wake) == 1
        assert exs.wake[0] is andb

    def test_recall_queue(self):
        exs = ExState()
        chb = ChoiceBox()
        exs.queue_recall(chb)
        assert len(exs.recall) == 1
        assert exs.recall[0] is chb

    def test_trail(self):
        exs = ExState()
        var = Var("X")

        exs.trail_binding(var, None)
        assert len(exs.trail) == 1
        assert exs.trail[0].var is var

    def test_undo_trail(self):
        exs = ExState()
        var = Var("X")

        exs.trail_binding(var, None)
        var.binding = Integer(42)

        exs.undo_trail()
        assert var.binding is None

    def test_trail_position(self):
        exs = ExState()
        var1 = Var("X")
        var2 = Var("Y")

        pos0 = exs.trail_position()
        assert pos0 == 0

        exs.trail_binding(var1)
        pos1 = exs.trail_position()
        assert pos1 == 1

        exs.trail_binding(var2)
        pos2 = exs.trail_position()
        assert pos2 == 2

        # Undo to pos1
        exs.undo_trail(pos1)
        assert exs.trail_position() == 1

    def test_context_push_pop(self):
        exs = ExState()
        andb = AndBox()

        exs.queue_promote(andb)
        exs.push_context()

        # Add more tasks
        exs.queue_wake(andb)

        ctx = exs.pop_context()
        assert ctx is not None
        assert ctx.task_pos == 1
        assert ctx.wake_pos == 0

    def test_restore_context(self):
        exs = ExState()
        andb = AndBox()
        var = Var("X")

        # Initial state
        exs.push_context()
        ctx = exs.contexts[-1]

        # Make changes
        exs.queue_promote(andb)
        exs.trail_binding(var)
        var.binding = Integer(42)

        # Restore
        exs.restore_context(ctx)
        assert len(exs.tasks) == 0
        assert var.binding is None


class TestCreateHelpers:
    """Tests for helper functions."""

    def test_create_root(self):
        goal = Struct(Atom("foo"), (Var("X"),))
        exs, andb = create_root(goal)

        assert exs.root is not None
        assert exs.andb is andb
        assert andb.father is exs.root
        assert len(andb.goals) == 1
        assert exs.has_tasks()

    def test_create_choice(self):
        exs, parent = create_root(Atom("test"))
        chb = create_choice(parent)

        assert chb.father is parent
        assert parent.tried is chb

    def test_create_alternative(self):
        exs, parent = create_root(Atom("test"))
        chb = create_choice(parent)
        andb = create_alternative(chb)

        assert andb.father is chb
        assert chb.tried is andb
        # Environment should be child of parent's environment
        assert andb.env.parent is parent.env


class TestVariableScope:
    """Tests for variable scope operations."""

    def test_is_local_var(self):
        andb = AndBox()
        local = ConstrainedVar("X", andb.env)
        other_env = EnvId()
        external = ConstrainedVar("Y", other_env)

        assert is_local_var(local, andb)
        assert not is_local_var(external, andb)

    def test_is_external_var(self):
        parent_env = EnvId()
        child_env = EnvId(parent_env)
        andb = AndBox()
        andb.env = child_env

        external = ConstrainedVar("X", parent_env)
        local = ConstrainedVar("Y", child_env)

        assert is_external_var(external, andb)
        assert not is_external_var(local, andb)

    def test_suspend_on_var(self):
        exs = ExState()
        andb = AndBox()
        var = Var("X")

        cvar = suspend_on_var(exs, andb, var)

        assert isinstance(cvar, ConstrainedVar)
        assert cvar.suspensions is not None
        assert cvar.suspensions.andbox is andb
        assert andb.is_unstable()

    def test_bind_var(self):
        exs = ExState()
        andb = AndBox()
        var = ConstrainedVar("X", andb.env)

        success = bind_var(exs, andb, var, Integer(42))

        assert success
        assert var.deref() == Integer(42)
        assert len(exs.trail) == 1

    def test_bind_var_wakes_suspended(self):
        exs = ExState()
        andb = AndBox()
        waiting = AndBox()
        var = ConstrainedVar("X", andb.env)

        # Suspend waiting on var
        susp = Suspension.for_andbox(waiting)
        var.add_suspension(susp)

        # Bind var
        bind_var(exs, andb, var, Integer(42))

        # Waiting should be in wake queue
        assert len(exs.wake) == 1
        assert exs.wake[0] is waiting
        assert var.suspensions is None


class TestWakeAll:
    """Tests for waking suspended goals."""

    def test_wake_all_andboxes(self):
        exs = ExState()
        env = EnvId()
        var = ConstrainedVar("X", env)

        andb1 = AndBox()
        andb2 = AndBox()
        var.add_suspension(Suspension.for_andbox(andb1))
        var.add_suspension(Suspension.for_andbox(andb2))

        var.wake_all(exs)

        assert var.suspensions is None
        assert len(exs.wake) == 2
        assert andb2 in exs.wake
        assert andb1 in exs.wake

    def test_wake_all_choiceboxes(self):
        exs = ExState()
        env = EnvId()
        var = ConstrainedVar("X", env)

        chb = ChoiceBox()
        var.add_suspension(Suspension.for_choicebox(chb))

        var.wake_all(exs)

        assert len(exs.recall) == 1
        assert exs.recall[0] is chb
