def test_stats_contains_all_states(client):
    response = client.get("/stats")
    assert response.status_code == 200
    assert set(response.json()) == {
        "running",
        "waiting",
        "paused",
        "succeeded",
        "failed",
        "blocked",
        "cancelled",
    }
