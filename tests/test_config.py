from storyweaver.config import load_settings


def test_load_settings_prefers_generic_llm_env(monkeypatch) -> None:
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("LLM_BASE_URL", "https://example.com/v1")
    monkeypatch.setenv("LLM_MODEL", "demo-model")
    monkeypatch.setenv("NVIDIA_API_KEY", "old-key")
    monkeypatch.setenv("NVIDIA_BASE_URL", "https://integrate.api.nvidia.com/v1")
    monkeypatch.setenv("NVIDIA_MODEL", "other-model")

    settings = load_settings()

    assert settings.llm_api_key == "test-key"
    assert settings.base_url == "https://example.com/v1"
    assert settings.model == "demo-model"


def test_load_settings_uses_large_model_default(monkeypatch) -> None:
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.delenv("LLM_BASE_URL", raising=False)
    monkeypatch.delenv("LLM_MODEL", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
    monkeypatch.delenv("OPENAI_MODEL", raising=False)
    monkeypatch.delenv("NVIDIA_API_KEY", raising=False)
    monkeypatch.delenv("NVIDIA_BASE_URL", raising=False)
    monkeypatch.delenv("NVIDIA_MODEL", raising=False)

    settings = load_settings()

    assert settings.model == "gpt-5.4"