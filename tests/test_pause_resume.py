import time


def wait_for_status(client, name, status, timeout=3):
    deadline = time.time() + timeout
    while time.time() < deadline:
        data = client.get(f"/tasks/{name}").json()
        if data["status"] == status:
            return data
        time.sleep(0.02)
    return client.get(f"/tasks/{name}").json()


def test_pause_preserves_progress_and_resume_continues(client):
    client.post(
        "/tasks",
        json={
            "tasks": [
                {"name": "Upload Document", "duration_seconds": 0.5},
                {
                    "name": "Extract Text",
                    "duration_seconds": 0.1,
                    "depends_on": ["Upload Document"],
                },
            ]
        },
    )

    running = wait_for_status(client, "Upload Document", "RUNNING")
    time.sleep(0.15)

    client.post("/tasks/Upload%20Document/pause")
    paused = wait_for_status(client, "Upload%20Document", "PAUSED")

    # The scheduler stores progress; it must not be reset by pause.
    assert paused["elapsed_seconds"] > 0
    assert paused["remaining_seconds"] < 0.5

    assert client.get("/tasks/Extract%20Text").json()["status"] == "PAUSED"

    response = client.post("/tasks/Upload%20Document/resume")
    assert response.status_code == 200

    result = wait_for_status(client, "Extract Text", "SUCCEEDED")
    assert result["status"] == "SUCCEEDED"
