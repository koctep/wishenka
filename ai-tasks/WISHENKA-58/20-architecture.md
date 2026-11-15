# WISHENKA-58: Item lock lifetime

## Research

`wishenka/wishlists/concurrency.py` holds every `asyncio.Lock` in a normal dictionary.
`WishlistService` owns one coordinator and uses `acquire(item_id)` for item and reservation
operations. A short master lock protects lookup and creation; each item lock protects the work.
The map currently retains every item ever seen. The project requires Python 3.12 or newer.

Python's [weak reference documentation](https://docs.python.org/3.12/library/weakref.html)
describes `WeakValueDictionary`: a value is removed when no strong reference to it remains.
This is suitable for the existing lock lifecycle, subject to preserving a strong local reference
for every holder and waiter. The coordinator remains an asyncio, in-process facility; database
transaction guarantees and the service interface are unchanged.

## Implementation Plan

1. Before production changes, add a bounded automated red test in a focused coordinator test
   module under `tests/`. Sequentially enter and exit the public context for many distinct IDs,
   allow completed context objects to be released, run garbage collection, and assert the
   coordinator's internal registry no longer retains those inactive IDs. The current ordinary
   dictionary retains them, so this fails for the intended memory-lifetime defect without any
   external service. Do not assert exact collection timing before explicit collection.
2. Replace the strong registry with `weakref.WeakValueDictionary[int, asyncio.Lock]`; retain
   the master lock. Under the master lock perform one lookup into a local strong `lock` variable;
   if absent, create and register a lock while retaining that local reference. Do not use a
   separate membership check followed by a weak lookup, which can lose the referent between calls.
3. Keep the local lock alive across `async with lock` and `yield`; do not remove entries manually
   when the holder exits. Existing exception and cancellation behavior of the async context
   manager remains in effect. No periodic task or cleanup configuration is necessary.
4. Make the red test green and add bounded synchronization tests for holder, multiple waiters,
   arrival during handoff, waiter cancellation, exceptions, reuse after collection, and independent
   keys. Use events and bounded waits rather than sleep-based ordering. Run the relevant existing
   reservation and gift tests and repository checks.

## Architecture

```text
WishlistService operations
        |
        v
ItemConcurrencyCoordinator.acquire(item_id)
        | short master lock: get/create and retain strong local reference
        v
Weak-value registry ----> per-item asyncio.Lock <---- holder and waiter contexts
                                        |
                                        v
                               protected item operation
```

- **Service:** unchanged consumer of the public `async with coordinator.acquire(item_id)` API.
- **Coordinator:** owns the weak registry and the existing master lock. The master lock only
  serializes lookup and creation, never the protected item work.
- **Item lock:** remains strongly referenced in every active acquisition coroutine, including
  while waiting and until its context exits. Thus the registry still returns the same lock to a
  newcomer while a holder or waiter exists. Once all such contexts and other strong references
  are gone, garbage collection can reclaim it and remove its registry entry. A later operation
  creates a new lock only after no old operation can use the previous lock.
- **Storage and transactions:** unchanged; this design does not coordinate across processes.

Cancellation before the master lock is acquired creates no item reference. Cancellation while
waiting for the item lock unwinds that acquisition context; other holders and waiters retain their
own strong references. A holder's exception or cancellation releases the item lock through the
existing async context manager before its local reference can disappear. Tests must cover these
paths, including a third arrival while an existing waiter remains. The weak registry is internal;
collection timing is runtime-dependent and no exact latency is promised.

## Q&A

- **Why not delete an unlocked entry?** An unlocked lock can still have a waiter or a caller that
  obtained a reference and has yet to acquire it; deleting it may create two locks for one item.
- **Why not hold the master lock around protected work?** That would block independent items.
- **What is the operational limit?** Active or referenced locks remain alive, and garbage collection
  timing is implementation-dependent; only inactive, unreferenced historical locks are reclaimed.
