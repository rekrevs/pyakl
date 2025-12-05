# Ports in AKL and PyAKL

This document describes AKL ports, how they work in the reference implementation
(akl-agents), and the design for implementing them in PyAKL.

## Overview

Ports provide a communication mechanism in AKL for multiple senders to
communicate with a single receiver through a shared channel. They solve
several problems with stream-based programming:

1. **Multiple senders**: Any number of processes can send to the same port
2. **Embeddable**: Ports can be stored in data structures and shared
3. **Constant-time send**: Unlike stream merging, send is O(1)
4. **Automatic cleanup**: Ports close automatically when no senders remain

## Conceptual Model

A port is a constraint relating a **bag** (multi-set) and a **stream** (list):

```
open_port(Port, Stream)
```

- `Port` - The port/bag that receives messages
- `Stream` - A list that produces messages (grows incrementally)

The port constraint states that the bag and stream contain the same elements,
in any order (first-come-first-served in practice).

### Sending Messages

```prolog
send(Message, Port)        % Send message to port
Message@Port               % Syntactic sugar for send/2
send(Message, Port, Port2) % Send with sequencing guarantee
```

When a message is sent to a port, it immediately appears on the stream.

### Port Closure

**Key semantics**: When a port has no more references (no process can send to it),
the port is automatically closed and the stream is terminated with `[]`.

This is the critical feature: the receiver consuming the stream is notified
that no more messages will arrive, allowing it to terminate gracefully.

## Usage Patterns

### Pattern 1: Collecting Results

```prolog
collect_results(Results) :-
    open_port(Port, Results),
    spawn_workers(Port),
    % Port closes when all workers finish
    % Results becomes a proper list
    process(Results).

spawn_workers(Port) :-
    worker(1, Port),
    worker(2, Port),
    worker(3, Port).

worker(Id, Port) :-
    compute(Id, Result),
    Result@Port.   % Send result to port
```

### Pattern 2: Monitor/Controller (from cipher.akl)

```prolog
control(Table, Domain) :-
    open_port(Port, Stream),
    spawn(Table, Port),      % Create monitors for each element
    length(Table, N),
    controller(Stream, N, Domain).  % Process stream

spawn([], _).
spawn([D|Ds], Port) :-
    monitor(D, Port),
    spawn(Ds, Port).

monitor(X, P) :-
    data(X)                  % Wait until X is bound
    |   X@P.                 % Then send it to the port

controller(_, 0, _) :- -> true.
controller([X|S], N, Domain) :-
    ->  del(X, Domain, Rest),
        N1 is N-1,
        controller(S, N1, Rest).
```

### Pattern 3: Event Aggregation (from knights.akl)

```prolog
constrain(I, J, Board, Tiles) :-
    neighbours(Neighbours, I, J, Board)
    ?   square(Board, P, I, J),
        open_port(Port, Stream),
        spawn(Neighbours, L, Port),
        wait(L, Stream, pos(P,I,J), Tiles, Board).

spawn([], L, _P) :- -> L = 0.
spawn([P|R], L, Port) :-
    ->  monitor(P, Port),
        spawn(R, L1, Port),
        L is L1+1.

monitor(pos(P,_,_), Port) :-
    data(P)                  % Wait for P to be instantiated
    |   P@Port.              % Then notify the port
```

## Reference Implementation (akl-agents)

### Data Structures

From `emulator/port.c`:

```c
typedef struct port {
    gvamethod   *method;      // Method table for GVA operations
    envid       *env;         // Environment (and-box) that owns this port
    Term        stream;       // The associated stream (list tail)
    constraint  *constr;      // Port constraint (for suspension)
} port;
```

### Key Operations

#### open_port/2

```c
bool akl_open_port(Arg) {
    // Create port object
    MakeGvainfo(prt, port, &portmethod, exs->andb);
    prt->stream = X1;        // Associate with stream variable
    prt->constr = make_port_constraint(exs);

    // Add to close list for GC tracking
    add_gvainfo_to_close((Gvainfo)prt, exs);

    // Unify Port argument with the port object
    MakeCvaTerm(res, (Gvainfo)prt);
    return unify(X0, res, exs->andb, exs);
}
```

#### send/2

```c
bool akl_send_2(Arg) {
    // Check port is local (can only send to local ports)
    if (IsLocalGVA(Ref(theport), exs->andb)) {
        // Get current stream tail
        point = Port(theport)->stream;
        Deref(point, point);

        // Create new cons cell: [message | NewTail]
        MakeListTerm(cons, exs->andb);
        InitVariable(LstCdrRef(Lst(cons)), exs->andb);
        LstCar(Lst(cons)) = message;

        // Update port's stream pointer to new tail
        GetLstCdr(new, Lst(cons));
        Port(theport)->stream = new;

        // Unify old tail with new cons (extends stream)
        return unify(point, cons, exs->andb, exs);
    }
    // Non-local port: suspend
    return SUSPEND;
}
```

### Port Closure via GC

The critical mechanism is in `gc.c`:

1. **Close list**: All ports are registered on a "close list"

2. **GC traversal**: During garbage collection:
   - If port was copied (still reachable): keep on close list
   - If port was NOT copied (unreachable): call `deallocate` method

3. **deallocateport**: Called when port has no more references

```c
envid *deallocateport(prt) {
    close_port_stream(&GvaPort(prt)->stream);
    return prt->env;  // Return env for close scheduling
}
```

4. **closeport**: Scheduled as a goal when port needs closing

```c
bool closeport(Arg) {
    Port(X0)->constr->method = NULL;  // Kill the constraint
    Deref(point, Port(X0)->stream);
    return unify(point, NIL, exs->andb, exs);  // Close stream with []
}
```

### The GC Close Mechanism

From `gc.c:gc_close()`:

```c
for (hare = close; hare != NULL; hare = hare->next) {
    if (!IsCopied(c.obj)) {
        // Object not copied = not reachable = no more references
        gen = (generic*)c.obj;
        c.env = gen->method->deallocate(gen);  // Call deallocate
        if (c.env != NULL) {
            // Schedule close operation
            // ... creates choice box with closeport goal
        }
    } else {
        // Object was copied = still alive
        // Add copy to new close list
        add_gvainfo_to_close((gvainfo*)(Forw(c.obj)), exs);
    }
}
```

## PyAKL Design

### Key Insight: Python Reference Counting

Python's reference counting provides exactly what we need:
- Objects are freed immediately when refcount hits zero
- `weakref.finalize()` can trigger callbacks on collection

Tested prototype:

```python
import weakref

class Port:
    def __init__(self):
        self.stream = []
        self._finalizer = weakref.finalize(
            self, Port._close_stream, self.stream
        )

    @staticmethod
    def _close_stream(stream):
        stream.append(None)  # End marker

    def send(self, msg):
        self.stream.append(msg)
```

This works correctly:
- Multiple references to port work (callback only when ALL gone)
- Immediate cleanup (not waiting for cycle GC)
- Stream survives port (passed to finalizer by value)

### Proposed Implementation

#### 1. Port Term Type

```python
class Port(Term):
    """AKL port for multi-sender communication."""

    def __init__(self):
        self._stream_tail = Var()  # Current tail of stream
        self._closed = False
        # Register finalizer to close stream when port is garbage
        self._finalizer = weakref.finalize(
            self, Port._do_close, self._stream_tail
        )

    @staticmethod
    def _do_close(stream_tail: Var):
        """Called when port has no more references."""
        # Bind stream tail to NIL to close the stream
        if isinstance(stream_tail, Var) and stream_tail.binding is None:
            stream_tail.binding = NIL

    def send(self, message: Term, exstate: 'ExState') -> bool:
        """Send a message to this port."""
        if self._closed:
            return False

        # Create new cons cell: [message | NewTail]
        new_tail = Var()
        cons = Cons(message, new_tail)

        # Unify current tail with cons
        old_tail = self._stream_tail
        if not unify(old_tail, cons, exstate):
            return False

        # Update stream pointer
        self._stream_tail = new_tail
        return True
```

#### 2. Built-in Predicates

```python
@register_builtin("open_port", 2)
def builtin_open_port(exstate, andb, args):
    port = Port()
    stream = port._stream_tail  # Initial stream is the tail variable
    return (unify(args[0], port, exstate) and
            unify(args[1], stream, exstate))

@register_builtin("send", 2)
def builtin_send(exstate, andb, args):
    message = args[0].deref()
    port = args[1].deref()
    if not isinstance(port, Port):
        return False
    return port.send(message, exstate)
```

#### 3. The `@` Operator

The `@` operator is syntactic sugar transformed during parsing/compilation:

```
Message@Port  =>  send(Message, Port)
```

### Integration Challenges

#### Challenge 1: Port References in Terms

When a port is unified with a variable or stored in a structure, Python's
reference counting handles it naturally. The port object is referenced by:
- The variable's binding
- Any structures containing it
- Local Python variables during execution

When all these references are gone, the finalizer fires.

#### Challenge 2: And-box Scope

In akl-agents, ports are associated with an and-box environment. When the
and-box is pruned/killed, its local objects are deallocated.

For PyAKL, we have two options:

**Option A: Rely on Python GC**

Let Python's reference counting handle it. When an and-box is abandoned:
- Its local variables go out of scope
- If those variables held port references, refcount decreases
- When no other references exist, port closes

This is simpler but may delay closure if references leak.

**Option B: Explicit Scope Tracking**

Track which ports belong to which and-box:
```python
class AndBox:
    def __init__(self):
        self.local_ports = []

    def kill(self):
        for port in self.local_ports:
            port.close()
```

This gives more control but adds complexity.

**Recommendation**: Start with Option A (Python GC), add explicit tracking
only if needed for correctness.

#### Challenge 3: Non-local Sends

In akl-agents, sending to a non-local port suspends. This is because the
port's stream tail is in a different and-box's scope.

For PyAKL, this may not be necessary if we use Python's reference counting
exclusively. The port object is shared, and sends modify the shared stream.

However, for full AKL semantics (suspension on non-local), we'd need to
track port ownership and suspend appropriately.

**Recommendation**: Start without non-local suspension. Add if needed for
specific demos.

### Testing Plan

1. **Basic port operations**:
   - open_port/2 creates port and stream
   - send/2 adds to stream
   - Multiple sends appear in order

2. **Port closure**:
   - Port closes when last reference dropped
   - Stream terminates with []
   - Receiver sees complete list

3. **Multiple senders**:
   - Multiple processes can send to same port
   - Port only closes when ALL senders done

4. **Demo programs**:
   - cipher.akl control/2 pattern
   - knights.akl constrain pattern (without full demo)

## Summary

| Aspect | akl-agents | PyAKL (proposed) |
|--------|------------|------------------|
| Port object | C struct (gvainfo) | Python class |
| Reference tracking | Close list + GC | Python refcount |
| Closure trigger | GC finds unreachable | weakref.finalize |
| Stream closure | Unify tail with NIL | Same |
| Non-local sends | Suspend | Allow (simplified) |
| Scope tracking | Explicit env | Python GC |

## References

- `../akl-agents/doc/aklintro.tex` - Section "Ports for Objects"
- `../akl-agents/doc/user.texi` - Port predicates documentation
- `../akl-agents/emulator/port.c` - Port implementation
- `../akl-agents/emulator/gc.c` - GC close mechanism
- `../akl-agents/demos/cipher.akl` - Port usage example
- `../akl-agents/demos/knights.akl` - Port usage example

## Related Tasks

- T-ENGINE-02: Ports research and design (this document)
- B-ENGINE-04: Implement ports (backlog item)
