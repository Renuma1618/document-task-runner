# Tradeoffs

## 1. SQLite instead of an external queue

SQLite keeps the project small and easy to run locally. A production service with multiple worker processes would need a stronger shared coordination mechanism.

## 2. FIFO instead of shortest-job-first

FIFO is deterministic and easy to explain, but can create head-of-line blocking when a long task is older than a short ready task.

## 3. Cancel as terminal instead of reset-to-waiting

Resetting cancellation to `WAITING` made the old implementation immediately rerun cancelled work. Terminal `CANCELLED` state is less surprising and makes retry an explicit operator action.

## 4. Periodic progress persistence

Saving progress every small interval is simpler than making every simulated unit of work transactional. A sudden process kill can lose the latest unsaved interval, but completed work remains durable.
