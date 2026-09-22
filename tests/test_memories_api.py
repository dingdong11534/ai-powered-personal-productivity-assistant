"""API endpoint tests for /memories router."""

def test_memories_api_crud(client):
    # 1. Create Memory (POST /memories)
    res = client.post(
        "/memories",
        json={"content": "Prefers morning coffee before coding", "category": "preference"},
    )
    assert res.status_code == 201
    data = res.json()
    mem_id = data["id"]
    assert data["content"] == "Prefers morning coffee before coding"
    assert data["category"] == "preference"

    # 2. Get Memory (GET /memories/{id})
    res_get = client.get(f"/memories/{mem_id}")
    assert res_get.status_code == 200
    assert res_get.json()["id"] == mem_id

    # 3. List Memories (GET /memories)
    res_list = client.get("/memories")
    assert res_list.status_code == 200
    assert len(res_list.json()) == 1

    # 4. Search Memories (GET /memories/search)
    res_search = client.get("/memories/search?query=coffee")
    assert res_search.status_code == 200
    assert len(res_search.json()) == 1

    # 5. Update Memory (PUT /memories/{id})
    res_put = client.put(f"/memories/{mem_id}", json={"content": "Prefers morning espresso"})
    assert res_put.status_code == 200
    assert res_put.json()["content"] == "Prefers morning espresso"

    # 6. Archive Memory (POST /memories/{id}/archive)
    res_archive = client.post(f"/memories/{mem_id}/archive")
    assert res_archive.status_code == 200
    assert res_archive.json()["is_active"] is False

    # 7. Delete Memory (DELETE /memories/{id})
    res_del = client.delete(f"/memories/{mem_id}")
    assert res_del.status_code == 204

    # 8. 404 check
    res_404 = client.get(f"/memories/{mem_id}")
    assert res_404.status_code == 404
