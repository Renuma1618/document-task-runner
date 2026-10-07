def test_circular_dependency_rejected_atomically(client):
    payload = {
        "tasks": [
            {"name": "A", "duration_seconds": 1, "depends_on": ["C"]},
            {"name": "B", "duration_seconds": 1, "depends_on": ["A"]},
            {"name": "C", "duration_seconds": 1, "depends_on": ["B"]},
        ]
    }
    response = client.post("/tasks", json=payload)
    assert response.status_code == 400
    assert "Circular dependency" in response.json()["detail"]

    assert client.get("/tasks").json() == []


def test_unknown_dependency_rejected(client):
    response = client.post(
        "/tasks",
        json={
            "tasks": [
                {
                    "name": "Extract Text",
                    "duration_seconds": 1,
                    "depends_on": ["Upload Document"],
                }
            ]
        },
    )
    assert response.status_code == 400
    assert "Unknown dependency" in response.json()["detail"]


def test_duplicate_names_rejected(client):
    response = client.post(
        "/tasks",
        json={
            "tasks": [
                {"name": "A", "duration_seconds": 1},
                {"name": "A", "duration_seconds": 2},
            ]
        },
    )
    assert response.status_code == 400
    assert "Duplicate" in response.json()["detail"]
