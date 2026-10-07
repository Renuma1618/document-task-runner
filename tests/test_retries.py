import time


def wait_for_status(client, name, status, timeout=5):
    deadline = time.time() + timeout
    while time.time() < deadline:
        data = client.get(f"/tasks/{name}").json()
        if data["status"] == status:
            return data
        time.sleep(0.03)
    return client.get(f"/tasks/{name}").json()


def test_permanent_failure_blocks_dependents(client):
    client.post(
        "/tasks",
        json={
            "tasks": [
                {
                    "name": "Upload Document",
                    "duration_seconds": 0.02,
                    "failure_rate": 1,
                    "max_retries": 0,
                },
                {
                    "name": "Extract Text",
                    "duration_seconds": 0.02,
                    "depends_on": ["Upload Document"],
                },
            ]
        },
    )

    result = wait_for_status(client, "Extract Text", "BLOCKED")
    assert result["status"] == "BLOCKED"

    parent = client.get("/tasks/Upload%20Document").json()
    assert parent["status"] == "FAILED"
    assert parent["attempts"] == 1
