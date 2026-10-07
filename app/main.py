from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from sqlalchemy import func, select

from .database import SessionLocal, engine
from .models import Base, Task, TaskStatus
from .schemas import (
    StatsResponse,
    TaskBatchCreate,
    TaskBatchResponse,
    TaskResponse,
)
from .scheduler import TaskScheduler
from .task_manager import create_tasks


CONCURRENCY_LIMIT = 2
scheduler = TaskScheduler(concurrency_limit=CONCURRENCY_LIMIT)


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    await scheduler.start()
    yield
    await scheduler.stop()


app = FastAPI(
    title="Document Task Runner",
    version="2.0.0",
    lifespan=lifespan,
)


def _to_response(task):
    return TaskResponse(
        id=task.id,
        name=task.name,
        status=task.status,
        duration_seconds=task.duration_seconds,
        elapsed_seconds=task.elapsed_seconds,
        remaining_seconds=max(
            0.0, task.duration_seconds - task.elapsed_seconds
        ),
        failure_rate=task.failure_rate,
        max_retries=task.max_retries,
        attempts=task.attempts,
        depends_on=[dependency.name for dependency in task.dependencies],
    )


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/tasks", response_model=TaskBatchResponse)
async def submit_tasks(payload: TaskBatchCreate):
    try:
        tasks = create_tasks(payload.tasks)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    scheduler.notify()
    return {
        "message": "Tasks submitted successfully",
        "tasks": [_to_response(task) for task in tasks],
    }


@app.get("/tasks", response_model=list[TaskResponse])
async def list_tasks():
    with SessionLocal() as db:
        tasks = db.scalars(
            select(Task).order_by(Task.created_at, Task.id)
        ).all()
        return [_to_response(task) for task in tasks]


@app.get("/tasks/{task_name}", response_model=TaskResponse)
async def get_task(task_name: str):
    with SessionLocal() as db:
        task = db.scalar(select(Task).where(Task.name == task_name))
        if task is None:
            raise HTTPException(status_code=404, detail="Task not found")
        return _to_response(task)


@app.post("/tasks/{task_name}/cancel")
async def cancel_task(task_name: str):
    with SessionLocal() as db:
        task = db.scalar(select(Task).where(Task.name == task_name))
        if task is None:
            raise HTTPException(status_code=404, detail="Task not found")
        task_id = task.id

    success = await scheduler.cancel_task(task_id)
    if not success:
        raise HTTPException(
            status_code=409,
            detail=f"Task '{task_name}' cannot be cancelled in its current state",
        )

    return {
        "message": f"Task '{task_name}' and its downstream dependency branch were cancelled",
        "status": TaskStatus.CANCELLED.value,
    }


@app.post("/tasks/{task_name}/retry")
async def retry_task(task_name: str):
    with SessionLocal() as db:
        task = db.scalar(select(Task).where(Task.name == task_name))
        if task is None:
            raise HTTPException(status_code=404, detail="Task not found")
        task_id = task.id

    success, error = await scheduler.retry_task(task_id)
    if not success:
        raise HTTPException(status_code=409, detail=error)

    return {
        "message": f"Task '{task_name}' and its cancelled downstream branch are ready to run",
        "status": TaskStatus.WAITING.value,
    }


@app.post("/tasks/{task_name}/pause")
async def pause_task(task_name: str):
    with SessionLocal() as db:
        task = db.scalar(select(Task).where(Task.name == task_name))
        if task is None:
            raise HTTPException(status_code=404, detail="Task not found")
        task_id = task.id

    if not await scheduler.pause_task(task_id):
        raise HTTPException(
            status_code=409,
            detail=f"Task '{task_name}' cannot be paused in its current state",
        )

    return {
        "message": f"Task '{task_name}' and its downstream dependency branch were paused",
        "status": TaskStatus.PAUSED.value,
    }


@app.post("/tasks/{task_name}/resume")
async def resume_task(task_name: str):
    with SessionLocal() as db:
        task = db.scalar(select(Task).where(Task.name == task_name))
        if task is None:
            raise HTTPException(status_code=404, detail="Task not found")
        task_id = task.id

    success, error = await scheduler.resume_task(task_id)
    if not success:
        raise HTTPException(status_code=409, detail=error)

    return {
        "message": f"Task '{task_name}' resumed from saved progress",
        "status": TaskStatus.WAITING.value,
    }


@app.get("/stats", response_model=StatsResponse)
async def stats():
    with SessionLocal() as db:
        values = {}
        for status in TaskStatus:
            values[status.value.lower()] = db.scalar(
                select(func.count(Task.id)).where(
                    Task.status == status.value
                )
            ) or 0

        return StatsResponse(
            running=values["running"],
            waiting=values["waiting"],
            paused=values["paused"],
            succeeded=values["succeeded"],
            failed=values["failed"],
            blocked=values["blocked"],
            cancelled=values["cancelled"],
        )
