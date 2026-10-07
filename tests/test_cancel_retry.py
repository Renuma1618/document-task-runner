import time


def wait_for_status(client, name, status, timeout=3):
    deadline = time.time() + timeout
    while time.time() < deadline:
        data = client.get(f"/tasks/{name}").json()
        if data["status"] == status:
            return data
        time.sleep(0.02)
    return client.get(f"/tasks/{name}").json()


def test_cancel_parent_cancels_downstream_and_does_not_restart(client):
    client.post(
        "/tasks",
        json={
            "tasks": [
                {"name": "Upload Document", "duration_seconds": 1},
                {
                    "name": "Extract Text",
                    "duration_seconds": 1,
                    "depends_on": ["Upload Document"],
                },
                {
                    "name": "Generate Report",
                    "duration_seconds": 1,
                    "depends_on": ["Extract Text"],
                },
            ]
        },
    )

    wait_for_status(client, "Upload Document", "RUNNING")
    response = client.post("/tasks/Upload%20Document/cancel")
    assert response.status_code == 200

    time.sleep(0.1)
    for name in ["Upload Document", "Extract Text", "Generate Report"]:
        data = client.get(f"/tasks/{name}").json()
        assert data["status"] == "CANCELLED"
        assert data["elapsed_seconds"] == 0
        assert data["attempts"] == 0


def test_retry_cancelled_branch(client):
    client.post(
        "/tasks",
        json={
            "tasks": [
                {"name": "Upload Document", "duration_seconds": 0.05},
                {
                    "name": "Extract Text",
                    "duration_seconds": 0.05,
                    "depends_on": ["Upload Document"],
                },
                {
                    "name": "Generate Report",
                    "duration_seconds": 0.05,
                    "depends_on": ["Extract Text"],
                },
            ]
        },
    )

    wait_for_status(client, "Upload Document", "RUNNING")
    client.post("/tasks/Upload%20Document/cancel")

    response = client.post("/tasks/Upload%20Document/retry")
    assert response.status_code == 200

    result = wait_for_status(client, "Generate Report", "SUCCEEDED")
    assert result["status"] == "SUCCEEDED"


def test_retry_rejected_when_dependency_not_succeeded(client):
    client.post(
        "/tasks",
        json={
            "tasks": [
                {"name": "Upload Document", "duration_seconds": 10},
                {
                    "name": "Extract Text",
                    "duration_seconds": 1,
                    "depends_on": ["Upload Document"],
                },
            ]
        },
    )

    wait_for_status(client, "Upload Document", "RUNNING")
    client.post("/tasks/Upload%20Document/cancel")

    response = client.post("/tasks/Extract%20Text/retry")
    assert response.status_code == 409
    assert "dependency" in response.json()["detail"]
