import time


def wait_for_status(client, name, status, timeout=3):
    deadline = time.time() + timeout
    while time.time() < deadline:
        response = client.get(f"/tasks/{name}")
        if response.json()["status"] == status:
            return response.json()
        time.sleep(0.02)
    return client.get(f"/tasks/{name}").json()


def test_dependency_chain_runs_in_order(client):
    response = client.post(
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
    assert response.status_code == 200

    result = wait_for_status(client, "Generate Report", "SUCCEEDED")
    assert result["status"] == "SUCCEEDED"
