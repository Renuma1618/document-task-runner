from pydantic import BaseModel, ConfigDict, Field


class TaskCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    duration_seconds: float = Field(gt=0)
    failure_rate: float = Field(default=0.0, ge=0.0, le=1.0)
    max_retries: int = Field(default=0, ge=0)
    depends_on: list[str] = Field(default_factory=list)


class TaskBatchCreate(BaseModel):
    tasks: list[TaskCreate] = Field(min_length=1)


class TaskResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    status: str
    duration_seconds: float
    elapsed_seconds: float
    remaining_seconds: float
    failure_rate: float
    max_retries: int
    attempts: int
    depends_on: list[str]


class TaskBatchResponse(BaseModel):
    message: str
    tasks: list[TaskResponse]


class StatsResponse(BaseModel):
    running: int
    waiting: int
    paused: int
    succeeded: int
    failed: int
    blocked: int
    cancelled: int
