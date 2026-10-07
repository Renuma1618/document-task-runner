# Document Task Runner

A small FastAPI + SQLite task runner for document-processing workflows.

Example workflow:

`Upload Document -> Extract Text -> Analyze Document -> Generate Report`

## Run

```bash
python -m venv .venv
# Windows
.venv\Scripts\activate


pip install -r requirements.txt
uvicorn app.main:app --reload
```

Open Swagger UI at `http://127.0.0.1:8000/docs`.

## API

- `POST /tasks` - submit an atomic batch
- `GET /tasks` - list tasks
- `GET /tasks/{task_name}` - task status
- `POST /tasks/{task_name}/pause` - pause task and downstream branch
- `POST /tasks/{task_name}/resume` - resume from saved progress
- `POST /tasks/{task_name}/cancel` - permanently cancel task and downstream branch
- `POST /tasks/{task_name}/retry` - retry a cancelled task and its cancelled downstream branch
- `GET /stats` - state counts
- `GET /health` - health check

## Cancel vs Pause

**Cancel**
- The selected task and every downstream dependent become `CANCELLED`.
- Runtime progress is discarded: `elapsed_seconds=0` and `attempts=0`.
- A cancelled task is never automatically scheduled again.
- An explicit `/retry` is required.
- Retry is rejected unless every direct dependency of the selected task is `SUCCEEDED`.

**Pause**
- The selected task and downstream branch become `PAUSED`.
- Elapsed progress is preserved.
- Resume requires the selected task to still be `PAUSED` and all its dependencies to be `SUCCEEDED`.
- The branch is returned to `WAITING`; the scheduler then respects dependencies and resumes work from saved progress.

## Restart

SQLite is the source of truth. Completed work is preserved. A task that was `RUNNING` when the process stopped is converted to `WAITING` on startup while retaining its persisted elapsed progress. Progress is saved periodically, so a sudden kill can lose at most the latest unsaved interval.

## Scheduling

Ready tasks are FIFO by creation time. The configured concurrency limit is never exceeded.

## Tests

```bash
pytest -q
```
