"""Integration coverage for LLM Runtime discovery endpoints."""

from fastapi.testclient import TestClient

from backend.app.main import app


def test_llm_discovery_includes_openai_and_gemini() -> None:
    with TestClient(app) as client:
        providers_response = client.get("/api/llm/providers")
        models_response = client.get("/api/llm/models")

    assert providers_response.status_code == 200
    assert providers_response.json() == {"providers": ["openai", "gemini"]}
    assert models_response.status_code == 200
    gemini = next(
        model
        for model in models_response.json()["models"]
        if model["provider"] == "gemini"
    )
    assert gemini["model_name"] == "gemini-3.6-flash"
    assert gemini["capabilities"] == ["chat"]
    assert isinstance(gemini["metadata"]["configured"], bool)
