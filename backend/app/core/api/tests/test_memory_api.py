"""REST coverage for agent-scoped Memory Runtime operations."""

import pytest
from fastapi.testclient import TestClient
from backend.app.main import app

@pytest.fixture
def client() -> TestClient:
    with TestClient(app) as test_client: yield test_client

def test_memory_crud_search_and_agent_scoping(client: TestClient) -> None:
    first = client.post("/api/agents", json={"name":"memory-agent","description":"Stores memory.","type":"test"}).json()["id"]
    second = client.post("/api/agents", json={"name":"other-agent","description":"Other memory.","type":"test"}).json()["id"]
    created = client.post(f"/api/agents/{first}/memory", json={"content":"Genesis keeps a useful note", "kind":"note", "tags":["useful"]})
    assert created.status_code == 201
    memory_id = created.json()["memory_id"]
    assert client.get(f"/api/agents/{first}/memory/search?query=useful").json()["memories"][0]["memory_id"] == memory_id
    assert client.get(f"/api/agents/{second}/memory").json() == {"memories": []}
    assert client.patch(f"/api/memory/{memory_id}", json={"content":"Updated note"}).json()["content"] == "Updated note"
    assert client.delete(f"/api/memory/{memory_id}").status_code == 200
    assert client.get(f"/api/memory/{memory_id}").status_code == 404
    assert client.post("/api/agents/00000000-0000-0000-0000-000000000000/memory", json={"content":"missing"}).status_code == 404
