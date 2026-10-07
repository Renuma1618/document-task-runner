import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models import Base
import app.database as database
import app.task_manager as task_manager
import app.scheduler as scheduler_module
import app.main as main


@pytest.fixture
def client(tmp_path, monkeypatch):
    db_path = tmp_path / "test.db"
    engine = create_engine(
        f"sqlite:///{db_path}",
        connect_args={"check_same_thread": False},
    )
    SessionTest = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    Base.metadata.create_all(bind=engine)

    monkeypatch.setattr(database, "SessionLocal", SessionTest)
    monkeypatch.setattr(task_manager, "SessionLocal", SessionTest)
    monkeypatch.setattr(scheduler_module, "SessionLocal", SessionTest)
    monkeypatch.setattr(main, "SessionLocal", SessionTest)
    monkeypatch.setattr(main, "engine", engine)

    main.scheduler = scheduler_module.TaskScheduler(
        concurrency_limit=2,
        progress_interval=0.02,
    )

    with TestClient(main.app) as test_client:
        yield test_client
