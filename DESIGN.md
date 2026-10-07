# Design

## Scenario

The runner models document processing:

1. Upload Document
2. Extract Text
3. Analyze Document
4. Generate Report

Dependencies ensure each stage runs only after its prerequisites succeed.

## Cancel decision

Cancel is terminal for the selected task until an retry.

If `A -> B -> C` and A is cancelled:

`A=CANCELLED, B=CANCELLED, C=CANCELLED`

The branch is not automatically restarted. This prevents a surprising situation where an API reports cancellation but the scheduler starts the same work again a moment later.

Cancellation discards runtime progress because the user's explicit retry represents a new execution from the beginning.

## Retry decision

`POST /tasks/{task_name}/retry` is available only for `CANCELLED` tasks.

Before changing any state, all direct dependencies of the selected task must be `SUCCEEDED`. If not, the request returns a conflict error.

The selected cancelled task and its cancelled downstream branch are reset to `WAITING`, with progress and attempts reset. The scheduler then runs the branch according to normal dependency rules.

## Pause/resume decision

Pause is non-terminal. It preserves elapsed progress.

Pausing A also pauses all downstream waiting/running tasks. In the normal dependency invariant, downstream tasks are waiting while A is running, but the implementation also signals any running descendant defensively.

Resume requires the selected task to be `PAUSED` and all its dependencies to be `SUCCEEDED`. The selected task and paused descendants return to `WAITING`. The scheduler then starts eligible tasks, and execution resumes from each task's saved elapsed progress.

## Concurrency guarantee

The scheduler creates no more than N execution coroutines and also guards execution with an asyncio semaphore. The `running_tasks` registry is checked before starting a task. This prevents many ready tasks from exceeding the configured limit when they become eligible together.

If this invariant were broken, resource usage could exceed the configured capacity and the service would violate its core scheduling contract.

## Restart behavior

SQLite is the source of truth. Succeeded, failed, blocked, cancelled, and paused states remain stored.

On startup, `RUNNING` tasks are changed to `WAITING` while retaining persisted elapsed progress. This means completed work is not rerun. A small amount of in-progress work can be repeated after a sudden kill because progress is persisted periodically rather than transactionally after every instruction.

## FIFO ordering and poor case

Waiting tasks are ordered by `(created_at, id)`. This is simple and deterministic.

A poor example is a very old 10-minute task ahead of a newly ready 1-second task. FIFO may make the short task wait even though running it first would improve latency.

## Core correctness invariant

A task may execute only when every dependency is `SUCCEEDED`.

This is enforced in `_dependencies_succeeded()` immediately before a task is started. The scheduler also rechecks state when the execution coroutine acquires its execution slot.

## Atomic submission

The entire batch is validated before inserts are committed. Duplicate names, unknown dependencies, and cycles reject the complete batch.

## Useful improvement

Pause/resume is an operational improvement beyond the minimum API. It lets an operator temporarily stop a dependency branch without discarding already completed runtime progress.
