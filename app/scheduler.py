# import asyncio
# import random

# from sqlalchemy import select

# from .database import SessionLocal
# from .models import Task, TaskStatus, utcnow


# class TaskScheduler:
#     def __init__(self, concurrency_limit=2, progress_interval=1.0):
#         self.concurrency_limit = concurrency_limit
#         self.progress_interval = progress_interval
#         self.semaphore = asyncio.Semaphore(concurrency_limit)
#         self.running_tasks = {}
#         self.cancel_events = {}
#         self.pause_events = {}
#         self.wakeup_event = asyncio.Event()
#         self.scheduler_task = None

#     async def start(self):
#         if self.scheduler_task is not None:
#             return
#         self._recover_after_restart()
#         self.scheduler_task = asyncio.create_task(self._scheduler_loop())

#     async def stop(self):
#         if self.scheduler_task is None:
#             return
#         self.scheduler_task.cancel()
#         try:
#             await self.scheduler_task
#         except asyncio.CancelledError:
#             pass
#         self.scheduler_task = None

#     def notify(self):
#         self.wakeup_event.set()

#     def _recover_after_restart(self):
#         with SessionLocal() as db:
#             running = db.scalars(
#                 select(Task).where(Task.status == TaskStatus.RUNNING.value)
#             ).all()
#             for task in running:
#                 # Preserve progress. A sudden kill can lose at most the last
#                 # progress interval that had not yet been persisted.
#                 task.status = TaskStatus.WAITING.value
#                 task.updated_at = utcnow()
#             db.commit()

#     async def _scheduler_loop(self):
#         while True:
#             try:
#                 await self._schedule_ready_tasks()
#                 self.wakeup_event.clear()
#                 try:
#                     await asyncio.wait_for(
#                         self.wakeup_event.wait(), timeout=0.5
#                     )
#                 except asyncio.TimeoutError:
#                     pass
#             except asyncio.CancelledError:
#                 raise
#             except Exception as exc:
#                 print(f"Scheduler error: {exc}")
#                 await asyncio.sleep(1)

#     async def _schedule_ready_tasks(self):
#         with SessionLocal() as db:
#             tasks = db.scalars(
#                 select(Task)
#                 .where(Task.status == TaskStatus.WAITING.value)
#                 .order_by(Task.created_at, Task.id)
#             ).all()

#         for task in tasks:
#             if len(self.running_tasks) >= self.concurrency_limit:
#                 break
#             if task.id in self.running_tasks:
#                 continue
#             if self._dependencies_succeeded(task.id):
#                 await self._start_task(task.id)

#     def _dependencies_succeeded(self, task_id):
#         with SessionLocal() as db:
#             task = db.get(Task, task_id)
#             if task is None:
#                 return False
#             return all(
#                 dependency.status == TaskStatus.SUCCEEDED.value
#                 for dependency in task.dependencies
#             )

#     async def _start_task(self, task_id):
#         cancel_event = asyncio.Event()
#         pause_event = asyncio.Event()
#         self.cancel_events[task_id] = cancel_event
#         self.pause_events[task_id] = pause_event

#         execution = asyncio.create_task(
#             self._execute_task(task_id, cancel_event, pause_event)
#         )
#         self.running_tasks[task_id] = execution
#         execution.add_done_callback(
#             lambda _: self._execution_finished(task_id)
#         )

#     def _execution_finished(self, task_id):
#         self.running_tasks.pop(task_id, None)
#         self.cancel_events.pop(task_id, None)
#         self.pause_events.pop(task_id, None)
#         self.notify()

#     async def _execute_task(self, task_id, cancel_event, pause_event):
#         async with self.semaphore:
#             with SessionLocal() as db:
#                 task = db.get(Task, task_id)
#                 if task is None or task.status != TaskStatus.WAITING.value:
#                     return

#                 task.status = TaskStatus.RUNNING.value
#                 task.updated_at = utcnow()
#                 db.commit()

#                 duration = task.duration_seconds
#                 elapsed = task.elapsed_seconds

#             remaining = max(0.0, duration - elapsed)

#             while remaining > 0:
#                 if cancel_event.is_set():
#                     await self._handle_cancelled_task(task_id)
#                     return
#                 if pause_event.is_set():
#                     await self._handle_paused_task(task_id)
#                     return

#                 sleep_time = min(self.progress_interval, remaining)
#                 await asyncio.sleep(sleep_time)
#                 remaining -= sleep_time
#                 elapsed += sleep_time
#                 await self._save_progress(task_id, elapsed)

#             if cancel_event.is_set():
#                 await self._handle_cancelled_task(task_id)
#                 return
#             if pause_event.is_set():
#                 await self._handle_paused_task(task_id)
#                 return

#             await self._finish_task(task_id)

#     async def _save_progress(self, task_id, elapsed):
#         with SessionLocal() as db:
#             task = db.get(Task, task_id)
#             if task is None or task.status != TaskStatus.RUNNING.value:
#                 return
#             task.elapsed_seconds = min(elapsed, task.duration_seconds)
#             task.updated_at = utcnow()
#             db.commit()

#     async def _finish_task(self, task_id):
#         with SessionLocal() as db:
#             task = db.get(Task, task_id)
#             if task is None or task.status != TaskStatus.RUNNING.value:
#                 return

#             if random.random() < task.failure_rate:
#                 task.attempts += 1
#                 if task.attempts <= task.max_retries:
#                     task.status = TaskStatus.WAITING.value
#                     task.elapsed_seconds = 0.0
#                     task.updated_at = utcnow()
#                     db.commit()
#                     delay = 2 ** (task.attempts - 1)
#                     await asyncio.sleep(delay)
#                     self.notify()
#                     return

#                 task.status = TaskStatus.FAILED.value
#                 task.elapsed_seconds = task.duration_seconds
#                 task.updated_at = utcnow()
#                 self._block_downstream(db, task.id)
#                 db.commit()
#                 return

#             task.status = TaskStatus.SUCCEEDED.value
#             task.elapsed_seconds = task.duration_seconds
#             task.updated_at = utcnow()
#             db.commit()

#     async def cancel_task(self, task_id):
#         with SessionLocal() as db:
#             task = db.get(Task, task_id)
#             if task is None:
#                 return False

#             if task.status in (
#                 TaskStatus.SUCCEEDED.value,
#                 TaskStatus.FAILED.value,
#                 TaskStatus.BLOCKED.value,
#                 TaskStatus.CANCELLED.value,
#             ):
#                 return False

#             # Persist terminal cancellation immediately. The running
#             # coroutine sees the event and exits without completing the task.
#             running_event = self.cancel_events.get(task_id)
#             if running_event is not None:
#                 running_event.set()

#             self._cancel_branch(db, task.id)
#             db.commit()

#         self.notify()
#         return True

#     async def retry_task(self, task_id):
#         with SessionLocal() as db:
#             task = db.get(Task, task_id)
#             if task is None:
#                 return False, "Task not found"

#             if task.status != TaskStatus.CANCELLED.value:
#                 return False, (
#                     f"Task '{task.name}' can only be retried when it is CANCELLED"
#                 )

#             # Every dependency must already be successful.
#             for dependency in task.dependencies:
#                 if dependency.status != TaskStatus.SUCCEEDED.value:
#                     return False, (
#                         f"Task '{task.name}' cannot be retried because dependency "
#                         f"'{dependency.name}' is not SUCCEEDED"
#                     )

#             branch = [task] + self._get_descendants(db, task.id)
#             for item in branch:
#                 item.status = TaskStatus.WAITING.value
#                 item.elapsed_seconds = 0.0
#                 item.attempts = 0
#                 item.updated_at = utcnow()

#             db.commit()

#         self.notify()
#         return True, None

#     async def pause_task(self, task_id):
#         with SessionLocal() as db:
#             task = db.get(Task, task_id)
#             if task is None:
#                 return False

#             if task.status not in (
#                 TaskStatus.WAITING.value,
#                 TaskStatus.RUNNING.value,
#             ):
#                 return False

#             pause_event = self.pause_events.get(task_id)
#             if pause_event is not None:
#                 pause_event.set()

#             # Descendants are held immediately. Running descendants, if any,
#             # are also signalled. Under the dependency invariant they normally
#             # cannot be running while this task is still running.
#             descendants = self._get_descendants(db, task.id)
#             for descendant in descendants:
#                 event = self.pause_events.get(descendant.id)
#                 if event is not None:
#                     event.set()
#                 if descendant.status in (
#                     TaskStatus.WAITING.value,
#                     TaskStatus.RUNNING.value,
#                 ):
#                     descendant.status = TaskStatus.PAUSED.value
#                     descendant.updated_at = utcnow()

#             if task.status == TaskStatus.WAITING.value:
#                 task.status = TaskStatus.PAUSED.value
#             task.updated_at = utcnow()
#             db.commit()

#         self.notify()
#         return True

#     async def resume_task(self, task_id):
#         with SessionLocal() as db:
#             task = db.get(Task, task_id)
#             if task is None:
#                 return False, "Task not found"

#             if task.status != TaskStatus.PAUSED.value:
#                 return False, f"Task '{task.name}' is not PAUSED"

#             # A paused task can resume only when all dependencies have
#             # succeeded. Descendants are released to WAITING and will run
#             # only after their own dependencies are satisfied.
#             if any(
#                 dependency.status != TaskStatus.SUCCEEDED.value
#                 for dependency in task.dependencies
#             ):
#                 return False, (
#                     f"Task '{task.name}' cannot be resumed because a dependency "
#                     "is not SUCCEEDED"
#                 )

#             branch = [task] + self._get_descendants(db, task.id)
#             for item in branch:
#                 if item.status == TaskStatus.PAUSED.value:
#                     item.status = TaskStatus.WAITING.value
#                     item.updated_at = utcnow()

#             db.commit()

#         self.notify()
#         return True, None

#     async def _handle_cancelled_task(self, task_id):
#         # The API persists CANCELLED before the coroutine exits. Never
#         # re-cancel a task after an explicit retry has already moved it back
#         # to WAITING; the old coroutine must simply terminate.
#         with SessionLocal() as db:
#             task = db.get(Task, task_id)
#             if task is None:
#                 return
#             if task.status == TaskStatus.CANCELLED.value:
#                 pass
#         self.notify()

#     async def _handle_paused_task(self, task_id):
#         with SessionLocal() as db:
#             task = db.get(Task, task_id)
#             if task is None:
#                 return
#             task.status = TaskStatus.PAUSED.value
#             task.updated_at = utcnow()
#             for descendant in self._get_descendants(db, task.id):
#                 if descendant.status in (
#                     TaskStatus.WAITING.value,
#                     TaskStatus.RUNNING.value,
#                 ):
#                     descendant.status = TaskStatus.PAUSED.value
#                     descendant.updated_at = utcnow()
#             db.commit()
#         self.notify()

#     def _get_descendants(self, db, root_id):
#         all_tasks = db.scalars(select(Task)).all()
#         descendants = []
#         known = {root_id}

#         changed = True
#         while changed:
#             changed = False
#             for task in all_tasks:
#                 if task.id in known:
#                     continue
#                 if any(dependency.id in known for dependency in task.dependencies):
#                     known.add(task.id)
#                     descendants.append(task)
#                     changed = True

#         return descendants

#     def _cancel_branch(self, db, root_id):
#         root = db.get(Task, root_id)
#         if root is None:
#             return

#         branch = [root] + self._get_descendants(db, root_id)
#         for task in branch:
#             task.status = TaskStatus.CANCELLED.value
#             # Cancel deliberately discards runtime progress.
#             task.elapsed_seconds = 0.0
#             task.attempts = 0
#             task.updated_at = utcnow()

#             event = self.cancel_events.get(task.id)
#             if event is not None:
#                 event.set()

#     def _block_downstream(self, db, root_id):
#         for task in self._get_descendants(db, root_id):
#             task.status = TaskStatus.BLOCKED.value
#             task.updated_at = utcnow()


import asyncio
import random

from sqlalchemy import select

from .database import SessionLocal
from .models import Task, TaskStatus, utcnow


class TaskScheduler:

    def __init__(self, concurrency_limit=2, progress_interval=1.0):
        self.concurrency_limit = concurrency_limit
        self.progress_interval = progress_interval

        self.semaphore = asyncio.Semaphore(concurrency_limit)

        self.running_tasks = {}
        self.cancel_events = {}
        self.pause_events = {}

        self.wakeup_event = asyncio.Event()
        self.scheduler_task = None

   

    async def start(self):
        if self.scheduler_task is not None:
            return

        self._recover_after_restart()

        self.scheduler_task = asyncio.create_task(
            self._scheduler_loop()
        )

    async def stop(self):
        if self.scheduler_task is None:
            return

        self.scheduler_task.cancel()

        try:
            await self.scheduler_task
        except asyncio.CancelledError:
            pass

        self.scheduler_task = None

    def notify(self):
        self.wakeup_event.set()

 

    def _recover_after_restart(self):
        with SessionLocal() as db:
            running = db.scalars(
                select(Task).where(
                    Task.status == TaskStatus.RUNNING.value
                )
            ).all()

            for task in running:
            
                task.status = TaskStatus.WAITING.value
                task.updated_at = utcnow()

            db.commit()

 

    async def _scheduler_loop(self):
        while True:
            try:
                await self._schedule_ready_tasks()

                self.wakeup_event.clear()

                try:
                    await asyncio.wait_for(
                        self.wakeup_event.wait(),
                        timeout=0.5,
                    )
                except asyncio.TimeoutError:
                    pass

            except asyncio.CancelledError:
                raise

            except Exception as exc:
                print(f"Scheduler error: {exc}")
                await asyncio.sleep(1)

   
    async def _schedule_ready_tasks(self):
        with SessionLocal() as db:
            tasks = db.scalars(
                select(Task)
                .where(
                    Task.status == TaskStatus.WAITING.value
                )
                .order_by(Task.created_at, Task.id)
            ).all()

        for task in tasks:

           
            if len(self.running_tasks) >= self.concurrency_limit:
                break

            if task.id in self.running_tasks:
                continue


            if self._dependencies_blocked(task.id):
                with SessionLocal() as db:
                    current_task = db.get(Task, task.id)

                    if (
                        current_task is not None
                        and current_task.status
                        == TaskStatus.WAITING.value
                    ):
                        current_task.status = (
                            TaskStatus.BLOCKED.value
                        )
                        current_task.updated_at = utcnow()

                        db.commit()

                continue

         

            if self._dependencies_succeeded(task.id):
                await self._start_task(task.id)

    def _dependencies_succeeded(self, task_id):
        with SessionLocal() as db:
            task = db.get(Task, task_id)

            if task is None:
                return False

            return all(
                dependency.status
                == TaskStatus.SUCCEEDED.value
                for dependency in task.dependencies
            )

    def _dependencies_blocked(self, task_id):
        """
        Return True when at least one dependency has permanently
        failed or has already been blocked.

        A task with such a dependency can never execute.
        """

        with SessionLocal() as db:
            task = db.get(Task, task_id)

            if task is None:
                return False

            return any(
                dependency.status
                in (
                    TaskStatus.FAILED.value,
                    TaskStatus.BLOCKED.value,
                )
                for dependency in task.dependencies
            )

    async def _start_task(self, task_id):
        cancel_event = asyncio.Event()
        pause_event = asyncio.Event()

        self.cancel_events[task_id] = cancel_event
        self.pause_events[task_id] = pause_event

        execution = asyncio.create_task(
            self._execute_task(
                task_id,
                cancel_event,
                pause_event,
            )
        )

        self.running_tasks[task_id] = execution

        execution.add_done_callback(
            lambda _: self._execution_finished(task_id)
        )

    def _execution_finished(self, task_id):
        self.running_tasks.pop(task_id, None)
        self.cancel_events.pop(task_id, None)
        self.pause_events.pop(task_id, None)

        self.notify()

    async def _execute_task(
        self,
        task_id,
        cancel_event,
        pause_event,
    ):
        async with self.semaphore:

            with SessionLocal() as db:
                task = db.get(Task, task_id)

                if (
                    task is None
                    or task.status
                    != TaskStatus.WAITING.value
                ):
                    return

                task.status = TaskStatus.RUNNING.value
                task.updated_at = utcnow()

                db.commit()

                duration = task.duration_seconds
                elapsed = task.elapsed_seconds

            remaining = max(
                0.0,
                duration - elapsed,
            )

            while remaining > 0:

             
                if cancel_event.is_set():
                    await self._handle_cancelled_task(task_id)
                    return


                if pause_event.is_set():
                    await self._handle_paused_task(task_id)
                    return

                sleep_time = min(
                    self.progress_interval,
                    remaining,
                )

                await asyncio.sleep(sleep_time)

                remaining -= sleep_time
                elapsed += sleep_time

                await self._save_progress(
                    task_id,
                    elapsed,
                )

       

            if cancel_event.is_set():
                await self._handle_cancelled_task(task_id)
                return

        

            if pause_event.is_set():
                await self._handle_paused_task(task_id)
                return

          

            await self._finish_task(task_id)


    async def _save_progress(self, task_id, elapsed):
        with SessionLocal() as db:
            task = db.get(Task, task_id)

            if (
                task is None
                or task.status != TaskStatus.RUNNING.value
            ):
                return

            task.elapsed_seconds = min(
                elapsed,
                task.duration_seconds,
            )

            task.updated_at = utcnow()

            db.commit()

  

    async def _finish_task(self, task_id):
        with SessionLocal() as db:
            task = db.get(Task, task_id)

            if (
                task is None
                or task.status != TaskStatus.RUNNING.value
            ):
                return

            

            if random.random() < task.failure_rate:

                task.attempts += 1

               

                if task.attempts <= task.max_retries:

                    task.status = TaskStatus.WAITING.value
                    task.elapsed_seconds = 0.0
                    task.updated_at = utcnow()

                    db.commit()

                  

                    delay = 2 ** (task.attempts - 1)

                    await asyncio.sleep(delay)

                    self.notify()

                    return

             
                task.status = TaskStatus.FAILED.value

                task.elapsed_seconds = task.duration_seconds
                task.updated_at = utcnow()

                # Block downstream tasks.
                self._block_downstream(
                    db,
                    task.id,
                )

                db.commit()

                return

           

            task.status = TaskStatus.SUCCEEDED.value

            task.elapsed_seconds = task.duration_seconds
            task.updated_at = utcnow()

            db.commit()



    async def cancel_task(self, task_id):
        with SessionLocal() as db:
            task = db.get(Task, task_id)

            if task is None:
                return False

            
            if task.status in (
                TaskStatus.SUCCEEDED.value,
                TaskStatus.FAILED.value,
                TaskStatus.BLOCKED.value,
                TaskStatus.CANCELLED.value,
            ):
                return False


            running_event = self.cancel_events.get(task_id)

            if running_event is not None:
                running_event.set()

            self._cancel_branch(
                db,
                task.id,
            )

            db.commit()

        self.notify()

        return True

  
    async def retry_task(self, task_id):
        with SessionLocal() as db:
            task = db.get(Task, task_id)

            if task is None:
                return False, "Task not found"

           

            if task.status not in (
                TaskStatus.FAILED.value,
                TaskStatus.CANCELLED.value,
            ):
                return (
                    False,
                    (
                        f"Task '{task.name}' can only be retried "
                        "when it is FAILED or CANCELLED"
                    ),
                )

            
            for dependency in task.dependencies:

                if (
                    dependency.status
                    != TaskStatus.SUCCEEDED.value
                ):
                    return (
                        False,
                        (
                            f"Task '{task.name}' cannot be retried "
                            f"because dependency "
                            f"'{dependency.name}' is not "
                            "SUCCEEDED"
                        ),
                    )

            branch = [
                task
            ] + self._get_descendants(
                db,
                task.id,
            )

            for item in branch:
                item.status = TaskStatus.WAITING.value
                item.elapsed_seconds = 0.0
                item.attempts = 0
                item.updated_at = utcnow()

            db.commit()

        self.notify()

        return True, None

  
    async def pause_task(self, task_id):
        with SessionLocal() as db:
            task = db.get(Task, task_id)

            if task is None:
                return False

            if task.status not in (
                TaskStatus.WAITING.value,
                TaskStatus.RUNNING.value,
            ):
                return False

            pause_event = self.pause_events.get(task_id)

            if pause_event is not None:
                pause_event.set()


            descendants = self._get_descendants(
                db,
                task.id,
            )

            for descendant in descendants:

                event = self.pause_events.get(
                    descendant.id
                )

                if event is not None:
                    event.set()

                if descendant.status in (
                    TaskStatus.WAITING.value,
                    TaskStatus.RUNNING.value,
                ):
                    descendant.status = (
                        TaskStatus.PAUSED.value
                    )
                    descendant.updated_at = utcnow()

            if task.status == TaskStatus.WAITING.value:
                task.status = TaskStatus.PAUSED.value

            task.updated_at = utcnow()

            db.commit()

        self.notify()

        return True

  
    async def resume_task(self, task_id):
        with SessionLocal() as db:
            task = db.get(Task, task_id)

            if task is None:
                return False, "Task not found"

            if task.status != TaskStatus.PAUSED.value:
                return (
                    False,
                    f"Task '{task.name}' is not PAUSED",
                )

          

            if any(
                dependency.status
                != TaskStatus.SUCCEEDED.value
                for dependency in task.dependencies
            ):
                return (
                    False,
                    (
                        f"Task '{task.name}' cannot be "
                        "resumed because a dependency "
                        "is not SUCCEEDED"
                    ),
                )

            branch = [
                task
            ] + self._get_descendants(
                db,
                task.id,
            )

            for item in branch:

                if item.status == TaskStatus.PAUSED.value:
                    item.status = TaskStatus.WAITING.value
                    item.updated_at = utcnow()

            db.commit()

        self.notify()

        return True, None


    async def _handle_cancelled_task(self, task_id):
       

        with SessionLocal() as db:
            task = db.get(Task, task_id)

            if task is None:
                return

            if task.status == TaskStatus.CANCELLED.value:
                pass

        self.notify()


    async def _handle_paused_task(self, task_id):
        with SessionLocal() as db:
            task = db.get(Task, task_id)

            if task is None:
                return

            task.status = TaskStatus.PAUSED.value
            task.updated_at = utcnow()

            for descendant in self._get_descendants(
                db,
                task.id,
            ):
                if descendant.status in (
                    TaskStatus.WAITING.value,
                    TaskStatus.RUNNING.value,
                ):
                    descendant.status = (
                        TaskStatus.PAUSED.value
                    )
                    descendant.updated_at = utcnow()

            db.commit()

        self.notify()

   

    def _get_descendants(self, db, root_id):
        all_tasks = db.scalars(
            select(Task)
        ).all()

        descendants = []

        known = {root_id}

        changed = True

        while changed:
            changed = False

            for task in all_tasks:

                if task.id in known:
                    continue

                if any(
                    dependency.id in known
                    for dependency in task.dependencies
                ):
                    known.add(task.id)
                    descendants.append(task)
                    changed = True

        return descendants

   
    def _cancel_branch(self, db, root_id):
        root = db.get(
            Task,
            root_id,
        )

        if root is None:
            return

        branch = [
            root
        ] + self._get_descendants(
            db,
            root_id,
        )

        for task in branch:

            task.status = TaskStatus.CANCELLED.value

            
            task.elapsed_seconds = 0.0
            task.attempts = 0
            task.updated_at = utcnow()

            event = self.cancel_events.get(
                task.id
            )

            if event is not None:
                event.set()

    
    def _block_downstream(self, db, root_id):
        for task in self._get_descendants(
            db,
            root_id,
        ):
            task.status = TaskStatus.BLOCKED.value
            task.updated_at = utcnow()