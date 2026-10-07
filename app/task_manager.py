from collections import defaultdict

from sqlalchemy import select

from .database import SessionLocal
from .models import Task, TaskStatus, task_dependencies, utcnow


def _detect_cycle(graph: dict[str, set[str]]) -> bool:
    visiting = set()
    visited = set()

    def visit(node):
        if node in visiting:
            return True
        if node in visited:
            return False
        visiting.add(node)
        for dep in graph.get(node, set()):
            if visit(dep):
                return True
        visiting.remove(node)
        visited.add(node)
        return False

    return any(visit(node) for node in graph)


def create_tasks(task_inputs):
    names = [item.name for item in task_inputs]
    if len(names) != len(set(names)):
        raise ValueError("Duplicate task names are not allowed")

    with SessionLocal() as db:
        existing = {
            task.name: task
            for task in db.scalars(select(Task)).all()
        }

        duplicates = set(names) & set(existing)
        if duplicates:
            raise ValueError(
                f"Task name already exists: {sorted(duplicates)[0]}"
            )

        all_names = set(existing) | set(names)
        graph = defaultdict(set)

        for task in existing.values():
            graph[task.name] = {dependency.name for dependency in task.dependencies}

        for item in task_inputs:
            graph[item.name] = set(item.depends_on)

            for dependency in item.depends_on:
                if dependency not in all_names:
                    raise ValueError(
                        f"Unknown dependency '{dependency}' for task '{item.name}'"
                    )

        if _detect_cycle(graph):
            raise ValueError("Circular dependency detected")

        created = []
        name_to_task = {}

        # No commit occurs until every validation above has passed.
        for item in task_inputs:
            task = Task(
                name=item.name,
                status=TaskStatus.WAITING.value,
                duration_seconds=item.duration_seconds,
                elapsed_seconds=0.0,
                failure_rate=item.failure_rate,
                max_retries=item.max_retries,
                attempts=0,
                created_at=utcnow(),
                updated_at=utcnow(),
            )
            db.add(task)
            created.append(task)

        db.flush()

        for task, item in zip(created, task_inputs):
            for dependency_name in item.depends_on:
                dependency = existing.get(dependency_name) or name_to_task.get(dependency_name)
                if dependency is None:
                    dependency = next(
                        t for t in created if t.name == dependency_name
                    )
                db.execute(
                    task_dependencies.insert().values(
                        task_id=task.id,
                        depends_on_task_id=dependency.id,
                    )
                )
            name_to_task[task.name] = task

        db.commit()
        for task in created:
            db.refresh(task)
        return created
