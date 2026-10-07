from datetime import datetime, timezone
from enum import Enum

from sqlalchemy import Column, DateTime, Float, ForeignKey, Integer, String, Table
from sqlalchemy.orm import DeclarativeBase, relationship


def utcnow():
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class TaskStatus(str, Enum):
    WAITING = "WAITING"
    RUNNING = "RUNNING"
    PAUSED = "PAUSED"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    BLOCKED = "BLOCKED"
    CANCELLED = "CANCELLED"


task_dependencies = Table(
    "task_dependencies",
    Base.metadata,
    Column("task_id", ForeignKey("tasks.id"), primary_key=True),
    Column("depends_on_task_id", ForeignKey("tasks.id"), primary_key=True),
)


class Task(Base):
    __tablename__ = "tasks"

    id = Column(Integer, primary_key=True)
    name = Column(String(200), unique=True, index=True, nullable=False)
    status = Column(String(20), nullable=False, default=TaskStatus.WAITING.value)
    duration_seconds = Column(Float, nullable=False)
    elapsed_seconds = Column(Float, nullable=False, default=0.0)
    failure_rate = Column(Float, nullable=False, default=0.0)
    max_retries = Column(Integer, nullable=False, default=0)
    attempts = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)

    dependencies = relationship(
        "Task",
        secondary=task_dependencies,
        primaryjoin=id == task_dependencies.c.task_id,
        secondaryjoin=id == task_dependencies.c.depends_on_task_id,
        lazy="selectin",
        overlaps="dependents",
    )
    dependents = relationship(
        "Task",
        secondary=task_dependencies,
        primaryjoin=id == task_dependencies.c.depends_on_task_id,
        secondaryjoin=id == task_dependencies.c.task_id,
        lazy="selectin",
        overlaps="dependencies",
    )
